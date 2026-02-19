import yfinance as yf
import pandas as pd
from datetime import datetime

symbol = "EURUSD=X"
ticker = yf.Ticker(symbol)

print(f"--- Diagnostic for {symbol} ---")
print(f"Time: {datetime.now()}")

for tf, interval in [("M15", "15m"), ("H1", "1h"), ("D1", "1d")]:
    print(f"\nTimeframe: {tf} (Interval: {interval})")
    df = ticker.history(period="5d" if "m" in interval else "30d", interval=interval)
    if df.empty:
        print("Result: EMPTY")
    else:
        print(f"Result: {len(df)} candles")
        print(f"Last Price: {df['Close'].iloc[-1]:.5f}")
        print(f"Last Time: {df.index[-1]}")
