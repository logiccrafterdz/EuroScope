import asyncio
import logging
from euroscope.main import Config
from euroscope.bot.telegram_bot import EuroScopeBot

logging.basicConfig(level=logging.INFO)

async def main():
    config = Config.from_env()
    bot = EuroScopeBot(config)
    print("Running periodic observation...")
    result = await bot.agent.run_periodic_observation()
    print("--------------------------------------------------")
    print(result)
    print("--------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(main())
