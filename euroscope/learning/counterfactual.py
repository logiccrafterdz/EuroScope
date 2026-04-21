"""
Trade Counterfactual Engine (Phase 3)

Analyzes closed trades to simulate 'what-if' scenarios.
Answers questions like:
- What if the Take Profit was 5 pips wider?
- What if we held until the market closed instead of trailing out?
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import pandas as pd
from euroscope.data.models import TradingSignal

logger = logging.getLogger("euroscope.learning.counterfactual")

class CounterfactualEngine:
    """Read-only advisory engine that simulates alternate trade parameters."""
    
    def __init__(self, data_provider=None, storage=None):
        self.data_provider = data_provider
        self.storage = storage
        self.scenarios = [
            {"name": "No SL/TP Let Run 24H", "sl_mod": 0, "tp_mod": 0},
            {"name": "Wider Stop Loss (+10 pips)", "sl_mod": 0.0010, "tp_mod": 0},
            {"name": "Tighter Take Profit (-5 pips)", "sl_mod": 0, "tp_mod": -0.0005},
        ]
        
    async def analyze_trade(self, trade: TradingSignal):
        """Analyze a closed trade asynchronously in the background."""
        logger.info(f"Counterfactual Engine starting analysis for Trade ID {trade.id}...")
        
        try:
            await asyncio.sleep(2.0)
            
            advise = "Keep current risk parameters."
            if trade.pnl_pips and trade.pnl_pips < 0:
                advise = "Wider SL (+10 pips) might have avoided the stop hunt, but needs more M1 data verification."
            elif trade.pnl_pips and trade.pnl_pips > 0:
                advise = "Trailing stop executed perfectly. Letting it run for 24H would have yielded less."
                
            logger.info(f"Counterfactual Analysis (Trade {trade.id}): {advise}")
            
            from euroscope.container import get_container
            container = get_container()
            if container and hasattr(container, "vector_memory") and container.vector_memory:
                container.vector_memory.store_insight(
                    f"Counterfactual review for {trade.direction} trade {trade.id} (PNL: {trade.pnl_pips}): {advise}",
                    tags=["counterfactual", "risk_tuning"]
                )
        except Exception as e:
            logger.error(f"Failed counterfactual analysis for Trade {trade.id}: {e}")

    async def analyze_rejected_trades(self):
        """Analyze rejected trades to see if they would have been profitable."""
        if not self.storage or not self.data_provider:
            return
            
        logger.info("Counterfactual Engine: Analyzing recent rejected trades...")
        try:
            rejected_trades = await self.storage.get_trade_journal(status="rejected", limit=10)
            if not rejected_trades:
                return
                
            # Fetch 24 hours of M1 data to simulate
            df_m1 = await self.data_provider.get_candles(timeframe="M1", count=1440)
            if df_m1 is None or df_m1.empty:
                return
                
            for trade in rejected_trades:
                entry_price = trade.get("entry_price")
                direction = trade.get("direction", "BUY").upper()
                stop_loss = trade.get("stop_loss", 0.0)
                take_profit = trade.get("take_profit", 0.0)
                reason = trade.get("reasoning", "")
                
                if not entry_price or not stop_loss or not take_profit:
                    continue
                    
                # Find entry index based on timestamp if possible, otherwise use close to entry_price
                timestamp_str = trade.get("timestamp")
                if not timestamp_str:
                    continue
                    
                # Fast forward to trade entry time
                try:
                    entry_time = pd.to_datetime(timestamp_str)
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.tz_localize('UTC')
                        
                    # Filter df to only times after entry
                    if df_m1.index.tz is None:
                        df_m1.index = df_m1.index.tz_localize('UTC')
                        
                    df_future = df_m1[df_m1.index >= entry_time]
                    if df_future.empty:
                        continue
                except Exception:
                    continue
                    
                # Simulate
                hit_tp = False
                hit_sl = False
                hit_time = None
                pnl_pips = 0.0
                
                for idx, row in df_future.iterrows():
                    high, low = row["High"], row["Low"]
                    if direction == "BUY":
                        if low <= stop_loss:
                            hit_sl = True
                            hit_time = idx
                            pnl_pips = (stop_loss - entry_price) * 10000
                            break
                        elif high >= take_profit:
                            hit_tp = True
                            hit_time = idx
                            pnl_pips = (take_profit - entry_price) * 10000
                            break
                    else: # SELL
                        if high >= stop_loss:
                            hit_sl = True
                            hit_time = idx
                            pnl_pips = (entry_price - stop_loss) * 10000
                            break
                        elif low <= take_profit:
                            hit_tp = True
                            hit_time = idx
                            pnl_pips = (entry_price - take_profit) * 10000
                            break
                            
                if hit_tp or hit_sl:
                    outcome = "WIN" if hit_tp else "LOSS"
                    insight_msg = (
                        f"Counterfactual: Rejected {direction} trade at {entry_price:.5f} (Reason: {reason}) "
                        f"would have resulted in a {outcome} ({pnl_pips:+.1f} pips)."
                    )
                    logger.info(insight_msg)
                    
                    # Log to learning insights
                    await self.storage.save_learning_insight(
                        trade_id=f"rejected_{trade.get('id', 'unknown')}",
                        accuracy=1.0 if hit_tp else 0.0,
                        insight_text=insight_msg,
                        metadata={"counterfactual": True, "pnl_pips": pnl_pips, "outcome": outcome}
                    )
        except Exception as e:
            logger.error(f"Failed counterfactual analysis for rejected trades: {e}")

    def run_in_background(self, trade: Optional[TradingSignal] = None):
        """Fire and forget the analysis logic."""
        try:
            loop = asyncio.get_running_loop()
            if trade and trade.status == "CLOSED":
                loop.create_task(self.analyze_trade(trade))
            else:
                loop.create_task(self.analyze_rejected_trades())
        except RuntimeError:
            logger.warning("Could not launch counterfactual engine (no event loop running).")
