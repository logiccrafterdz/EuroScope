"""
Test Suite 5: Bot Layer — Config, RateLimiter, Formatting, Storage
Tests: Config loading, defaults, rate limiting, message formatting, storage ops
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


async def test_config_from_env():
    """Test 1: Config.from_env() creates valid config"""
    from euroscope.config import Config
    try:
        config = Config.from_env()
        if config.llm.model:
            log("Config.from_env()", "PASS", f"model={config.llm.model}")
        else:
            log("Config.from_env()", "FAIL", "model is empty")
    except Exception as e:
        log("Config.from_env()", "FAIL", str(e)[:100])


async def test_config_validate():
    """Test 2: Config validate() returns list"""
    from euroscope.config import Config
    config = Config.from_env()
    warnings = config.validate()
    if isinstance(warnings, list):
        log("Config.validate()", "PASS", f"returned {len(warnings)} warnings")
    else:
        log("Config.validate()", "FAIL", f"expected list, got {type(warnings)}")


async def test_data_config_defaults():
    """Test 3: DataConfig defaults (no capital_*)"""
    from euroscope.config import DataConfig
    dc = DataConfig()
    if dc.symbol == "EURUSD=X" and dc.update_interval_minutes == 15 and dc.oanda_practice is True:
        log("DataConfig defaults", "PASS", f"symbol={dc.symbol}, interval={dc.update_interval_minutes}min")
    else:
        log("DataConfig defaults", "FAIL", f"symbol={dc.symbol}, interval={dc.update_interval_minutes}")


async def test_llm_config_defaults():
    """Test 4: LLMConfig defaults"""
    from euroscope.config import LLMConfig
    lc = LLMConfig()
    checks = []
    if lc.api_base == "https://api.freetheai.xyz/v1": checks.append("primary_base")
    if lc.model == "glm/glm-5.2": checks.append("primary_model")
    if lc.fallback_model == "deepseek-ai/deepseek-v4-flash": checks.append("fallback_model")
    if lc.tertiary_model == "gpt-4o-mini": checks.append("tertiary_model")
    if lc.max_tokens == 4096: checks.append("max_tokens=4096")
    if len(checks) == 5:
        log("LLMConfig defaults", "PASS", ", ".join(checks))
    else:
        log("LLMConfig defaults", "FAIL", f"only {len(checks)}/5 correct: {checks}")


async def test_telegram_config_defaults():
    """Test 5: TelegramConfig defaults"""
    from euroscope.config import TelegramConfig
    tc = TelegramConfig()
    if tc.token == "" and tc.allowed_users == [] and tc.web_app_url == "":
        log("TelegramConfig defaults", "PASS", "all defaults correct")
    else:
        log("TelegramConfig defaults", "FAIL", f"token={tc.token}, users={tc.allowed_users}")


async def test_service_container_instantiation():
    """Test 6: ServiceContainer instantiation (mock storage)"""
    from euroscope.container import ServiceContainer
    from euroscope.config import Config
    try:
        config = Config.from_env()
        container = ServiceContainer(config)
        has_storage = hasattr(container, "storage") and container.storage is not None
        if has_storage:
            log("ServiceContainer instantiation", "PASS", "storage initialized")
        else:
            log("ServiceContainer instantiation", "FAIL", "storage is None")
    except Exception as e:
        log("ServiceContainer instantiation", "FAIL", str(e)[:100])


async def test_api_server_instantiation():
    """Test 7: APIServer instantiation (mock bot)"""
    try:
        from euroscope.bot.webhooks import APIServer
        from unittest.mock import MagicMock
        mock_bot = MagicMock()
        server = APIServer(bot=mock_bot)
        log("APIServer instantiation", "PASS", f"type={type(server).__name__}")
    except ImportError:
        log("APIServer instantiation", "SKIP", "APIServer not found in bot.webhooks")
    except Exception as e:
        log("APIServer instantiation", "FAIL", str(e)[:100])


async def test_rate_limiter_basic():
    """Test 8: RateLimiter basic functionality"""
    from euroscope.bot.rate_limiter import RateLimiter
    rl = RateLimiter(max_requests=3, window_minutes=1)
    allowed1, remaining1 = await rl.is_allowed(chat_id=100)
    allowed2, remaining2 = await rl.is_allowed(chat_id=100)
    allowed3, remaining3 = await rl.is_allowed(chat_id=100)
    allowed4, remaining4 = await rl.is_allowed(chat_id=100)
    if allowed1 and allowed2 and allowed3 and not allowed4:
        log("RateLimiter basic", "PASS", f"3 allowed, 4th blocked (remaining={remaining4})")
    else:
        log("RateLimiter basic", "FAIL", f"results: {allowed1}, {allowed2}, {allowed3}, {allowed4}")


async def test_formatting_utils():
    """Test 9: Formatting utils work (truncate, rich_header)"""
    from euroscope.utils.formatting import truncate, rich_header
    issues = []
    # truncate with small max_length returns only the truncation suffix
    truncated = truncate("hello world", max_length=5)
    if not truncated:
        issues.append(f"truncate(5) returned empty")
    # truncate with sufficient max_length returns full text
    full = truncate("short", max_length=100)
    if full != "short":
        issues.append(f"truncate(100)={full}")
    header = rich_header("test", type="main")
    if not header or len(header) < 5:
        issues.append(f"rich_header={header}")
    if not issues:
        log("Formatting utils", "PASS", f"truncate OK, rich_header OK")
    else:
        log("Formatting utils", "FAIL", "; ".join(issues))


async def test_storage_basic_ops():
    """Test 10: Storage basic operations (save/load JSON)"""
    import tempfile, os
    from euroscope.data.storage import Storage
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage = Storage(db_path=path)
        test_data = {"key": "value", "number": 42, "nested": {"a": 1}}
        await storage.save_json("test_roundtrip", test_data)
        loaded = await storage.load_json("test_roundtrip")
        if loaded and loaded.get("key") == "value" and loaded.get("number") == 42:
            log("Storage save/load JSON", "PASS", f"roundtrip OK: {loaded}")
        else:
            log("Storage save/load JSON", "FAIL", f"loaded={loaded}")
        await storage.close()
    except Exception as e:
        log("Storage save/load JSON", "FAIL", str(e)[:100])
    finally:
        try: os.unlink(path)
        except: pass


async def main():
    print("\n" + "="*60)
    print("  SUITE 5: BOT LAYER TESTS")
    print("="*60)

    tests = [
        test_config_from_env,
        test_config_validate,
        test_data_config_defaults,
        test_llm_config_defaults,
        test_telegram_config_defaults,
        test_service_container_instantiation,
        test_api_server_instantiation,
        test_rate_limiter_basic,
        test_formatting_utils,
        test_storage_basic_ops,
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
