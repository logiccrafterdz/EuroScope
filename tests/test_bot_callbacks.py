"""
Tests for inline keyboard generation, callback routing, and menu structure.
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock optional dependencies before EuroScope imports
sys.modules.setdefault("yfinance", MagicMock())
sys.modules.setdefault("mplfinance", MagicMock())
sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())

from telegram import InlineKeyboardMarkup


class TestMainMenu:
    """Test main menu keyboard construction."""

    def test_menu_has_buttons(self):
        """Import and verify menu keyboard has expected rows."""
        from euroscope.bot.telegram_bot import EuroScopeBot

        # Create a mock config
        config = MagicMock()
        config.telegram.token = "fake"
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
        config.rate_limit_requests = 5
        config.rate_limit_window_minutes = 1
        config.admin_chat_ids = []
        config.vector_memory_ttl_days = 30

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
            kb = bot._main_menu_keyboard()

        assert isinstance(kb, InlineKeyboardMarkup)
        # 6 rows of buttons
        assert len(kb.inline_keyboard) == 6
        # First row has 3 buttons (Price, Analysis, Chart)
        assert len(kb.inline_keyboard[0]) == 3

    def test_menu_callback_data(self):
        """Verify all buttons have cmd: prefixed callback data."""
        from euroscope.bot.telegram_bot import EuroScopeBot

        config = MagicMock()
        config.telegram.token = "fake"
        config.telegram.allowed_users = []
        config.data.brave_api_key = ""
        config.llm = MagicMock()
        config.data.alphavantage_key = ""
        config.data.tiingo_key = ""
        config.data.fred_api_key = ""
        config.llm.api_key = ""
        config.llm.api_base = ""
        config.llm.model = ""
        config.llm.fallback_api_key = ""
        config.rate_limit_requests = 5
        config.rate_limit_window_minutes = 1
        config.admin_chat_ids = []
        config.vector_memory_ttl_days = 30

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
            kb = bot._main_menu_keyboard()

        for row in kb.inline_keyboard:
            for button in row:
                assert button.callback_data.startswith(("cmd:", "settings:"))

    def test_build_app_registers_callback_handler(self):
        """Verify CallbackQueryHandler is registered."""
        from euroscope.bot.telegram_bot import EuroScopeBot

        config = MagicMock()
        config.telegram.token = "fake:test"
        config.telegram.allowed_users = []
        config.data.brave_api_key = ""
        config.llm = MagicMock()
        config.data.alphavantage_key = ""
        config.data.tiingo_key = ""
        config.data.fred_api_key = ""
        config.llm.api_key = ""
        config.llm.api_base = ""
        config.llm.model = ""
        config.llm.fallback_api_key = ""
        config.rate_limit_requests = 5
        config.rate_limit_window_minutes = 1
        config.admin_chat_ids = []
        config.vector_memory_ttl_days = 30

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
            app = bot.build_app()

        # Get all handler types
        from telegram.ext import CallbackQueryHandler
        handler_types = []
        for group in app.handlers.values():
            for handler in group:
                handler_types.append(type(handler))

        assert CallbackQueryHandler in handler_types

    def test_all_commands_registered(self):
        """Verify all expected commands are registered."""
        from euroscope.bot.telegram_bot import EuroScopeBot

        config = MagicMock()
        config.telegram.token = "fake:test"
        config.telegram.allowed_users = []
        config.data.brave_api_key = ""
        config.llm = MagicMock()
        config.data.alphavantage_key = ""
        config.data.tiingo_key = ""
        config.data.fred_api_key = ""
        config.llm.api_key = ""
        config.llm.api_base = ""
        config.llm.model = ""
        config.llm.fallback_api_key = ""
        config.rate_limit_requests = 5
        config.rate_limit_window_minutes = 1
        config.admin_chat_ids = []
        config.vector_memory_ttl_days = 30

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
            app = bot.build_app()

        from telegram.ext import CommandHandler
        registered_commands = set()
        for group in app.handlers.values():
            for handler in group:
                if isinstance(handler, CommandHandler):
                    registered_commands.update(handler.commands)

        expected = {
            "start", "help", "menu", "price", "analysis", "chart",
            "patterns", "levels", "signals", "news", "calendar",
            "forecast", "report", "accuracy", "strategy", "risk",
            "trades", "performance", "settings", "ask", "smart_analysis",
            "comprehensive_analysis", "quick_analysis",
        }
        assert expected.issubset(registered_commands)
