"""
Tests for euroscope.data.storage module (async).
"""

import os
import pytest  # type: ignore

from euroscope.data.storage import Storage  # type: ignore


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
        # Use sync sqlite3 to insert data directly for init test
        import sqlite3
        conn = sqlite3.connect(temp_db_path)
        conn.execute(
            "INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?, ?, ?)",
            ("test_key", "test_value", "2024-01-01")
        )
        conn.commit()
        conn.close()

        # Re-init
        storage2 = Storage(temp_db_path)
        # Verify data persisted (check via sync sqlite3 since init is sync)
        conn2 = sqlite3.connect(temp_db_path)
        row = conn2.execute("SELECT value FROM memory WHERE key=?", ("test_key",)).fetchone()
        conn2.close()
        assert row is not None
        assert row[0] == "test_value"


class TestPredictions:
    """Test prediction CRUD."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, temp_db_path):
        s = Storage(temp_db_path)
        pid = await s.save_prediction("H1", "BULLISH", 75.0, "Test reasoning", 1.0850)
        assert pid is not None
        assert pid > 0
        await s.close()

    @pytest.mark.asyncio
    async def test_unresolved_predictions(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_prediction("H1", "BULLISH", 75.0)
        await s.save_prediction("D1", "BEARISH", 60.0)

        preds = await s.get_unresolved_predictions()
        assert len(preds) == 2
        await s.close()

    @pytest.mark.asyncio
    async def test_resolve_prediction(self, temp_db_path):
        s = Storage(temp_db_path)
        pid = await s.save_prediction("H1", "BULLISH", 75.0)
        await s.resolve_prediction(pid, "BULLISH", 1.0)

        preds = await s.get_unresolved_predictions()
        assert len(preds) == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_accuracy_stats(self, temp_db_path):
        s = Storage(temp_db_path)
        p1 = await s.save_prediction("H1", "BULLISH", 75.0)
        p2 = await s.save_prediction("H1", "BEARISH", 60.0)
        await s.resolve_prediction(p1, "BULLISH", 1.0)
        await s.resolve_prediction(p2, "BULLISH", 0.0)

        stats = await s.get_accuracy_stats(30)
        assert stats["total"] == 2
        assert stats["correct"] == 1
        assert stats["accuracy"] == 50.0
        await s.close()

    @pytest.mark.asyncio
    async def test_no_predictions_stats(self, temp_db_path):
        s = Storage(temp_db_path)
        stats = await s.get_accuracy_stats(30)
        assert stats["total"] == 0
        await s.close()


class TestAlerts:
    """Test alert CRUD."""

    @pytest.mark.asyncio
    async def test_add_and_get_alerts(self, temp_db_path):
        s = Storage(temp_db_path)
        aid = await s.add_alert("above", 1.0900, 12345)
        assert aid > 0

        alerts = await s.get_active_alerts()
        assert len(alerts) == 1
        assert alerts[0]["condition"] == "above"
        await s.close()

    @pytest.mark.asyncio
    async def test_trigger_alert(self, temp_db_path):
        s = Storage(temp_db_path)
        aid = await s.add_alert("above", 1.0900, 12345)
        await s.trigger_alert(aid)

        alerts = await s.get_active_alerts()
        assert len(alerts) == 0
        await s.close()


class TestMemory:
    """Test key-value memory store."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.set_memory("key1", "value1")
        assert await s.get_memory("key1") == "value1"
        await s.close()

    @pytest.mark.asyncio
    async def test_overwrite(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.set_memory("key1", "old")
        await s.set_memory("key1", "new")
        assert await s.get_memory("key1") == "new"
        await s.close()

    @pytest.mark.asyncio
    async def test_missing_key(self, temp_db_path):
        s = Storage(temp_db_path)
        assert await s.get_memory("nonexistent") is None
        await s.close()

    @pytest.mark.asyncio
    async def test_json_value(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.set_memory("data", {"foo": "bar"})
        result = await s.get_memory("data")
        assert '"foo"' in result
        await s.close()


class TestMarketNotes:
    """Test market notes."""

    @pytest.mark.asyncio
    async def test_add_and_retrieve(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.add_note("analysis", "EUR/USD looking bullish")
        notes = await s.get_recent_notes("analysis")
        assert len(notes) == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_filter_by_category(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.add_note("analysis", "Note 1")
        await s.add_note("news", "Note 2")
        assert len(await s.get_recent_notes("analysis")) == 1
        assert len(await s.get_recent_notes()) == 2
        await s.close()


class TestTradingSignals:
    """Test trading signal CRUD."""

    @pytest.mark.asyncio
    async def test_save_signal(self, temp_db_path):
        s = Storage(temp_db_path)
        sid = await s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1",
                            reasoning="Test signal", risk_reward_ratio=2.0)
        assert sid > 0
        await s.close()

    @pytest.mark.asyncio
    async def test_get_signals(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1")
        await s.save_signal("SELL", 1.0900, 1.0930, 1.0840, 60.0, "H4")

        all_signals = await s.get_signals()
        assert len(all_signals) == 2
        await s.close()

    @pytest.mark.asyncio
    async def test_filter_by_status(self, temp_db_path):
        s = Storage(temp_db_path)
        sid = await s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1")
        await s.update_signal_status(sid, "closed", pnl_pips=30.0)

        pending = await s.get_signals(status="pending")
        closed = await s.get_signals(status="closed")
        assert len(pending) == 0
        assert len(closed) == 1
        assert closed[0]["pnl_pips"] == 30.0
        await s.close()

    @pytest.mark.asyncio
    async def test_closed_has_timestamp(self, temp_db_path):
        s = Storage(temp_db_path)
        sid = await s.save_signal("BUY", 1.0850, 1.0820, 1.0910, 75.0, "H1")
        await s.update_signal_status(sid, "closed")
        closed = await s.get_signals(status="closed")
        assert closed[0]["closed_at"] is not None
        await s.close()


class TestNewsEvents:
    """Test news event storage."""

    @pytest.mark.asyncio
    async def test_save_news(self, temp_db_path):
        s = Storage(temp_db_path)
        nid = await s.save_news_event(
            title="ECB raises rates",
            source="reuters",
            impact_score=8.5,
            sentiment="bullish",
            currency_impact="EUR",
        )
        assert nid > 0
        await s.close()

    @pytest.mark.asyncio
    async def test_get_recent_news(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_news_event("News 1", "brave", impact_score=5.0)
        await s.save_news_event("News 2", "reuters", impact_score=8.0)
        await s.save_news_event("News 3", "twitter", impact_score=2.0)

        all_news = await s.get_recent_news()
        assert len(all_news) == 3

        high_impact = await s.get_recent_news(min_impact=6.0)
        assert len(high_impact) == 1
        await s.close()


class TestPerformanceMetrics:
    """Test performance metrics storage."""

    @pytest.mark.asyncio
    async def test_save_metrics(self, temp_db_path):
        s = Storage(temp_db_path)
        mid = await s.save_performance_metric(
            period="daily",
            total_signals=10,
            winning_signals=7,
            win_rate=70.0,
            total_pnl_pips=150.0,
            sharpe_ratio=1.5,
        )
        assert mid > 0
        await s.close()

    @pytest.mark.asyncio
    async def test_get_latest(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_performance_metric("daily", total_signals=5, win_rate=60.0)
        await s.save_performance_metric("daily", total_signals=10, win_rate=70.0)

        latest = await s.get_latest_metrics("daily")
        assert latest is not None
        assert latest["win_rate"] == 70.0
        await s.close()

    @pytest.mark.asyncio
    async def test_no_metrics(self, temp_db_path):
        s = Storage(temp_db_path)
        assert await s.get_latest_metrics("daily") is None
        await s.close()


class TestUserPreferences:
    """Test user preferences storage."""

    @pytest.mark.asyncio
    async def test_save_preferences(self, temp_db_path):
        s = Storage(temp_db_path)
        pid = await s.save_user_preferences(12345, risk_tolerance="high")
        assert pid is not None
        await s.close()

    @pytest.mark.asyncio
    async def test_get_preferences(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_user_preferences(12345, risk_tolerance="high", language="ar")
        prefs = await s.get_user_preferences(12345)
        assert prefs is not None
        assert prefs["risk_tolerance"] == "high"
        assert prefs["language"] == "ar"
        await s.close()

    @pytest.mark.asyncio
    async def test_upsert_preferences(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_user_preferences(12345, risk_tolerance="low")
        await s.save_user_preferences(12345, risk_tolerance="high")
        prefs = await s.get_user_preferences(12345)
        assert prefs["risk_tolerance"] == "high"
        await s.close()

    @pytest.mark.asyncio
    async def test_missing_user(self, temp_db_path):
        s = Storage(temp_db_path)
        assert await s.get_user_preferences(99999) is None
        await s.close()

    @pytest.mark.asyncio
    async def test_defaults(self, temp_db_path):
        s = Storage(temp_db_path)
        await s.save_user_preferences(12345)
        prefs = await s.get_user_preferences(12345)
        assert prefs["preferred_timeframe"] == "H1"
        assert prefs["alert_min_confidence"] == 60.0
        assert prefs["daily_report_hour"] == 8
        assert prefs["compact_mode"] == 0
        await s.close()
