"""
Tests for Phase 3: Adaptive Brain modules.
- ForecastTracker (active learning loop)
- RegimeAdaptiveEngine (regime-adaptive parameters)
- TrailingStopEngine (trailing stops)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, UTC


# ── ForecastTracker Tests ──────────────────────────────────────

class TestForecastTracker:
    """Test the active learning loop."""

    def _make_tracker(self):
        from euroscope.learning.forecast_tracker import ForecastTracker
        storage = MagicMock()
        storage.load_json.return_value = None
        storage.save_json = MagicMock()
        return ForecastTracker(storage=storage)

    @pytest.mark.asyncio
    async def test_register_forecast(self):
        tracker = self._make_tracker()
        fc = await tracker.register_forecast(
            skill="technical_analysis",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            confidence=70,
            stop_price=1.0820,
        )
        assert fc.id.startswith("fc_")
        assert fc.direction == "BUY"
        assert fc.skill == "technical_analysis"
        assert not fc.resolved

    @pytest.mark.asyncio
    async def test_resolve_hit_target(self):
        tracker = self._make_tracker()
        await tracker.register_forecast(
            skill="technical_analysis",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            confidence=70,
        )
        resolved = await tracker.resolve_all(current_price=1.0910)
        assert len(resolved) == 1
        assert resolved[0].outcome == "hit_target"
        assert resolved[0].pnl_pips > 0

    @pytest.mark.asyncio
    async def test_resolve_hit_stop(self):
        tracker = self._make_tracker()
        await tracker.register_forecast(
            skill="technical_analysis",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            stop_price=1.0820,
            confidence=80,
        )
        resolved = await tracker.resolve_all(current_price=1.0810)
        assert len(resolved) == 1
        assert resolved[0].outcome == "hit_stop"
        assert resolved[0].pnl_pips < 0

    @pytest.mark.asyncio
    async def test_resolve_sell_target(self):
        tracker = self._make_tracker()
        await tracker.register_forecast(
            skill="correlation_monitor",
            direction="SELL",
            entry_price=1.0850,
            target_price=1.0800,
            confidence=65,
        )
        resolved = await tracker.resolve_all(current_price=1.0790)
        assert len(resolved) == 1
        assert resolved[0].outcome == "hit_target"

    @pytest.mark.asyncio
    async def test_resolve_expired(self):
        tracker = self._make_tracker()
        fc = await tracker.register_forecast(
            skill="multi_timeframe_confluence",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            confidence=50,
            ttl_hours=1,
        )
        # Force expiry
        fc.expires_at = datetime.now(UTC) - timedelta(hours=1)
        resolved = await tracker.resolve_all(current_price=1.0840)
        assert len(resolved) == 1
        assert resolved[0].outcome == "expired"

    @pytest.mark.asyncio
    async def test_resolve_partial(self):
        tracker = self._make_tracker()
        fc = await tracker.register_forecast(
            skill="technical_analysis",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            confidence=60,
            ttl_hours=1,
        )
        fc.expires_at = datetime.now(UTC) - timedelta(hours=1)
        # Price moved in right direction but didnt hit target
        resolved = await tracker.resolve_all(current_price=1.0870)
        assert len(resolved) == 1
        assert resolved[0].outcome == "partial"

    @pytest.mark.asyncio
    async def test_weight_adjustment_on_success(self):
        tracker = self._make_tracker()
        initial_weight = tracker.get_weight("technical_analysis")
        await tracker.register_forecast(
            skill="technical_analysis",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            confidence=80,
        )
        await tracker.resolve_all(current_price=1.0910)
        new_weight = tracker.get_weight("technical_analysis")
        assert new_weight > initial_weight

    @pytest.mark.asyncio
    async def test_weight_adjustment_on_failure(self):
        tracker = self._make_tracker()
        initial_weight = tracker.get_weight("technical_analysis")
        await tracker.register_forecast(
            skill="technical_analysis",
            direction="BUY",
            entry_price=1.0850,
            target_price=1.0900,
            stop_price=1.0820,
            confidence=80,
        )
        await tracker.resolve_all(current_price=1.0810)
        new_weight = tracker.get_weight("technical_analysis")
        assert new_weight < initial_weight

    @pytest.mark.asyncio
    async def test_weight_bounds(self):
        from euroscope.learning.forecast_tracker import WEIGHT_MIN, WEIGHT_MAX
        tracker = self._make_tracker()
        # Extreme failures should not go below minimum
        for _ in range(50):
            await tracker.register_forecast(
                skill="bad_skill",
                direction="BUY",
                entry_price=1.0850,
                target_price=1.0900,
                stop_price=1.0820,
                confidence=90,
            )
            await tracker.resolve_all(current_price=1.0810)
        assert tracker.get_weight("bad_skill") >= WEIGHT_MIN

    @pytest.mark.asyncio
    async def test_get_open_forecasts(self):
        tracker = self._make_tracker()
        await tracker.register_forecast(
            skill="a", direction="BUY", entry_price=1.08, target_price=1.09, confidence=50
        )
        await tracker.register_forecast(
            skill="b", direction="SELL", entry_price=1.08, target_price=1.07, confidence=50
        )
        assert len(tracker.get_open_forecasts()) == 2

    @pytest.mark.asyncio
    async def test_skill_accuracy(self):
        tracker = self._make_tracker()
        await tracker.register_forecast(
            skill="technical_analysis", direction="BUY",
            entry_price=1.0850, target_price=1.0900, confidence=70,
        )
        await tracker.resolve_all(current_price=1.0910)
        stats = tracker.get_skill_accuracy("technical_analysis")
        assert stats["total"] == 1
        assert stats["accuracy"] == 100.0

    @pytest.mark.asyncio
    async def test_scoreboard(self):
        tracker = self._make_tracker()
        await tracker.register_forecast(
            skill="technical_analysis", direction="BUY",
            entry_price=1.0850, target_price=1.0900, confidence=70,
        )
        await tracker.resolve_all(current_price=1.0910)
        board = tracker.get_scoreboard()
        assert "technical_analysis" in board

    @pytest.mark.asyncio
    async def test_format_scoreboard(self):
        tracker = self._make_tracker()
        text = tracker.format_scoreboard()
        assert "Scoreboard" in text


# ── RegimeAdaptiveEngine Tests ─────────────────────────────────

class TestRegimeAdaptiveEngine:
    """Test regime detection and adaptive parameters."""

    def _make_engine(self):
        from euroscope.trading.regime_adaptive import RegimeAdaptiveEngine
        return RegimeAdaptiveEngine()

    def test_detect_trending(self):
        engine = self._make_engine()
        regime = engine.detect_regime({
            "ADX": {"value": 35},
            "ATR": {"value": 0.001, "average": 0.001},
            "BB": {"bandwidth": 0.01},
        })
        assert regime == "trending"

    def test_detect_ranging(self):
        engine = self._make_engine()
        regime = engine.detect_regime({
            "ADX": {"value": 15},
            "ATR": {"value": 0.0005, "average": 0.0005},
            "BB": {"bandwidth": 0.005},
        })
        assert regime == "ranging"

    def test_detect_volatile(self):
        engine = self._make_engine()
        regime = engine.detect_regime({
            "ADX": {"value": 30},
            "ATR": {"value": 0.003, "average": 0.001},
            "BB": {"bandwidth": 0.03},
        })
        assert regime == "volatile"

    def test_regime_transition_tracking(self):
        engine = self._make_engine()
        assert engine.transition_count == 0
        engine.detect_regime({
            "ADX": {"value": 35}, "ATR": {"value": 0.001, "average": 0.001},
            "BB": {"bandwidth": 0.01},
        })
        # Default is "ranging", trending is a transition
        assert engine.transition_count == 1
        assert engine.current_regime == "trending"

    def test_get_profile(self):
        engine = self._make_engine()
        profile = engine.get_profile("trending")
        assert profile.stop_loss_multiplier == 2.0
        assert profile.risk_per_trade == 1.5

    def test_get_profile_default(self):
        engine = self._make_engine()
        profile = engine.get_profile()
        assert profile.name == "ranging"  # Default

    def test_indicator_weights_differ_by_regime(self):
        engine = self._make_engine()
        trending_rsi = engine.get_indicator_weight("RSI", "trending")
        ranging_rsi = engine.get_indicator_weight("RSI", "ranging")
        assert trending_rsi < ranging_rsi  # RSI less important in trends

    def test_confidence_thresholds(self):
        engine = self._make_engine()
        # Volatile regime should require higher confidence
        volatile_conf = engine.get_confidence_threshold("volatile")
        trending_conf = engine.get_confidence_threshold("trending")
        assert volatile_conf > trending_conf

    def test_format_regime(self):
        engine = self._make_engine()
        text = engine.format_regime()
        assert "Regime" in text
        assert "ATR" in text


# ── TrailingStopEngine Tests ───────────────────────────────────

class TestTrailingStopEngine:
    """Test trailing stop mechanics."""

    def _make_engine(self):
        from euroscope.trading.trailing_stop import TrailingStopEngine, TrailMethod
        return TrailingStopEngine(
            default_method=TrailMethod.ATR,
            atr_multiplier=1.5,
            breakeven_pips=15.0,
        )

    def test_register_trade(self):
        engine = self._make_engine()
        state = engine.register_trade(
            trade_id="t001", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
            atr_value=0.0015,
        )
        assert state.trade_id == "t001"
        assert state.current_stop == 1.0820
        assert state.direction == "BUY"

    def test_trailing_stop_moves_up_buy(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t001", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
            atr_value=0.0015,
        )
        # Price moves up significantly
        result = engine.update("t001", current_price=1.0900, atr_value=0.0015)
        assert result is not None
        assert result.current_stop > 1.0820

    def test_trailing_stop_does_not_move_down(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t001", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
            atr_value=0.0015,
        )
        # Price moves up then down
        engine.update("t001", current_price=1.0900, atr_value=0.0015)
        state = engine.get_state("t001")
        stop_after_up = state.current_stop
        engine.update("t001", current_price=1.0870, atr_value=0.0015)
        assert state.current_stop == stop_after_up  # Didn't move down

    def test_trailing_stop_sell(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t002", direction="SELL",
            entry_price=1.0850, initial_stop=1.0880,
            atr_value=0.0015,
        )
        # Price moves down
        result = engine.update("t002", current_price=1.0800, atr_value=0.0015)
        assert result is not None
        assert result.current_stop < 1.0880

    def test_breakeven_upgrade(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t003", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
            atr_value=0.0015,
        )
        # Price moves 20 pips in favor (above breakeven_pips threshold of 15)
        engine.update("t003", current_price=1.0870, atr_value=0.0015)
        state = engine.get_state("t003")
        assert state.moved_to_breakeven is True
        assert state.current_stop >= 1.0850  # At least breakeven

    def test_is_stopped_out(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t004", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
        )
        assert not engine.is_stopped_out("t004", 1.0840)
        assert engine.is_stopped_out("t004", 1.0815)

    def test_update_all(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t005", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820, atr_value=0.0015,
        )
        engine.register_trade(
            trade_id="t006", direction="SELL",
            entry_price=1.0850, initial_stop=1.0880, atr_value=0.0015,
        )
        moved = engine.update_all(current_price=1.0900, atr_value=0.0015)
        # The BUY should have moved up, the SELL should not have moved further
        assert len(moved) >= 1

    def test_remove_trade(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t007", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
        )
        engine.remove_trade("t007")
        assert engine.get_state("t007") is None

    def test_percentage_method(self):
        from euroscope.trading.trailing_stop import TrailingStopEngine, TrailMethod
        engine = TrailingStopEngine(default_method=TrailMethod.PERCENTAGE, trail_pct=0.003)
        engine.register_trade(
            trade_id="t008", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
        )
        result = engine.update("t008", current_price=1.0900)
        assert result is not None

    def test_format_status(self):
        engine = self._make_engine()
        # No trades
        text = engine.format_status()
        assert "No active" in text

        # With trade
        engine.register_trade(
            trade_id="t009", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
        )
        text = engine.format_status()
        assert "t009" in text
        assert "BUY" in text

    def test_pnl_calculation(self):
        engine = self._make_engine()
        engine.register_trade(
            trade_id="t010", direction="BUY",
            entry_price=1.0850, initial_stop=1.0820,
            atr_value=0.0015,
        )
        engine.update("t010", current_price=1.0900, atr_value=0.0015)
        state = engine.get_state("t010")
        pnl = engine._pnl_pips(state)
        # Stop moved above entry → positive locked pnl
        if state.current_stop > state.entry_price:
            assert pnl > 0
