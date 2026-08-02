"""
Tests for Trailing Stop Engine — partial exits, time-based reduction.
"""

import pytest

from euroscope.trading.trailing_stop import (
    TrailingStopEngine, TrailMethod,
)


class TestPartialExit:

    def test_partial_exit_triggers_at_1rr(self):
        engine = TrailingStopEngine(partial_exit_rr=1.0, partial_exit_fraction=0.5)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        action = engine.check_partial_exit("t1", 1.0930, stop_pips=30)
        assert action is not None
        assert action.close_fraction == 0.5
        assert action.trade_id == "t1"

    def test_partial_exit_not_triggered_below_target(self):
        engine = TrailingStopEngine(partial_exit_rr=1.0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        action = engine.check_partial_exit("t1", 1.0910, stop_pips=30)
        assert action is None

    def test_partial_exit_only_once(self):
        engine = TrailingStopEngine(partial_exit_rr=1.0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        action1 = engine.check_partial_exit("t1", 1.0930, stop_pips=30)
        assert action1 is not None
        action2 = engine.check_partial_exit("t1", 1.0950, stop_pips=30)
        assert action2 is None

    def test_partial_exit_moves_to_breakeven(self):
        engine = TrailingStopEngine(partial_exit_rr=1.0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        engine.check_partial_exit("t1", 1.0930, stop_pips=30)
        state = engine.get_state("t1")
        assert state.moved_to_breakeven is True
        assert state.current_stop >= 1.0900

    def test_partial_exit_sell(self):
        engine = TrailingStopEngine(partial_exit_rr=1.0)
        engine.register_trade("t1", "SELL", 1.0900, 1.0930, TrailMethod.ATR, 0.0050)
        action = engine.check_partial_exit("t1", 1.0870, stop_pips=30)
        assert action is not None


class TestTimeBasedReduction:

    def test_time_reduce_triggers_after_bars(self):
        engine = TrailingStopEngine(time_reduce_bars=10, time_reduce_fraction=0.5)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        for _ in range(9):
            assert engine.tick_bar("t1") is None
        action = engine.tick_bar("t1")
        assert action is not None
        assert action.close_fraction == 0.5

    def test_time_reduce_disabled_when_zero(self):
        engine = TrailingStopEngine(time_reduce_bars=0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        assert engine.tick_bar("t1") is None

    def test_time_reduce_only_once(self):
        engine = TrailingStopEngine(time_reduce_bars=5)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        for _ in range(5):
            engine.tick_bar("t1")
        action = engine.tick_bar("t1")
        assert action is None

    def test_bars_held_counter(self):
        engine = TrailingStopEngine(time_reduce_bars=10)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        for _ in range(3):
            engine.tick_bar("t1")
        state = engine.get_state("t1")
        assert state.bars_held == 3


class TestExistingFeatures:

    def test_register_and_update(self):
        engine = TrailingStopEngine()
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        state = engine.update("t1", 1.0920, 0.0050)
        assert state is not None
        assert state.current_stop > 1.0870

    def test_breakeven_trigger(self):
        engine = TrailingStopEngine(breakeven_pips=15)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        engine.update("t1", 1.0920, 0.0050)
        state = engine.get_state("t1")
        assert state.moved_to_breakeven is True

    def test_chandelier_trail(self):
        engine = TrailingStopEngine(default_method=TrailMethod.CHANDELIER, atr_multiplier=2.0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0860, TrailMethod.CHANDELIER, 0.0050)
        engine.update("t1", 1.0950, 0.0050)
        state = engine.get_state("t1")
        assert state.current_stop > 1.0860

    def test_stopped_out(self):
        engine = TrailingStopEngine()
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        assert engine.is_stopped_out("t1", 1.0860) is True
        assert engine.is_stopped_out("t1", 1.0920) is False

    def test_remove_trade(self):
        engine = TrailingStopEngine()
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        engine.remove_trade("t1")
        assert engine.get_state("t1") is None

    def test_format_status(self):
        engine = TrailingStopEngine()
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        status = engine.format_status()
        assert "Trailing Stops" in status
        assert "t1" in status


# ── Institutional upgrades ───────────────────────────────

class TestTrailActivation:

    def test_stop_untouched_below_activation(self):
        """With activation > 0, no trailing or breakeven before the threshold."""
        engine = TrailingStopEngine(
            breakeven_pips=15.0, trail_activation_pips=25.0
        )
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        result = engine.update("t1", 1.0915, 0.0050)  # 15 pips: BE would fire, but gated
        assert result is None
        state = engine.get_state("t1")
        assert state.trail_active is False
        assert state.current_stop == 1.0870
        assert state.moved_to_breakeven is False

    def test_activates_at_threshold(self):
        engine = TrailingStopEngine(trail_activation_pips=25.0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        engine.update("t1", 1.0915, 0.0050)  # below threshold
        engine.update("t1", 1.0926, 0.0050)  # 26 pips -> activates
        state = engine.get_state("t1")
        assert state.trail_active is True

    def test_trails_only_after_activation(self):
        engine = TrailingStopEngine(
            breakeven_pips=100.0, trail_activation_pips=25.0
        )
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        engine.update("t1", 1.0926, 0.0050)   # activate at 26 pips
        engine.update("t1", 1.0960, 0.0050)   # 60 pips -> ATR trail locks
        state = engine.get_state("t1")
        assert state.current_stop > 1.0870
        assert state.trail_active is True

    def test_default_activation_immediate(self):
        """Default activation of 0 keeps legacy behavior (trail from first tick)."""
        engine = TrailingStopEngine(breakeven_pips=15.0)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        result = engine.update("t1", 1.0920, 0.0050)
        assert result is not None
        assert engine.get_state("t1").trail_active is True


class TestChandelierConsistency:

    def test_initial_trail_uses_atr_multiplier(self):
        """Chandelier must trail from entry by N×ATR, matching the update logic."""
        engine = TrailingStopEngine(default_method=TrailMethod.CHANDELIER, atr_multiplier=2.0)
        state = engine.register_trade("t1", "BUY", 1.0900, 1.0860, TrailMethod.CHANDELIER, 0.0050)
        assert state.trail_distance == pytest.approx(0.0050 * 2.0)

    def test_chandelier_stop_tracks_highest_high(self):
        engine = TrailingStopEngine(
            default_method=TrailMethod.CHANDELIER,
            atr_multiplier=1.0,
            breakeven_pips=100.0,
        )
        engine.register_trade("t1", "BUY", 1.0900, 1.0850, TrailMethod.CHANDELIER, 0.0010)
        engine.update("t1", 1.0930, 0.0010)  # high 1.0930 - 1×ATR(0.0010) = 1.0920
        state = engine.get_state("t1")
        assert state.current_stop == pytest.approx(1.0920, abs=0.0001)


class TestTrailInvariants:

    def test_stop_never_moves_against_position(self):
        engine = TrailingStopEngine(atr_multiplier=1.5)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        stops = []
        for price in (1.0910, 1.0940, 1.0930, 1.0960, 1.0955, 1.0980):
            engine.update("t1", price, 0.0050)
            stops.append(engine.get_state("t1").current_stop)
        assert stops == sorted(stops)  # monotonically non-decreasing for BUY

    def test_sell_trail_monotonic(self):
        engine = TrailingStopEngine(atr_multiplier=1.5)
        engine.register_trade("t1", "SELL", 1.0900, 1.0930, TrailMethod.ATR, 0.0050)
        stops = []
        for price in (1.0890, 1.0860, 1.0870, 1.0840, 1.0845, 1.0820):
            engine.update("t1", price, 0.0050)
            stops.append(engine.get_state("t1").current_stop)
        assert stops == sorted(stops, reverse=True)  # non-increasing for SELL

    def test_pnl_pips_matches_stop(self):
        engine = TrailingStopEngine(atr_multiplier=1.5)
        engine.register_trade("t1", "BUY", 1.0900, 1.0870, TrailMethod.ATR, 0.0050)
        engine.update("t1", 1.0980, 0.0050)
        state = engine.get_state("t1")
        expected = (state.current_stop - state.entry_price) * 10000
        assert engine._pnl_pips(state) == pytest.approx(round(expected, 1), abs=0.1)
