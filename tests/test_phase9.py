"""Phase 9: Adaptive Learning — Tests."""

import pytest
from euroscope.data.storage import Storage
from euroscope.learning.pattern_tracker import PatternTracker
from euroscope.learning.adaptive_tuner import AdaptiveTuner


@pytest.fixture
def storage(tmp_path):
    """Create a fresh storage for each test."""
    db = str(tmp_path / "test.db")
    return Storage(db_path=db)


# ── Trade Journal ─────────────────────────────────────────

class TestTradeJournal:
    def test_save_and_get(self, storage):
        tid = storage.save_trade_journal(
            direction="BUY", entry_price=1.0850,
            stop_loss=1.0800, take_profit=1.0950,
            strategy="trend_following", timeframe="H1",
            regime="trending", confidence=75.0,
            indicators={"RSI": 55.0}, patterns=["double_bottom"],
            reasoning="Strong bullish momentum",
        )
        assert tid == 1

        journal = storage.get_trade_journal()
        assert len(journal) == 1
        assert journal[0]["direction"] == "BUY"
        assert journal[0]["strategy"] == "trend_following"
        assert journal[0]["status"] == "open"

    def test_causal_chain_persisted(self, storage):
        chain = {
            "trigger": "macro_event",
            "reaction": "strong_break",
            "indicator_response": "confirmed",
            "outcome": "profitable",
        }
        tid = storage.save_trade_journal(
            direction="BUY", entry_price=1.0850,
            strategy="trend_following",
            causal_chain=chain,
        )
        trade = storage.get_trade_with_causal(tid)
        assert trade is not None
        assert trade["causal_chain"] == chain

    def test_close_and_stats(self, storage):
        tid = storage.save_trade_journal(
            direction="BUY", entry_price=1.0850,
            strategy="trend_following",
        )
        storage.close_trade_journal(tid, exit_price=1.0900, pnl_pips=50.0, is_win=True)

        stats = storage.get_trade_journal_stats()
        assert stats["total"] == 1
        assert stats["wins"] == 1
        assert stats["win_rate"] == 100.0
        assert stats["total_pnl"] == 50.0

    def test_stats_by_strategy(self, storage):
        for i in range(3):
            tid = storage.save_trade_journal(
                direction="BUY", entry_price=1.0850,
                strategy="trend_following" if i < 2 else "mean_reversion",
            )
            storage.close_trade_journal(
                tid, exit_price=1.09 if i == 0 else 1.08,
                pnl_pips=50.0 if i == 0 else -20.0,
                is_win=i == 0,
            )

        stats = storage.get_trade_journal_stats()
        assert stats["total"] == 3
        assert "trend_following" in stats["by_strategy"]
        assert "mean_reversion" in stats["by_strategy"]

    def test_filter_by_status(self, storage):
        tid = storage.save_trade_journal(direction="BUY", entry_price=1.08)
        storage.save_trade_journal(direction="SELL", entry_price=1.09)

        storage.close_trade_journal(tid, 1.09, 100.0, True)

        open_trades = storage.get_trade_journal(status="open")
        assert len(open_trades) == 1
        assert open_trades[0]["direction"] == "SELL"


# ── Trade Journal Skill ───────────────────────────────────

class TestTradeJournalSkill:
    def test_log_and_close(self, storage):
        from euroscope.skills.trade_journal.skill import TradeJournalSkill
        from euroscope.skills.base import SkillContext

        skill = TradeJournalSkill()
        skill.storage = storage
        ctx = SkillContext()

        result = skill.execute(ctx, "log_trade",
                               direction="BUY", entry_price=1.085,
                               strategy="breakout")
        assert result.success
        trade_id = result.data["trade_id"]

        result = skill.execute(ctx, "close_trade",
                               trade_id=trade_id, exit_price=1.09,
                               pnl_pips=50.0, is_win=True)
        assert result.success

        result = skill.execute(ctx, "get_stats")
        assert result.success
        assert result.data["total"] == 1
        assert result.data["win_rate"] == 100.0


# ── Pattern Tracker ───────────────────────────────────────

