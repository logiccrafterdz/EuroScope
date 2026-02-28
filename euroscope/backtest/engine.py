"""
Historical Backtest Engine

Fast, offline, deterministic replay engine that evaluates the StrategyEngine's
technical/quantitative logic against historical OHLCV data.
Bypasses LLM analysis for huge speedups and zero API cost.
"""

import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

from ..trading.strategy_engine import StrategyEngine, StrategySignal
from ..trading.execution_simulator import ExecutionSimulator, ExecutionConfig
from ..analysis.technical import TechnicalAnalyzer
from ..analysis.patterns import PatternDetector
from ..analysis.levels import LevelAnalyzer
from .offline_executor import OfflineExecutor, TradeSignal
from ..trading.risk_manager import RiskManager

logger = logging.getLogger("euroscope.backtest.engine")


class BacktestEngine:
    """
    Deterministically replays historical data through the StrategyEngine.
    """
    
    def __init__(self, initial_balance: float = 10000.0):
        self.strategy_engine = StrategyEngine()
        self.risk_manager = RiskManager()
        self.risk_manager.config.account_balance = initial_balance
        
        self.tech_analyzer = TechnicalAnalyzer()
        self.pattern_detector = PatternDetector()
        self.level_analyzer = LevelAnalyzer()
        
        # Use full realistic execution simulating spread/slippage
        self.executor = OfflineExecutor(ExecutionSimulator(ExecutionConfig(enabled=True)))
        
        self.initial_balance = initial_balance
        self.data: pd.DataFrame = pd.DataFrame()
        self.results = {}
        
    def fetch_data(self, symbol: str = "EURUSD=X", timeframe: str = "1h", days: int = 700) -> pd.DataFrame:
        """Fetch historical data using yfinance."""
        logger.info(f"Fetching {days} days of {timeframe} data for {symbol}...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        df = yf.download(
            tickers=symbol,
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
            interval=timeframe,
            progress=False
        )
        
        if df.empty:
            logger.error("No data fetched.")
            return df
            
        # Clean multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        df.dropna(inplace=True)
        self.data = df
        logger.info(f"Fetched {len(self.data)} candles. From {self.data.index[0]} to {self.data.index[-1]}")
        return self.data
        
    def run(self, warmup_period: int = 100):
        """
        Run the backtest loop.
        warmup_period: Candles to skip at start to let indicators (e.g. SMA200) populate.
        """
        if self.data.empty:
            logger.error("No data to run backtest on. Call fetch_data() first.")
            return
            
        logger.info("Starting backtest loop...")
        total_candles = len(self.data)
        
        for i in range(warmup_period, total_candles):
            # Slice data up to current candle (exclusive of current for indicators)
            # This simulates real-time where we only know closed candles
            # WAIT: to be accurate, we compute indicators on slice up to i (which is closed)
            # and then we execute at open of i+1, but we can just use Close of i as "current"
            
            # The current closed candle is i. 
            # We will use indicators up to i.
            # We will then "update positions" based on the extreme (High/Low) of i.
            # Actually, to prevent look-ahead bias:
            # - At the START of candle i, we have data up to i-1.
            # - We evaluate signals based on i-1.
            # - We execute entries at Open of i.
            # - We update positions using High/Low of i.
            
            slice_df = self.data.iloc[:i].copy()
            current_bar = self.data.iloc[i]
            prev_bar = self.data.iloc[i-1]
            current_time = self.data.index[i]
            
            # 1. Update Open Positions (using current bar's extremes)
            # To get an ATR proxy for spread widening during this bar:
            # We just use the ATR from the previous bar's indicators
            if len(self.executor.open_positions) > 0:
                # We need ATR for slippage simulation. We'll compute it shortly, 
                # but if we don't have it yet, use a default.
                pass # update happens below after indicators are computed
                
            # 2. Compute Indicators (on historical slice)
            # Fast approximations or use full analysis
            # We must suppress logs inside individual analyzers because this runs 1000s of times
            ta = self.tech_analyzer.analyze(slice_df)
            patterns = [] # self.pattern_detector.detect_all(slice_df) # Too slow for 5000 candles
            levels = self.level_analyzer.find_support_resistance(slice_df)
            
            atr = ta.get("ATR", {}).get("value", 0.0005) # EUR/USD default
            
            # Now update positions against this bar's extremes
            self.executor.update_positions(
                high=current_bar["High"],
                low=current_bar["Low"],
                current_time=current_time,
                atr=atr
            )
            
            # 3. Assess Signal from StrategyEngine
            # only if we don't have max positions open
            if len(self.executor.open_positions) < self.risk_manager.config.max_open_trades:
                levels_data = {
                    "current_price": prev_bar["Close"], # Price at indicator completion
                    "support": levels.get("support", []),
                    "resistance": levels.get("resistance", [])
                }
                
                # Map indicators to the format expected by StrategyEngine
                # Provide strict floats where expected to avoid NoneType comparisons
                ta_inds = ta.get("indicators", {})
                ind = {
                    "adx": float(ta_inds.get("ADX", {}).get("value", 0)) if ta_inds.get("ADX", {}).get("value") else 0.0,
                    "rsi": float(ta_inds.get("RSI", {}).get("value", 50)) if ta_inds.get("RSI", {}).get("value") else 50.0,
                    "overall_bias": ta.get("overall_bias", "neutral"),
                    "macd": ta_inds.get("MACD", {}),
                    "bollinger": ta_inds.get("Bollinger", {}),
                    "ema": ta_inds.get("EMA", {}),
                    "atr": ta_inds.get("ATR", {}),
                    "stochastic": ta_inds.get("Stochastic", {}),
                }

                # Mock uncertainty/macro for backtester
                signal_raw: StrategySignal = self.strategy_engine.detect_strategy(
                    indicators=ind,
                    levels=levels_data,
                    patterns=patterns,
                    uncertainty={"score": 30, "level": "low"}, # Favorable
                    macro_data={"divergence": False}
                )
                
                if signal_raw.direction in ["BUY", "SELL"]:
                    # Create actionable TradeSignal via RiskManager
                    trade_risk = self.risk_manager.assess_trade(
                        direction=signal_raw.direction,
                        entry_price=current_bar["Open"],
                        atr=atr,
                        regime=signal_raw.regime
                    )
                    
                    if trade_risk.approved:
                        sig = TradeSignal(
                            direction=trade_risk.direction,
                            entry_price=trade_risk.entry_price,
                            sl_price=trade_risk.stop_loss,
                            tp_price=trade_risk.take_profit,
                            position_size=trade_risk.position_size,
                            strategy=signal_raw.strategy,
                            timeframe="1h",
                            confidence=signal_raw.confidence,
                            reasoning=signal_raw.reasoning
                        )
                        
                        self.executor.open_position(
                            signal=sig,
                            current_price=current_bar["Open"],
                            current_time=current_time,
                            atr=atr
                        )
                    else:
                        logger.debug(f"[{current_time}] Trade rejected by RiskManager: {trade_risk.warnings}")
                else:
                    logger.debug(f"[{current_time}] Signal WAIT (Strategy: {signal_raw.strategy}, Regime: {signal_raw.regime})")
            
            if i % 500 == 0:
                logger.info(f"Processed {i}/{total_candles} candles... Closed trades: {len(self.executor.closed_positions)}")
                
        # End of loop. Close all remaining.
        if len(self.executor.open_positions) > 0:
            final_price = self.data.iloc[-1]["Close"]
            final_time = self.data.index[-1]
            ta_final = self.tech_analyzer.analyze(self.data)
            atr_final = ta_final.get("ATR", {}).get("value", 0.0005)
            self.executor.close_all(final_price, final_time, atr_final, reason="end_of_backtest")
            
        logger.info(f"Backtest complete. Total trades: {len(self.executor.closed_positions)}")
