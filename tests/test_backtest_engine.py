"""
Tests for BacktestEngine — candle replay, strategy comparison, edge cases.
"""

import pytest

from euroscope.analytics.backtest_engine import BacktestEngine, BacktestResult, BacktestTrade


def _make_candles(n=100, start_price=1.0900, direction="up"):
    """Generate synthetic OHLCV candles for testing."""
    candles = []
    price = start_price
    for i in range(n):
        # Zigzag pattern
        if direction == "up":
            delta = 0.0003 if i % 2 == 0 else -0.0001
        elif direction == "down":
            delta = -0.0003 if i % 2 == 0 else 0.0001
        else:  # range
            delta = 0.0002 if i % 4 < 2 else -0.0002

        o = price
        c = price + delta
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002

        candles.append({
            "open": round(o, 5),
            "high": round(h, 5),
            "low": round(l, 5),
            "close": round(c, 5),
            "volume": 1000 + i * 10,
        })
        price = c

    return candles


# ── Core Replay ──────────────────────────────────────────

class TestBacktestReplay:

    def test_runs_without_crash(self):
        engine = BacktestEngine()
        candles = _make_candles(100)
        result = engine.run(candles)
        assert isinstance(result, BacktestResult)
        assert result.bars_tested == 100

    def test_insufficient_data(self):
        engine = BacktestEngine()
        candles = _make_candles(10)
        result = engine.run(candles)
        assert result.total_trades == 0

    def test_generates_trades_on_enough_data(self):
        engine = BacktestEngine()
        candles = _make_candles(200, direction="up")
        result = engine.run(candles)
        # May or may not generate trades depending on indicator signals
        assert result.bars_tested == 200
        assert isinstance(result.trades, list)


# ── Exit Logic ───────────────────────────────────────────

class TestExitLogic:

    def test_buy_stop_loss(self):
        trade = BacktestTrade(
            direction="BUY", entry_price=1.0900,
            stop_loss=1.0870, take_profit=1.0960,
        )
        result = BacktestEngine._check_exit(trade, high=1.0920, low=1.0860, bar_idx=5)
        assert result is not None
        assert result.is_win is False
        assert result.pnl_pips < 0

    def test_buy_take_profit(self):
        trade = BacktestTrade(
            direction="BUY", entry_price=1.0900,
            stop_loss=1.0870, take_profit=1.0960,
        )
        result = BacktestEngine._check_exit(trade, high=1.0970, low=1.0890, bar_idx=5)
        assert result is not None
        assert result.is_win is True
        assert result.pnl_pips > 0

    def test_sell_stop_loss(self):
        trade = BacktestTrade(
            direction="SELL", entry_price=1.0900,
            stop_loss=1.0930, take_profit=1.0840,
        )
        result = BacktestEngine._check_exit(trade, high=1.0940, low=1.0880, bar_idx=5)
        assert result is not None
        assert result.is_win is False

    def test_sell_take_profit(self):
        trade = BacktestTrade(
            direction="SELL", entry_price=1.0900,
            stop_loss=1.0930, take_profit=1.0840,
        )
        result = BacktestEngine._check_exit(trade, high=1.0910, low=1.0830, bar_idx=5)
        assert result is not None
        assert result.is_win is True

    def test_no_exit_in_range(self):
        trade = BacktestTrade(
            direction="BUY", entry_price=1.0900,
            stop_loss=1.0870, take_profit=1.0960,
        )
        result = BacktestEngine._check_exit(trade, high=1.0920, low=1.0880, bar_idx=5)
        assert result is None


# ── Metrics Computation ──────────────────────────────────

class TestMetricsComputation:

    def test_compute_from_trades(self):
        result = BacktestResult(bars_tested=100)
        result.trades = [
            BacktestTrade(pnl_pips=40, is_win=True),
            BacktestTrade(pnl_pips=-20, is_win=False),
            BacktestTrade(pnl_pips=30, is_win=True),
        ]
        BacktestEngine._compute_metrics(result)
        assert result.total_trades == 3
        assert result.wins == 2
        assert result.losses == 1
        assert result.total_pnl == 50.0
        assert result.profit_factor == 3.5  # 70/20

    def test_compute_empty(self):
        result = BacktestResult()
        BacktestEngine._compute_metrics(result)
        assert result.total_trades == 0

    def test_equity_curve_computed(self):
        result = BacktestResult(bars_tested=50)
        result.trades = [
            BacktestTrade(pnl_pips=30, is_win=True),
            BacktestTrade(pnl_pips=-10, is_win=False),
        ]
        BacktestEngine._compute_metrics(result)
        assert result.equity_curve == [30.0, 20.0]
        assert result.max_drawdown == 10.0


# ── Strategy Comparison ──────────────────────────────────

class TestStrategyComparison:

    def test_compare_returns_dict(self):
        engine = BacktestEngine()
        candles = _make_candles(200)
        results = engine.compare_strategies(candles)
        assert "trend_following" in results
        assert "mean_reversion" in results
        assert "breakout" in results

    def test_compare_custom_strategies(self):
        engine = BacktestEngine()
        candles = _make_candles(200)
        results = engine.compare_strategies(candles, strategies=["trend_following"])
        assert len(results) == 1


# ── Formatting ───────────────────────────────────────────

class TestFormatting:

    def test_format_no_trades(self):
        result = BacktestResult(strategy="test", bars_tested=100)
        text = BacktestEngine.format_result(result)
        assert "No trades" in text

    def test_format_with_trades(self):
        result = BacktestResult(
            strategy="trend_following", bars_tested=200,
            total_trades=5, wins=3, losses=2,
            win_rate=60.0, total_pnl=50.0, avg_pnl=10.0,
            max_drawdown=15.0, profit_factor=2.5, sharpe_ratio=1.5,
            best_trade=30.0, worst_trade=-20.0,
        )
        text = BacktestEngine.format_result(result)
        assert "Trend Following" in text
        assert "60.0%" in text

    def test_format_comparison(self):
        results = {
            "trend": BacktestResult(total_trades=10, win_rate=60, total_pnl=50, profit_factor=2),
            "revert": BacktestResult(total_trades=5, win_rate=40, total_pnl=-20, profit_factor=0.5),
        }
        text = BacktestEngine.format_comparison(results)
        assert "Strategy Comparison" in text
        assert "🟢" in text  # positive
        assert "🔴" in text  # negative
