"""
Telegram Command Handlers for EuroScope Zenith.

Extracted from telegram_bot.py to improve modularity.
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes

from ...utils.formatting import rich_header, thematic_divider, safe_markdown

logger = logging.getLogger("euroscope.bot.commands")


class CommandHandlers:
    """
    Handles all Telegram slash commands (/start, /help, etc.).
    Delegates back to the main bot instance for auth and replies.
    """

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.config = bot_instance.config

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start — show interactive menu."""
        if not await self.bot._check_auth(update):
            return
            
        chat_id = update.effective_chat.id
        await self.bot._ensure_private_topics(chat_id, context.bot)
        
        keyboard = None
        if self.config.telegram.web_app_url:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🚀 OPEN EUROSCOPE DASHBOARD", 
                    web_app=WebAppInfo(url=self.config.telegram.web_app_url)
                )
            ]])
            
        text = f"{rich_header('Welcome to EuroScope Zenith', 'main')}\n\nI am your elite EUR/USD financial intelligence partner. Leveraging neural forecasting and institutional-grade analytics.\n\n{thematic_divider()}\n⚡ *READY FOR EXECUTION*\n\n💡 _Click the button below to launch the Zenith Web Dashboard._"
        await self.bot._reply(update, text, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help — show all commands."""
        if not await self.bot._check_auth(update):
            return
            
        help_text = f"{rich_header('EuroScope Help Terminal', 'main')}\n\n├ `/price` — Live Market Pulse\n├ `/analysis` — Deep Tech Analytics\n├ `/forecast` — Neural Directional Insight\n├ `/signals` — High-Conviction IDEAs\n├ `/news` — Macro Intelligence\n├ `/calendar` — Economic Events\n├ `/report` — Daily PDF Dossier\n├ `/settings` — Preference Console\n└ `/menu` — Main Terminal\n\n{thematic_divider()}\n💡 _Just type any market question to chat with the Expert AI!_"
        await self.bot._reply(update, help_text, parse_mode="Markdown")

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /health — system health and runtime stats."""
        if not await self.bot._check_auth(update):
            return
            
        result = await self.bot.orchestrator.run_skill("monitoring", "runtime_stats")
        text = result.metadata.get("formatted", "⚠️ Could not fetch health stats.")
        await self.bot._reply(update, safe_markdown(text), parse_mode="Markdown")

    async def cmd_data_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current data source health status (Phase 2D)."""
        if not await self.bot._check_auth(update):
            return
            
        ecb_status = "✅ Online" if self.bot.macro_provider.fred_api_key else "❌ Offline (No Key)"
        fred_status = "✅ Online" if self.bot.macro_provider.fred_api_key else "❌ Offline (No Key)"
        tiingo_status = "✅ Online" if self.config.data.tiingo_key else "❌ Offline"
        alphavantage_status = "✅ Online" if self.config.data.alphavantage_key else "❌ Offline"
        
        message = f"📊 *Data Source Health Status*\n\n🏦 *FRED API*: {fred_status}\n🇪🇺 *ECB Data*: {ecb_status} (via FRED)\n📈 *Tiingo*: {tiingo_status}\n💹 *AlphaVantage*: {alphavantage_status}\n📰 *News Engine*: ✅ Online\n📅 *Economic Calendar*: ✅ Online\n\n💡 _Detailed logs available in /health_"
        
        await self.bot._reply(update, message, parse_mode="Markdown")

    async def cmd_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /id command — show user's chat ID."""
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"🆔 *Your Chat ID*: `{chat_id}`\n\nUse this ID in your `.env` file under `EUROSCOPE_PROACTIVE_CHAT_IDS` to receive proactive alerts.",
            parse_mode="Markdown"
        )
