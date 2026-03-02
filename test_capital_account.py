import asyncio
import json
from euroscope.trading.capital_provider import CapitalProvider
from euroscope.config import Config

async def test_capital_account():
    config = Config.from_env()
    provider = CapitalProvider(
        config.data.capital_api_key,
        config.data.capital_identifier,
        config.data.capital_password
    )
    
    try:
        if await provider.login():
            info = await provider.get_account_info()
            print(json.dumps(info, indent=2))
    finally:
        await provider.close()

if __name__ == "__main__":
    asyncio.run(test_capital_account())
