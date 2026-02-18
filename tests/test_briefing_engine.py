import pytest
import asyncio
from unittest.mock import MagicMock, patch
from euroscope.brain.briefing_engine import BriefingEngine
from euroscope.data.storage import Storage

@pytest.fixture
def mock_storage():
    storage = MagicMock(spec=Storage)
    storage.get_recent_news.return_value = [
        {"title": "ECB Rate Decision", "source": "Reuters", "sentiment": "bullish", "impact": 0.9}
    ]
    storage.get_recent_notes.return_value = []
    storage.get_recent_learning_insights.return_value = [
        {"trade_id": "123", "recommendations": ["Avoid high spreads"]}
    ]
    storage.get_trade_journal_stats.return_value = {
        "win_rate": 65,
        "total": 10,
        "total_pnl": 120.5
    }
    return storage

@pytest.mark.asyncio
async def test_generate_briefing(mock_storage):
    engine = BriefingEngine(storage=mock_storage)
    
    # Mock HealthMonitor
    with patch("euroscope.brain.briefing_engine.HealthMonitor") as MockHealth:
        mock_health_instance = MockHealth.return_value
        
        from unittest.mock import AsyncMock
        mock_health_instance.full_check_async = AsyncMock(return_value=MagicMock(components=[MagicMock(healthy=True)]))
        
        report = await engine.generate_briefing()
        
        assert "EuroScope Daily Proactive Plan" in report
        assert "ECB Rate Decision" in report
        assert "Lesson from trade #123" in report
        assert "Win Rate: 65%" in report
        assert "P/L: +120.5 pips" in report
        assert "Operational" in report
