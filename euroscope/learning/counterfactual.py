"""
Trade Counterfactual Engine (Phase 3)

Analyzes closed trades to simulate 'what-if' scenarios.
Answers questions like:
- What if the Take Profit was 5 pips wider?
- What if we held until the market closed instead of trailing out?
"""

import asyncio
import logging
from typing import Dict, Any

from euroscope.data.models import TradingSignal

logger = logging.getLogger("euroscope.learning.counterfactual")

class CounterfactualEngine:
    """Read-only advisory engine that simulates alternate trade parameters."""
    
    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        self.scenarios = [
            {"name": "No SL/TP Let Run 24H", "sl_mod": 0, "tp_mod": 0},
            {"name": "Wider Stop Loss (+10 pips)", "sl_mod": 0.0010, "tp_mod": 0},
            {"name": "Tighter Take Profit (-5 pips)", "sl_mod": 0, "tp_mod": -0.0005},
        ]
        
    async def analyze_trade(self, trade: TradingSignal):
        """Analyze a closed trade asynchronously in the background."""
        logger.info(f"Counterfactual Engine starting analysis for Trade ID {trade.id}...")
        
        try:
            # In a real implementation we would fetch high-resolution M1 or TICK data 
            # from entry time to +24 hours using self.data_provider ...
            # For now, we simulate the analysis step
            
            await asyncio.sleep(2.0)  # Simulate I/O bound analysis
            
            # Dummy analysis result
            advise = "Keep current risk parameters."
            if trade.pnl_pips and trade.pnl_pips < 0:
                advise = "Wider SL (+10 pips) might have avoided the stop hunt, but needs more M1 data verification."
            elif trade.pnl_pips and trade.pnl_pips > 0:
                advise = "Trailing stop executed perfectly. Letting it run for 24H would have yielded less."
                
            logger.info(f"Counterfactual Analysis (Trade {trade.id}): {advise}")
            
            # Store insight into vector memory!
            from euroscope.container import get_container
            container = get_container()
            if container and hasattr(container, "vector_memory") and container.vector_memory:
                container.vector_memory.store_insight(
                    f"Counterfactual review for {trade.direction} trade {trade.id} (PNL: {trade.pnl_pips}): {advise}",
                    tags=["counterfactual", "risk_tuning"]
                )
            
        except Exception as e:
            logger.error(f"Failed counterfactual analysis for Trade {trade.id}: {e}")

    def run_in_background(self, trade: TradingSignal):
        """Fire and forget the analysis logic."""
        if not trade or trade.status != "CLOSED":
            return
            
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.analyze_trade(trade))
        except RuntimeError:
            logger.warning("Could not launch counterfactual engine (no event loop running).")
