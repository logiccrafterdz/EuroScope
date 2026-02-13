"""
Tests for signal executor: open/close/check lifecycle, PnL tracking.
"""

import os
import tempfile

import pytest

from euroscope.data.storage import Storage
from euroscope.trading.signal_executor import SignalExecutor


@pytest.fixture
def executor(tmp_path):
    db_path = str(tmp_path / "test_signals.db")
    storage = Storage(db_path)
    return SignalExecutor(storage)


# ── Open Signals ─────────────────────────────────────────

class TestOpenSignal:

    def test_open_returns_id(self, executor):
        sig_id = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        assert isinstance(sig_id, int)
        assert sig_id > 0

    def test_open_sets_status_open(self, executor):
        sig_id = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        signals = executor.get_open_signals()
        assert len(signals) == 1
        assert signals[0]["status"] == "open"

    def test_direction_normalized(self, executor):
        executor.open_signal("buy", 1.0900, 1.0870, 1.0960)
        signals = executor.get_open_signals()
        assert signals[0]["direction"] == "BUY"

    def test_multiple_open(self, executor):
        executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        executor.open_signal("SELL", 1.0950, 1.0980, 1.0890)
        signals = executor.get_open_signals()
        assert len(signals) == 2


# ── Close Signals ────────────────────────────────────────

class TestCloseSignal:

    def test_close_buy_profit(self, executor):
        sig_id = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        result = executor.close_signal(sig_id, 1.0940, "manual")
        assert result is not None
        assert result["pnl_pips"] == 40.0
        assert result["is_win"] is True

    def test_close_buy_loss(self, executor):
        sig_id = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        result = executor.close_signal(sig_id, 1.0870, "stop_loss")
        assert result["pnl_pips"] == -30.0
        assert result["is_win"] is False

    def test_close_sell_profit(self, executor):
        sig_id = executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        result = executor.close_signal(sig_id, 1.0850, "take_profit")
        assert result["pnl_pips"] == 50.0
        assert result["is_win"] is True

    def test_close_sell_loss(self, executor):
        sig_id = executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        result = executor.close_signal(sig_id, 1.0930, "stop_loss")
        assert result["pnl_pips"] == -30.0

    def test_close_nonexistent(self, executor):
        result = executor.close_signal(999, 1.0900)
        assert result is None

    def test_closed_not_in_open_list(self, executor):
        sig_id = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        executor.close_signal(sig_id, 1.0950, "take_profit")
        assert len(executor.get_open_signals()) == 0


# ── Check Signals (Auto SL/TP) ───────────────────────────

class TestCheckSignals:

    def test_buy_stop_loss_triggered(self, executor):
        executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        closed = executor.check_signals(1.0860)  # Below SL
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"

    def test_buy_take_profit_triggered(self, executor):
        executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        closed = executor.check_signals(1.0970)  # Above TP
        assert len(closed) == 1
        assert closed[0]["reason"] == "take_profit"

    def test_sell_stop_loss_triggered(self, executor):
        executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        closed = executor.check_signals(1.0940)  # Above SL
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"

    def test_sell_take_profit_triggered(self, executor):
        executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        closed = executor.check_signals(1.0830)  # Below TP
        assert len(closed) == 1
        assert closed[0]["reason"] == "take_profit"

    def test_no_trigger_in_range(self, executor):
        executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        closed = executor.check_signals(1.0920)  # Between SL and TP
        assert len(closed) == 0


# ── Performance ──────────────────────────────────────────

class TestPerformance:

    def test_no_trades_performance(self, executor):
        perf = executor.get_performance()
        assert perf["total_trades"] == 0

    def test_performance_with_trades(self, executor):
        # Win
        sig1 = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        executor.close_signal(sig1, 1.0960, "take_profit")

        # Loss
        sig2 = executor.open_signal("SELL", 1.0950, 1.0980, 1.0890)
        executor.close_signal(sig2, 1.0980, "stop_loss")

        perf = executor.get_performance()
        assert perf["total_trades"] == 2
        assert perf["wins"] == 1
        assert perf["losses"] == 1
        assert perf["win_rate"] == 50.0

    def test_profit_factor(self, executor):
        # 2 wins of +40 pips each
        for _ in range(2):
            sid = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
            executor.close_signal(sid, 1.0940, "take_profit")

        # 1 loss of -30 pips
        sid = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        executor.close_signal(sid, 1.0870, "stop_loss")

        perf = executor.get_performance()
        assert perf["profit_factor"] == round(80 / 30, 2)


# ── Formatting ───────────────────────────────────────────

class TestFormatting:

    def test_format_no_open(self, executor):
        text = executor.format_open_signals()
        assert "No open signals" in text

    def test_format_open(self, executor):
        executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        text = executor.format_open_signals()
        assert "BUY" in text
        assert "1.09" in text

    def test_format_performance_no_trades(self, executor):
        text = executor.format_performance()
        assert "No trades closed" in text

    def test_format_performance_with_trades(self, executor):
        sid = executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        executor.close_signal(sid, 1.0940, "take_profit")
        text = executor.format_performance()
        assert "Win Rate" in text
