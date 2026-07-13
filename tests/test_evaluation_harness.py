"""
Tests for Evaluation Harness — ReplayEngine, ShadowMode, WalkForwardEvaluator, EvalHarness.
"""

import math
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

from euroscope.evaluation.harness_core import (
    EvalMetrics,
    EvalResult,
    ReplayEngine,
    ShadowMode,
    WalkForwardEvaluator,
    EvalHarness,
    _spearman_rank_corr,
    _classify_session,
    _build_equity_curve,
    _compute_core_metrics,
    CONFIDENCE_BUCKETS,
)


# ── Helper Tests ───────────────────────────────────────────────

class TestHelpers:
    def test_spearmanperfect_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert _spearman_rank_corr(xs, ys) == 1.0

    def test_spearman_inverse_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [50.0, 40.0, 30.0, 20.0, 10.0]
        assert _spearman_rank_corr(xs, ys) == -1.0

    def test_spearman_insufficient_data(self):
        assert _spearman_rank_corr([1.0], [2.0]) == 0.0
        assert _spearman_rank_corr([], []) == 0.0

    def test_classify_session_asia(self):
        dt = datetime(2025, 1, 1, 3, 0, tzinfo=timezone.utc)
        assert _classify_session(dt) == "Asia"

    def test_classify_session_london(self):
        dt = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert _classify_session(dt) == "London"

    def test_classify_session_newyork(self):
        dt = datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc)
        assert _classify_session(dt) == "New_York"

    def test_build_equity_curve(self):
        curve = _build_equity_curve([10, -5, 15, -3])
        assert curve == [10.0, 5.0, 20.0, 17.0]

    def test_compute_core_metrics_empty(self):
        assert _compute_core_metrics([]) == {}

    def test_compute_core_metrics_basic(self):
        pnls = [10.0, -5.0, 20.0, -3.0, 15.0]
        m = _compute_core_metrics(pnls)
        assert m["total_trades"] == 5
        assert m["wins"] == 3
        assert m["losses"] == 2
        assert m["win_rate"] == 60.0
        assert m["total_pnl"] == 37.0
        assert m["best_trade"] == 20.0
        assert m["worst_trade"] == -5.0
        assert m["max_drawdown"] >= 0


# ── ReplayEngine Tests ────────────────────────────────────────

