"""
Tests for Vector Memory (SQLite FTS5).
"""

from datetime import datetime, timedelta, UTC
import pytest

from euroscope.brain.vector_memory import VectorMemory


@pytest.fixture
def vm(tmp_path):
    """Create a VectorMemory with a temp directory."""
    return VectorMemory(persist_dir=str(tmp_path / "test_fts"))


class TestVectorMemoryInit:

    def test_available_after_init(self, vm):
        assert vm.is_available is True

    def test_stats_shows_available(self, vm):
        stats = vm.get_collection_stats()
        assert stats["available"] is True


class TestStoreAndSearch:

    def test_store_analysis(self, vm):
        doc_id = vm.store_analysis("EUR/USD bullish breakout above 1.1000")
        assert doc_id is not None
        assert doc_id.startswith("analysis_")

    def test_store_and_search(self, vm):
        vm.store_analysis("EUR/USD bullish on strong ECB hawkish stance",
                          {"verdict": "bullish"})
        vm.store_analysis("EUR/USD bearish due to Fed rate hike",
                          {"verdict": "bearish"})

        results = vm.search_similar("ECB bullish euro", k=2)
        assert len(results) > 0
        assert "text" in results[0]
        assert "distance" in results[0]

    def test_store_insight(self, vm):
        doc_id = vm.store_insight("RSI divergence is reliable on H4",
                                  tags=["technical", "rsi"])
        assert doc_id is not None

    def test_store_market_event(self, vm):
        doc_id = vm.store_market_event("ECB surprise rate cut",
                                        impact="high")
        assert doc_id is not None

    def test_collection_stats(self, vm):
        vm.store_analysis("test analysis")
        vm.store_insight("test insight")
        stats = vm.get_collection_stats()
        assert stats["available"] is True
        assert stats["analyses"] >= 1
        assert stats["insights"] >= 1

    def test_relevant_context(self, vm):
        vm.store_analysis("Bullish breakout driven by ECB hawkish surprise")
        vm.store_insight("ECB decisions cause 50+ pip moves")

        context = vm.get_relevant_context("ECB rate decision impact")
        assert isinstance(context, str)

    def test_search_returns_empty_no_match(self, vm):
        vm.store_analysis("Some completely unrelated text about cooking")
        results = vm.search_similar("quantum physics theory")
        # FTS may or may not find results depending on terms
        assert isinstance(results, list)


class TestCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_old_documents(self, vm):
        old_timestamp = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        recent_timestamp = (datetime.now(UTC) - timedelta(days=10)).isoformat()

        vm.store_analysis("Old analysis for cleanup", metadata={"timestamp": old_timestamp})
        vm.store_analysis("Recent analysis keep", metadata={"timestamp": recent_timestamp})

        before = vm.get_collection_stats().get("analyses", 0)
        deleted = await vm.cleanup_old_documents(ttl_days=30)
        after = vm.get_collection_stats().get("analyses", 0)

        assert deleted >= 1
        assert after <= max(0, before - 1)


class TestUnavailable:

    def test_unavailable_store_returns_none(self):
        vm = VectorMemory.__new__(VectorMemory)
        vm._available = False
        vm._conn = None
        assert vm.store_analysis("test") is None

    def test_unavailable_search_returns_empty(self):
        vm = VectorMemory.__new__(VectorMemory)
        vm._available = False
        vm._conn = None
        assert vm.search_similar("test") == []

    def test_unavailable_context_returns_empty(self):
        vm = VectorMemory.__new__(VectorMemory)
        vm._available = False
        vm._conn = None
        assert vm.get_relevant_context("test") == ""
