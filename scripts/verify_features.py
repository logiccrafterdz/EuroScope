import asyncio
import os
import sys

# Add root folder to path (the parent of euroscope folder)
sys.path.insert(0, r"C:\Users\Hp\Desktop\EuroScope")

from euroscope.bot.config import Config
from euroscope.brain.orchestrator import Orchestrator
from euroscope.skills.base import SkillContext

async def test_all():
    print("Initializing EuroScope with enhanced config...")
    config = Config()
    # Force test configuration
    config.data_provider = "yfinance" # Assuming yfinance is setup, change to oanda if token is ready
    
    print("\n--- Testing Orchestrator and Enhanced Skills ---")
    orchestrator = Orchestrator()
    ctx = SkillContext()
    
    # 1. Test Market Data (Base)
    print("\n1. Fetching Market Data...")
    mkt_res = await orchestrator.run_skill("market_data", "get_price", context=ctx)
    if not mkt_res.success:
        print(f"FAILED: {mkt_res.error}")
        return
    print(f"Price: {mkt_res.data.get('price')}")
    
    # 2. Test Fundamental (Rate Differential Trend)
    print("\n2. Testing Fundamental Analysis (Rate Differentials)...")
    fund_res = await orchestrator.run_skill("fundamental_analysis", "full", context=ctx)
    if not fund_res.success:
        print(f"FAILED: {fund_res.error}")
    else:
        print(f"Fundamental Bias: {fund_res.data.get('bias')}")
        print(f"News Sentiment: {fund_res.data.get('news_sentiment', {}).get('sentiment')}")
    
    # 3. Test Liquidity Awareness (PDH/PDL/Weekly)
    print("\n3. Testing Liquidity Awareness (PDH/PDL/Weekly Levels)...")
    # First get candles
    can_res = await orchestrator.run_skill("market_data", "get_candles", context=ctx, timeframe="H1", count=400)
    if not can_res.success:
        print(f"FAILED to get candles: {can_res.error}")
    else:
        liq_res = await orchestrator.run_skill("liquidity_awareness", "analyze", context=ctx)
        if not liq_res.success:
            print(f"FAILED: {liq_res.error}")
        else:
            zones = liq_res.data.get("liquidity_zones", [])
            print(f"Found {len(zones)} zones:")
            for z in zones[:8]:
                print(f"  - {z['zone_type']} at {z['price_level']} (Strength: {z['strength']})")

    # 4. Test Strategy Engine (ATR instead of Volume)
    print("\n4. Testing Strategy Engine (ATR Momentum Check)...")
    # Need full TA first
    ta_res = await orchestrator.run_skill("technical_analysis", "full", context=ctx, timeframe="H1")
    if ta_res.success:
        strat_res = await orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
        if not strat_res.success:
            print(f"FAILED: {strat_res.error}")
        else:
            print(f"Signal Result: {strat_res.data}")
            
    print("\n--- Tests Completed ---")

if __name__ == "__main__":
    asyncio.run(test_all())
