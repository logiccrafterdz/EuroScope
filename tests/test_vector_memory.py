"""
Tests for Vector Memory (ChromaDB).

Tests graceful fallback when ChromaDB is not installed.
"""

import pytest
from unittest.mock import patch

from euroscope.brain.vector_memory import VectorMemory


class TestVectorMemoryFallback:
    """Test behavior when ChromaDB is not installed."""

    @patch.dict("sys.modules", {"chromadb": None})
    def test_graceful_without_chromadb(self):
        vm = VectorMemory(persist_dir="/tmp/test_vm")
        assert vm.is_available is False

    @patch.dict("sys.modules", {"chromadb": None})
    def test_store_returns_none_without_chromadb(self):
        vm = VectorMemory(persist_dir="/tmp/test_vm")
        result = vm.store_analysis("test analysis")
        assert result is None

    @patch.dict("sys.modules", {"chromadb": None})
    def test_search_returns_empty_without_chromadb(self):
        vm = VectorMemory(persist_dir="/tmp/test_vm")
        result = vm.search_similar("query")
        assert result == []

    @patch.dict("sys.modules", {"chromadb": None})
    def test_context_returns_empty_without_chromadb(self):
        vm = VectorMemory(persist_dir="/tmp/test_vm")
        result = vm.get_relevant_context("current situation")
        assert result == ""

    @patch.dict("sys.modules", {"chromadb": None})
    def test_stats_shows_unavailable(self):
        vm = VectorMemory(persist_dir="/tmp/test_vm")
        stats = vm.get_collection_stats()
        assert stats["available"] is False


class TestVectorMemoryWithChromaDB:
    """Test actual ChromaDB operations (skipped if not installed)."""

    @pytest.fixture
    def vm(self, tmp_path):
        """Create a VectorMemory with a temp directory."""
        vm = VectorMemory(persist_dir=str(tmp_path / "test_chroma"))
        if not vm.is_available:
            pytest.skip("ChromaDB not installed")
        return vm

    def test_store_analysis(self, vm):
        doc_id = vm.store_analysis("EUR/USD bullish breakout above 1.1000")
        assert doc_id is not None
        assert doc_id.startswith("analysis_")

    def test_store_and_search(self, vm):
        vm.store_analysis("EUR/USD bullish on strong ECB hawkish stance",
                          {"verdict": "bullish"})
        vm.store_analysis("EUR/USD bearish due to Fed rate hike",
                          {"verdict": "bearish"})

        results = vm.search_similar("ECB policy bullish euro", k=2)
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
        vm.store_analysis("test")
        vm.store_insight("test insight")
        stats = vm.get_collection_stats()
        assert stats["available"] is True
        assert stats["analyses"] >= 1
        assert stats["insights"] >= 1

    def test_relevant_context(self, vm):
        vm.store_analysis("Bullish breakout driven by ECB hawkish surprise")
        vm.store_insight("ECB decisions cause 50+ pip moves")

        context = vm.get_relevant_context("ECB rate decision impact")
        # May or may not find results depending on embedding quality
        assert isinstance(context, str)
