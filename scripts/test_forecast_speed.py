import asyncio
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from euroscope.config import Config
from euroscope.bot.telegram_bot import EuroScopeBot
from dotenv import load_dotenv

load_dotenv()

async def test_forecast_speed():
    print("Loading config...", flush=True)
    config = Config.from_env()
    bot = EuroScopeBot(config)
    
    print("\nStarting Forecaster engine measuring speed...", flush=True)
    start_time = time.time()
    
    try:
        # Wrap in 60 second timeout just like the API server
        result = await asyncio.wait_for(bot.forecaster.generate_forecast("H1"), timeout=60.0)
        elapsed = time.time() - start_time
        print(f"\n✅ Forecast SUCCESS in {elapsed:.2f} seconds.")
        print("-" * 40)
        print(f"Direction: {result.get('direction')}")
        print(f"Confidence: {result.get('confidence')}%")
        print("Reasoning snippet: ", result.get('text', '')[:200].replace('\n', ' '), "...")
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"\n❌ Forecast TIMED OUT after {elapsed:.2f} seconds!")
        
if __name__ == "__main__":
    asyncio.run(test_forecast_speed())
