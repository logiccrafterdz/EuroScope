"""
Tests for Trailing Stop Engine — partial exits, time-based reduction.
"""

import pytest

from euroscope.trading.trailing_stop import (
    TrailingStopEngine, TrailMethod, TrailingState, PartialExitAction,
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
