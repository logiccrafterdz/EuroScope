"""
Test Suite 2: Brain Layer — LLMRouter, CostTracker, DifficultyRouter
Tests: Router creation, chat fallback, stats, cost tracking, performance routing
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


async def test_llm_router_from_config_no_keys():
    """Test 1: LLMRouter.from_config() creates router with 0 providers"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config()
    count = len(router.providers)
    if count == 0:
        log("Router from_config (no keys)", "PASS", f"providers={count}")
    else:
        log("Router from_config (no keys)", "FAIL", f"expected 0 providers, got {count}")
    await router.close()


async def test_llm_router_chat_no_providers():
    """Test 2: LLMRouter chat() returns warning when no providers"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config()
    result = await router.chat([{"role": "user", "content": "test"}])
    if "No LLM providers configured" in result:
        log("Router chat (no providers)", "PASS", "returned expected warning")
    else:
        log("Router chat (no providers)", "FAIL", f"unexpected: {result[:100]}")
    await router.close()


async def test_llm_router_chat_json_no_providers():
    """Test 3: LLMRouter chat_json() returns error dict when no providers"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config()
    result = await router.chat_json([{"role": "user", "content": "test"}])
    if isinstance(result, dict) and "error" in result:
        log("Router chat_json (no providers)", "PASS", f"error={result['error'][:60]}")
    else:
        log("Router chat_json (no providers)", "FAIL", f"unexpected: {result}")
    await router.close()


async def test_llm_router_stats_keys():
    """Test 4: LLMRouter stats dict has correct keys"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config()
    stats = router.stats
    expected_keys = {"total_calls", "failures", "success_rate", "providers_available", "last_provider"}
    actual_keys = set(stats.keys())
    if expected_keys == actual_keys:
        log("Router stats keys", "PASS", f"keys={sorted(actual_keys)}")
    else:
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        log("Router stats keys", "FAIL", f"missing={missing}, extra={extra}")
    await router.close()


async def test_llm_router_reset_breakers():
    """Test 5: LLMRouter reset_breakers() doesn't throw"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config()
    try:
        router.reset_breakers()
        log("Router reset_breakers", "PASS", "no exception")
    except Exception as e:
        log("Router reset_breakers", "FAIL", str(e)[:100])
    await router.close()


async def test_llm_router_close():
    """Test 6: LLMRouter close() doesn't throw"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config()
    try:
        await router.close()
        log("Router close", "PASS", "no exception")
    except Exception as e:
        log("Router close", "FAIL", str(e)[:100])


async def test_llm_router_fake_keys_creates_2():
    """Test 7: LLMRouter.from_config with fake keys creates 2 providers"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config(primary_key="fake-primary", fallback_key="fake-fallback")
    count = len(router.providers)
    if count == 2:
        log("Router 2 providers", "PASS", f"providers={count}")
    else:
        log("Router 2 providers", "FAIL", f"expected 2, got {count}")
    await router.close()


async def test_llm_router_all_3_keys_creates_3():
    """Test 8: LLMRouter.from_config with all 3 keys creates 3 providers"""
    from euroscope.brain.llm_router import LLMRouter
    router = LLMRouter.from_config(
        primary_key="fake-primary",
        fallback_key="fake-fallback",
        tertiary_key="fake-tertiary",
    )
    count = len(router.providers)
    if count == 3:
        log("Router 3 providers", "PASS", f"providers={count}")
    else:
        log("Router 3 providers", "FAIL", f"expected 3, got {count}")
    await router.close()


async def test_cost_tracker_instantiation():
    """Test 9: CostTracker instantiation"""
    from euroscope.brain.cost_tracker import CostTracker
    try:
        tracker = CostTracker()
        tracker.record_call("gpt-4o-mini", prompt_tokens=100, completion_tokens=50)
        summary = tracker.get_daily_summary()
        if summary["total_calls"] == 1 and summary["total_tokens"] == 150:
            log("CostTracker instantiation", "PASS", f"calls={summary['total_calls']}, tokens={summary['total_tokens']}")
        else:
            log("CostTracker instantiation", "FAIL", f"unexpected summary: {summary}")
    except Exception as e:
        log("CostTracker instantiation", "FAIL", str(e)[:100])


async def test_difficulty_router_instantiation():
    """Test 10: DifficultyRouter instantiation"""
    from euroscope.brain.performance import DifficultyRouter
    from euroscope.brain.llm_router import LLMRouter
    try:
        router = LLMRouter.from_config()
        dr = DifficultyRouter(router)
        stats = dr.stats
        if "total" in stats and "simple" in stats:
            log("DifficultyRouter instantiation", "PASS", f"stats keys={sorted(stats.keys())}")
        else:
            log("DifficultyRouter instantiation", "FAIL", f"unexpected stats: {stats}")
        await router.close()
    except Exception as e:
        log("DifficultyRouter instantiation", "FAIL", str(e)[:100])


async def main():
    print("\n" + "="*60)
    print("  SUITE 2: BRAIN LAYER TESTS")
    print("="*60)

    tests = [
        test_llm_router_from_config_no_keys,
        test_llm_router_chat_no_providers,
        test_llm_router_chat_json_no_providers,
        test_llm_router_stats_keys,
        test_llm_router_reset_breakers,
        test_llm_router_close,
        test_llm_router_fake_keys_creates_2,
        test_llm_router_all_3_keys_creates_3,
        test_cost_tracker_instantiation,
        test_difficulty_router_instantiation,
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
