"""
Behavioral Walk-Forward Simulation Runner.

Downloads ~2 weeks of historical candles for EUR/USD and streams them
through the Behavioral Simulator to judge EuroScope's Orchestrator performance.
"""

import asyncio
import logging
from datetime import datetime

# Configure minimal logging for the simulator
logging.basicConfig(level=logging.INFO, format="%(message)s")

from euroscope.brain.orchestrator import Orchestrator
from euroscope.analytics.behavior_simulator import BehavioralSimulator
from dotenv import load_dotenv

load_dotenv()

# Setup Orchestrator
orchestrator = Orchestrator()

def _make_candles(n=1000, start_price=1.0900):
    import datetime
    candles = []
    price = start_price
    base_time = datetime.datetime.now() - datetime.timedelta(days=30)
    for i in range(n):
        # Add basic trends and noise
        import math
        trend = math.sin(i / 100.0) * 0.0050
        noise = (i % 5 - 2) * 0.0005
        
        o = price
        c = start_price + trend + noise
        h = max(o, c) + 0.0008
        l = min(o, c) - 0.0008
        
        candles.append({
            "timestamp": (base_time + datetime.timedelta(minutes=15 * i)).isoformat(),
            "Open": round(o, 5),
            "High": round(h, 5),
            "Low": round(l, 5),
            "Close": round(c, 5),
            "Volume": 1000.0 + (i % 20) * 10,
        })
        price = c
    return candles

async def main():
    print(f"[{datetime.now().time()}] 📡 Generating synthetic EUR/USD M15 candles for simulation...")
    try:
        candles = _make_candles(1000)
        print(f"✅ Generated {len(candles)} bars successfully.")
        
        sim = BehavioralSimulator(orchestrator)
        report = await sim.run(candles)
        
        print("\n\n")
        print(report)

    except Exception as e:
        print(f"Simulation crashed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
