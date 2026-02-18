import pytest
from euroscope.brain.conflict_arbiter import ConflictArbiter
from euroscope.skills.base import SkillContext

class TestConflictArbiter:
    @pytest.fixture
    def arbiter(self):
        return ConflictArbiter()

    @pytest.fixture
    def context(self):
        ctx = SkillContext()
        ctx.metadata["session_regime"] = "overlap"
        ctx.metadata["regime"] = "trending"
        return ctx

    def test_resolve_consensus(self, arbiter, context):
        context.metadata["technical_bias"] = "BULLISH"
        context.metadata["liquidity_signal"] = "BUY"
        context.signals["direction"] = "BUY"
        
        res = arbiter.resolve(context)
        assert res["final_direction"] == "BUY"
        assert res["confidence"] > 0.8

    def test_resolve_conflict_liquidity_wins(self, arbiter, context):
        # We need a context where Liquidity actually wins.
        # Asian session nerfs Technical and Patterns.
        context.metadata["session_regime"] = "asian"
        context.metadata["technical_bias"] = "BEARISH"
        context.metadata["liquidity_signal"] = "BUY"
        
        res = arbiter.resolve(context)
        assert res["final_direction"] == "BUY"
        assert "Overrode technical_analysis" in str(res["conflicts_resolved"])

    def test_session_aware_weighting(self, arbiter, context):
        # In Asian session, technical and patterns are weighted less
        context.metadata["session_regime"] = "asian"
        context.metadata["technical_bias"] = "BUY"
        context.metadata["liquidity_signal"] = "SELL"
        
        res = arbiter.resolve(context)
        # Liquidity should dominate even more in Asian session if others are nerfed
        assert res["final_direction"] == "SELL"

    def test_regime_aware_weighting(self, arbiter, context):
        # In ranging market, patterns are weighted less
        context.metadata["regime"] = "ranging"
        context.metadata["pattern_signal"] = "BUY" # Pattern says buy
        context.metadata["technical_bias"] = "SELL" # Indicators say sell
        
        res = arbiter.resolve(context)
        assert res["final_direction"] == "SELL" # Technical wins because patterns nerfed in ranging
