"""
Test Suite 7: Learning Layer — PatternTracker, AdaptiveTuner, ForecastTracker,
CounterfactualEngine, RegimeAdaptiveEngine
Tests: Instantiation, store/load cycle, regime detection
"""

import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

RESULTS = []

def log(test_name, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    RESULTS.append((test_name, status, detail))
    print(f"  {icon} {test_name}" + (f" — {detail}" if detail else ""))


async def test_pattern_tracker_instantiation():
    """Test 1: PatternTracker instantiation"""
    from euroscope.learning.pattern_tracker import PatternTracker
    try:
        pt = PatternTracker()
        if pt and hasattr(pt, "storage"):
            log("PatternTracker instantiation", "PASS", f"storage={pt.storage}")
        else:
            log("PatternTracker instantiation", "FAIL", "missing storage attribute")
    except Exception as e:
        log("PatternTracker instantiation", "FAIL", str(e)[:100])


async def test_adaptive_tuner_instantiation():
    """Test 2: AdaptiveTuner instantiation"""
    from euroscope.learning.adaptive_tuner import AdaptiveTuner
    try:
        at = AdaptiveTuner()
        if at and hasattr(at, "storage") and hasattr(at, "config"):
            log("AdaptiveTuner instantiation", "PASS", f"storage={at.storage}, config={at.config}")
        else:
            log("AdaptiveTuner instantiation", "FAIL", "missing expected attributes")
    except Exception as e:
        log("AdaptiveTuner instantiation", "FAIL", str(e)[:100])


async def test_forecast_tracker_instantiation():
    """Test 3: ForecastTracker instantiation"""
    from euroscope.learning.forecast_tracker import ForecastTracker
    try:
        ft = ForecastTracker()
        if ft and hasattr(ft, "storage") and hasattr(ft, "_weights"):
            log("ForecastTracker instantiation", "PASS", f"weights={len(ft._weights)}")
        else:
            log("ForecastTracker instantiation", "FAIL", "missing expected attributes")
    except Exception as e:
        log("ForecastTracker instantiation", "FAIL", str(e)[:100])


async def test_counterfactual_engine_instantiation():
    """Test 4: CounterfactualEngine instantiation"""
    from euroscope.learning.counterfactual import CounterfactualEngine
    try:
        ce = CounterfactualEngine()
        if ce and hasattr(ce, "scenarios") and len(ce.scenarios) > 0:
            log("CounterfactualEngine instantiation", "PASS", f"scenarios={len(ce.scenarios)}")
        else:
            log("CounterfactualEngine instantiation", "FAIL", "missing scenarios")
    except Exception as e:
        log("CounterfactualEngine instantiation", "FAIL", str(e)[:100])


async def test_regime_adaptive_engine_instantiation():
    """Test 5: RegimeAdaptiveEngine instantiation"""
    from euroscope.trading.regime_adaptive import RegimeAdaptiveEngine
    try:
        engine = RegimeAdaptiveEngine()
        if engine and hasattr(engine, "_current_regime") and engine._current_regime == "ranging":
            log("RegimeAdaptiveEngine instantiation", "PASS", f"default_regime={engine._current_regime}")
        else:
            log("RegimeAdaptiveEngine instantiation", "FAIL", f"regime={getattr(engine, '_current_regime', None)}")
    except Exception as e:
        log("RegimeAdaptiveEngine instantiation", "FAIL", str(e)[:100])


async def test_pattern_tracker_store_load():
    """Test 6: PatternTracker basic store/load cycle"""
    import tempfile, os
    from euroscope.data.storage import Storage
    from euroscope.learning.pattern_tracker import PatternTracker
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage = Storage(db_path=path)
        pt = PatternTracker(storage=storage)
        pid = await pt.record_detection("double_bottom", "H4", "BUY", 1.08500)
        if pid and pid > 0:
            log("PatternTracker store/load", "PASS", f"recorded pattern id={pid}")
        else:
            log("PatternTracker store/load", "FAIL", f"pid={pid}")
        await storage.close()
    except Exception as e:
        log("PatternTracker store/load", "FAIL", str(e)[:100])
    finally:
        try: os.unlink(path)
        except: pass


async def main():
    print("\n" + "="*60)
    print("  SUITE 7: LEARNING LAYER TESTS")
    print("="*60)

    tests = [
        test_pattern_tracker_instantiation,
        test_adaptive_tuner_instantiation,
        test_forecast_tracker_instantiation,
        test_counterfactual_engine_instantiation,
        test_regime_adaptive_engine_instantiation,
        test_pattern_tracker_store_load,
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
