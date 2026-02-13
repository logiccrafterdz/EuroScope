"""
Tests for euroscope.data.storage module.
"""

import os
import pytest

from euroscope.data.storage import Storage


class TestDatabaseInit:
    """Test database initialization."""

    def test_creates_database_file(self, temp_db_path):
        storage = Storage(temp_db_path)
        assert os.path.exists(temp_db_path)

    def test_creates_all_tables(self, temp_db_path):
        import sqlite3
        storage = Storage(temp_db_path)
        with sqlite3.connect(temp_db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}

        expected = {
            "predictions", "alerts", "market_notes", "memory",
            "trading_signals", "news_events", "performance_metrics", "user_preferences",
        }
        assert expected.issubset(table_names)

    def test_reinit_is_safe(self, temp_db_path):
        """Re-initializing should not drop existing data."""
        storage = Storage(temp_db_path)
        storage.set_memory("test_key", "test_value")

        # Re-init
        storage2 = Storage(temp_db_path)
        assert storage2.get_memory("test_key") == "test_value"


class TestPredictions:
    """Test prediction CRUD."""

    def test_save_and_retrieve(self, temp_db_path):
        s = Storage(temp_db_path)
        pid = s.save_prediction("H1", "BULLISH", 75.0, "Test reasoning", 1.0850)
        assert pid is not None
        assert pid > 0

    def test_unresolved_predictions(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_prediction("H1", "BULLISH", 75.0)
        s.save_prediction("D1", "BEARISH", 60.0)

        preds = s.get_unresolved_predictions()
        assert len(preds) == 2

    def test_resolve_prediction(self, temp_db_path):
        s = Storage(temp_db_path)
        pid = s.save_prediction("H1", "BULLISH", 75.0)
        s.resolve_prediction(pid, "BULLISH", 1.0)

        preds = s.get_unresolved_predictions()
        assert len(preds) == 0

    def test_accuracy_stats(self, temp_db_path):
        s = Storage(temp_db_path)
        p1 = s.save_prediction("H1", "BULLISH", 75.0)
        p2 = s.save_prediction("H1", "BEARISH", 60.0)
        s.resolve_prediction(p1, "BULLISH", 1.0)
        s.resolve_prediction(p2, "BULLISH", 0.0)

        stats = s.get_accuracy_stats(30)
        assert stats["total"] == 2
        assert stats["correct"] == 1
        assert stats["accuracy"] == 50.0

    def test_no_predictions_stats(self, temp_db_path):
        s = Storage(temp_db_path)
        stats = s.get_accuracy_stats(30)
        assert stats["total"] == 0


class TestAlerts:
    """Test alert CRUD."""

    def test_add_and_get_alerts(self, temp_db_path):
        s = Storage(temp_db_path)
        aid = s.add_alert("above", 1.0900, 12345)
        assert aid > 0

        alerts = s.get_active_alerts()
        assert len(alerts) == 1
        assert alerts[0]["condition"] == "above"

    def test_trigger_alert(self, temp_db_path):
        s = Storage(temp_db_path)
        aid = s.add_alert("above", 1.0900, 12345)
        s.trigger_alert(aid)

        alerts = s.get_active_alerts()
        assert len(alerts) == 0


class TestMemory:
    """Test key-value memory store."""

    def test_set_and_get(self, temp_db_path):
        s = Storage(temp_db_path)
        s.set_memory("key1", "value1")
        assert s.get_memory("key1") == "value1"

    def test_overwrite(self, temp_db_path):
        s = Storage(temp_db_path)
        s.set_memory("key1", "old")
        s.set_memory("key1", "new")
        assert s.get_memory("key1") == "new"

    def test_missing_key(self, temp_db_path):
        s = Storage(temp_db_path)
        assert s.get_memory("nonexistent") is None

    def test_json_value(self, temp_db_path):
        s = Storage(temp_db_path)
        s.set_memory("data", {"foo": "bar"})
        result = s.get_memory("data")
        assert '"foo"' in result


class TestMarketNotes:
    """Test market notes."""

    def test_add_and_retrieve(self, temp_db_path):
        s = Storage(temp_db_path)
        s.add_note("analysis", "EUR/USD looking bullish")
        notes = s.get_recent_notes("analysis")
        assert len(notes) == 1

    def test_filter_by_category(self, temp_db_path):
        s = Storage(temp_db_path)
        s.add_note("analysis", "Note 1")
        s.add_note("news", "Note 2")
        assert len(s.get_recent_notes("analysis")) == 1
        assert len(s.get_recent_notes()) == 2


class TestTradingSignals:
    """Test trading signal CRUD."""

    def test_save_signal(self, temp_db_path):
        s = Storage(temp_db_path)
        sid = s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1",
                            reasoning="Test signal", risk_reward_ratio=2.0)
        assert sid > 0

    def test_get_signals(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1")
        s.save_signal("SELL", 1.0900, 1.0930, 1.0840, 60.0, "H4")

        all_signals = s.get_signals()
        assert len(all_signals) == 2

    def test_filter_by_status(self, temp_db_path):
        s = Storage(temp_db_path)
        sid = s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1")
        s.update_signal_status(sid, "closed", pnl_pips=30.0)

        pending = s.get_signals(status="pending")
        closed = s.get_signals(status="closed")
        assert len(pending) == 0
        assert len(closed) == 1
        assert closed[0]["pnl_pips"] == 30.0

    def test_closed_has_timestamp(self, temp_db_path):
        s = Storage(temp_db_path)
        sid = s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1")
        s.update_signal_status(sid, "closed")
        closed = s.get_signals(status="closed")
        assert closed[0]["closed_at"] is not None


class TestNewsEvents:
    """Test news event storage."""

    def test_save_news(self, temp_db_path):
        s = Storage(temp_db_path)
        nid = s.save_news_event(
            title="ECB raises rates",
            source="reuters",
            impact_score=8.5,
            sentiment="bullish",
            currency_impact="EUR",
        )
        assert nid > 0

    def test_get_recent_news(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_news_event("News 1", "brave", impact_score=5.0)
        s.save_news_event("News 2", "reuters", impact_score=8.0)
        s.save_news_event("News 3", "twitter", impact_score=2.0)

        all_news = s.get_recent_news()
        assert len(all_news) == 3

        high_impact = s.get_recent_news(min_impact=6.0)
        assert len(high_impact) == 1


class TestPerformanceMetrics:
    """Test performance metrics storage."""

    def test_save_metrics(self, temp_db_path):
        s = Storage(temp_db_path)
        mid = s.save_performance_metric(
            period="daily",
            total_signals=10,
            winning_signals=7,
            win_rate=70.0,
            total_pnl_pips=150.0,
            sharpe_ratio=1.5,
        )
        assert mid > 0

    def test_get_latest(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_performance_metric("daily", total_signals=5, win_rate=60.0)
        s.save_performance_metric("daily", total_signals=10, win_rate=70.0)

        latest = s.get_latest_metrics("daily")
        assert latest is not None
        assert latest["win_rate"] == 70.0

    def test_no_metrics(self, temp_db_path):
        s = Storage(temp_db_path)
        assert s.get_latest_metrics("daily") is None


class TestUserPreferences:
    """Test user preferences storage."""

    def test_save_preferences(self, temp_db_path):
        s = Storage(temp_db_path)
        pid = s.save_user_preferences(12345, risk_tolerance="high")
        assert pid is not None

    def test_get_preferences(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_user_preferences(12345, risk_tolerance="high", language="ar")
        prefs = s.get_user_preferences(12345)
        assert prefs is not None
        assert prefs["risk_tolerance"] == "high"
        assert prefs["language"] == "ar"

    def test_upsert_preferences(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_user_preferences(12345, risk_tolerance="low")
        s.save_user_preferences(12345, risk_tolerance="high")
        prefs = s.get_user_preferences(12345)
        assert prefs["risk_tolerance"] == "high"

    def test_missing_user(self, temp_db_path):
        s = Storage(temp_db_path)
        assert s.get_user_preferences(99999) is None

    def test_defaults(self, temp_db_path):
        s = Storage(temp_db_path)
        s.save_user_preferences(12345)
        prefs = s.get_user_preferences(12345)
        assert prefs["preferred_timeframe"] == "H1"
        assert prefs["alert_min_confidence"] == 60.0
        assert prefs["daily_report_hour"] == 8
