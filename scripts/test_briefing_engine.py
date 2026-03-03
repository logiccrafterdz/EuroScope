import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from euroscope.config import Config
from euroscope.bot.telegram_bot import EuroScopeBot
from dotenv import load_dotenv

load_dotenv()

async def test_briefing():
    print("Loading config...", flush=True)
    config = Config.from_env()
    
    print("Initializing bot...", flush=True)
    bot = EuroScopeBot(config)
    
    print("Generating briefing...", flush=True)
    briefing = await bot.briefing_engine.generate_briefing()
    print("\n--- GENERATED BRIEFING (RAW) ---\n")
    print(briefing)
    print("\n--------------------------------\n")
    
    # We also need to test VoiceBriefingEngine explicitly
    print("Generating voice briefing...", flush=True)
    from euroscope.analytics.voice_briefing import VoiceBriefingEngine
    v_engine = VoiceBriefingEngine(orchestrator=bot.orchestrator, storage=bot.storage)
    v_briefing = await v_engine.generate_briefing()
    
    print("\n--- GENERATED VOICE BRIEFING SECTIONS ---\n")
    for section in v_briefing.sections:
        print(f"[{section.title}] (Priority: {section.priority})")
        print(section.content)
        print("-" * 20)
    print("\n----------------------------------------\n")

if __name__ == "__main__":
    asyncio.run(test_briefing())
