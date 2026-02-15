import pandas as pd
import pytest

from euroscope.skills.liquidity_awareness import LiquidityAwarenessSkill
from euroscope.skills.base import SkillContext


def _make_df(prices, start="2026-01-06 06:00"):
    times = pd.date_range(start, periods=len(prices), freq="H")
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p + 0.0004 for p in prices],
            "Low": [p - 0.0004 for p in prices],
            "Close": prices,
            "Volume": [100.0 for _ in prices],
        },
        index=times,
    )
    return df


class TestLiquidityZones:
    def test_equal_highs_detection(self):
        prices = [1.0950 + (i * 0.0002) for i in range(25)]
        df = _make_df(prices)
        df.iloc[20:23, df.columns.get_loc("High")] = 1.1000
        skill = LiquidityAwarenessSkill()
        zones = skill._detect_liquidity_zones(df, "london")
        assert any(z["zone_type"] == "equal_highs" and abs(z["price_level"] - 1.1000) < 0.0005 for z in zones)

    def test_insufficient_data_defaults(self):
        df = _make_df([1.1000 for _ in range(10)])
        skill = LiquidityAwarenessSkill()
        zones, intent = skill._run(df, "london")
        assert zones == []
        assert intent["current_phase"] == "unknown"


class TestMarketIntent:
    def test_liquidity_sweep_detection(self):
        prices = [1.0990 for _ in range(30)]
        df = _make_df(prices)
        df.iloc[-1, df.columns.get_loc("High")] = 1.1020
        df.iloc[-1, df.columns.get_loc("Close")] = 1.0990
        zones = [{"price_level": 1.1000, "zone_type": "psychological", "strength": 0.8, "session": "london"}]
        skill = LiquidityAwarenessSkill()
        intent = skill._assess_market_intent(df, zones, "london")
        assert intent["current_phase"] == "liquidity_sweep"
        assert intent["next_likely_move"] == "down"

    def test_compression_detection(self):
        prices = [1.1000 + (0.0002 * (i % 3)) for i in range(20)]
        df = _make_df(prices)
        df.iloc[-15:, df.columns.get_loc("High")] = 1.1006
        df.iloc[-15:, df.columns.get_loc("Low")] = 1.1000
        zones = [{"price_level": 1.1000, "zone_type": "psychological", "strength": 0.8, "session": "london"}]
        skill = LiquidityAwarenessSkill()
        intent = skill._assess_market_intent(df, zones, "london")
        assert intent["current_phase"] == "compression"
        assert intent["next_likely_move"] == "breakout_pending"

    def test_asian_session_defaults_to_range(self):
        prices = [1.1010 for _ in range(30)]
        df = _make_df(prices)
        skill = LiquidityAwarenessSkill()
        intent = skill._assess_market_intent(df, [], "asian")
        assert intent["next_likely_move"] == "range"


class TestIntegration:
    @pytest.mark.asyncio
    async def test_execute_sets_metadata(self):
        prices = [1.1000 for _ in range(30)]
        df = _make_df(prices)
        ctx = SkillContext()
        ctx.market_data["candles"] = df
        ctx.metadata["session_regime"] = "london"
        skill = LiquidityAwarenessSkill()
        result = await skill.execute(ctx, "analyze")
        assert result.success
        assert "liquidity_zones" in ctx.metadata
        assert ctx.metadata["liquidity_aware"] is True
