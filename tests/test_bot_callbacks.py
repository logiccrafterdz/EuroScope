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
            "comprehensive_analysis", "quick_analysis", "daily_summary",
        }
        assert expected.issubset(registered_commands)

    @pytest.mark.asyncio
    async def test_daily_summary_command(self):
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

        update = MagicMock()
        update.effective_user.id = 123
        update.effective_chat.id = 123
        update.message.reply_text = AsyncMock()

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

        bot.daily_tracker.get_summary = MagicMock(return_value={
            "date": "2026-02-17",
            "signals_generated": 5,
            "signals_executed": 2,
            "signals_rejected": 3,
            "rejection_reasons": {"high_uncertainty": 2, "emergency_mode": 1},
            "avg_confidence": 0.68,
            "max_uncertainty": 0.82,
            "max_uncertainty_time": "2026-02-17T14:23:00",
            "max_uncertainty_reason": "Lagarde speech",
        })
        bot._check_auth = AsyncMock(return_value=True)

        await bot.cmd_daily_summary(update, MagicMock())

        update.message.reply_text.assert_awaited_once()
        args, kwargs = update.message.reply_text.call_args
        text = args[0]
        assert "Today's Activity (Feb 17)" in text
        assert "Signals executed: 2/5" in text
        assert "Rejected: 3" in text
        assert kwargs.get("parse_mode") == "HTML"

    @pytest.mark.asyncio
    async def test_signals_command(self):
        from euroscope.bot.telegram_bot import EuroScopeBot
        from euroscope.skills.base import SkillResult

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

        update = MagicMock()
        update.effective_user.id = 123
        update.effective_chat.id = 123
        update.message.reply_text = AsyncMock()

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

        async def run_skill(skill_name, action, **_):
            if skill_name == "market_data":
                return SkillResult(success=True, data={})
            if skill_name == "technical_analysis":
                return SkillResult(success=True, data={"indicators": {}, "patterns": [], "levels": {}})
            if skill_name == "trading_strategy":
                return SkillResult(success=True, data={"direction": "WAIT"}, metadata={"formatted": "ok"})
            return SkillResult(success=False, error="unknown")

        bot._check_auth = AsyncMock(return_value=True)
        bot.orchestrator.run_skill = AsyncMock(side_effect=run_skill)
        context = MagicMock()
        context.args = []

        await bot.cmd_signals(update, context)

        assert update.message.reply_text.await_count >= 2
        args, kwargs = update.message.reply_text.call_args
        assert "ok" in args[0]
        assert kwargs.get("parse_mode") == "Markdown"
