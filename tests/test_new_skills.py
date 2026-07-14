"""
Tests for the three new skills: VolatilityForecast, OrderFlow, Microstructure.
"""

import pytest
import math
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from euroscope.skills.base import SkillContext, SkillResult
from euroscope.skills.volatility_forecast.skill import (
    VolatilityForecastSkill, _log_returns, _garch_forecast,
    _classify_regime, _percentile_rank, REGIMES, REGIME_CONFIDENCE,
)
from euroscope.skills.order_flow.skill import (
    OrderFlowSkill, _body_ratio, _wick_ratio, _estimate_delta,
)
from euroscope.skills.microstructure.skill import (
    MicrostructureSkill, _efficiency_ratio, _consecutive_direction,
    _momentum_autocorrelation, _amihud_illiquidity, _spread_estimate,
    _tick_pattern,
)


# ── Helpers ────────────────────────────────────────────────────

def _make_candles(n=60, base_price=1.0800, volatility=0.0010, seed=42):
    """Generate synthetic OHLCV candles."""
    rng = np.random.RandomState(seed)
    data = []
    price = base_price
    for i in range(n):
        ret = rng.normal(0, volatility)
        o = price
        c = price + ret
        h = max(o, c) + abs(rng.normal(0, volatility * 0.5))
        l = min(o, c) - abs(rng.normal(0, volatility * 0.5))
        vol = rng.randint(100, 1000)
        data.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": vol})
        price = c
    return pd.DataFrame(data)


def _trending_candles(n=60, start=1.0800, step=0.0005):
    """Generate clearly trending candles."""
    data = []
    price = start
    for i in range(n):
        o = price
        c = price + step
        h = c + 0.0002
        l = o - 0.0001
        data.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 500})
        price = c
    return pd.DataFrame(data)


# ── Volatility Forecast Tests ─────────────────────────────────

class TestVolatilityHelpers:
    def test_log_returns_basic(self):
        close = pd.Series([1.0, 1.01, 1.02, 1.015])
        ret = _log_returns(close)
        assert len(ret) == 3
        assert abs(ret.iloc[0] - math.log(1.01)) < 1e-10

    def test_log_returns_all_same(self):
        close = pd.Series([1.0, 1.0, 1.0, 1.0])
        ret = _log_returns(close)
        assert all(abs(r) < 1e-10 for r in ret)

    def test_garch_forecast_short_data(self):
        returns = pd.Series([0.001] * 10)
        result = _garch_forecast(returns)
        assert result["current_vol"] == 0.0

    def test_garch_forecast_normal(self):
        rng = np.random.RandomState(42)
        returns = pd.Series(rng.normal(0, 0.005, 100))
        result = _garch_forecast(returns)
        assert result["current_vol"] > 0
        assert result["forecast_vol"] > 0
        assert isinstance(result["expanding"], bool)

    def test_classify_regime(self):
        assert _classify_regime(0.03) == "low"
        assert _classify_regime(0.07) == "normal"
        assert _classify_regime(0.12) == "elevated"
        assert _classify_regime(0.20) == "high"
        assert _classify_regime(0.30) == "extreme"

    def test_percentile_rank(self):
        assert _percentile_rank([1, 2, 3, 4, 5], 3) == 60.0
        assert _percentile_rank([1, 2, 3, 4, 5], 1) == 20.0
        assert _percentile_rank([], 5) == 50.0


class TestVolatilityForecastSkill:
    @pytest.fixture
    def skill(self):
        return VolatilityForecastSkill()

    @pytest.fixture
    def ctx(self):
        return SkillContext()

    def test_capabilities(self, skill):
        assert "forecast" in skill.capabilities
        assert "regime" in skill.capabilities

    def test_metadata(self, skill):
        assert skill.name == "volatility_forecast"
        assert skill.category.value == "analysis"
        assert "market_data" in skill.dependencies

    @pytest.mark.asyncio
    async def test_forecast_with_candles(self, skill, ctx):
        candles = _make_candles(60)
        result = await skill.execute(ctx, "forecast", candles=candles)
        assert result.success
        assert result.data["regime"] in REGIMES
        assert 0 <= result.data["confidence_multiplier"] <= 1
        assert ctx.analysis["volatility"] == result.data

    @pytest.mark.asyncio
    async def test_regime_quick(self, skill, ctx):
        candles = _make_candles(60)
        result = await skill.execute(ctx, "regime", candles=candles)
        assert result.success
        assert result.data["regime"] in REGIMES

    @pytest.mark.asyncio
    async def test_insufficient_data(self, skill, ctx):
        candles = _make_candles(5)
        result = await skill.execute(ctx, "forecast", candles=candles)
        assert not result.success
        assert "Insufficient" in result.error

    @pytest.mark.asyncio
    async def test_no_candles(self, skill, ctx):
        result = await skill.execute(ctx, "forecast")
        assert not result.success
        assert "No candle data" in result.error

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill, ctx):
        result = await skill.execute(ctx, "unknown_action")
        assert not result.success
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_forecast_writes_context(self, skill, ctx):
        candles = _make_candles(60)
        await skill.execute(ctx, "forecast", candles=candles)
        assert "volatility" in ctx.analysis

    @pytest.mark.asyncio
    async def test_list_input(self, skill, ctx):
        candles = _make_candles(60)
        candle_list = candles.to_dict("records")
        result = await skill.execute(ctx, "forecast", candles=candle_list)
        assert result.success

    @pytest.mark.asyncio
    async def test_forecast_has_all_fields(self, skill, ctx):
        candles = _make_candles(60)
        result = await skill.execute(ctx, "forecast", candles=candles)
        data = result.data
        assert "current_vol" in data
        assert "forecast_vol" in data
        assert "regime" in data
        assert "expanding" in data
        assert "confidence_multiplier" in data
        assert "percentile_rank" in data


