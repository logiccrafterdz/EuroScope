"""
Test Suite 8: Storage + Integration — Storage layer, Container wiring, Capital removal verification
Tests: Storage CRUD, signal round-trip, container attributes, no capital imports
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


async def test_storage_instantiation():
    """Test 1: Storage instantiation"""
    from euroscope.data.storage import Storage
    try:
        storage = Storage(db_path=":memory:")
        if storage and storage.db_path == ":memory:":
            log("Storage instantiation", "PASS", f"db_path={storage.db_path}")
        else:
            log("Storage instantiation", "FAIL", f"db_path={getattr(storage, 'db_path', None)}")
        await storage.close()
    except Exception as e:
        log("Storage instantiation", "FAIL", str(e)[:100])


async def test_storage_json_roundtrip():
    """Test 2: Storage save/load JSON round-trip"""
    import tempfile, os
    from euroscope.data.storage import Storage
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage = Storage(db_path=path)
        test_data = {"price": 1.085, "direction": "BUY", "nested": {"a": [1, 2, 3]}}
        await storage.save_json("integration_test", test_data)
        loaded = await storage.load_json("integration_test")
        if loaded and loaded.get("price") == 1.085 and loaded.get("direction") == "BUY":
            log("Storage JSON round-trip", "PASS", f"loaded={loaded}")
        else:
            log("Storage JSON round-trip", "FAIL", f"loaded={loaded}")
        await storage.close()
    except Exception as e:
        log("Storage JSON round-trip", "FAIL", str(e)[:100])
    finally:
        try: os.unlink(path)
        except: pass


async def test_storage_signal_roundtrip():
    """Test 3: Storage save_signal / get_signals round-trip"""
    import tempfile, os
    from euroscope.data.storage import Storage
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage = Storage(db_path=path)
        sid = await storage.save_signal(
            direction="BUY", entry_price=1.08500, stop_loss=1.07800,
            take_profit=1.09900, confidence=0.75, timeframe="H4",
            source="test", reasoning="test signal", risk_reward_ratio=2.0
        )
        signals = await storage.get_signals(status="open")
        found = [s for s in signals if s.get("id") == sid]
        if found and found[0]["direction"] == "BUY" and found[0]["entry_price"] == 1.08500:
            log("Storage signal round-trip", "PASS", f"signal id={sid}, dir={found[0]['direction']}")
        else:
            log("Storage signal round-trip", "FAIL", f"signals={signals}")
        await storage.close()
    except Exception as e:
        log("Storage signal round-trip", "FAIL", str(e)[:100])
    finally:
        try: os.unlink(path)
        except: pass


async def test_storage_clear_and_reload():
    """Test 4: Storage clear and reload"""
    import tempfile, os
    from euroscope.data.storage import Storage
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage = Storage(db_path=path)
        await storage.save_json("clear_test", {"value": 42})
        loaded_before = await storage.load_json("clear_test")
        await storage.save_json("clear_test", {"value": 99})
        loaded_after = await storage.load_json("clear_test")
        if loaded_before and loaded_before.get("value") == 42 and loaded_after.get("value") == 99:
            log("Storage clear and reload", "PASS", f"before=42, after=99")
        else:
            log("Storage clear and reload", "FAIL", f"before={loaded_before}, after={loaded_after}")
        await storage.close()
    except Exception as e:
        log("Storage clear and reload", "FAIL", str(e)[:100])
    finally:
        try: os.unlink(path)
        except: pass


async def test_container_required_attributes():
    """Test 5: Container has all required attributes"""
    from euroscope.container import ServiceContainer
    from euroscope.config import Config
    try:
        config = Config.from_env()
        container = ServiceContainer(config)
        required = [
            "price_provider", "orchestrator", "memory", "storage",
            "router", "risk_manager", "registry", "bus", "alerts",
            "daily_tracker", "pattern_tracker", "agent",
        ]
        missing = [attr for attr in required if not hasattr(container, attr)]
        if not missing:
            log("Container required attrs", "PASS", f"all {len(required)} attrs present")
        else:
            log("Container required attrs", "FAIL", f"missing: {missing}")
    except Exception as e:
        log("Container required attrs", "FAIL", str(e)[:100])


async def test_container_price_provider_type():
    """Test 6: Container price_provider is MultiSourceProvider"""
    from euroscope.container import ServiceContainer
    from euroscope.config import Config
    from euroscope.data.multi_provider import MultiSourceProvider
    try:
        config = Config.from_env()
        container = ServiceContainer(config)
        if isinstance(container.price_provider, MultiSourceProvider):
            log("Container price_provider type", "PASS", f"type={type(container.price_provider).__name__}")
        else:
            log("Container price_provider type", "FAIL", f"expected MultiSourceProvider, got {type(container.price_provider).__name__}")
    except Exception as e:
        log("Container price_provider type", "FAIL", str(e)[:100])


async def test_container_no_broker():
    """Test 7: Container has no broker (None) — after Capital removal"""
    from euroscope.container import ServiceContainer
    from euroscope.config import Config
    try:
        config = Config.from_env()
        container = ServiceContainer(config)
        if container.broker is None:
            log("Container no broker", "PASS", "broker is None")
        else:
            log("Container no broker", "FAIL", f"broker={container.broker}")
    except Exception as e:
        log("Container no broker", "FAIL", str(e)[:100])


async def test_container_no_ws_client():
    """Test 8: Container has no ws_client (None) — after Capital removal"""
    from euroscope.container import ServiceContainer
    from euroscope.config import Config
    try:
        config = Config.from_env()
        container = ServiceContainer(config)
        if container.ws_client is None:
            log("Container no ws_client", "PASS", "ws_client is None")
        else:
            log("Container no ws_client", "FAIL", f"ws_client={container.ws_client}")
    except Exception as e:
        log("Container no ws_client", "FAIL", str(e)[:100])


async def test_no_capital_in_multi_provider():
    """Test 9: No capital imports in multi_provider.py"""
    import re
    try:
        from pathlib import Path
        import inspect
        from euroscope.data.multi_provider import MultiSourceProvider
        source_file = Path(inspect.getfile(MultiSourceProvider))
        content = source_file.read_text(encoding="utf-8")
        import_lines = [line for line in content.split("\n") if line.strip().startswith("import") or line.strip().startswith("from")]
        capital_imports = [line for line in import_lines if "capital" in line.lower() and ".capitalize()" not in line]
        if not capital_imports:
            log("No capital imports in multi_provider.py", "PASS", f"checked {len(import_lines)} import lines")
        else:
            log("No capital imports in multi_provider.py", "FAIL", f"found: {capital_imports}")
    except Exception as e:
        log("No capital imports in multi_provider.py", "FAIL", str(e)[:100])


async def test_no_capital_in_container():
    """Test 10: No capital imports in container.py"""
    import re
    try:
        from pathlib import Path
        import inspect
        from euroscope.container import ServiceContainer
        source_file = Path(inspect.getfile(ServiceContainer))
        content = source_file.read_text(encoding="utf-8")
        import_lines = [line for line in content.split("\n") if line.strip().startswith("import") or line.strip().startswith("from")]
        capital_imports = [line for line in import_lines if "capital" in line.lower() and ".capitalize()" not in line]
        if not capital_imports:
            log("No capital imports in container.py", "PASS", f"checked {len(import_lines)} import lines")
        else:
            log("No capital imports in container.py", "FAIL", f"found: {capital_imports}")
    except Exception as e:
        log("No capital imports in container.py", "FAIL", str(e)[:100])


async def main():
    print("\n" + "="*60)
    print("  SUITE 8: STORAGE + INTEGRATION TESTS")
    print("="*60)

    tests = [
        test_storage_instantiation,
        test_storage_json_roundtrip,
        test_storage_signal_roundtrip,
        test_storage_clear_and_reload,
        test_container_required_attributes,
        test_container_price_provider_type,
        test_container_no_broker,
        test_container_no_ws_client,
        test_no_capital_in_multi_provider,
        test_no_capital_in_container,
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
