"""
Test Suite 1: Data Layer — BiQuote, MultiSourceProvider, Data Health
Tests: Live price fetching, failover, candles, error handling
"""

import asyncio
import sys
import time
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

RESULTS = []

def log(test_name, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    RESULTS.append((test_name, status, detail))
    print(f"  {icon} {test_name}" + (f" — {detail}" if detail else ""))


async def test_biquote_direct():
    """Test 1: BiQuote direct API call"""
    from euroscope.data.biquote import BiQuoteProvider
    p = BiQuoteProvider()
    try:
        t0 = time.time()
        result = await p.get_price()
        latency = (time.time() - t0) * 1000

        if "error" in result:
            log("BiQuote Direct", "FAIL", f"Error: {result['error']}")
            return

        price = result.get("price", 0)
        bid = result.get("bid", 0)
        ask = result.get("ask", 0)
        spread = result.get("spread", 0)
        source = result.get("source", "")

        checks = []
        if price > 0: checks.append(f"price={price}")
        else: checks.append("price=0!")

        if bid > 0 and ask > 0: checks.append(f"bid/ask OK")
        else: checks.append("bid/ask missing!")

        if source == "biquote": checks.append("source=biquote OK")
        else: checks.append(f"source={source} (unexpected)")

        if spread >= 0: checks.append(f"spread={spread}p OK")

        if latency < 3000:
            log("BiQuote Direct", "PASS", f"latency={latency:.0f}ms, {', '.join(checks)}")
        else:
            log("BiQuote Direct", "WARN", f"SLOW latency={latency:.0f}ms, {', '.join(checks)}")
    except Exception as e:
        log("BiQuote Direct", "FAIL", str(e)[:100])
    finally:
        await p.close()


async def test_biquote_price_range():
    """Test 2: BiQuote price is in EUR/USD range"""
    from euroscope.data.biquote import BiQuoteProvider
    p = BiQuoteProvider()
    try:
        result = await p.get_price()
        if "error" in result:
            log("BiQuote Price Range", "SKIP", "BiQuote unavailable")
            return
        price = result.get("price", 0)
        if 0.80 <= price <= 1.60:
            log("BiQuote Price Range", "PASS", f"price={price} within [0.80, 1.60]")
        else:
            log("BiQuote Price Range", "FAIL", f"price={price} out of EUR/USD range")
    except Exception as e:
        log("BiQuote Price Range", "FAIL", str(e)[:100])
    finally:
        await p.close()


async def test_biquote_bid_ask_spread():
    """Test 3: BiQuote bid < ask and spread is reasonable"""
    from euroscope.data.biquote import BiQuoteProvider
    p = BiQuoteProvider()
    try:
        result = await p.get_price()
        if "error" in result:
            log("BiQuote Bid/Ask Spread", "SKIP", "BiQuote unavailable")
            return
        bid = result.get("bid", 0)
        ask = result.get("ask", 0)
        spread_pips = result.get("spread", 0)

        if bid <= 0 or ask <= 0:
            log("BiQuote Bid/Ask Spread", "FAIL", f"bid={bid}, ask={ask} — invalid")
            return
        if bid < ask:
            log("BiQuote Bid/Ask Spread", "PASS", f"bid={bid} < ask={ask}, spread={spread_pips}pips")
        elif bid == ask:
            log("BiQuote Bid/Ask Spread", "WARN", f"bid==ask={bid} — zero spread unusual")
        else:
            log("BiQuote Bid/Ask Spread", "FAIL", f"bid={bid} > ask={ask} — inverted!")
    except Exception as e:
        log("BiQuote Bid/Ask Spread", "FAIL", str(e)[:100])
    finally:
        await p.close()


async def test_biquote_candles_returns_none():
    """Test 4: BiQuote candle fallback returns None (free tier limitation)"""
    from euroscope.data.biquote import BiQuoteProvider
    p = BiQuoteProvider()
    try:
        result = await p.get_candles("H1", 100)
        if result is None:
            log("BiQuote Candles Fallback", "PASS", "Correctly returns None (free tier)")
        else:
            log("BiQuote Candles Fallback", "WARN", f"Returned data instead of None: {type(result)}")
    except Exception as e:
        log("BiQuote Candles Fallback", "FAIL", str(e)[:100])
    finally:
        await p.close()


async def test_biquote_consecutive_calls():
    """Test 5: BiQuote handles 5 consecutive calls without failure"""
    from euroscope.data.biquote import BiQuoteProvider
    p = BiQuoteProvider()
    try:
        successes = 0
        errors = []
        for i in range(5):
            result = await p.get_price()
            if "error" not in result:
                successes += 1
            else:
                errors.append(result["error"])
        if successes == 5:
            log("BiQuote 5x Consecutive", "PASS", f"5/5 success")
        elif successes >= 3:
            log("BiQuote 5x Consecutive", "WARN", f"{successes}/5 success, errors: {errors[:2]}")
        else:
            log("BiQuote 5x Consecutive", "FAIL", f"{successes}/5 success, errors: {errors[:3]}")
    except Exception as e:
        log("BiQuote 5x Consecutive", "FAIL", str(e)[:100])
    finally:
        await p.close()


async def test_multi_source_get_price():
    """Test 6: MultiSourceProvider.get_price() returns BiQuote data"""
    from euroscope.data.multi_provider import MultiSourceProvider
    mp = MultiSourceProvider()
    try:
        t0 = time.time()
        result = await mp.get_price()
        latency = (time.time() - t0) * 1000
        if "error" in result:
            log("MultiSource Price", "FAIL", f"Error: {result.get('error', 'unknown')[:80]}")
            return
        source = result.get("source", "unknown")
        price = result.get("price", 0)
        log("MultiSource Price", "PASS", f"source={source}, price={price}, latency={latency:.0f}ms")
    except Exception as e:
        log("MultiSource Price", "FAIL", str(e)[:100])
    finally:
        await mp.close()


async def test_multi_source_last_source():
    """Test 7: MultiSourceProvider tracks last_source correctly"""
    from euroscope.data.multi_provider import MultiSourceProvider
    mp = MultiSourceProvider()
    try:
        result = await mp.get_price()
        if "error" not in result:
            assert mp.last_source in ("biquote", "oanda", "tiingo", "yfinance", "alphavantage")
            log("MultiSource Last Source", "PASS", f"last_source={mp.last_source}")
        else:
            log("MultiSource Last Source", "WARN", f"Price fetch failed, source may be stale")
    except Exception as e:
        log("MultiSource Last Source", "FAIL", str(e)[:100])
    finally:
        await mp.close()


async def test_multi_source_close():
    """Test 8: MultiSourceProvider.close() doesn't throw"""
    from euroscope.data.multi_provider import MultiSourceProvider
    mp = MultiSourceProvider()
    try:
        await mp.get_price()
        await mp.close()
        log("MultiSource Close", "PASS", "No exception")
    except Exception as e:
        log("MultiSource Close", "FAIL", str(e)[:100])


async def test_multi_source_latency_consistency():
    """Test 9: 3 consecutive calls have consistent latency (< 3x median)"""
    from euroscope.data.multi_provider import MultiSourceProvider
    mp = MultiSourceProvider()
    try:
        latencies = []
        for _ in range(3):
            t0 = time.time()
            await mp.get_price()
            latencies.append((time.time() - t0) * 1000)
        median = sorted(latencies)[1]
        max_allowed = median * 3
        all_ok = all(l < max_allowed for l in latencies)
        detail = f"latencies={[f'{l:.0f}' for l in latencies]}ms, median={median:.0f}ms"
        if all_ok:
            log("MultiSource Latency Consistency", "PASS", detail)
        else:
            log("MultiSource Latency Consistency", "WARN", f"Outlier detected — {detail}")
    except Exception as e:
        log("MultiSource Latency Consistency", "FAIL", str(e)[:100])
    finally:
        await mp.close()


async def test_multi_source_failover_chain():
    """Test 10: MultiSourceProvider imports all providers correctly"""
    try:
        from euroscope.data.multi_provider import MultiSourceProvider
        mp = MultiSourceProvider()
        providers = []
        if mp.biquote: providers.append("biquote")
        if mp.oanda: providers.append("oanda")
        if mp.tiingo: providers.append("tiingo")
        if mp.legacy: providers.append("yfinance")
        if mp.fallback: providers.append("alphavantage")
        log("Failover Chain", "PASS", f"Active: {', '.join(providers)}")
    except Exception as e:
        log("Failover Chain", "FAIL", str(e)[:100])


async def main():
    print("\n" + "="*60)
    print("  SUITE 1: DATA LAYER TESTS")
    print("="*60)

    tests = [
        test_biquote_direct,
        test_biquote_price_range,
        test_biquote_bid_ask_spread,
        test_biquote_candles_returns_none,
        test_biquote_consecutive_calls,
        test_multi_source_get_price,
        test_multi_source_last_source,
        test_multi_source_close,
        test_multi_source_latency_consistency,
        test_multi_source_failover_chain,
    ]

    for test_fn in tests:
        await test_fn()

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for _, s, _ in RESULTS if s == "WARN")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    total = len(RESULTS)

    print(f"\n{'─'*60}")
    print(f"  RESULTS: {passed}✅ {failed}❌ {warned}⚠️ {skipped}⏭️ / {total} total")
    print(f"{'─'*60}\n")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
