import pytest

from euroscope.analysis.patterns import PatternDetector
from euroscope.analysis.technical import TechnicalAnalyzer
from euroscope.skills.base import SkillContext
from euroscope.skills.uncertainty_assessment import UncertaintyAssessmentSkill


@pytest.mark.asyncio
async def test_uncertainty_assessment_sets_metadata(sample_ohlcv):
    ctx = SkillContext()
    ctx.market_data["candles"] = sample_ohlcv
    ctx.market_data["timeframe"] = "H1"

    analyzer = TechnicalAnalyzer()
    ctx.analysis["indicators"] = analyzer.analyze(sample_ohlcv)
    ctx.analysis["patterns"] = PatternDetector().detect_all(sample_ohlcv)

    skill = UncertaintyAssessmentSkill()
    result = await skill.execute(ctx, "assess")

    assert result.success
    assert 0.0 <= ctx.metadata["uncertainty_score"] <= 1.0
    assert 0.0 <= ctx.metadata["confidence_adjustment"] <= 1.0
    assert isinstance(ctx.metadata["high_uncertainty"], bool)
    assert ctx.metadata["market_regime"] in ("trending", "ranging", "volatile")
    breakdown = ctx.metadata["uncertainty_breakdown"]
    assert set(breakdown.keys()) == {"technical", "causal", "behavioral"}
    assert breakdown["technical"] == ctx.metadata["technical_uncertainty"]
    assert breakdown["behavioral"] == ctx.metadata["behavioral_uncertainty"]
    assert breakdown["causal"] == ctx.metadata["causal_uncertainty"]
    assert ctx.metadata["blocking_reason"] is None
    assert isinstance(ctx.metadata["uncertainty_reasoning"], str)
    assert len(ctx.metadata["uncertainty_reasoning"]) <= 100


def test_behavioral_uncertainty_asian_reversal():
    skill = UncertaintyAssessmentSkill()
    ctx = SkillContext()
    ctx.metadata["session_regime"] = "asian"
    ctx.metadata["market_intent"] = {"current_phase": "reversal", "confidence": 0.6}
    behavioral, reasons = skill._calculate_behavioral_uncertainty(ctx, [{"pattern": "double_top"}])
    assert behavioral >= 0.2
    assert "asian reversal" in reasons


def test_behavioral_uncertainty_intent_conflict():
    skill = UncertaintyAssessmentSkill()
    ctx = SkillContext()
    ctx.metadata["session_regime"] = "london"
    ctx.metadata["market_intent"] = {"next_likely_move": "down", "confidence": 0.7}
    behavioral, reasons = skill._calculate_behavioral_uncertainty(ctx, [{"signal": "bullish"}])
    assert behavioral >= 0.2
    assert "intent conflict" in reasons


def test_composite_uncertainty_compounding():
    composite = UncertaintyAssessmentSkill._compose_uncertainty_layers(0.35, 0.2, 0.25)
    assert round(composite, 3) == 0.485


def test_behavioral_uncertainty_missing_context():
    skill = UncertaintyAssessmentSkill()
    ctx = SkillContext()
    behavioral, reasons = skill._calculate_behavioral_uncertainty(ctx, [])
    assert behavioral == 0.0
    assert reasons == []


def test_macro_override_confidence_adjustment():
    macro_data = {"differential": {"confidence": 0.9}}
    adjusted = UncertaintyAssessmentSkill._calculate_confidence_adjustment(0.7, macro_data)
    assert adjusted == 0.75
