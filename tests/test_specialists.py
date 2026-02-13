"""
Tests for specialist agents and orchestrator.
"""

import pytest

from euroscope.brain.specialists import (
    TechnicalSpecialist,
    FundamentalSpecialist,
    SentimentSpecialist,
    RiskSpecialist,
)
from euroscope.brain.orchestrator import Orchestrator


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def bullish_context():
    """Market context that should produce bullish signals."""
    return {
        "indicators": {
            "overall_bias": "bullish",
            "rsi": 55.0,
            "macd": {"histogram_latest": 0.002},
            "atr": 0.0050,
        },
        "patterns": [
            {"name": "Double Bottom", "bias": "bullish"},
        ],
        "levels": {
            "current_price": 1.0950,
            "support": [1.0900, 1.0850],
            "resistance": [1.1000, 1.1050],
        },
        "macro": {
            "rate_differential": {"differential": -0.5},
            "yield_spread": {"spread": -0.3},
            "us_cpi": {"yoy_change": 1.8},
        },
        "calendar": [],
        "sentiment_summary": {
            "total": 10, "bullish": 7, "bearish": 2, "neutral": 1,
            "avg_score": 0.35, "overall": "bullish",
        },
        "news_articles": [],
    }


@pytest.fixture
def bearish_context():
    """Market context that should produce bearish signals."""
    return {
        "indicators": {
            "overall_bias": "bearish",
            "rsi": 35.0,
            "macd": {"histogram_latest": -0.003},
            "atr": 0.0060,
        },
        "patterns": [
            {"name": "Head and Shoulders", "bias": "bearish"},
        ],
        "levels": {
            "current_price": 1.0800,
            "support": [1.0750],
            "resistance": [1.0850, 1.0900],
        },
        "macro": {
            "rate_differential": {"differential": 1.5},
            "yield_spread": {"spread": 2.0},
            "us_cpi": {"yoy_change": 4.5},
        },
        "calendar": [],
        "sentiment_summary": {
            "total": 8, "bullish": 1, "bearish": 6, "neutral": 1,
            "avg_score": -0.4, "overall": "bearish",
        },
        "news_articles": [],
    }


@pytest.fixture
def neutral_context():
    return {
        "indicators": {"overall_bias": "neutral", "rsi": 50.0, "atr": 0.0040},
        "patterns": [],
        "levels": {"current_price": 1.0900, "support": [1.0850], "resistance": [1.0950]},
        "macro": {},
        "calendar": [],
        "sentiment_summary": {"total": 0, "overall": "neutral"},
        "news_articles": [],
    }


# ── Technical Specialist ──────────────────────────────────

class TestTechnicalSpecialist:

    def test_bullish_verdict(self, bullish_context):
        s = TechnicalSpecialist()
        result = s.analyze(bullish_context)
        assert result["verdict"] == "bullish"
        assert result["specialist"] == "technical"
        assert result["confidence"] > 50

    def test_bearish_verdict(self, bearish_context):
        s = TechnicalSpecialist()
        result = s.analyze(bearish_context)
        assert result["verdict"] == "bearish"

    def test_neutral_verdict(self, neutral_context):
        s = TechnicalSpecialist()
        result = s.analyze(neutral_context)
        assert result["verdict"] == "neutral"

    def test_has_key_points(self, bullish_context):
        s = TechnicalSpecialist()
        result = s.analyze(bullish_context)
        assert len(result["key_points"]) > 0

    def test_confidence_range(self, bullish_context):
        s = TechnicalSpecialist()
        result = s.analyze(bullish_context)
        assert 0 <= result["confidence"] <= 100

    def test_empty_context(self):
        s = TechnicalSpecialist()
        result = s.analyze({})
        assert result["verdict"] in ("bullish", "bearish", "neutral")


# ── Fundamental Specialist ────────────────────────────────

class TestFundamentalSpecialist:

    def test_bearish_on_usd_strength(self, bearish_context):
        s = FundamentalSpecialist()
        result = s.analyze(bearish_context)
        assert result["verdict"] == "bearish"
        assert result["specialist"] == "fundamental"

    def test_bullish_on_eur_strength(self, bullish_context):
        s = FundamentalSpecialist()
        result = s.analyze(bullish_context)
        assert result["verdict"] == "bullish"

    def test_no_macro_data(self):
        s = FundamentalSpecialist()
        result = s.analyze({"macro": {}, "calendar": []})
        assert result["verdict"] == "neutral"
        assert "Insufficient" in result["key_points"][0]


# ── Sentiment Specialist ──────────────────────────────────

class TestSentimentSpecialist:

    def test_bullish_sentiment(self, bullish_context):
        s = SentimentSpecialist()
        result = s.analyze(bullish_context)
        assert result["verdict"] == "bullish"

    def test_bearish_sentiment(self, bearish_context):
        s = SentimentSpecialist()
        result = s.analyze(bearish_context)
        assert result["verdict"] == "bearish"

    def test_no_news(self):
        s = SentimentSpecialist()
        result = s.analyze({"sentiment_summary": {"total": 0, "overall": "neutral"}})
        assert result["verdict"] == "neutral"


# ── Risk Specialist ───────────────────────────────────────

class TestRiskSpecialist:

    def test_always_neutral_verdict(self, bullish_context):
        s = RiskSpecialist()
        ctx = dict(bullish_context)
        ctx["other_verdicts"] = [
            {"verdict": "bullish", "confidence": 70},
            {"verdict": "bullish", "confidence": 65},
        ]
        result = s.analyze(ctx)
        assert result["verdict"] == "neutral"  # risk specialist stays neutral

    def test_detects_conflicting_signals(self):
        s = RiskSpecialist()
        result = s.analyze({
            "indicators": {}, "levels": {}, "calendar": [],
            "other_verdicts": [
                {"verdict": "bullish"},
                {"verdict": "bearish"},
            ],
        })
        conflict_points = [p for p in result["key_points"] if "Conflicting" in p]
        assert len(conflict_points) > 0

    def test_detects_high_volatility(self):
        s = RiskSpecialist()
        result = s.analyze({
            "indicators": {"atr": 0.0100},  # 100 pips
            "levels": {}, "calendar": [],
            "other_verdicts": [],
        })
        vol_points = [p for p in result["key_points"] if "volatility" in p.lower()]
        assert len(vol_points) > 0


# ── Orchestrator ──────────────────────────────────────────

class TestOrchestrator:

    def test_bullish_consensus(self, bullish_context):
        o = Orchestrator()
        result = o.run_analysis(bullish_context)
        assert result["consensus"]["verdict"] == "bullish"
        assert result["consensus"]["confidence"] > 0
        assert len(result["specialists"]) == 3

    def test_bearish_consensus(self, bearish_context):
        o = Orchestrator()
        result = o.run_analysis(bearish_context)
        assert result["consensus"]["verdict"] == "bearish"

    def test_has_formatted_output(self, bullish_context):
        o = Orchestrator()
        result = o.run_analysis(bullish_context)
        assert "Multi-Agent Analysis" in result["formatted"]
        assert "Consensus" in result["formatted"]

    def test_has_risk_assessment(self, bullish_context):
        o = Orchestrator()
        result = o.run_analysis(bullish_context)
        assert result["risk_assessment"]["specialist"] == "risk"

    def test_empty_context_no_crash(self):
        o = Orchestrator()
        result = o.run_analysis({})
        assert result["consensus"]["verdict"] in ("bullish", "bearish", "neutral")

    def test_consensus_score_range(self, bullish_context):
        o = Orchestrator()
        result = o.run_analysis(bullish_context)
        assert -1 <= result["consensus"]["score"] <= 1
