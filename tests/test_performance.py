"""
Tests for Phase 5: Performance optimizations (DifficultyRouter, PromptCompressor, DB indexes).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from euroscope.brain.performance import (
    classify_difficulty,
    DifficultyRouter,
    PromptCompressor,
    COMPLEX_INDICATORS,
    SIMPLE_INDICATORS,
)


# ── classify_difficulty Tests ─────────────────────────────────

class TestClassifyDifficulty:
    def test_empty_messages(self):
        assert classify_difficulty([]) == "simple"

    def test_empty_content(self):
        assert classify_difficulty([{"role": "user", "content": ""}]) == "simple"

    def test_simple_price_query(self):
        msgs = [{"role": "user", "content": "What is the current price of EUR/USD?"}]
        assert classify_difficulty(msgs) == "simple"

    def test_simple_status_query(self):
        msgs = [{"role": "user", "content": "Show me the status summary"}]
        assert classify_difficulty(msgs) == "simple"

    def test_simple_list_query(self):
        msgs = [{"role": "user", "content": "List all open trades"}]
        assert classify_difficulty(msgs) == "simple"

    def test_complex_debate(self):
        msgs = [{"role": "user", "content": "Run the investment debate and argue both sides of the conflict"}]
        assert classify_difficulty(msgs) == "complex"

    def test_complex_risk_assessment(self):
        msgs = [{"role": "user", "content": "Perform a risk assessment and justify the position sizing"}]
        assert classify_difficulty(msgs) == "complex"

    def test_complex_chain_of_thought(self):
        msgs = [
            {"role": "system", "content": "You are a trading expert."},
            {"role": "user", "content": "Analyze the interaction between technical and fundamental signals"},
            {"role": "assistant", "content": "Here is my analysis..."},
            {"role": "user", "content": "Now explain why the conflict matters"},
            {"role": "assistant", "content": "The conflict is significant because..."},
            {"role": "user", "content": "And what about the reasoning behind it?"},
        ]
        assert classify_difficulty(msgs) == "complex"

    def test_medium_mixed_signals(self):
        msgs = [
            {"role": "system", "content": "You are a trading expert."},
            {"role": "user", "content": "Analyze the current market conditions and provide a recommendation"},
            {"role": "assistant", "content": "Based on the data..."},
            {"role": "user", "content": "Now explain why this conflicts with our current position"},
            {"role": "assistant", "content": "The conflict arises because..."},
            {"role": "user", "content": "What is the reasoning behind this?"},
        ]
        assert classify_difficulty(msgs) == "complex"

    def test_many_messages_push_to_complex(self):
        msgs = [{"role": "user", "content": f"Message {i} about the debate"} for i in range(10)]
        assert classify_difficulty(msgs) == "complex"

    def test_long_system_prompt(self):
        msgs = [
            {"role": "system", "content": "x" * 6000},
            {"role": "user", "content": "hello"},
        ]
        assert classify_difficulty(msgs) == "complex"

    def test_short_context_simple(self):
        msgs = [
            {"role": "system", "content": "You are a trading assistant."},
            {"role": "user", "content": "What is the price?"},
        ]
        assert classify_difficulty(msgs) == "simple"


# ── DifficultyRouter Tests ────────────────────────────────────

class TestDifficultyRouter:
    @pytest.fixture
    def mock_router(self):
        router = MagicMock()
        router.providers = [MagicMock(name="primary")]
        router._call_count = 0
        router._last_provider = ""
        router._call_provider = AsyncMock(return_value="OK")
        router.chat = AsyncMock(return_value="full chain result")
        router.chat_json = AsyncMock(return_value={"result": "ok"})
        return router

    @pytest.mark.asyncio
    async def test_simple_query_fast_path(self, mock_router):
        router = DifficultyRouter(mock_router)
        msgs = [{"role": "user", "content": "What is the price?"}]
        result = await router.chat(msgs)
        assert result == "OK"
        mock_router._call_provider.assert_called_once()

    @pytest.mark.asyncio
    async def test_complex_query_full_chain(self, mock_router):
        router = DifficultyRouter(mock_router)
        msgs = [{"role": "user", "content": "Run the debate and argue the conflict"}]
        result = await router.chat(msgs)
        assert result == "full chain result"
        mock_router.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_provider(self, mock_router):
        router = DifficultyRouter(mock_router)
        msgs = [{"role": "user", "content": "price"}]
        await router.chat(msgs, force_provider="fallback")
        mock_router.chat.assert_called_once_with(msgs, temperature=None, force_provider="fallback")

    @pytest.mark.asyncio
    async def test_chat_json_delegates(self, mock_router):
        router = DifficultyRouter(mock_router)
        msgs = [{"role": "user", "content": "status"}]
        result = await router.chat_json(msgs)
        assert result == {"result": "ok"}

    def test_stats_tracking(self, mock_router):
        router = DifficultyRouter(mock_router)
        router._stats = {"simple": 5, "medium": 3, "complex": 2}
        stats = router.stats
        assert stats["total"] == 10
        assert stats["simple_pct"] == 50.0


# ── PromptCompressor Tests ────────────────────────────────────

class TestPromptCompressor:
    def test_no_compression_needed(self):
        compressor = PromptCompressor(max_tokens=12000)
        msgs = [
            {"role": "system", "content": "You are a trading bot."},
            {"role": "user", "content": "What is the price?"},
        ]
        result = compressor.compress(msgs)
        assert len(result) == 2

    def test_compression_truncates_old(self):
        compressor = PromptCompressor(max_tokens=500, reserve_tokens=100)
        msgs = [
            {"role": "system", "content": "System prompt. " * 100},
        ] + [
            {"role": "user", "content": f"User message {i} " * 50}
            for i in range(20)
        ]
        result = compressor.compress(msgs, max_tokens=500)
        assert len(result) < len(msgs)

    def test_system_prompt_preserved(self):
        compressor = PromptCompressor(max_tokens=500)
        msgs = [
            {"role": "system", "content": "Important system instructions."},
            {"role": "user", "content": "x " * 5000},
        ]
        result = compressor.compress(msgs, max_tokens=500)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) >= 1
        assert "Important system instructions" in system_msgs[0]["content"]

    def test_estimate_tokens(self):
        compressor = PromptCompressor()
        msgs = [{"role": "user", "content": "a" * 100}]
        tokens = compressor.estimate_tokens(msgs)
        assert tokens == 25  # 100 chars / 4 chars_per_token

    def test_needs_compression(self):
        compressor = PromptCompressor()
        msgs = [{"role": "user", "content": "a" * 50000}]
        assert compressor.needs_compression(msgs, max_tokens=1000) is True
        assert compressor.needs_compression(msgs, max_tokens=20000) is False

    def test_empty_messages(self):
        compressor = PromptCompressor()
        result = compressor.compress([])
        assert result == []

    def test_recent_messages_kept(self):
        compressor = PromptCompressor(max_tokens=200)
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old " * 200},
            {"role": "assistant", "content": "reply " * 200},
            {"role": "user", "content": "recent question"},
        ]
        result = compressor.compress(msgs, max_tokens=200)
        # Last message should be in result
        contents = [m.get("content", "") for m in result]
        assert any("recent question" in c for c in contents)


# ── DB Index Tests ────────────────────────────────────────────

class TestDatabaseIndexes:
    def test_indexes_created_on_init(self, tmp_path):
        from euroscope.data.storage import Storage
        db_path = str(tmp_path / "test_index.db")
        storage = Storage(db_path=db_path)

        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_signals_status" in indexes
        assert "idx_signals_created" in indexes
        assert "idx_signals_status_created" in indexes
        assert "idx_journal_status" in indexes
        assert "idx_journal_timestamp" in indexes
        assert "idx_journal_status_timestamp" in indexes
        assert "idx_journal_strategy" in indexes
        assert "idx_predictions_resolved" in indexes
        assert "idx_news_impact" in indexes
        assert "idx_alerts_triggered" in indexes
        assert "idx_performance_period" in indexes
        assert "idx_learning_trade" in indexes

    def test_indexes_idempotent(self, tmp_path):
        from euroscope.data.storage import Storage
        db_path = str(tmp_path / "test_idempotent.db")
        Storage(db_path=db_path)
        Storage(db_path=db_path)  # Second init should not fail

        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert len(indexes) >= 14  # At least our 14 indexes
