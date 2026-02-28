import asyncio
import logging
import sys
from euroscope.config import Config
from euroscope.trading.capital_provider import CapitalProvider
from euroscope.trading.capital_ws import CapitalWebsocketClient
from euroscope.trading.signal_executor import SignalExecutor
from euroscope.data.storage import Storage

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger("test_ws_executor")

async def test_integration():
    config = Config.from_env()
    storage = Storage()
    
    # 1. Initialize Provder & WS
    broker = CapitalProvider(
        config.data.capital_api_key,
        config.data.capital_identifier,
        config.data.capital_password
    )
    if not await broker.login():
        print("Login failed.")
        return

    ws_client = CapitalWebsocketClient(broker)
    executor = SignalExecutor(storage=storage, broker=broker, paper_trading=True)
    
    # 2. Bind them
    executor.start_streaming(ws_client)
    
    # 3. Create a dummy open trade in DB to test exit
    # We'll use a very tight SL/TP or just watch it log ticks
    print("\n--- Creating Test Trade ---")
    current_price = (await broker.get_price("EURUSD"))["price"]
    print(f"Current EURUSD: {current_price}")
    
    # Create a trade that will close instantly (SL/TP very close)
    # Note: Use a real Epic if EURUSD is closed. BTCUSD works on weekends.
    symbol = "BTCUSD"
    btc_price = (await broker.get_price(symbol))["price"]
    print(f"Current {symbol}: {btc_price}")
    
    sig_id = await executor.open_signal(
        direction="BUY",
        entry_price=btc_price,
        stop_loss=btc_price - 5,
        take_profit=btc_price + 5,
        strategy="ws_test"
    )
    print(f"Opened Test Signal #{sig_id}")

    # 4. Start WS and wait for ticks
    print(f"\n--- Starting WebSocket for {symbol}... ---")
    if await ws_client.connect():
        await ws_client.subscribe([symbol])
        
        print("Waiting for ticks... (30s)")
        try:
            await asyncio.wait_for(asyncio.sleep(30), timeout=35)
        except asyncio.TimeoutError:
            pass
        
    await ws_client.close()
    await broker.close()
    print("\n--- Test Finished ---")

if __name__ == "__main__":
    asyncio.run(test_integration())