class TestPatternTracker:
    def test_record_and_resolve(self, storage):
        tracker = PatternTracker(storage)

        pid = tracker.record_detection("double_bottom", "H4", "BUY", 1.0850)
        assert pid == 1

        tracker.resolve(pid, "BUY", 1.0900, True)

        rates = tracker.get_success_rates()
        key = "double_bottom_H4"
        assert key in rates
        assert rates[key]["success_rate"] == 100.0

    def test_confidence_multiplier(self, storage):
        tracker = PatternTracker(storage)

        # Too little data → 1.0
        pid = tracker.record_detection("head_shoulders", "H1", "SELL", 1.09)
        tracker.resolve(pid, "SELL", 1.08, True)
        assert tracker.get_confidence_multiplier("head_shoulders", "H1") == 1.0

        # Add more data (need >= 3)
        for _ in range(3):
            pid = tracker.record_detection("head_shoulders", "H1", "SELL", 1.09)
            tracker.resolve(pid, "SELL", 1.08, True)

        mult = tracker.get_confidence_multiplier("head_shoulders", "H1")
        assert mult > 1.0  # 100% success → ~1.5
        assert mult <= 1.5

    def test_unresolved(self, storage):
        tracker = PatternTracker(storage)
        tracker.record_detection("triangle", "H4", "BUY", 1.09)
        tracker.record_detection("flag", "H1", "SELL", 1.08)

        unresolved = tracker.get_unresolved()
        assert len(unresolved) == 2

    def test_format_report(self, storage):
        tracker = PatternTracker(storage)

        for _ in range(3):
            pid = tracker.record_detection("double_bottom", "H4", "BUY", 1.08)
            tracker.resolve(pid, "BUY", 1.09, True)

        pid = tracker.record_detection("double_bottom", "H4", "BUY", 1.08)
        tracker.resolve(pid, "SELL", 1.07, False)

        report = tracker.format_report()
        assert "double_bottom" in report
        assert "75.0%" in report


# ── Adaptive Tuner ────────────────────────────────────────

class TestAdaptiveTuner:
    def test_not_enough_data(self, storage):
        tuner = AdaptiveTuner(storage)
        result = tuner.analyze()
        assert not result["ready"]

    def test_low_win_rate_recommendation(self, storage):
        tuner = AdaptiveTuner(storage)

        # Create 6 losing trades
        for _ in range(6):
            tid = storage.save_trade_journal(
                direction="BUY", entry_price=1.085, strategy="trend",
            )
            storage.close_trade_journal(tid, 1.08, -50.0, False)

        result = tuner.analyze()
        assert result["ready"]
        assert len(result["recommendations"]) > 0

        # Should recommend raising confidence threshold
        params = [r["param"] for r in result["recommendations"]]
        assert "confidence_threshold" in params

    def test_high_win_rate_recommendation(self, storage):
        tuner = AdaptiveTuner(storage)

        # Create 6 winning trades
        for _ in range(6):
            tid = storage.save_trade_journal(
                direction="BUY", entry_price=1.085, strategy="trend",
            )
            storage.close_trade_journal(tid, 1.09, 50.0, True)

        result = tuner.analyze()
        assert result["ready"]

        params = [r["param"] for r in result["recommendations"]]
        assert "confidence_threshold" in params
        # Should suggest decreasing (capture more opportunities)
        conf_rec = next(r for r in result["recommendations"]
                        if r["param"] == "confidence_threshold")
        assert conf_rec["action"] == "decrease"

    def test_apply_adjustment_with_bounds(self, storage):
        tuner = AdaptiveTuner(storage)

        # RSI oversold: bounds (20, 40)
        assert tuner.apply_adjustment("rsi_oversold", 30, -5) == 25
        assert tuner.apply_adjustment("rsi_oversold", 22, -10) == 20  # clamped
        assert tuner.apply_adjustment("rsi_oversold", 38, +5) == 40  # clamped

    def test_format_report(self, storage):
        tuner = AdaptiveTuner(storage)

        for _ in range(6):
            tid = storage.save_trade_journal(
                direction="BUY", entry_price=1.085, strategy="trend",
            )
            storage.close_trade_journal(tid, 1.08, -50.0, False)

        report = tuner.format_report()
        assert "Adaptive Tuner" in report
        assert "Recommendations" in report


# ── Workspace Memory Refresh ──────────────────────────────

class TestWorkspaceMemoryRefresh:
    def test_refresh_memory(self, storage, tmp_path):
        from euroscope.workspace import WorkspaceManager

        ws = WorkspaceManager(workspace_dir=tmp_path)

        # Put some initial content
        (tmp_path / "MEMORY.md").write_text("# Memory\n\n## Recent Analyses\n- old entry\n")

        ws.refresh_memory(storage)

        content = (tmp_path / "MEMORY.md").read_text()
        assert "Auto-refreshed" in content
        assert "Recent Analyses" in content
