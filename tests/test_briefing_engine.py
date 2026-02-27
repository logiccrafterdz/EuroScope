import pytest
import asyncio
from unittest.mock import MagicMock, patch
from euroscope.brain.briefing_engine import BriefingEngine
from euroscope.data.storage import Storage

from unittest.mock import AsyncMock

@pytest.fixture
def mock_storage():
    storage = MagicMock(spec=Storage)
    storage.get_recent_news = AsyncMock(return_value=[
        {"title": "ECB Rate Decision", "source": "Reuters", "sentiment": "bullish", "impact": 0.9}
    ])
    storage.get_recent_notes = AsyncMock(return_value=[])
    storage.get_recent_learning_insights = AsyncMock(return_value=[
        {"trade_id": "123", "recommendations": ["Avoid high spreads"]}
    ])
    storage.get_trade_journal_stats = AsyncMock(return_value={
        "win_rate": 65,
        "total": 10,
        "total_pnl": 120.5
    })
    # Add mock for get_trade_journal_for_date
    storage.get_trade_journal_for_date = AsyncMock(return_value=[
        {"id": "T1", "pips": 15.0},
        {"id": "T2", "pips": -5.0}
    ])
    return storage

@pytest.mark.asyncio
async def test_generate_briefing(mock_storage):
    engine = BriefingEngine(storage=mock_storage)
    
    # Mock HealthMonitor - though not used in the new generate_briefing, keeping for compatibility if it was used
    with patch("euroscope.brain.briefing_engine.HealthMonitor", autospec=True):
        report = await engine.generate_briefing()
        
        assert "EuroScope Daily Intelligence Briefing" in report
        assert "ECB Rate Decision" in report
        assert "Key Lesson" in report
        assert "Win Rate: 50%" in report # 1 win out of 2 trades in mock_journal_for_date
        assert "P/L: +10.0p" in report # 15 - 5 = 10
        assert "CPI" in report
