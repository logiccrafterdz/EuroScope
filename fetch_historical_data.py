import yfinance as yf
import pandas as pd
import os

def fetch_data(symbol="EURUSD=X", period="730d", interval="1h", output_file="data/eurusd_h1_2years.csv"):
    print(f"📡 Fetching {period} of {interval} data for {symbol} using yfinance...")
    
    # yfinance allows 730d maximum for 1h interval
    df = yf.download(tickers=symbol, period=period, interval=interval)
    
    if df.empty:
        print("❌ Failed to fetch data. Check your network or ticker symbol.")
        return
        
    # Formatting columns to match standard Orchestrator expectations
    df.columns = [col[0] for col in df.columns] # Flatten multi-index if it exists
    df.reset_index(inplace=True)
    
    # Ensure standard names
    # Datetime, Open, High, Low, Close, Adj Close, Volume
    rename_map = {
        "Datetime": "timestamp",
        "Date": "timestamp",
        "Open": "Open",
        "High": "High",
        "Low": "Low",
        "Close": "Close",
        "Volume": "Volume"
    }
    df.rename(columns=rename_map, inplace=True)
    
    # Save to CSV
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df.to_csv(output_file, index=False)
    
    print(f"✅ Successfully downloaded {len(df)} candles.")
    print(f"📁 Saved to {output_file}")
    
    print("\nSample Data:")
    print(df.head())

if __name__ == "__main__":
    fetch_data()
