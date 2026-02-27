"""
Tests for euroscope.brain.memory module.
"""

import os
import tempfile

import pytest

from euroscope.data.storage import Storage
from euroscope.brain.memory import Memory


@pytest.fixture
def memory_instance():
    """Create a Memory instance with a temporary database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = Storage(path)
    mem = Memory(storage)
    yield mem
    try:
        if os.path.exists(path):
            os.unlink(path)
    except PermissionError:
        pass  # Windows may still lock the file


class TestRecordPrediction:
    """Test prediction recording."""

    @pytest.mark.asyncio
    async def test_record_returns_id(self, memory_instance):
        pid = await memory_instance.record_prediction("BULLISH", 75.0, "Test reasoning")
        assert pid is not None
        assert pid > 0

    @pytest.mark.asyncio
    async def test_record_with_target(self, memory_instance):
        pid = await memory_instance.record_prediction(
            "BEARISH", 60.0, "Bearish divergence",
            target_price=1.0800, timeframe="H4"
        )
        assert pid > 0


class TestEvaluatePrediction:
    """Test prediction evaluation."""

    @pytest.mark.asyncio
    async def test_correct_prediction(self, memory_instance):
        pid = await memory_instance.record_prediction("BULLISH", 75.0, "Test")
        await memory_instance.evaluate_prediction(pid, "BULLISH", 1.0850)
        # After evaluation, prediction should be resolved
        preds = await memory_instance.storage.get_unresolved_predictions()
        assert len(preds) == 0

    @pytest.mark.asyncio
    async def test_wrong_prediction(self, memory_instance):
        pid = await memory_instance.record_prediction("BULLISH", 75.0, "Test")
        await memory_instance.evaluate_prediction(pid, "BEARISH", 1.0750)
        preds = await memory_instance.storage.get_unresolved_predictions()
        assert len(preds) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_prediction(self, memory_instance):
        # Should not crash
        await memory_instance.evaluate_prediction(9999, "BULLISH", 1.0850)


class TestAccuracyReport:
    """Test accuracy report generation."""

    @pytest.mark.asyncio
    async def test_no_predictions(self, memory_instance):
        report = await memory_instance.get_accuracy_report()
        assert "No predictions" in report or "no" in report.lower()

    @pytest.mark.asyncio
    async def test_with_predictions(self, memory_instance):
        p1 = await memory_instance.record_prediction("BULLISH", 75.0, "Test 1")
        p2 = await memory_instance.record_prediction("BEARISH", 60.0, "Test 2")
        await memory_instance.evaluate_prediction(p1, "BULLISH", 1.0850)
        await memory_instance.evaluate_prediction(p2, "BULLISH", 1.0850)

        report = await memory_instance.get_accuracy_report()
        assert "Accuracy" in report


class TestLearningContext:
    """Test learning context generation."""

    @pytest.mark.asyncio
    async def test_insufficient_history(self, memory_instance):
        context = await memory_instance.get_learning_context()
        assert "No sufficient" in context

    @pytest.mark.asyncio
    async def test_with_history(self, memory_instance):
        for i in range(5):
            pid = await memory_instance.record_prediction("BULLISH", 70.0, f"Test {i}")
            await memory_instance.evaluate_prediction(pid, "BULLISH", 1.0850)

        context = await memory_instance.get_learning_context()
        assert "accuracy" in context.lower() or "prediction" in context.lower()


class TestInsights:
    """Test insight saving."""

    @pytest.mark.asyncio
    async def test_save_insight(self, memory_instance):
        await memory_instance.save_insight("RSI divergence near support is a strong signal")
        insights = await memory_instance.storage.get_memory("learning_insights")
        assert "RSI divergence" in insights

    @pytest.mark.asyncio
    async def test_multiple_insights(self, memory_instance):
        for i in range(7):
            await memory_instance.save_insight(f"Insight {i}")

        insights = await memory_instance.storage.get_memory("learning_insights")
        # Should keep only last 5
        assert "Insight 6" in insights
        assert "Insight 0" not in insights
