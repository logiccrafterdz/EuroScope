"""
Behavioral Walk-Forward Simulator.

Reads historical candles, steps through them sequentially (time-traveling),
injects the current slice into the Orchestrator, and lets the TraderProfiles
react to the outputs.
"""

import asyncio
import logging
from typing import List, Dict
import pandas as pd
from datetime import datetime

from .trader_profiles import ScalperProfile, SwingProfile
from .simulation_metrics import SimulationMetrics

logger = logging.getLogger("euroscope.analytics.simulator")

class MockPriceProvider:
    """Spoofs price data based on the current step in the simulation."""
    def __init__(self, history_df: pd.DataFrame):
        self.history = history_df
        self.current_idx = 0
        
    def step(self):
        if self.current_idx < len(self.history) - 1:
            self.current_idx += 1
            return True
        return False
        
    async def get_price(self):
        row = self.history.iloc[self.current_idx]
        return {
            "price": row["Close"],
            "spread_pips": 1.0,
            "change": 0.0,
            "change_pct": 0.0,
            "timestamp": row.name.isoformat() if hasattr(row.name, 'isoformat') else str(row.name)
        }
        
    async def get_candles(self, timeframe="H1", count=100):
        # Only return candles UP TO the current index (No future peeking)
        end_idx = self.current_idx + 1
        start_idx = max(0, end_idx - count)
        
        subset = self.history.iloc[start_idx:end_idx].copy()
        
        # We need to rename index to Timestamp if needed but Orchestrator expects a DataFrame
        # with open, high, low, close, volume columns.
        if subset.index.name != "Timestamp":
             subset.index.name = "Timestamp"
             
        # Return as DataFrame natively since the orchestrator technical_analysis requires it
        return subset


class BehavioralSimulator:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.metrics = SimulationMetrics()
        self.profiles = [ScalperProfile(), SwingProfile()]
        
    async def run(self, history: list[dict]):
        """
        Run the walk-forward simulation over a list of OHLCV dicts.
        """
        if not history:
            return "No historical data provided."
            
        # Convert to DF for easy slicing
        df = pd.DataFrame(history)
        if 'timestamp' in df.columns:
            df.set_index('timestamp', inplace=True)
            
        provider = MockPriceProvider(df)
        
        # Re-wire Orchestrator skills to use the Mock Provider
        market_skill = self.orchestrator.registry.get("market_data")
        if market_skill:
            market_skill.set_provider(provider)
            
        logger.info(f"🚀 Starting Walk-Forward Simulation: {len(history)} bars")
        
        bar_idx = 0
        lookback = 50 # Let it warm up
        
        # Advance provider to lookback index
        for _ in range(lookback):
            provider.step()
            bar_idx += 1
            
        while provider.step():
            bar_idx += 1
            price_data = await provider.get_price()
            current_price = price_data["price"]
            timestamp = price_data["timestamp"]
            
            # 1. Manage existing profile open trades (SL/TP)
            for profile in self.profiles:
                profile.manage_open_trade(current_price, bar_idx, timestamp)
                
            # 2. Grade active alerts in metrics
            self.metrics.grade_meaningful_alerts(current_price, bar_idx)
            
            if bar_idx % 500 == 0:
                print(f"⏳ Processed {bar_idx}/{len(history)} bars...")
            
            # To simulate real-time behavior without doing 24 hours a day
            # we'll only trigger a full Orchestrator pipeline every 4 bars (e.g. 4 hours)
            # or if volatility explodes. For simplicity, just every 4 bars.
            if bar_idx % 4 != 0:
                continue
                
            # 3. Fire the Orchestrator Pipeline
            try:
                # We do NOT want to inject this into LLMs natively to save costs/time.
                # The Orchestrator `run_full_analysis_pipeline` itself doesn't invoke the LLM Agent unless asked.
                # It just runs the mathematical skills.
                ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe="H1")
                
                # Extract the final consensus processed by the entire pipeline (including Conflict Arbiter)
                signal_data = ctx.signals or {}
                # The arbiter places the final synthesized trade plan into "verdict",
                # while trading_strategy raw sets "direction". We prioritize "verdict".
                direction = signal_data.get("verdict", signal_data.get("direction", "WAIT")).upper()
                conf = signal_data.get("confidence", signal_data.get("raw_confidence", 0))
                
                if direction in ("BUY", "SELL"):
                    # Record the alert
                    self.metrics.record_signal(direction, conf, current_price, bar_idx, timestamp)
                    
                    # Let profiles react
                    orchestrator_output = {
                        "signal_data": signal_data,
                        "technical": ctx.analysis,
                        "market": ctx.market_data
                    }
                    for profile in self.profiles:
                        action = profile.evaluate_signal(orchestrator_output, current_price, bar_idx, timestamp)
                        if action:
                            logger.debug(f"[{timestamp}] {action}")
                                
            except Exception as e:
                logger.error(f"Simulator error at bar {bar_idx}: {e}")
                
        # Simulation complete. Flush open trades.
        final_price = (await provider.get_price())["price"]
        for profile in self.profiles:
            if profile.open_trade:
                profile._close_trade(final_price, bar_idx, timestamp, "End of Simulation")
                
        # Build Report
        return self._generate_report()
        
    def _generate_report(self) -> str:
        report = []
        report.append("=========================================")
        report.append("🏁 BEHAVIORAL SIMULATION COMPLETE 🏁")
        report.append("=========================================")
        report.append(self.metrics.get_report())
        report.append("")
        report.append("👥 **Trader Profile Results (Theoretical PnL)**")
        
        for p in self.profiles:
            total_trades = len(p.trades)
            if total_trades == 0:
                report.append(f"• {p.name}: No trades taken.")
                continue
                
            wins = sum(1 for t in p.trades if t.pnl_pips > 0)
            wr = (wins / total_trades) * 100
            total_pnl = sum(t.pnl_pips for t in p.trades)
            report.append(f"• {p.name}: {total_trades} trades | Win Rate: {wr:.1f}% | Net PnL: {total_pnl:+.1f} pips")
            
        report.append("=========================================")
        return "\n".join(report)
