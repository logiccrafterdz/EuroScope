"""
Tests for bot initialization, command registration, and API server.

These tests validate the EuroScopeBot's actual command structure after
the V3 Skills-Based refactor. Legacy inline-keyboard and per-command
tests have been replaced to match the current architecture.
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock optional dependencies before EuroScope imports
sys.modules.setdefault("yfinance", MagicMock())
sys.modules.setdefault("mplfinance", MagicMock())
sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())


def _make_bot():
    """Helper to create a mocked EuroScopeBot instance."""
    from euroscope.bot.telegram_bot import EuroScopeBot

    config = MagicMock()
    config.telegram.token = "fake:test"
    config.telegram.allowed_users = []
    config.telegram.web_app_url = ""
    config.data.brave_api_key = ""
    config.data.alphavantage_key = ""
    config.data.tiingo_key = ""
    config.data.fred_api_key = ""
    config.llm = MagicMock()
    config.llm.api_key = ""
    config.llm.api_base = ""
    config.llm.model = ""
    config.llm.fallback_api_key = ""
    config.llm.fallback_api_base = ""
    config.llm.fallback_model = ""
    config.rate_limit_requests = 5
    config.rate_limit_window_minutes = 1
    config.admin_chat_ids = []
    config.vector_memory_ttl_days = 30
    config.data_dir = "."
    config.proactive_alert_chat_ids = []

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
    return bot


class TestBotInitialization:
    """Test that the bot initializes correctly."""

    def test_bot_creates_successfully(self):
        """EuroScopeBot should instantiate without errors."""
        bot = _make_bot()
        assert bot is not None
        assert bot.config.telegram.token == "fake:test"

    def test_bot_has_orchestrator(self):
        """Bot should have an orchestrator for skill execution."""
        bot = _make_bot()
        assert bot.orchestrator is not None

    def test_bot_has_storage(self):
        """Bot should have storage component."""
        bot = _make_bot()
        assert bot.storage is not None

    def test_bot_has_daily_tracker(self):
        """Bot should have a DailyTracker."""
        bot = _make_bot()
        assert bot.daily_tracker is not None


class TestBuildApp:
    """Test the Telegram Application building process."""

    def test_build_app_returns_application(self):
        """build_app should return a configured Application object."""
        from telegram.ext import Application as TGApp
        bot = _make_bot()
        app = bot.build_app()
        assert isinstance(app, TGApp)

    def test_build_app_registers_command_handlers(self):
        """build_app should register at least the core commands."""
        from telegram.ext import CommandHandler
        bot = _make_bot()
        app = bot.build_app()

        registered_commands = set()
        for group in app.handlers.values():
            for handler in group:
                if isinstance(handler, CommandHandler):
                    registered_commands.update(handler.commands)

        # The current bot registers: start, help, id, health, data_health
        expected_core = {"start", "help", "id", "health", "data_health"}
        assert expected_core.issubset(registered_commands), \
            f"Missing commands: {expected_core - registered_commands}"

    def test_build_app_has_error_handler(self):
        """build_app should register an error handler."""
        bot = _make_bot()
        app = bot.build_app()
        assert len(app.error_handlers) > 0


class TestAuthAndRateLimit:
    """Test authorization and rate limiting."""

    @pytest.mark.asyncio
    async def test_check_auth_allows_when_no_restrictions(self):
        """When allowed_users is empty, all users should be allowed."""
        bot = _make_bot()
        update = MagicMock()
        update.effective_user.id = 123
        update.effective_chat.id = 123
        update.effective_message = MagicMock()
        bot.rate_limiter.is_allowed = AsyncMock(return_value=(True, 5))
        result = await bot._check_auth(update)
        assert result is True

    def test_is_authorized_with_empty_list(self):
        """Empty allowed_users means everyone is authorized."""
        bot = _make_bot()
        assert bot._is_authorized(12345) is True

    def test_is_authorized_rejects_unlisted_user(self):
        """User not in allowed_users should be rejected."""
        bot = _make_bot()
        bot.config.telegram.allowed_users = [111, 222]
        assert bot._is_authorized(999) is False


class TestEmergencyKillSwitch:
    """Test the emergency mode bot settings."""

    def test_bot_settings_default(self):
        """Default bot_settings should have auto_trading disabled."""
        bot = _make_bot()
        assert bot.bot_settings.get("auto_trading_enabled") is False

    def test_bot_settings_risk_defaults(self):
        """Default risk settings should be 1% risk, 3% max daily loss."""
        bot = _make_bot()
        assert bot.bot_settings.get("risk_per_trade") == 1.0
        assert bot.bot_settings.get("max_daily_loss") == 3.0
