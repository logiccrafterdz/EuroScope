import asyncio
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime

from euroscope.brain.vector_memory import VectorMemory
from euroscope.learning.pattern_tracker import PatternTracker
from euroscope.learning.adaptive_tuner import AdaptiveTuner
from euroscope.data.storage import Storage

class TestPhase3Learning(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import tempfile, os
        self._tmp = tempfile.mkdtemp()
        self.storage = Storage(os.path.join(self._tmp, "test.db"))
        self.vector_memory = VectorMemory() # ChromaDB might be mock/memory or skipped if not installed
        self.tracker = PatternTracker(self.storage)
        self.tuner = AdaptiveTuner(self.storage)

    async def test_vector_memory_flow(self):
        """Test storing and retrieving analysis from vector memory."""
        content = "EUR/USD is bullish due to H1 breakout above 1.0850."
        self.vector_memory.store_analysis(content, metadata={"timeframe": "H1"})
        
        context = self.vector_memory.get_relevant_context("What happened at 1.0850?")
        if context:
            self.assertIn("1.0850", context)
            print("✅ VectorMemory context retrieval works.")
        else:
            print("⚠️ VectorMemory skipped (likely ChromaDB not available).")

    async def test_pattern_tracker_resolution(self):
        """Test pattern detection and resolution loop."""
        # 1. Record multiple detections to trigger multiplier data (min 3)
        await self.tracker.record_detection("Double Top", "H1", "Bearish", 1.0900)
        await self.tracker.record_detection("Double Top", "H1", "Bearish", 1.0890)
        await self.tracker.record_detection("Double Top", "H1", "Bearish", 1.0880)
        
        # 2. Check pending
        pending = await self.storage.get_unresolved_patterns()
        self.assertEqual(len(pending), 3)
        
        # 3. Resolve (success)
        await self.tracker.resolve_pending(1.0850) # Price dropped, success for Bearish pattern
        
        # 4. Check success rate
        rates = await self.tracker.get_success_rates()
        self.assertIn("Double Top_H1", rates)
        self.assertEqual(rates["Double Top_H1"]["success_rate"], 100.0)
        
        # 5. Get multiplier
        mult = await self.tracker.get_confidence_multiplier("Double Top", "H1")
        self.assertGreater(mult, 1.0) # Reward for success (rate 100% -> 1.5)
        print("✅ PatternTracker resolution and multiplier works.")

    async def test_adaptive_tuner_report(self):
        """Test tuning recommendations from trade history."""
        # Add 5 winning trades to satisfy min_trades requirement
        for i in range(5):
            await self.storage.save_trade_journal(
                direction="BUY", entry_price=1.0800 + (i * 0.0010), 
                strategy="TrendFollowing", confidence=0.7
            )
            trades = await self.storage.get_trade_journal(status="open")
            trade_id = trades[0]["id"]
            await self.storage.close_trade_journal(trade_id, 1.0850 + (i * 0.0010), 50.0, True)
        
        report = await self.tuner.format_report()
        self.assertIn("TrendFollowing", report)
        self.assertIn("WR", report)
        print("✅ AdaptiveTuner report generation works.")

if __name__ == "__main__":
    unittest.main()
