"""
Tests for signal executor: open/close/check lifecycle, PnL tracking.
"""

import os
import tempfile

import pytest

from euroscope.data.storage import Storage
from euroscope.trading.signal_executor import SignalExecutor
from euroscope.trading.execution_simulator import ExecutionSimulator, ExecutionConfig


@pytest.fixture
def executor(tmp_path):
    db_path = str(tmp_path / "test_signals.db")
    storage = Storage(db_path)
    # Disable execution simulation for deterministic testing
    sim = ExecutionSimulator(config=ExecutionConfig(enabled=False))
    return SignalExecutor(storage, execution_sim=sim)


# ── Open Signals ─────────────────────────────────────────

class TestOpenSignal:

    @pytest.mark.asyncio
    async def test_open_returns_id(self, executor):
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        assert isinstance(sig_id, int)
        assert sig_id > 0

    @pytest.mark.asyncio
    async def test_open_sets_status_open(self, executor):
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        signals = await executor.get_open_signals()
        assert len(signals) == 1
        assert signals[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_direction_normalized(self, executor):
        await executor.open_signal("buy", 1.0900, 1.0870, 1.0960)
        signals = await executor.get_open_signals()
        assert signals[0]["direction"] == "BUY"

    @pytest.mark.asyncio
    async def test_multiple_open(self, executor):
        await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        await executor.open_signal("SELL", 1.0950, 1.0980, 1.0890)
        signals = await executor.get_open_signals()
        assert len(signals) == 2


# ── Close Signals ────────────────────────────────────────

class TestCloseSignal:

    @pytest.mark.asyncio
    async def test_close_buy_profit(self, executor):
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        result = await executor.close_signal(sig_id, 1.0940, "manual")
        assert result is not None
        assert result["pnl_pips"] == 40.0
        assert result["is_win"] is True

    @pytest.mark.asyncio
    async def test_close_buy_loss(self, executor):
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        result = await executor.close_signal(sig_id, 1.0870, "stop_loss")
        assert result["pnl_pips"] == -30.0
        assert result["is_win"] is False

    @pytest.mark.asyncio
    async def test_close_sell_profit(self, executor):
        sig_id = await executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        result = await executor.close_signal(sig_id, 1.0850, "take_profit")
        assert result["pnl_pips"] == 50.0
        assert result["is_win"] is True

    @pytest.mark.asyncio
    async def test_close_sell_loss(self, executor):
        sig_id = await executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        result = await executor.close_signal(sig_id, 1.0930, "stop_loss")
        assert result["pnl_pips"] == -30.0

    @pytest.mark.asyncio
    async def test_close_nonexistent(self, executor):
        result = await executor.close_signal(999, 1.0900)
        assert result is None

    @pytest.mark.asyncio
    async def test_closed_not_in_open_list(self, executor):
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        await executor.close_signal(sig_id, 1.0950, "take_profit")
        assert len(await executor.get_open_signals()) == 0


# ── Check Signals (Auto SL/TP) ───────────────────────────

class TestCheckSignals:

    @pytest.mark.asyncio
    async def test_buy_stop_loss_triggered(self, executor):
        await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        closed = await executor.check_signals(1.0860)  # Below SL
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"

    @pytest.mark.asyncio
    async def test_buy_take_profit_triggered(self, executor):
        await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        closed = await executor.check_signals(1.0970)  # Above TP
        assert len(closed) == 1
        assert closed[0]["reason"] == "take_profit"

    @pytest.mark.asyncio
    async def test_sell_stop_loss_triggered(self, executor):
        await executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        closed = await executor.check_signals(1.0940)  # Above SL
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"

    @pytest.mark.asyncio
    async def test_sell_take_profit_triggered(self, executor):
        await executor.open_signal("SELL", 1.0900, 1.0930, 1.0840)
        closed = await executor.check_signals(1.0830)  # Below TP
        assert len(closed) == 1
        assert closed[0]["reason"] == "take_profit"

    @pytest.mark.asyncio
    async def test_no_trigger_in_range(self, executor):
        await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        closed = await executor.check_signals(1.0920)  # Between SL and TP
        assert len(closed) == 0

    @pytest.mark.asyncio
    async def test_trailing_stop_activation_buy(self, executor):
        # Current price targets = Entry = 1.0900
        # SL = 1.0850 (50 pips risk)
        # TP = 1.0950 (50 pips reward)
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0850, 1.0950)
        
        # Determine the exact entry price after simulated slippage
        open_sigs = await executor.get_open_signals()
        actual_entry = open_sigs[0]["entry_price"]
        
        # Move price up enough to exceed the 15 pip threshold 
        # (15 pips + some buffer to be safe) => 25 pips
        check_price_1 = round(actual_entry + 0.0025, 4)
        await executor.check_signals(check_price_1)
        
        # Verify SL moved to lock in profit
        open_sigs = await executor.get_open_signals()
        assert len(open_sigs) == 1
        new_sl = open_sigs[0]["stop_loss"]
        # With trailing_activation_pips=15, new SL = check_price_1 - 0.0015
        expected_sl_1 = round(check_price_1 - 0.0015, 5)
        assert new_sl == expected_sl_1
        
        # Test trailing further: Move up another 5 pips
        check_price_2 = round(check_price_1 + 0.0005, 4)
        await executor.check_signals(check_price_2)
        
        open_sigs = await executor.get_open_signals()
        newer_sl = open_sigs[0]["stop_loss"]
        expected_sl_2 = round(check_price_2 - 0.0015, 5)
        assert newer_sl == expected_sl_2
        
        # Test price drop: Should hit the trailing stop `expected_sl_2` instead of original
        closed = await executor.check_signals(expected_sl_2)
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"
        assert closed[0]["pnl_pips"] > 0


# ── Performance ──────────────────────────────────────────

class TestPerformance:

    @pytest.mark.asyncio
    async def test_no_trades_performance(self, executor):
        perf = await executor.get_performance()
        assert perf["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_performance_with_trades(self, executor):
        # Win
        sig1 = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        await executor.close_signal(sig1, 1.0960, "take_profit")

        # Loss
        sig2 = await executor.open_signal("SELL", 1.0950, 1.0980, 1.0890)
        await executor.close_signal(sig2, 1.0980, "stop_loss")

        perf = await executor.get_performance()
        assert perf["total_trades"] == 2
        assert perf["wins"] == 1
        assert perf["losses"] == 1
        assert perf["win_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_profit_factor(self, executor):
        # 2 wins of +40 pips each
        for _ in range(2):
            sid = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
            await executor.close_signal(sid, 1.0940, "take_profit")

        # 1 loss of -30 pips
        sid = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        await executor.close_signal(sid, 1.0870, "stop_loss")

        perf = await executor.get_performance()
        assert perf["profit_factor"] == round(80 / 30, 2)


# ── Formatting ───────────────────────────────────────────

class TestFormatting:

    @pytest.mark.asyncio
    async def test_format_no_open(self, executor):
        text = await executor.format_open_signals()
        assert "No open signals" in text

    @pytest.mark.asyncio
    async def test_format_open(self, executor):
        await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        text = await executor.format_open_signals()
        assert "BUY" in text
        assert "1.09" in text

    @pytest.mark.asyncio
    async def test_format_performance_no_trades(self, executor):
        text = await executor.format_performance()
        assert "No trades closed" in text

    @pytest.mark.asyncio
    async def test_format_performance_with_trades(self, executor):
        sid = await executor.open_signal("BUY", 1.0900, 1.0870, 1.0960)
        await executor.close_signal(sid, 1.0940, "take_profit")
        text = await executor.format_performance()
        assert "Win Rate" in text
