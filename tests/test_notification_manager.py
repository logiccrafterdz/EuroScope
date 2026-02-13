"""
Tests for NotificationManager — alert filtering and structure.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from euroscope.data.storage import Storage
from euroscope.bot.notification_manager import NotificationManager


@pytest.fixture
def manager(tmp_path):
    db_path = str(tmp_path / "test_notif.db")
    storage = Storage(db_path)
    nm = NotificationManager(storage)
    nm.set_bot(AsyncMock())
    return nm


@pytest.fixture
def storage_only(tmp_path):
    db_path = str(tmp_path / "test_notif2.db")
    return Storage(db_path)


class TestSignalAlerts:

    @pytest.mark.asyncio
    async def test_notify_signal_sends_message(self, manager):
        result = {
            "id": 1, "direction": "BUY", "entry_price": 1.0900,
            "exit_price": 1.0940, "pnl_pips": 40.0, "is_win": True,
            "reason": "take_profit", "strategy": "trend_following",
        }
        await manager.notify_signal_closed(12345, result)
        manager._bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_skipped_when_alerts_off(self, manager):
        # Save prefs with signals disabled
        manager.storage.save_user_preferences(12345, alert_on_signals=0)

        result = {
            "id": 1, "direction": "BUY", "entry_price": 1.0900,
            "exit_price": 1.0940, "pnl_pips": 40.0, "is_win": True,
            "reason": "take_profit", "strategy": "manual",
        }
        await manager.notify_signal_closed(12345, result)
        manager._bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_bot_no_crash(self, storage_only):
        nm = NotificationManager(storage_only)
        # No bot set — should silently return
        result = {
            "id": 1, "direction": "SELL", "entry_price": 1.0900,
            "exit_price": 1.0870, "pnl_pips": 30.0, "is_win": True,
            "reason": "take_profit", "strategy": "manual",
        }
        await nm.notify_signal_closed(12345, result)  # No crash


class TestPriceAlerts:

    @pytest.mark.asyncio
    async def test_price_alert_triggered(self, manager):
        manager.storage.add_alert("above", 1.1000, chat_id=12345)
        await manager.check_price_alerts(1.1010)
        manager._bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_price_alert_not_triggered(self, manager):
        manager.storage.add_alert("above", 1.1000, chat_id=12345)
        await manager.check_price_alerts(1.0990)
        manager._bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_below_alert_triggered(self, manager):
        manager.storage.add_alert("below", 1.0900, chat_id=12345)
        await manager.check_price_alerts(1.0890)
        manager._bot.send_message.assert_called_once()


class TestNewsAlerts:

    @pytest.mark.asyncio
    async def test_high_impact_forwarded(self, manager):
        articles = [
            {"title": "ECB Hikes", "sentiment": "bearish",
             "sentiment_score": -0.8, "url": "https://example.com"},
        ]
        await manager.notify_high_impact_news(12345, articles)
        manager._bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_impact_skipped(self, manager):
        articles = [
            {"title": "Minor Update", "sentiment": "neutral",
             "sentiment_score": 0.1},
        ]
        await manager.notify_high_impact_news(12345, articles)
        manager._bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_news_skipped_when_disabled(self, manager):
        manager.storage.save_user_preferences(12345, alert_on_news=0)
        articles = [
            {"title": "Big News", "sentiment": "bullish",
             "sentiment_score": 0.9},
        ]
        await manager.notify_high_impact_news(12345, articles)
        manager._bot.send_message.assert_not_called()


class TestStats:

    def test_stats_with_bot(self, manager):
        stats = manager.get_notification_stats()
        assert stats["bot_connected"] is True

    def test_stats_no_bot(self, storage_only):
        nm = NotificationManager(storage_only)
        stats = nm.get_notification_stats()
        assert stats["bot_connected"] is False