# ── Order Flow Tests ──────────────────────────────────────────

class TestOrderFlowHelpers:
    def test_body_ratio_doji(self):
        row = {"open": 1.08, "high": 1.09, "low": 1.07, "close": 1.0801}
        assert _body_ratio(row) < 0.1

    def test_body_ratio_strong_bull(self):
        row = {"open": 1.07, "high": 1.09, "low": 1.07, "close": 1.09}
        assert _body_ratio(row) == 1.0

    def test_wick_ratio_full_body(self):
        row = {"open": 1.07, "high": 1.09, "low": 1.07, "close": 1.09}
        assert _wick_ratio(row) == 0.0

    def test_estimate_delta_bull(self):
        row = {"open": 1.07, "high": 1.09, "low": 1.07, "close": 1.09, "volume": 1000}
        delta = _estimate_delta(row)
        assert delta > 0

    def test_estimate_delta_bear(self):
        row = {"open": 1.09, "high": 1.09, "low": 1.07, "close": 1.07, "volume": 1000}
        delta = _estimate_delta(row)
        assert delta < 0


class TestOrderFlowSkill:
    @pytest.fixture
    def skill(self):
        return OrderFlowSkill()

    @pytest.fixture
    def ctx(self):
        return SkillContext()

    def test_capabilities(self, skill):
        assert "analyze" in skill.capabilities
        assert "delta" in skill.capabilities
        assert "absorption" in skill.capabilities

    @pytest.mark.asyncio
    async def test_full_analysis(self, skill, ctx):
        candles = _make_candles(50)
        result = await skill.execute(ctx, "analyze", candles=candles)
        assert result.success
        assert "buying_pressure" in result.data
        assert "selling_pressure" in result.data
        assert "delta_cumulative" in result.data
        assert "divergence" in result.data
        assert ctx.analysis["order_flow"] == result.data

    @pytest.mark.asyncio
    async def test_quick_delta(self, skill, ctx):
        candles = _make_candles(20)
        result = await skill.execute(ctx, "delta", candles=candles)
        assert result.success
        assert "buying_pressure" in result.data

    @pytest.mark.asyncio
    async def test_absorption(self, skill, ctx):
        candles = _make_candles(20)
        result = await skill.execute(ctx, "absorption", candles=candles)
        assert result.success
        assert "absorption_detected" in result.data or "detected" in result.data

    @pytest.mark.asyncio
    async def test_no_candles(self, skill, ctx):
        result = await skill.execute(ctx, "analyze")
        assert not result.success

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill, ctx):
        result = await skill.execute(ctx, "unknown_action")
        assert not result.success

    @pytest.mark.asyncio
    async def test_list_input(self, skill, ctx):
        candles = _make_candles(20)
        candle_list = candles.to_dict("records")
        result = await skill.execute(ctx, "analyze", candles=candle_list)
        assert result.success

    @pytest.mark.asyncio
    async def test_pressure_sum(self, skill, ctx):
        candles = _make_candles(50)
        result = await skill.execute(ctx, "analyze", candles=candles)
        bp = result.data["buying_pressure"]
        sp = result.data["selling_pressure"]
        assert bp >= 0 and sp >= 0

    @pytest.mark.asyncio
    async def test_has_next_skill(self, skill, ctx):
        candles = _make_candles(20)
        result = await skill.execute(ctx, "analyze", candles=candles)
        assert result.next_skill == "trading_strategy"


# ── Microstructure Tests ──────────────────────────────────────

