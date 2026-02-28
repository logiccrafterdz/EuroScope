import asyncio
import logging
from euroscope.trading.capital_provider import CapitalProvider
from euroscope.config import Config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("capital_test")

async def test_capital_connection():
    config = Config.from_env()
    
    # Check if credentials are set
    if not config.data.capital_api_key or not config.data.capital_identifier:
        logger.error("Capital.com credentials not found in .env!")
        print("\n❌ MISSING CREDENTIALS")
        print("Please fill EUROSCOPE_CAPITAL_API_KEY, IDENTIFIER, and PASSWORD in your .env file.")
        return

    provider = CapitalProvider(
        config.data.capital_api_key,
        config.data.capital_identifier,
        config.data.capital_password
    )
    
    print("\n--- 🚀 Testing Capital.com Async Connection ---")
    
    try:
        if await provider.login():
            print(f"✅ Login Successful! Account: {provider.account_id}")
            
            # Test Price Fetching
            price = await provider.get_price("EURUSD")
            if price:
                print(f"💹 EUR/USD Price: {price['price']} (Bid: {price['bid']} / Ask: {price['ask']})")
                
                # Test Historical Candles
                print("📊 Fetching H1 candles...")
                df = await provider.get_candles("EURUSD", timeframe="H1", count=5)
                if df is not None:
                    print(f"✅ Fetched {len(df)} candles.")
                    print(df)
            else:
                print("❌ Could not fetch price. Check if 'EURUSD' is the correct Epic.")
        else:
            print("❌ Login Failed. Check credentials and ensure 2FA is ENABLED (Capital.com API requirement).")
    finally:
        await provider.close()

if __name__ == "__main__":
    asyncio.run(test_capital_connection())
