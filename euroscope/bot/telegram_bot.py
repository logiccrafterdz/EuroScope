"""
EuroScope Telegram Bot V2

Interactive bot with inline keyboards, new commands for trading brain,
and integrated notification system.
"""

import asyncio
import logging
from typing import Optional

from telegram import (
    Update, InputFile,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from ..config import Config
from ..brain.agent import Agent
from ..brain.memory import Memory
from ..brain.orchestrator import Orchestrator
from ..data.provider import PriceProvider
from ..data.news import NewsEngine
from ..data.calendar import EconomicCalendar
from ..data.storage import Storage
from ..analysis.technical import TechnicalAnalyzer
from ..analysis.patterns import PatternDetector
from ..analysis.levels import LevelAnalyzer
from ..analysis.signals import SignalGenerator
from ..forecast.engine import Forecaster
from ..trading.risk_manager import RiskManager
from ..trading.strategy_engine import StrategyEngine
from ..trading.signal_executor import SignalExecutor
from ..utils.charts import generate_chart
from ..utils.formatting import truncate
from .user_settings import UserSettings
from .notification_manager import NotificationManager

from ..skills.registry import SkillsRegistry
from ..skills.base import SkillContext
from ..workspace import WorkspaceManager
from ..automation import HeartbeatService, EventBus, SmartAlerts, AlertChannel, setup_default_alerts, CronScheduler

logger = logging.getLogger("euroscope.bot")


class EuroScopeBot:
    """Telegram bot for EUR/USD analysis — V3 Skills-Based."""

    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage()
        
        # New Skills-Based Architecture
        self.registry = SkillsRegistry()
        self.registry.discover()
        self.orchestrator = Orchestrator() # Already discover inside
        self.workspace = WorkspaceManager()
        
        # Automation & Events
        self.bus = EventBus()
        self.alerts = SmartAlerts()
        setup_default_alerts(self.alerts)
        self.heartbeat = HeartbeatService(interval=300) # 5 min health checks
        self.cron = CronScheduler()

        # Phase 5 integrations
        self.user_settings = UserSettings(self.storage)
        self.notifications = NotificationManager(self.storage)
        
        # Setup alert handler to send to Telegram
        self.alerts.register_handler(AlertChannel.TELEGRAM, self._on_alert_triggered)
        
        # Legacy components (still used by some handlers until fully migrated to skills)
        self.agent = Agent(config.llm)
        self.price_provider = PriceProvider()
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()
        self.signals = SignalGenerator()
        
        self.forecaster = Forecaster(self.agent, Memory(self.storage), self.price_provider, NewsEngine(config.data.brave_api_key))

    def _on_alert_triggered(self, alert):
        """Callback for SmartAlerts — sends to allowed users."""
        asyncio.create_task(self.notifications.broadcast_alert(alert))


    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        if not self.config.telegram.allowed_users:
            return True
        return user_id in self.config.telegram.allowed_users

    async def _check_auth(self, update: Update) -> bool:
        """Check authorization and reply if not allowed."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("🔒 Unauthorized. Contact the bot admin.")
            return False
        return True

    # ─── Main Menu ───────────────────────────────────────────

    def _main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Build the main interactive menu."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💱 Price", callback_data="cmd:price"),
                InlineKeyboardButton("📊 Analysis", callback_data="cmd:analysis"),
                InlineKeyboardButton("📈 Chart", callback_data="cmd:chart"),
            ],
            [
                InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
                InlineKeyboardButton("🔮 Forecast", callback_data="cmd:forecast"),
                InlineKeyboardButton("📰 News", callback_data="cmd:news"),
            ],
            [
                InlineKeyboardButton("🧠 Strategy", callback_data="cmd:strategy"),
                InlineKeyboardButton("🛡️ Risk", callback_data="cmd:risk"),
                InlineKeyboardButton("📋 Trades", callback_data="cmd:trades"),
            ],
            [
                InlineKeyboardButton("📊 Performance", callback_data="cmd:performance"),
                InlineKeyboardButton("📅 Calendar", callback_data="cmd:calendar"),
                InlineKeyboardButton("⚙️ Settings", callback_data="cmd:settings"),
            ],
        ])

    # ─── Command Handlers ────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start — show interactive menu."""
        if not await self._check_auth(update):
            return

        welcome = (
            "🌐 *EuroScope — EUR/USD Expert Bot*\n\n"
            "I'm your personal AI assistant specialized exclusively in EUR/USD.\n\n"
            "Tap a button below or use /help for commands 👇"
        )
        await update.message.reply_text(
            welcome,
            reply_markup=self._main_menu_keyboard(),
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help — show all commands."""
        if not await self._check_auth(update):
            return

        help_text = (
            "📋 *Available Commands:*\n\n"
            "├ /price — Current price & daily stats\n"
            "├ /analysis [tf] — Technical analysis\n"
            "├ /chart [tf] — Candlestick chart\n"
            "├ /patterns — Chart patterns\n"
            "├ /levels — Support/resistance & Fibonacci\n"
            "├ /signals — Trading signals\n"
            "├ /news — Latest EUR/USD news\n"
            "├ /calendar — Economic events\n"
            "├ /forecast — AI directional forecast\n"
            "├ /strategy — Strategy recommendation\n"
            "├ /risk — Risk assessment\n"
            "├ /trades — Open paper trades\n"
            "├ /performance — Trading stats\n"
            "├ /report — Full daily report\n"
            "├ /accuracy — Prediction track record\n"
            "├ /settings — Bot preferences\n"
            "├ /menu — Interactive menu\n"
            "└ /ask [question] — Ask about EUR/USD\n\n"
            "💡 _Just type any message to chat!_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu — show interactive menu."""
        if not await self._check_auth(update):
            return
        await update.message.reply_text(
            "📋 *EuroScope Menu*",
            reply_markup=self._main_menu_keyboard(),
            parse_mode="Markdown",
        )

    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /price command."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Fetching EUR/USD price...")
        result = self.orchestrator.run_skill("market_data", "get_price")

        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        data = result.data
        msg = (
            f"💱 *EUR/USD Price*\n\n"
            f"{data['direction']} Price: `{data['price']}`\n"
            f"📈 Open: `{data['open']}`\n"
            f"⬆️ High: `{data['high']}`\n"
            f"⬇️ Low: `{data['low']}`\n"
            f"📊 Change: `{data['change']:+.5f}` ({data['change_pct']:+.3f}%)\n"
            f"📏 Range: `{data['spread_pips']} pips`\n\n"
            f"🕐 {data['timestamp']}"
        )

        # Quick action buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Analysis", callback_data="cmd:analysis"),
                InlineKeyboardButton("📈 Chart", callback_data="cmd:chart"),
                InlineKeyboardButton("🎯 Signal", callback_data="cmd:signals"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analysis command."""
        if not await self._check_auth(update):
            return

        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Running {tf} technical analysis...")

        result = self.orchestrator.run_skill("technical_analysis", "analyze", timeframe=tf)
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        # Formatting is now part of what we get back or can be handled by skill
        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /chart command."""
        if not await self._check_auth(update):
            return

        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Generating {tf} chart...")

        candles = self.price_provider.get_candles(tf, count=80)
        if candles is None:
            await update.message.reply_text("❌ Could not fetch candle data.")
            return

        chart_path = generate_chart(candles, tf)
        if chart_path:
            with open(chart_path, "rb") as f:
                await update.message.reply_photo(
                    photo=InputFile(f),
                    caption=f"📊 EUR/USD — {tf} Chart"
                )
        else:
            await update.message.reply_text("❌ Chart generation failed.")

    async def cmd_patterns(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /patterns command."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Scanning for patterns...")

        result = self.orchestrator.run_skill("technical_analysis", "detect_patterns")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_levels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /levels command."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Calculating key levels...")
        result = self.orchestrator.run_skill("technical_analysis", "find_levels")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signals command."""
        if not await self._check_auth(update):
            return

        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Generating {tf} signals...")

        result = self.orchestrator.run_skill("trading_strategy", "detect_signal", timeframe=tf)
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /news command."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Fetching EUR/USD news...")
        result = self.orchestrator.run_skill("fundamental_analysis", "get_news")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /calendar command."""
        if not await self._check_auth(update):
            return

        result = self.orchestrator.run_skill("fundamental_analysis", "get_calendar")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_forecast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /forecast command."""
        if not await self._check_auth(update):
            return

        tf = " ".join(context.args) if context.args else "24 hours"
        await update.message.reply_text(f"⏳ Generating AI forecast for {tf}...")

        result = await self.forecaster.generate_forecast(tf)
        header = (
            f"🔮 *EUR/USD Forecast ({tf})*\n\n"
            f"Direction: {'🟢 BULLISH' if result['direction'] == 'BULLISH' else '🔴 BEARISH' if result['direction'] == 'BEARISH' else '⚪ NEUTRAL'}\n"
            f"Confidence: {result['confidence']:.0f}%\n"
            f"{'─' * 25}\n\n"
        )
        full_msg = header + result["text"]
        await update.message.reply_text(truncate(full_msg), parse_mode="Markdown")

    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /report — comprehensive analysis report using skills pipeline."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Generating comprehensive report using skills pipeline...")

        # Run the full analysis pipeline
        tf = context.args[0].upper() if context.args else "H1"
        ctx = self.orchestrator.run_full_analysis_pipeline(timeframe=tf)

        # Build report from context
        lines = [
            "📋 *EuroScope Skills Report*",
            f"🕐 Generated at {ctx.market_data.get('price', {}).get('timestamp', 'N/A')}\n",
        ]

        # Price section
        price = ctx.market_data.get("price", {})
        if price:
            lines.append(f"💱 *Price*: `{price['price']}` ({price['direction']} {price['change_pct']:+.3f}%)")
            lines.append(f"   Range: `{price['low']}` — `{price['high']}` ({price['spread_pips']} pips)\n")

        # Analysis section
        ta = ctx.analysis.get("indicators", {})
        if ta:
            bias = ta.get("overall_bias", "N/A")
            icon = {"Bullish": "🟢", "Bearish": "🔴"}.get(bias, "⚪")
            rsi_val = ta.get("indicators", {}).get("RSI", {}).get("value", "?")
            lines.append(f"📊 *Technical Bias*: {icon} {bias} (RSI: {rsi_val})")

        # Signal section
        sig = ctx.signals
        if sig and sig.get("direction") != "NONE":
            lines.append(f"🎯 *Signal*: {sig.get('direction')} (Score: {sig.get('score', 0):+d})")

        # Risk section
        risk = ctx.risk
        if risk:
            lines.append(f"�️ *Risk*: {'Approved ✅' if risk.get('approved') else 'Rejected ❌'}")
            lines.append(f"   SL: `{risk.get('stop_loss')}` | TP: `{risk.get('take_profit')}`")

        await update.message.reply_text(truncate("\n".join(lines)), parse_mode="Markdown")

    async def cmd_accuracy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /accuracy command."""
        if not await self._check_auth(update):
            return

        report = self.memory.get_accuracy_report()
        await update.message.reply_text(report, parse_mode="Markdown")

    # ─── New Phase 3-4 Commands ──────────────────────────────

    async def cmd_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /strategy — detect market regime and recommend strategy."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Analyzing market regime...")
        result = self.orchestrator.run_skill("trading_strategy", "detect_signal")

        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🛡️ Risk Check", callback_data="cmd:risk"),
                InlineKeyboardButton("🎯 Signal", callback_data="cmd:signals"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(
            truncate(formatted), reply_markup=keyboard, parse_mode="Markdown"
        )

    async def cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk — assess trade risk for current conditions."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Assessing trade risk...")
        result = self.orchestrator.run_skill("risk_management", "assess_trade")
        
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades — show open paper trades."""
        if not await self._check_auth(update):
            return

        result = self.orchestrator.run_skill("signal_executor", "list_trades")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(formatted, parse_mode="Markdown")

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance — show trading stats."""
        if not await self._check_auth(update):
            return

        result = self.orchestrator.run_skill("performance_analytics", "get_snapshot")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(formatted, parse_mode="Markdown")

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings — show settings with inline keyboard."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        text, keyboard = self.user_settings.build_settings_keyboard(chat_id)
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ask [question] command."""
        if not await self._check_auth(update):
            return

        if not context.args:
            await update.message.reply_text("❓ Usage: /ask [your question about EUR/USD]")
            return

        question = " ".join(context.args)
        await update.message.reply_text("🤔 Thinking...")

        price = self.price_provider.get_price()
        h1_candles = self.price_provider.get_candles("H1")
        ta = self.technical.analyze(h1_candles) if h1_candles is not None else {}
        sr = self.levels.find_support_resistance(h1_candles) if h1_candles is not None else {}

        answer = await self.agent.ask(
            question=question,
            current_price=str(price.get("price", "N/A")),
            current_bias=ta.get("overall_bias", "N/A"),
            support=str(sr.get("support", ["N/A"])[:2]),
            resistance=str(sr.get("resistance", ["N/A"])[:2]),
        )
        await update.message.reply_text(truncate(answer), parse_mode="Markdown")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free-form text messages — treat as questions."""
        if not await self._check_auth(update):
            return

        text = update.message.text
        if not text:
            return

        await update.message.reply_text("🤔 Thinking...")

        price = self.price_provider.get_price()
        answer = await self.agent.ask(
            question=text,
            current_price=str(price.get("price", "N/A")),
        )
        await update.message.reply_text(truncate(answer), parse_mode="Markdown")

    # ─── Callback Query Handler ──────────────────────────────

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Route inline keyboard button presses."""
        query = update.callback_query
        await query.answer()

        data = query.data

        # Settings callbacks
        if data.startswith("settings:"):
            await self.user_settings.handle_callback(update, context)
            return

        # Menu callback
        if data == "menu:main":
            await query.edit_message_text(
                "📋 *EuroScope Menu*",
                reply_markup=self._main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        # Command callbacks — send a new message with the result
        cmd_map = {
            "cmd:price": "Fetching price...",
            "cmd:analysis": "Running analysis...",
            "cmd:chart": "Generating chart...",
            "cmd:signals": "Generating signals...",
            "cmd:forecast": "Generating forecast...",
            "cmd:news": "Fetching news...",
            "cmd:calendar": "Loading calendar...",
            "cmd:strategy": "Analyzing strategy...",
            "cmd:risk": "Assessing risk...",
            "cmd:trades": "Loading trades...",
            "cmd:performance": "Loading performance...",
            "cmd:settings": "Loading settings...",
        }

        if data in cmd_map:
            # Map callback to the command method name
            cmd_name = data.split(":")[1]
            method = getattr(self, f"cmd_{cmd_name}", None)
            if method:
                # Create a pseudo-update that allows the handler to work
                # We send a new message from the bot, not editing the button message
                chat_id = query.message.chat_id
                await self._bot_send_and_handle(
                    context.bot, chat_id, cmd_name, method, context
                )

    async def _bot_send_and_handle(self, bot, chat_id: int, cmd_name: str,
                                   handler, context: ContextTypes.DEFAULT_TYPE):
        """Execute a command handler triggered by a callback button."""
        # For settings, handle differently
        if cmd_name == "settings":
            text, keyboard = self.user_settings.build_settings_keyboard(chat_id)
            await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="Markdown")
            return

        if cmd_name == "trades":
            result = self.orchestrator.run_skill("signal_executor", "list_trades")
            text = result.metadata.get("formatted", str(result.data))
            await bot.send_message(chat_id, text, parse_mode="Markdown")
            return

        if cmd_name == "performance":
            result = self.orchestrator.run_skill("performance_analytics", "get_snapshot")
            text = result.metadata.get("formatted", str(result.data))
            await bot.send_message(chat_id, text, parse_mode="Markdown")
            return

        if cmd_name == "calendar":
            result = self.orchestrator.run_skill("fundamental_analysis", "get_calendar")
            text = result.metadata.get("formatted", str(result.data))
            await bot.send_message(chat_id, truncate(text), parse_mode="Markdown")
            return

        if cmd_name == "price":
            result = self.orchestrator.run_skill("market_data", "get_price")
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            data = result.data
            msg = (
                f"💱 *EUR/USD Price*\n\n"
                f"{data['direction']} Price: `{data['price']}`\n"
                f"📊 Change: `{data['change']:+.5f}` ({data['change_pct']:+.3f}%)\n"
                f"📏 Range: `{data['spread_pips']} pips`"
            )
            await bot.send_message(chat_id, msg, parse_mode="Markdown")
            return

        # For data-heavy commands, just prompt the user
        await bot.send_message(
            chat_id,
            f"💡 Use `/{cmd_name}` command directly for full results.",
            parse_mode="Markdown",
        )

    # ─── Bot Setup ───────────────────────────────────────────

    def build_app(self) -> Application:
        """Build and configure the Telegram bot application."""
        app = Application.builder() \
            .token(self.config.telegram.token) \
            .post_init(self.post_init) \
            .build()

        # Register command handlers
        commands = {
            "start": self.cmd_start,
            "help": self.cmd_help,
            "menu": self.cmd_menu,
            "price": self.cmd_price,
            "analysis": self.cmd_analysis,
            "chart": self.cmd_chart,
            "patterns": self.cmd_patterns,
            "levels": self.cmd_levels,
            "signals": self.cmd_signals,
            "news": self.cmd_news,
            "calendar": self.cmd_calendar,
            "forecast": self.cmd_forecast,
            "report": self.cmd_report,
            "accuracy": self.cmd_accuracy,
            "strategy": self.cmd_strategy,
            "risk": self.cmd_risk,
            "trades": self.cmd_trades,
            "performance": self.cmd_performance,
            "settings": self.cmd_settings,
            "ask": self.cmd_ask,
            "health": self.cmd_health,
        }

        for cmd, handler in commands.items():
            app.add_handler(CommandHandler(cmd, handler))

        # Callback query handler for inline buttons
        app.add_handler(CallbackQueryHandler(self.callback_handler))

        # Free-form message handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        return app

    async def post_init(self, application: Application):
        """Called after bot is initialized, before polling starts."""
        # Start automation services
        asyncio.create_task(self.heartbeat.start())
        asyncio.create_task(self.cron.start())
        logger.info("⚡ Background services (Heartbeat, Cron) started.")

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /health — system health and runtime stats."""
        if not await self._check_auth(update):
            return

        result = self.orchestrator.run_skill("monitoring", "runtime_stats")
        text = result.metadata.get("formatted", "⚠️ Could not fetch health stats.")
        await update.message.reply_text(text, parse_mode="Markdown")

    def run(self):
        """Start the Telegram bot polling and automation services."""
        if not self.config.telegram.token:
            logger.error("Telegram token not configured!")
            return

        logger.info("🌐 EuroScope bot V3 starting...")
        
        # Build app (now includes post_init)
        app = self.build_app()

        # Set up notifications
        self.notifications.set_bot(app.bot)
        if self.config.telegram.allowed_users:
            self.notifications.schedule_daily_reports(
                app.job_queue, self.config.telegram.allowed_users
            )

        app.run_polling(drop_pending_updates=True)
