import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from euroscope.config import Config
from euroscope.bot.telegram_bot import EuroScopeBot
from dotenv import load_dotenv

load_dotenv()

async def test_pulse():
    print("Loading config...", flush=True)
    config = Config.from_env()
    
    print("Initializing bot...", flush=True)
    bot = EuroScopeBot(config)
    
    print("Running periodic observation...", flush=True)
    pulse = await bot.agent.run_periodic_observation()
    
    print("\n--- GENERATED PULSE ---\n")
    print(pulse)
    print("\n-----------------------\n")

if __name__ == "__main__":
    asyncio.run(test_pulse())