class TestReplayEngine:
    @pytest.fixture
    def mock_storage(self):
        storage = MagicMock()
        storage.get_signals = AsyncMock(return_value=[])
        storage.get_trade_journal = AsyncMock(return_value=[])
        return storage

    @pytest.fixture
    def sample_signals(self):
        now = datetime.now(timezone.utc)
        return [
            {"id": 1, "direction": "BUY", "entry_price": 1.0800, "pnl_pips": 15.0,
             "confidence": 75, "created_at": (now - timedelta(days=5)).isoformat(),
             "status": "closed", "source": "system"},
            {"id": 2, "direction": "SELL", "entry_price": 1.0850, "pnl_pips": -8.0,
             "confidence": 60, "created_at": (now - timedelta(days=4)).isoformat(),
             "status": "closed", "source": "system"},
            {"id": 3, "direction": "BUY", "entry_price": 1.0820, "pnl_pips": 22.0,
             "confidence": 85, "created_at": (now - timedelta(days=3)).isoformat(),
             "status": "closed", "source": "system"},
            {"id": 4, "direction": "SELL", "entry_price": 1.0900, "pnl_pips": 5.0,
             "confidence": 55, "created_at": (now - timedelta(days=2)).isoformat(),
             "status": "closed", "source": "manual"},
            {"id": 5, "direction": "BUY", "entry_price": 1.0780, "pnl_pips": -12.0,
             "confidence": 70, "created_at": (now - timedelta(days=1)).isoformat(),
             "status": "closed", "source": "system"},
        ]

    @pytest.mark.asyncio
    async def test_replay_empty_signals(self, mock_storage):
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30)
        assert result.mode == "replay"
        assert result.metrics.total_trades == 0

    @pytest.mark.asyncio
    async def test_replay_with_signals(self, mock_storage, sample_signals):
        mock_storage.get_signals.return_value = sample_signals
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30, source="signals")
        assert result.mode == "replay"
        assert result.metrics.total_trades == 5
        assert result.metrics.win_rate == 60.0
        assert result.metrics.total_pnl == 22.0

    @pytest.mark.asyncio
    async def test_replay_information_coefficient(self, mock_storage, sample_signals):
        mock_storage.get_signals.return_value = sample_signals
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30)
        ic = result.metrics.information_coefficient
        assert -1.0 <= ic <= 1.0

    @pytest.mark.asyncio
    async def test_replay_confidence_calibration(self, mock_storage, sample_signals):
        mock_storage.get_signals.return_value = sample_signals
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30)
        cal = result.metrics.confidence_calibration
        assert isinstance(cal, dict)
        assert len(cal) > 0
        for bucket, data in cal.items():
            assert "count" in data
            assert "actual_win_rate" in data

    @pytest.mark.asyncio
    async def test_replay_session_breakdown(self, mock_storage, sample_signals):
        mock_storage.get_signals.return_value = sample_signals
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30)
        sb = result.metrics.session_breakdown
        assert isinstance(sb, dict)
        total_trades = sum(v["trades"] for v in sb.values())
        assert total_trades == 5

    @pytest.mark.asyncio
    async def test_replay_skill_attribution(self, mock_storage, sample_signals):
        mock_storage.get_signals.return_value = sample_signals
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30)
        sa = result.metrics.skill_attribution
        assert "system" in sa
        assert "manual" in sa
        assert sa["system"]["trades"] == 4
        assert sa["manual"]["trades"] == 1

    @pytest.mark.asyncio
    async def test_replay_flip_flop_rate(self, mock_storage, sample_signals):
        mock_storage.get_signals.return_value = sample_signals
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=30)
        assert 0.0 <= result.metrics.flip_flop_rate <= 100.0

    @pytest.mark.asyncio
    async def test_replay_journal_source(self, mock_storage):
        now = datetime.now(timezone.utc)
        journal = [
            {"id": 1, "direction": "BUY", "entry_price": 1.0800, "pnl_pips": 10.0,
             "confidence": 70, "timestamp": (now - timedelta(days=1)).isoformat(),
             "status": "closed", "strategy": "trend_following"},
        ]
        mock_storage.get_trade_journal.return_value = journal
        engine = ReplayEngine(mock_storage)
        result = await engine.run(days=7, source="journal")
        assert result.metrics.total_trades == 1


# ── ShadowMode Tests ──────────────────────────────────────────

class TestShadowMode:
    def test_start_stop(self):
        shadow = ShadowMode()
        shadow.start()
        assert shadow._active is True
        shadow.tick("BUY", 75.0, 1.0800)
        shadow.tick("SELL", 60.0, 1.0850)
        shadow.grade(1.0820)
        result = shadow.stop()
        assert result.mode == "shadow"
        assert len(result.trades) == 2
        assert shadow._active is False

    def test_tick_when_inactive(self):
        shadow = ShadowMode()
        shadow.tick("BUY", 75.0, 1.0800)
        assert len(shadow.predictions) == 0

    def test_grade_predictions(self):
        shadow = ShadowMode()
        shadow.start()
        shadow.tick("BUY", 75.0, 1.0800)
        shadow.tick("SELL", 60.0, 1.0850)
        shadow.grade(1.0820)
        assert shadow.predictions[0]["graded"] is True
        assert shadow.predictions[0]["is_correct"] is True
        assert shadow.predictions[0]["outcome_pips"] == 20.0
        assert shadow.predictions[1]["graded"] is True
        assert shadow.predictions[1]["is_correct"] is True
        assert shadow.predictions[1]["outcome_pips"] == 30.0

    def test_grade_wrong_direction(self):
        shadow = ShadowMode()
        shadow.start()
        shadow.tick("BUY", 75.0, 1.0800)
        shadow.grade(1.0750)
        assert shadow.predictions[0]["is_correct"] is False
        assert shadow.predictions[0]["outcome_pips"] == -50.0

    def test_finalize_empty(self):
        shadow = ShadowMode()
        shadow.start()
        result = shadow.stop()
        assert result.metrics.total_trades == 0

    def test_finalize_with_graded(self):
        shadow = ShadowMode()
        shadow.start()
        shadow.tick("BUY", 75.0, 1.0800)
        shadow.tick("BUY", 80.0, 1.0810)
        shadow.grade(1.0830)
        result = shadow.stop()
        assert result.metrics.total_trades == 2
        assert result.metrics.win_rate == 100.0


