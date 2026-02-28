#!/usr/bin/env python3
"""
EuroScope Backtest Runner

Executes the quantitative trading rules of the StrategyEngine against historical data,
applying realistic execution simulation (spread and slippage) to evaluate genuine performance.
"""

import logging
import argparse
from euroscope.backtest import BacktestEngine, BacktestMetrics

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RUNNER")

def main():
    parser = argparse.ArgumentParser(description="Run EuroScope Historical Backtest")
    parser.add_argument("--days", type=int, default=700, help="Days of history to fetch via yfinance")
    parser.add_argument("--symbol", type=str, default="EURUSD=X", help="Yahoo Finance symbol")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (e.g., 1h, 15m)")
    
    args = parser.parse_args()
    
    engine = BacktestEngine(initial_balance=10000.0)
    df = engine.fetch_data(symbol=args.symbol, timeframe=args.timeframe, days=args.days)
    
    if df.empty:
        logger.error("Data fetch failed. Exiting.")
        return
        
    logger.info("Starting historical replay...")
    engine.run(warmup_period=200)  # Use 200 candles warmup for EMA200
    
    metrics = BacktestMetrics(initial_balance=engine.initial_balance, positions=engine.executor.closed_positions)
    print("\n" + metrics.generate_tear_sheet())

if __name__ == "__main__":
    main()
