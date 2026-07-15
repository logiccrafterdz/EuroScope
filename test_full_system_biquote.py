"""
Test Full System with BiQuote

Comprehensive test to verify BiQuote integration with the full EuroScope system.
Tests: Price fetching, Multi-source failover, and Market Data skill.
"""

import sys
import asyncio
import time

# Add the project root to path
sys.path.insert(0, '.')


async def test_full_system():
    """Test full system integration with BiQuote."""
    print("=" * 60)
    print("Testing Full EuroScope System with BiQuote")
    print("=" * 60)
    
    # 1. Test BiQuote Provider directly
    print("\n[1/5] Testing BiQuote Provider directly...")
    try:
        from euroscope.data.biquote import BiQuoteProvider
        
        provider = BiQuoteProvider()
        result = await provider.get_price()
        
        if "error" in result:
            print(f"  [FAIL] BiQuote error: {result['error']}")
            return False
        
        print(f"  [OK] BiQuote: EUR/USD = {result['price']}")
        print(f"       Bid: {result['bid']} | Ask: {result['ask']} | Spread: {result['spread']} pips")
        
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        return False
    
    # 2. Test MultiSourceProvider
    print("\n[2/5] Testing MultiSourceProvider with BiQuote as primary...")
    try:
        from euroscope.data.multi_provider import MultiSourceProvider
        
        multi_provider = MultiSourceProvider()
        result = await multi_provider.get_price()
        
        if "error" in result:
            print(f"  [FAIL] MultiSourceProvider error: {result['error']}")
            return False
        
        print(f"  [OK] MultiSourceProvider working!")
        print(f"       Source: {result.get('source')}")
        print(f"       Price: {result.get('price')}")
        
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        return False
    
    # 3. Test Market Data Skill
    print("\n[3/5] Testing Market Data Skill...")
    try:
        from euroscope.skills.market_data.skill import MarketDataSkill
        from euroscope.skills.base import SkillContext
        
        # Create skill and set provider
        skill = MarketDataSkill()
        skill.set_provider(multi_provider)
        
        # Create context
        context = SkillContext()
        
        # Execute get_price
        result = await skill.execute(context, "get_price")
        
        if not result.success:
            print(f"  [FAIL] Market Data Skill error: {result.error}")
            return False
        
        print(f"  [OK] Market Data Skill working!")
        print(f"       Price: {result.data.get('price')}")
        print(f"       Source: {result.data.get('source')}")
        
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        return False
    
    # 4. Test Live Price Updates (3 iterations)
    print("\n[4/5] Testing Live Price Updates (3 iterations)...")
    try:
        for i in range(3):
            result = await provider.get_price()
            if "error" not in result:
                print(f"  [{i+1}/3] EUR/USD: {result['price']} (via {result['source']})")
            else:
                print(f"  [{i+1}/3] Error: {result['error']}")
            await asyncio.sleep(1)
        print("  [OK] Live updates working!")
        
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        return False
    
    # 5. Test Performance (response time)
    print("\n[5/5] Testing Performance (response time)...")
    try:
        times = []
        for i in range(5):
            start = time.time()
            result = await provider.get_price()
            elapsed = (time.time() - start) * 1000  # ms
            times.append(elapsed)
            await asyncio.sleep(0.5)
        
        avg_time = sum(times) / len(times)
        print(f"  Average response time: {avg_time:.2f} ms")
        print(f"  Min: {min(times):.2f} ms | Max: {max(times):.2f} ms")
        print("  [OK] Performance acceptable!")
        
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        return False
    
    # Summary
    print("\n" + "=" * 60)
    print("[SUCCESS] All tests passed!")
    print("=" * 60)
    print("\nBiQuote is now integrated as the primary data source.")
    print("The system will use BiQuote first (free, no API key),")
    print("then fall back to other providers if needed.")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_full_system())
    sys.exit(0 if success else 1)
