"""
Tests for Phase 4: Production Excellence modules.
- VoiceBriefingEngine
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, UTC


class TestVoiceBriefingEngine:
    """Test voice briefing engine."""

    def _make_engine(self, orchestrator=None, storage=None):
        from euroscope.analytics.voice_briefing import VoiceBriefingEngine
        return VoiceBriefingEngine(orchestrator=orchestrator, storage=storage)

    @pytest.mark.asyncio
    async def test_generate_briefing_no_sources(self):
        """Briefing with no orchestrator/storage should still work."""
        engine = self._make_engine()
        briefing = await engine.generate_briefing()
        assert briefing is not None
        assert briefing.summary == "No market data available for briefing."
        assert briefing.urgency == "normal"

    @pytest.mark.asyncio
    async def test_generate_briefing_with_storage(self):
        """Briefing with mocked storage should include signal section."""
        storage = MagicMock()
        storage.get_signals = AsyncMock(return_value=[
            {"direction": "BUY", "entry_price": 1.085}
        ])
        storage.get_trade_journal_stats = AsyncMock(return_value={
            "total": 10, "win_rate": 65.0, "total_pnl": 42.3,
        })
        storage.get_active_alerts = AsyncMock(return_value=[])

        engine = self._make_engine(storage=storage)
        briefing = await engine.generate_briefing()
        titles = [s.title for s in briefing.sections]
        assert "Trading Signals" in titles
        assert "Performance" in titles

    @pytest.mark.asyncio
    async def test_risk_alerts_urgency(self):
        """Briefing with many alerts should have 'alert' urgency."""
        storage = MagicMock()
        storage.get_signals = AsyncMock(return_value=[])
        storage.get_trade_journal_stats = AsyncMock(return_value={"total": 0})
        storage.get_active_alerts = AsyncMock(return_value=[
            {"price": 1.08}, {"price": 1.09}, {"price": 1.10}
        ])

        engine = self._make_engine(storage=storage)
        briefing = await engine.generate_briefing()
        assert briefing.urgency == "alert"

    def test_format_for_telegram(self):
        from euroscope.analytics.voice_briefing import (
            VoiceBriefingEngine, MarketBriefing, BriefingSection
        )
        engine = self._make_engine()
        briefing = MarketBriefing(
            summary="EUR/USD at 1.08500",
            sections=[
                BriefingSection(title="Current Price", content="1.08500", priority=1),
            ],
        )
        text = engine.format_for_telegram(briefing)
        assert "Market Briefing" in text
        assert "Current Price" in text
        assert "1.08500" in text

    def test_format_for_api(self):
        from euroscope.analytics.voice_briefing import (
            VoiceBriefingEngine, MarketBriefing, BriefingSection
        )
        engine = self._make_engine()
        briefing = MarketBriefing(
            summary="Test summary",
            sections=[
                BriefingSection(title="Price", content="1.085", priority=1),
            ],
        )
        data = engine.format_for_api(briefing)
        assert data["summary"] == "Test summary"
        assert data["urgency"] == "normal"
        assert len(data["sections"]) == 1
        assert "text_for_tts" in data

    def test_to_text(self):
        from euroscope.analytics.voice_briefing import MarketBriefing, BriefingSection
        briefing = MarketBriefing(
            summary="Summary",
            sections=[
                BriefingSection(title="A", content="content A", priority=2),
                BriefingSection(title="B", content="content B", priority=1),
            ],
        )
        text = briefing.to_text()
        assert "Summary" in text
        assert "content A" in text
        # Priority 1 should come first
        assert text.index("content B") < text.index("content A")

    @pytest.mark.asyncio
    async def test_generate_audio_returns_none(self):
        """Audio generation placeholder returns None."""
        from euroscope.analytics.voice_briefing import MarketBriefing
        engine = self._make_engine()
        briefing = MarketBriefing(summary="Test")
        result = await engine.generate_audio(briefing)
        assert result is None

    def test_briefing_section_defaults(self):
        from euroscope.analytics.voice_briefing import BriefingSection
        s = BriefingSection(title="Test", content="Content")
        assert s.priority == 5

    @pytest.mark.asyncio
    async def test_performance_section_excluded_when_no_trades(self):
        """Performance section should not appear when total is 0."""
        storage = MagicMock()
        storage.get_signals = AsyncMock(return_value=[])
        storage.get_trade_journal_stats = AsyncMock(return_value={"total": 0})
        storage.get_active_alerts = AsyncMock(return_value=[])

        engine = self._make_engine(storage=storage)
        briefing = await engine.generate_briefing()
        titles = [s.title for s in briefing.sections]
        assert "Performance" not in titles
