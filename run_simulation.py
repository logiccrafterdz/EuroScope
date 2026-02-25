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

def _load_historical_data(file_path="data/eurusd_h1_2years.csv"):
    import pandas as pd
    try:
        df = pd.read_csv(file_path)
        # Ensure timestamp is string for JSON serialization
        df['timestamp'] = df['timestamp'].astype(str)
        # Convert to list of dicts
        records = df.to_dict('records')
        return records
    except Exception as e:
        print(f"Failed to load CSV: {e}")
        return []

async def main():
    print(f"[{datetime.now().time()}] 📡 Loading real EUR/USD H1 historical data for simulation...")
    try:
        candles = _load_historical_data()
        if not candles:
            print("❌ Failed to load candles. Run fetch_historical_data.py first.")
            return
            
        print(f"✅ Loaded {len(candles)} bars successfully.")
        
        sim = BehavioralSimulator(orchestrator)
        report = await sim.run(candles)
        
        print("\n\n")
        print(report)

    except Exception as e:
        print(f"Simulation crashed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
