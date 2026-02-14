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
    assert 0.4 <= ctx.metadata["confidence_adjustment"] <= 1.0
    assert isinstance(ctx.metadata["high_uncertainty"], bool)
    assert ctx.metadata["market_regime"] in ("trending", "ranging", "volatile")
    breakdown = ctx.metadata["uncertainty_breakdown"]
    assert set(breakdown.keys()) == {"technical", "behavioral"}
    assert breakdown["technical"] == ctx.metadata["technical_uncertainty"]
    assert breakdown["behavioral"] == ctx.metadata["behavioral_uncertainty"]
    assert ctx.metadata["blocking_reason"] is None
