"""
Tests for PerformanceAnalytics — Sharpe, drawdown, equity curve, snapshots.
"""

import pytest

from euroscope.data.storage import Storage
from euroscope.analytics.performance_analytics import PerformanceAnalytics, PerformanceSnapshot


@pytest.fixture
def analytics(tmp_path):
    db_path = str(tmp_path / "test_perf.db")
    storage = Storage(db_path)
    return PerformanceAnalytics(storage)


def _seed_trades(storage, trades):
    """Helper: insert closed trades into DB."""
    for t in trades:
        sig_id = storage.save_signal(
            direction=t["direction"], entry_price=t["entry"],
            stop_loss=t.get("sl", 0), take_profit=t.get("tp", 0),
            confidence=70, timeframe="H1",
            source=t.get("strategy", "trend_following"),
            risk_reward_ratio=t.get("rr", 2.0),
        )
        storage.update_signal_status(sig_id, "closed", pnl_pips=t["pnl"])


# ── Basic Metrics ────────────────────────────────────────

class TestBasicMetrics:

    def test_empty_trades(self, analytics):
        snap = analytics.calculate()
        assert snap.total_trades == 0
        assert snap.win_rate == 0

    def test_single_win(self, analytics):
        _seed_trades(analytics.storage, [
            {"direction": "BUY", "entry": 1.09, "pnl": 40},
        ])
        snap = analytics.calculate()
        assert snap.total_trades == 1
        assert snap.wins == 1
        assert snap.win_rate == 100.0
        assert snap.total_pnl == 40.0

    def test_win_loss_mix(self, analytics):
        _seed_trades(analytics.storage, [
            {"direction": "BUY", "entry": 1.09, "pnl": 40},
            {"direction": "SELL", "entry": 1.10, "pnl": -20},
            {"direction": "BUY", "entry": 1.08, "pnl": 30},
        ])
        snap = analytics.calculate()
        assert snap.total_trades == 3
        assert snap.wins == 2
        assert snap.losses == 1
        assert snap.win_rate == pytest.approx(66.7, abs=0.1)
        assert snap.total_pnl == 50.0

    def test_profit_factor(self, analytics):
        _seed_trades(analytics.storage, [
            {"direction": "BUY", "entry": 1.09, "pnl": 60},
            {"direction": "SELL", "entry": 1.10, "pnl": -20},
        ])
        snap = analytics.calculate()
        assert snap.profit_factor == 3.0  # 60/20


# ── Advanced Metrics ─────────────────────────────────────

class TestAdvancedMetrics:

    def test_equity_curve(self):
        curve = PerformanceAnalytics._build_equity_curve([10, -5, 20, -10])
        assert curve == [10, 5, 25, 15]

    def test_max_drawdown(self):
        curve = [10, 5, 25, 15, 30]
        dd = PerformanceAnalytics._max_drawdown(curve)
        assert dd == 10.0  # 25 → 15

    def test_max_drawdown_empty(self):
        assert PerformanceAnalytics._max_drawdown([]) == 0.0

    def test_sharpe_ratio_positive(self):
        pnls = [10, 15, 12, 8, 20]
        sharpe = PerformanceAnalytics._sharpe_ratio(pnls)
        assert sharpe > 0

    def test_sharpe_ratio_insufficient_data(self):
        assert PerformanceAnalytics._sharpe_ratio([10]) == 0.0

    def test_sortino_positive_only(self):
        pnls = [10, 20, 15]  # All positive → inf
        sortino = PerformanceAnalytics._sortino_ratio(pnls)
        assert sortino == float("inf")

    def test_sortino_with_losses(self):
        pnls = [10, -5, 20, -10, 15]
        sortino = PerformanceAnalytics._sortino_ratio(pnls)
        assert sortino > 0

    def test_expectancy(self):
        wins = [40, 50, 30]
        losses = [-20, -15]
        win_rate = 0.6
        exp = PerformanceAnalytics._expectancy(wins, losses, win_rate)
        # 0.6 * 40 - 0.4 * 17.5 = 24 - 7 = 17.0
        assert exp == pytest.approx(17.0, abs=0.1)


# ── Snapshot Persistence ─────────────────────────────────

class TestSnapshotPersistence:

    def test_save_and_retrieve(self, analytics):
        _seed_trades(analytics.storage, [
            {"direction": "BUY", "entry": 1.09, "pnl": 40},
            {"direction": "SELL", "entry": 1.10, "pnl": -20},
        ])
        snap = analytics.calculate("daily")
        snap_id = analytics.save_snapshot(snap)
        assert snap_id > 0

        latest = analytics.get_latest("daily")
        assert latest is not None
        assert latest["total_signals"] == 2
        assert latest["win_rate"] == 50.0


# ── Breakdowns ───────────────────────────────────────────

class TestBreakdowns:

    def test_by_strategy(self, analytics):
        _seed_trades(analytics.storage, [
            {"direction": "BUY", "entry": 1.09, "pnl": 40, "strategy": "trend_following"},
            {"direction": "SELL", "entry": 1.10, "pnl": -20, "strategy": "mean_reversion"},
        ])
        snap = analytics.calculate()
        assert "trend_following" in snap.by_strategy
        assert snap.by_strategy["trend_following"]["total_pnl"] == 40.0


# ── Formatting ───────────────────────────────────────────

class TestFormatting:

    def test_format_empty(self, analytics):
        snap = analytics.calculate()
        text = analytics.format_full_report(snap)
        assert "No closed trades" in text

    def test_format_with_data(self, analytics):
        _seed_trades(analytics.storage, [
            {"direction": "BUY", "entry": 1.09, "pnl": 40},
            {"direction": "SELL", "entry": 1.10, "pnl": -20},
        ])
        snap = analytics.calculate()
        text = analytics.format_full_report(snap)
        assert "Sharpe" in text
        assert "Drawdown" in text
