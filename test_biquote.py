"""
Test BiQuote API Connection

Quick test to verify BiQuote API works for EUR/USD data.
Run this script to test the connection.
"""

import sys
import asyncio

# Add the project root to path
sys.path.insert(0, '.')

from euroscope.data.biquote import BiQuoteProvider


async def test_biquote_connection():
    """Test BiQuote API connection and data retrieval."""
    print("=" * 50)
    print("Testing BiQuote API Connection")
    print("=" * 50)
    
    # Create provider
    provider = BiQuoteProvider()
    
    print("\n1. Testing get_price()...")
    try:
        result = await provider.get_price()
        
        if "error" in result:
            print(f"[ERROR] {result['error']}")
            return False
        
        print("[OK] Success! Received price data:")
        print(f"   Symbol: {result.get('symbol')}")
        print(f"   Price: {result.get('price')}")
        print(f"   Bid: {result.get('bid')}")
        print(f"   Ask: {result.get('ask')}")
        print(f"   Spread: {result.get('spread')} pips")
        print(f"   Source: {result.get('source')}")
        print(f"   Timestamp: {result.get('timestamp')}")
        
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        return False
    
    print("\n2. Testing multiple calls (simulating live feed)...")
    try:
        for i in range(3):
            result = await provider.get_price()
            if "error" not in result:
                print(f"   [{i+1}] EUR/USD: {result['price']}")
            await asyncio.sleep(1)
        print("[OK] Live feed simulation successful!")
    except Exception as e:
        print(f"[ERROR] Error during live feed: {e}")
        return False
    
    print("\n3. Testing MultiSourceProvider integration...")
    try:
        from euroscope.data.multi_provider import MultiSourceProvider
        
        multi_provider = MultiSourceProvider()
        result = await multi_provider.get_price()
        
        if "error" not in result:
            print(f"[OK] MultiSourceProvider working! Source: {result.get('source')}")
        else:
            print(f"[WARN] MultiSourceProvider error: {result.get('error')}")
    except Exception as e:
        print(f"[WARN] MultiSourceProvider test failed: {e}")
    
    print("\n" + "=" * 50)
    print("[OK] BiQuote API test completed!")
    print("=" * 50)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_biquote_connection())
    sys.exit(0 if success else 1)
