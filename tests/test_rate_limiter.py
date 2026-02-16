import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from euroscope.bot.rate_limiter import RateLimiter


sys.modules.setdefault("yfinance", MagicMock())
sys.modules.setdefault("mplfinance", MagicMock())
sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())


@pytest.mark.asyncio
async def test_allows_within_window():
    limiter = RateLimiter(max_requests=5, window_minutes=1)
    for i in range(5):
        allowed, remaining = await limiter.is_allowed(1)
        assert allowed is True
        assert remaining == 4 - i
    allowed, remaining = await limiter.is_allowed(1)
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_window_expiration(monkeypatch):
    limiter = RateLimiter(max_requests=1, window_minutes=1)
    state = {"calls": 0}

    def fake_time():
        state["calls"] += 1
        return 0.0 if state["calls"] == 1 else 61.0

    monkeypatch.setattr("euroscope.bot.rate_limiter.time.monotonic", fake_time)
    allowed, remaining = await limiter.is_allowed(1)
    assert allowed is True
    assert remaining == 0
    allowed, remaining = await limiter.is_allowed(1)
    assert allowed is True
    assert remaining == 0


@pytest.mark.asyncio
async def test_reset_clears_counter():
    limiter = RateLimiter(max_requests=1, window_minutes=1)
    allowed, _ = await limiter.is_allowed(1)
    assert allowed is True
    allowed, _ = await limiter.is_allowed(1)
    assert allowed is False
    await limiter.reset(1)
    allowed, _ = await limiter.is_allowed(1)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limit_blocks_non_admin():
    from euroscope.bot.telegram_bot import EuroScopeBot

    config = MagicMock()
    config.telegram.token = "fake:test"
    config.telegram.allowed_users = []
    config.data.brave_api_key = ""
    config.data.alphavantage_key = ""
    config.data.tiingo_key = ""
    config.data.fred_api_key = ""
    config.llm = MagicMock()
    config.llm.api_key = ""
    config.llm.api_base = ""
    config.llm.model = ""
    config.llm.fallback_api_key = ""
    config.rate_limit_requests = 2
    config.rate_limit_window_minutes = 1
    config.admin_chat_ids = []

    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_message.reply_text = AsyncMock()

    with patch("euroscope.bot.telegram_bot.PriceProvider"), \
         patch("euroscope.bot.telegram_bot.NewsEngine"), \
         patch("euroscope.bot.telegram_bot.EconomicCalendar"), \
         patch("euroscope.bot.telegram_bot.Agent"), \
         patch("euroscope.bot.telegram_bot.Memory"), \
         patch("euroscope.bot.telegram_bot.Forecaster"), \
         patch("euroscope.bot.telegram_bot.Orchestrator"), \
         patch("euroscope.bot.telegram_bot.RiskManager"), \
         patch("euroscope.bot.telegram_bot.StrategyEngine"), \
         patch("euroscope.bot.telegram_bot.SignalExecutor"), \
         patch("euroscope.bot.telegram_bot.Storage"):
        bot = EuroScopeBot(config)

    assert await bot._check_rate_limit(update) is True
    assert await bot._check_rate_limit(update) is True
    assert await bot._check_rate_limit(update) is False
    update.effective_message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_admin_bypass():
    from euroscope.bot.telegram_bot import EuroScopeBot

    config = MagicMock()
    config.telegram.token = "fake:test"
    config.telegram.allowed_users = []
    config.data.brave_api_key = ""
    config.data.alphavantage_key = ""
    config.data.tiingo_key = ""
    config.data.fred_api_key = ""
    config.llm = MagicMock()
    config.llm.api_key = ""
    config.llm.api_base = ""
    config.llm.model = ""
    config.llm.fallback_api_key = ""
    config.rate_limit_requests = 1
    config.rate_limit_window_minutes = 1
    config.admin_chat_ids = ["123"]

    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_message.reply_text = AsyncMock()

    with patch("euroscope.bot.telegram_bot.PriceProvider"), \
         patch("euroscope.bot.telegram_bot.NewsEngine"), \
         patch("euroscope.bot.telegram_bot.EconomicCalendar"), \
         patch("euroscope.bot.telegram_bot.Agent"), \
         patch("euroscope.bot.telegram_bot.Memory"), \
         patch("euroscope.bot.telegram_bot.Forecaster"), \
         patch("euroscope.bot.telegram_bot.Orchestrator"), \
         patch("euroscope.bot.telegram_bot.RiskManager"), \
         patch("euroscope.bot.telegram_bot.StrategyEngine"), \
         patch("euroscope.bot.telegram_bot.SignalExecutor"), \
         patch("euroscope.bot.telegram_bot.Storage"):
        bot = EuroScopeBot(config)

    for _ in range(3):
        assert await bot._check_rate_limit(update) is True
    update.effective_message.reply_text.assert_not_called()