class TestMicrostructureHelpers:
    def test_efficiency_ratio_identical(self):
        assert _efficiency_ratio([1.0, 1.0, 1.0]) == 0.0

    def test_efficiency_ratio_straight_line(self):
        assert _efficiency_ratio([1.0, 2.0, 3.0, 4.0]) == 1.0

    def test_efficiency_ratio_choppy(self):
        prices = [1.0, 1.1, 1.0, 1.1, 1.0, 1.1, 1.0]
        er = _efficiency_ratio(prices)
        assert er < 0.2

    def test_consecutive_direction_up(self):
        assert _consecutive_direction([1, 2, 3, 4, 5]) == 4

    def test_consecutive_direction_down(self):
        assert _consecutive_direction([5, 4, 3, 2, 1]) == 4

    def test_consecutive_direction_mixed(self):
        assert _consecutive_direction([1, 2, 1, 2, 1]) == 1

    def test_momentum_autocorrelation_insufficient(self):
        assert _momentum_autocorrelation([0.01, -0.01, 0.01]) == 0.0

    def test_amihud_with_volume(self):
        closes = [1.0, 1.01, 1.02, 1.015, 1.03]
        volumes = [1000, 1200, 800, 1100, 900]
        illiq = _amihud_illiquidity(closes, volumes)
        assert illiq > 0

    def test_amihud_no_volume(self):
        closes = [1.0, 1.0, 1.0, 1.0]
        assert _amihud_illiquidity(closes, [0, 0, 0, 0]) == 0.0

    def test_spread_estimate(self):
        highs = [1.085, 1.086, 1.084]
        lows = [1.080, 1.081, 1.079]
        closes = [1.083, 1.084, 1.082]
        spread = _spread_estimate(highs, lows, closes)
        assert spread > 0

    def test_tick_pattern_trending(self):
        assert _tick_pattern(0.8, 0.2, 10) == "trending"

    def test_tick_pattern_volatile(self):
        assert _tick_pattern(0.5, 0.0, 25) == "volatile"

    def test_tick_pattern_mean_reverting(self):
        assert _tick_pattern(0.2, 0.0, 5) == "mean_reverting"

    def test_tick_pattern_random(self):
        assert _tick_pattern(0.5, 0.0, 10) == "random"


class TestMicrostructureSkill:
    @pytest.fixture
    def skill(self):
        return MicrostructureSkill()

    @pytest.fixture
    def ctx(self):
        return SkillContext()

    def test_capabilities(self, skill):
        assert "analyze" in skill.capabilities
        assert "efficiency" in skill.capabilities
        assert "liquidity" in skill.capabilities

    @pytest.mark.asyncio
    async def test_full_analysis(self, skill, ctx):
        candles = _make_candles(50)
        result = await skill.execute(ctx, "analyze", candles=candles)
        assert result.success
        assert "spread_estimate" in result.data
        assert "efficiency_ratio" in result.data
        assert "liquidity_score" in result.data
        assert "tick_pattern" in result.data
        assert ctx.analysis["microstructure"] == result.data

    @pytest.mark.asyncio
    async def test_efficiency_quick(self, skill, ctx):
        candles = _make_candles(30)
        result = await skill.execute(ctx, "efficiency", candles=candles)
        assert result.success
        assert "efficiency_ratio" in result.data
        assert "regime" in result.data

    @pytest.mark.asyncio
    async def test_liquidity_assessment(self, skill, ctx):
        candles = _make_candles(30)
        result = await skill.execute(ctx, "liquidity", candles=candles)
        assert result.success
        assert "liquidity_score" in result.data
        assert "session_quality" in result.data

    @pytest.mark.asyncio
    async def test_trending_candles_high_efficiency(self, skill, ctx):
        candles = _trending_candles(30)
        result = await skill.execute(ctx, "efficiency", candles=candles)
        assert result.data["efficiency_ratio"] > 0.8

    @pytest.mark.asyncio
    async def test_no_candles(self, skill, ctx):
        result = await skill.execute(ctx, "analyze")
        assert not result.success

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill, ctx):
        result = await skill.execute(ctx, "unknown_action")
        assert not result.success

    @pytest.mark.asyncio
    async def test_insufficient_data(self, skill, ctx):
        candles = _make_candles(3)
        result = await skill.execute(ctx, "analyze", candles=candles)
        assert not result.success

    @pytest.mark.asyncio
    async def test_has_next_skill(self, skill, ctx):
        candles = _make_candles(20)
        result = await skill.execute(ctx, "analyze", candles=candles)
        assert result.next_skill == "trading_strategy"

    @pytest.mark.asyncio
    async def test_list_input(self, skill, ctx):
        candles = _make_candles(20)
        candle_list = candles.to_dict("records")
        result = await skill.execute(ctx, "analyze", candles=candle_list)
        assert result.success

    @pytest.mark.asyncio
    async def test_confidence_adjustment_range(self, skill, ctx):
        candles = _make_candles(50)
        result = await skill.execute(ctx, "analyze", candles=candles)
        adj = result.data["confidence_adjustment"]
        assert -0.15 <= adj <= 0.15


# ── Registry Discovery Tests ──────────────────────────────────

class TestSkillDiscovery:
    def test_all_three_skills_discoverable(self):
        from euroscope.skills.registry import SkillsRegistry
        registry = SkillsRegistry()
        discovered = registry.discover()
        assert "volatility_forecast" in discovered
        assert "order_flow" in discovered
        assert "microstructure" in discovered

    def test_all_three_have_skill_md(self):
        from pathlib import Path
        import euroscope.skills.volatility_forecast
        import euroscope.skills.order_flow
        import euroscope.skills.microstructure

        for mod in [euroscope.skills.volatility_forecast,
                     euroscope.skills.order_flow,
                     euroscope.skills.microstructure]:
            skill_dir = Path(mod.__file__).parent
            assert (skill_dir / "SKILL.md").exists(), f"Missing SKILL.md in {skill_dir}"
            assert (skill_dir / "skill.py").exists(), f"Missing skill.py in {skill_dir}"