# ── WalkForwardEvaluator Tests ────────────────────────────────

class TestWalkForwardEvaluator:
    def test_insufficient_data(self):
        mock_bt = MagicMock()
        evaluator = WalkForwardEvaluator(mock_bt)
        result = evaluator.run(candles=[{"close": 1.0}] * 10, window_size=100)
        assert result.mode == "walk_forward"
        assert "error" in result.metadata

    def test_walk_forward_with_mock_bt(self):
        mock_bt = MagicMock()
        from euroscope.analytics.backtest_engine import BacktestResult, BacktestTrade

        trade1 = BacktestTrade(direction="BUY", entry_price=1.08, exit_price=1.085,
                               pnl_pips=5.0, strategy="trend_following", is_win=True)
        trade2 = BacktestTrade(direction="SELL", entry_price=1.09, exit_price=1.092,
                               pnl_pips=-2.0, strategy="mean_reversion", is_win=False)
        res = BacktestResult(total_trades=2, wins=1, losses=1, win_rate=50.0, trades=[trade1, trade2])
        mock_bt.run.return_value = res

        evaluator = WalkForwardEvaluator(mock_bt)
        candles = [{"close": 1.0 + i * 0.001} for i in range(600)]
        result = evaluator.run(candles, window_size=200, step_size=100)
        assert result.mode == "walk_forward"
        assert result.metrics.total_trades > 0
        assert "stability" in result.metadata
        assert result.metadata["windows"] > 0


# ── EvalHarness Tests ─────────────────────────────────────────

class TestEvalHarness:
    @pytest.mark.asyncio
    async def test_full_report_no_storage(self):
        harness = EvalHarness()
        report = await harness.full_report()
        assert "EVALUATION REPORT" in report
        assert "replay" in report.lower()

    @pytest.mark.asyncio
    async def test_full_report_with_storage(self):
        storage = MagicMock()
        storage.get_signals = AsyncMock(return_value=[])
        harness = EvalHarness(storage=storage)
        report = await harness.full_report(days=7)
        assert "EVALUATION REPORT" in report

    def test_format_report(self):
        m = EvalMetrics(
            total_trades=10, wins=6, losses=4, win_rate=60.0,
            total_pnl=25.0, profit_factor=1.8, sharpe_ratio=1.5,
            information_coefficient=0.35,
            confidence_calibration={"medium": {"count": 5, "actual_win_rate": 50.0}},
            session_breakdown={"London": {"trades": 6, "win_rate": 66.7, "total_pnl": 20.0}},
            skill_attribution={"system": {"trades": 8, "win_rate": 62.5, "avg_pnl": 3.1}},
        )
        result = EvalResult(mode="replay", metrics=m, metadata={"days": 30})
        report = EvalHarness.format_report(result)
        assert "REPLAY" in report
        assert "60.0%" in report
        assert "Information Coefficient" in report
        assert "Confidence Calibration" in report
        assert "Session Breakdown" in report
        assert "Skill Attribution" in report


# ── EvalMetrics Dataclass Tests ───────────────────────────────

class TestEvalMetrics:
    def test_default_values(self):
        m = EvalMetrics()
        assert m.total_trades == 0
        assert m.information_coefficient == 0.0
        assert m.confidence_calibration == {}
        assert m.equity_curve == []

    def test_all_fields_settable(self):
        m = EvalMetrics(
            total_trades=100, wins=60, win_rate=60.0,
            information_coefficient=0.42,
            confidence_calibration={"high": {"count": 20, "actual_win_rate": 75.0}},
            regime_breakdown={"trending": {"trades": 50}},
        )
        assert m.total_trades == 100
        assert m.information_coefficient == 0.42
        assert m.regime_breakdown["trending"]["trades"] == 50
