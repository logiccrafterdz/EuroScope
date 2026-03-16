import asyncio
import logging
from euroscope.data.storage import Storage
from euroscope.trading.signal_executor import SignalExecutor

logging.basicConfig(level=logging.INFO)

async def run():
    import os
    db_file = "test_temp.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    # Setup
    storage = Storage(db_file)
    executor = SignalExecutor(storage=storage, paper_trading=True)
    await executor.initialize()
    
    with open("trailer_log.txt", "w") as f:
        # 1. Open trade
        sig_id = await executor.open_signal("BUY", 1.0900, 1.0850, 1.0950)
        f.write(f"Opened: {sig_id}\n")
        
        # Check open signals
        signals = await executor.get_open_signals()
        f.write(f"SL starts at: {signals[0]['stop_loss']}\n")
        
        # 2. Advance price to 1.0915 (+15 pips)
        f.write("\n--- Moving to 1.0915 ---\n")
        await executor.check_signals(1.0915)
        
        # Check if SL updated
        signals = await executor.get_open_signals()
        f.write(f"SL after 1.0915: {signals[0]['stop_loss']}\n")
        
        # 3. Advance to 1.0920 (+20 pips)
        f.write("\n--- Moving to 1.0920 ---\n")
        await executor.check_signals(1.0920)
        
        signals = await executor.get_open_signals()
        f.write(f"SL after 1.0920: {signals[0]['stop_loss']}\n")
        
        # 4. Drop price back down to 1.0905 (Should hit new trailing stop)
        f.write("\n--- Dropping to 1.0905 ---\n")
        closed = await executor.check_signals(1.0905)
        f.write(f"Closed signals: {closed}\n")
    
    # Delay gracefully to allow aiosqlite threads to close
    await asyncio.sleep(0.5)
    
if __name__ == "__main__":
    asyncio.run(run())
