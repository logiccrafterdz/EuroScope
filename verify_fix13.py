import asyncio
import sys
import os

# Add EuroScope to path
sys.path.append(os.getcwd())

from euroscope.data.sentiment import analyze_sentiment_onnx
from euroscope.trading.risk_manager import RiskManager, RiskConfig
from euroscope.data.storage import Storage

async def test_sentiment():
    print("Testing Sentiment Engine (ONNX + Numpy)...")
    texts = [
        "Goldman Sachs raises EUR/USD forecast as Fed pivot looms.",
        "Eurozone inflation spikes, ECB likely to keep rates high.",
        "Market remains quiet ahead of NFP data.",
        "GREAT NEWS! Euro skyrockets as economy thrives.",
        "DISASTER! Euro plunges as recession hits Germany."
    ]
    for text in texts:
        result = analyze_sentiment_onnx(text)
        print(f"Text: {text[:50]}...")
        print(f"Result: {result}\n")

async def test_risk_persistence():
    print("Testing RiskManager Persistence...")
    test_db = "temp_test_risk.db"
    if os.path.exists(test_db):
        os.remove(test_db)
        
    storage = Storage(test_db)
    
    rm = RiskManager(storage=storage)
    await rm.load_state()
    print(f"Initial State: PnL={rm._daily_pnl}, Streak={rm._consecutive_losses}")
    
    print("Recording a loss of -250...")
    rm.record_trade_result(-250.0)
    print(f"Updated State: PnL={rm._daily_pnl}, Streak={rm._consecutive_losses}")
    
    print("Simulating bot restart...")
    # Close old storage connection
    await storage.close()
    
    storage2 = Storage(test_db)
    rm2 = RiskManager(storage=storage2)
    await rm2.load_state()
    print(f"Recovered State: PnL={rm2._daily_pnl}, Streak={rm2._consecutive_losses}")
    
    success = rm2._daily_pnl == -250.0 and rm2._consecutive_losses == 1
    await storage2.close()
    if os.path.exists(test_db):
        os.remove(test_db)
        
    if success:
        print("✅ Risk persistence SUCCESS")
    else:
        print("❌ Risk persistence FAILED")

async def main():
    try:
        await test_sentiment()
    except Exception as e:
        print(f"Sentiment Test Error: {e}")
        
    try:
        await test_risk_persistence()
    except Exception as e:
        print(f"Risk Persistence Test Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
