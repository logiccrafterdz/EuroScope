"""
Phase 5 Verification Test — EuroScope
Verifies Smart Briefings, Confidence Filtering, and Alert Management.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from euroscope.bot.notification_manager import NotificationManager
from euroscope.data.storage import Storage
from euroscope.brain.orchestrator import Orchestrator
from euroscope.skills.base import SkillResult

@pytest.mark.asyncio
async def test_morning_briefing_content():
    # 1. Setup
    storage = MagicMock(spec=Storage)
    nm = NotificationManager(storage)
    bot = AsyncMock()
    nm.set_bot(bot)
    
    orch = MagicMock(spec=Orchestrator)
    nm.set_orchestrator(orch)
    
    # 2. Mock Skills
    orch.run_skill.side_effect = [
        # market_data.get_price
        SkillResult(success=True, data={"price": 1.0850, "bid": 1.0849, "ask": 1.0851}),
        # fundamental_analysis.get_news
        SkillResult(success=True, data=[{"title": "Euro Gains on ECB Talk"}])
    ]
    
    # 3. Trigger Job
    job = MagicMock()
    job.data = {"chat_id": 12345}
    context = MagicMock()
    context.job = job
    
    await nm._daily_report_job(context)
    
    # 4. Verify output
    args, kwargs = bot.send_message.call_args
    msg = kwargs['text']
    assert "Morning Briefing" in msg
    assert "1.085" in msg
    assert "Euro Gains" in msg

@pytest.mark.asyncio
async def test_confidence_filtering():
    # 1. Setup
    storage = MagicMock(spec=Storage)
    nm = NotificationManager(storage)
    bot = AsyncMock()
    nm.set_bot(bot)
    
    # 2. Mock User Prefs (threshold = 80%)
    storage.get_user_preferences.return_value = {"alert_min_confidence": 80.0, "alert_on_signals": 1}
    
    # 3. Test Low Confidence Signal (should skip)
    low_sig = {"id": 1, "direction": "BUY", "confidence": 65.0, "entry_price": 1.08, "stop_loss": 1.07, "take_profit": 1.09, "timeframe": "H1"}
    await nm.notify_new_signal(12345, low_sig)
    assert not bot.send_message.called
    
    # 4. Test High Confidence Signal (should send)
    high_sig = {"id": 2, "direction": "SELL", "confidence": 85.0, "entry_price": 1.08, "stop_loss": 1.09, "take_profit": 1.07, "timeframe": "H1"}
    await nm.notify_new_signal(12345, high_sig)
    assert bot.send_message.called
    assert "New Trading Signal" in bot.send_message.call_args[1]['text']

@pytest.mark.asyncio
async def test_alert_storage_ops(tmp_path):
    # 1. Real storage (file-based) for logic check
    storage = Storage(str(tmp_path / "test.db"))
    chat_id = 999
    
    # 2. Add alerts
    await storage.add_alert("above", 1.1000, chat_id)
    await storage.add_alert("below", 1.0500, chat_id)
    
    # 3. Verify get_user_alerts
    alerts = await storage.get_user_alerts(chat_id)
    assert len(alerts) == 2
    assert alerts[0]['target_value'] == 1.1000
    
    # 4. Delete one
    await storage.delete_alert(alerts[0]['id'])
    remaining = await storage.get_user_alerts(chat_id)
    assert len(remaining) == 1
    assert remaining[0]['target_value'] == 1.0500

if __name__ == "__main__":
    asyncio.run(test_morning_briefing_content())
