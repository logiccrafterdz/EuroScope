"""
EuroScope Telegram Bot V2

Interactive bot with inline keyboards, new commands for trading brain,
and integrated notification system.
"""

import asyncio
import logging
import re
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
from telegram import BotCommand

from ..config import Config
from ..brain.agent import Agent
from ..brain.memory import Memory
from ..brain.orchestrator import Orchestrator
from ..brain.llm_router import LLMRouter, LLMProvider
from ..brain.vector_memory import VectorMemory
from ..learning.pattern_tracker import PatternTracker
from ..learning.adaptive_tuner import AdaptiveTuner
from ..data.provider import PriceProvider
from ..data.news import NewsEngine
from ..data.calendar import EconomicCalendar
from ..data.fundamental import FundamentalDataProvider
from ..data.storage import Storage
from ..forecast.engine import Forecaster
from ..trading.risk_manager import RiskManager
from ..trading.strategy_engine import StrategyEngine
from ..trading.signal_executor import SignalExecutor
from ..utils.charts import generate_chart
from ..utils.formatting import truncate, safe_markdown
from .user_settings import UserSettings
from .notification_manager import NotificationManager

from ..skills.registry import SkillsRegistry
from ..skills.base import SkillContext
from ..workspace import WorkspaceManager
from ..automation import HeartbeatService, EventBus, SmartAlerts, AlertChannel, setup_default_alerts, CronScheduler, TaskFrequency

logger = logging.getLogger("euroscope.bot")


class EuroScopeBot:
    """Telegram bot for EUR/USD analysis — V3 Skills-Based."""

    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage()
        
        # New Skills-Based Architecture
        self.orchestrator = Orchestrator()  # discovers skills internally
        self.registry = self.orchestrator.registry  # share single registry
        self.workspace = WorkspaceManager()
        
        # Automation & Events
        self.bus = EventBus()
        self.alerts = SmartAlerts()
        setup_default_alerts(self.alerts)
        self.heartbeat = HeartbeatService(interval=300, event_bus=self.bus)
        self.cron = CronScheduler()

        # Phase 5 integrations
        self.user_settings = UserSettings(self.storage)
        self.notifications = NotificationManager(self.storage)
        self.notifications.set_orchestrator(self.orchestrator)
        
        # Setup alert handler to send to Telegram
        self.alerts.register_handler(AlertChannel.TELEGRAM, self._on_alert_triggered)
        
        # Sub-systems
        self.price_provider = PriceProvider()
        self.macro_provider = FundamentalDataProvider(config.data.fred_api_key)
        self.news_engine = NewsEngine(config.data.brave_api_key, self.storage) # Key ignored in DDG version
        self.calendar = EconomicCalendar()
        
        # LLM & Memory
        self.router = LLMRouter.from_config(
            primary_key=config.llm.api_key,
            primary_base=config.llm.api_base,
            primary_model=config.llm.model,
            fallback_key=config.llm.api_key, # Can add separate fallback keys here
        )
        self.vector_memory = VectorMemory()
        self.agent = Agent(config.llm, router=self.router, vector_memory=self.vector_memory)
        self.memory = Memory(self.storage)
        
        # Learning Module
        self.pattern_tracker = PatternTracker(self.storage)
        self.adaptive_tuner = AdaptiveTuner(self.storage)
        
        self.forecaster = Forecaster(self.agent, self.memory, self.orchestrator, pattern_tracker=self.pattern_tracker)

        self.orchestrator.set_alerts(self.alerts)
        market_data_skill = self.registry.get("market_data")
        
        # Inject dependencies into the skills system
        self.orchestrator.inject_dependencies(
            price_provider=self.price_provider,
            macro_provider=self.macro_provider,
            news_engine=self.news_engine,
            calendar=self.calendar,
            storage=self.storage,
            agent=self.agent,
            vector_memory=self.vector_memory,
            pattern_tracker=self.pattern_tracker,
            adaptive_tuner=self.adaptive_tuner,
            risk_manager=RiskManager(),
            event_bus=self.bus,
            heartbeat=self.heartbeat,
            market_data_skill=market_data_skill,
            global_context=self.orchestrator.global_context
        )

    def _on_alert_triggered(self, alert):
        """Callback for SmartAlerts — sends to allowed users."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.notifications.broadcast_alert(alert))
        except RuntimeError:
            logger.warning("Alert triggered outside event loop — skipped.")


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
                InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
            ],
            [
                InlineKeyboardButton("🔮 Forecast", callback_data="cmd:forecast"),
                InlineKeyboardButton("📈 Chart", callback_data="cmd:chart"),
                InlineKeyboardButton("🧠 Strategy", callback_data="cmd:strategy"),
            ],
            [
                InlineKeyboardButton("📰 News", callback_data="cmd:news"),
                InlineKeyboardButton("📅 Calendar", callback_data="cmd:calendar"),
                InlineKeyboardButton("📋 Report", callback_data="cmd:report"),
            ],
            [
                InlineKeyboardButton("📍 Levels", callback_data="cmd:levels"),
                InlineKeyboardButton("🧩 Patterns", callback_data="cmd:patterns"),
                InlineKeyboardButton("🛡️ Risk", callback_data="cmd:risk"),
            ],
            [
                InlineKeyboardButton("📋 Trades", callback_data="cmd:trades"),
                InlineKeyboardButton("📊 Performance", callback_data="cmd:performance"),
                InlineKeyboardButton("🧠 Accuracy", callback_data="cmd:accuracy"),
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="cmd:settings"),
                InlineKeyboardButton("🧪 Health", callback_data="cmd:health"),
                InlineKeyboardButton("🔔 Alerts", callback_data="settings:manage_alerts"),
            ],
        ])

    def _is_compact_mode(self, chat_id: int) -> bool:
        prefs = self.user_settings.get_prefs(chat_id)
        return bool(prefs.get("compact_mode"))

    def _format_for_user(self, chat_id: int, text: str, max_length: int = 4096) -> str:
        if self._is_compact_mode(chat_id):
            return truncate(text, max_length=1200)
        return truncate(text, max_length=max_length)

    def _preferred_timeframe(self, chat_id: int) -> str:
        prefs = self.user_settings.get_prefs(chat_id)
        return (prefs.get("preferred_timeframe") or "H1").upper()

    def _preferred_language(self, chat_id: int, text: str = "") -> str:
        prefs = self.user_settings.get_prefs(chat_id)
        lang = prefs.get("language")
        if lang in ("ar", "en"):
            return lang
        return "ar" if self._looks_arabic(text) else "en"

    def _looks_arabic(self, text: str) -> bool:
        return bool(re.search(r"[\u0600-\u06FF]", text or ""))

    def _is_market_status_question(self, text: str) -> bool:
        t = (text or "").lower()
        arabic = [
            "السوق", "مغلق", "مفتوح", "جلسة", "جلسات", "تداول", "متى يفتح", "متى يغلق"
        ]
        english = [
            "market", "open", "closed", "session", "trading hours", "weekend"
        ]
        if any(k in t for k in english):
            return True
        return any(k in (text or "") for k in arabic)

    async def _get_market_status(self) -> dict:
        result = await self.orchestrator.run_skill("market_data", "check_market_status")
        return result.data if result.success else {}

    def _translate_market_reason(self, reason: str) -> str:
        if not reason:
            return ""
        if "Friday" in reason:
            return "السوق مغلق لعطلة نهاية الأسبوع (الجمعة 5:00 مساءً بتوقيت نيويورك)."
        if "Saturday" in reason:
            return "السوق مغلق (السبت)."
        if "Sunday" in reason:
            return "السوق يفتح قريبًا (الأحد 5:00 مساءً بتوقيت نيويورك)."
        if "Trading sessions are active" in reason:
            return "السوق مفتوح وجلسات التداول نشطة."
        return reason

    def _format_market_status_reply(self, data: dict, lang: str) -> str:
        is_open = data.get("is_open")
        status = "مفتوح" if is_open else "مغلق"
        time_et = data.get("current_time_et", "N/A")
        reason = data.get("reason", "")
        if lang == "ar":
            reason = self._translate_market_reason(reason)
            return (
                "🕒 *حالة السوق الحالية لزوج EUR/USD:*\n\n"
                f"السوق *{status}* حاليًا.\n\n"
                f"⏱️ الوقت الحالي (ET): `{time_et}`\n"
                f"📝 السبب: {reason}\n\n"
                "🧭 جلسات التداول (GMT):\n"
                "• لندن: 07:00 - 16:00\n"
                "• نيويورك: 12:00 - 21:00\n"
            )
        return (
            "🕒 *EUR/USD Market Status:*\n\n"
            f"The market is *{'OPEN' if is_open else 'CLOSED'}* right now.\n\n"
            f"⏱️ Current time (ET): `{time_et}`\n"
            f"📝 Reason: {reason or 'N/A'}\n\n"
            "🧭 Main sessions (GMT):\n"
            "• London: 07:00 - 16:00\n"
            "• New York: 12:00 - 21:00\n"
        )

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

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings — show user preferences menu."""
        if not await self._check_auth(update):
            return
        
        text, keyboard = self.user_settings.build_settings_keyboard(update.effective_chat.id)
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alert [above/below] [rate] — set a price alert."""
        if not await self._check_auth(update):
            return

        args = context.args
        usage = "💡 *Usage*: `/alert above 1.0850` or `/alert below 1.0700`"
        
        if len(args) < 2:
            await update.message.reply_text(usage, parse_mode="Markdown")
            return

        condition = args[0].lower()
        if condition not in ("above", "below"):
            await update.message.reply_text(f"❌ Invalid condition '{condition}'. Use 'above' or 'below'.", parse_mode="Markdown")
            return

        try:
            target = float(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid price target. Please use a number like `1.0850`.", parse_mode="Markdown")
            return

        alert_id = self.storage.add_alert(condition, target, update.effective_chat.id)
        await update.message.reply_text(
            f"✅ *Alert Set!*\nI'll notify you when EUR/USD moves *{condition}* `{target}`.",
            parse_mode="Markdown"
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
            "├ /alert [above/below] [price] — Set price level alert\n"
            "├ /performance — Trading stats\n"
            "├ /report — Full daily report\n"
            "├ /accuracy — Prediction track record\n"
            "├ /settings — Bot preferences & alerts\n"
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
        result = await self.orchestrator.run_skill("market_data", "get_price")

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

        chat_id = update.effective_chat.id
        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Running {tf} technical analysis...")

        result = await self.orchestrator.run_skill("technical_analysis", "analyze", timeframe=tf)
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        # Formatting is now part of what we get back or can be handled by skill
        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📈 Chart", callback_data="cmd:chart"),
                InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
                InlineKeyboardButton("🔮 Forecast", callback_data="cmd:forecast"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(
            safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
        )

    async def cmd_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /chart command."""
        if not await self._check_auth(update):
            return

        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Generating {tf} chart...")

        candles = await self.price_provider.get_candles(tf, count=80)
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

        chat_id = update.effective_chat.id
        await update.message.reply_text("⏳ Scanning for patterns...")

        result = await self.orchestrator.run_skill("technical_analysis", "detect_patterns")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    async def cmd_levels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /levels command."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        await update.message.reply_text("⏳ Calculating key levels...")
        result = await self.orchestrator.run_skill("technical_analysis", "find_levels")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    async def cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signals command."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Generating {tf} signals...")

        # Run analysis first to populate context
        ctx = SkillContext()
        
        # 1. Technical Analysis (Full)
        res_ta = await self.orchestrator.run_skill("technical_analysis", "full", context=ctx, timeframe=tf)
        if not res_ta.success:
            await update.message.reply_text(f"❌ Analysis failed: {res_ta.error}")
            return

        # 2. Trading Strategy
        result = await self.orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
        if not result.success:
            await update.message.reply_text(f"❌ Result generation failed: {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🛡️ Risk", callback_data="cmd:risk"),
                InlineKeyboardButton("📋 Trades", callback_data="cmd:trades"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(
            safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
        )

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /news command."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        await update.message.reply_text("⏳ Fetching EUR/USD news...")
        result = await self.orchestrator.run_skill("fundamental_analysis", "get_news")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📅 Calendar", callback_data="cmd:calendar"),
                InlineKeyboardButton("🔮 Forecast", callback_data="cmd:forecast"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(
            safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
        )

    async def cmd_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /calendar command."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        result = await self.orchestrator.run_skill("fundamental_analysis", "get_calendar")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    async def cmd_forecast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /forecast command."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
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
        full_msg = self._format_for_user(chat_id, full_msg)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Analysis", callback_data="cmd:analysis"),
                InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(
            safe_markdown(full_msg), reply_markup=keyboard, parse_mode="Markdown"
        )

    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /report — comprehensive analysis report using skills pipeline."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        await update.message.reply_text("⏳ Generating comprehensive report using skills pipeline...")

        # Run the full analysis pipeline
        tf = context.args[0].upper() if context.args else "H1"
        ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe=tf)

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

        report = self._format_for_user(chat_id, "\n".join(lines))
        await update.message.reply_text(safe_markdown(report), parse_mode="Markdown")

    async def cmd_accuracy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /accuracy command."""
        if not await self._check_auth(update):
            return

        report = self.memory.get_accuracy_report()
        await update.message.reply_text(safe_markdown(report), parse_mode="Markdown")

    # ─── New Phase 3-4 Commands ──────────────────────────────

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /macro — show interest rates and yield spreads."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Fetching institutional macro data...")
        result = await self.orchestrator.run_skill("fundamental_analysis", "get_macro")
        
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backtest — run historical simulation."""
        if not await self._check_auth(update):
            return

        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 30
        await update.message.reply_text(f"⏳ Running {days}-day strategy backtest...")

        # Backtest skilled is technically part of analytics or a dedicated skill
        # Assuming we have a backtesting skill or we call the engine directly via a skill
        result = await self.orchestrator.run_skill("backtesting", "run_backtest", days=days)
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    async def cmd_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /strategy — detect market regime and recommend strategy."""
        if not await self._check_auth(update):
            return

        chat_id = update.effective_chat.id
        await update.message.reply_text("⏳ Analyzing market regime...")
        ctx = SkillContext()

        # 1. Analysis
        res_ta = await self.orchestrator.run_skill("technical_analysis", "full", context=ctx)
        if not res_ta.success:
            await update.message.reply_text(f"❌ Analysis failed: {res_ta.error}")
            return

        # 2. Strategy
        result = await self.orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)

        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        formatted = self._format_for_user(chat_id, formatted)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🛡️ Risk Check", callback_data="cmd:risk"),
                InlineKeyboardButton("🎯 Signal", callback_data="cmd:signals"),
            ],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
        ])
        await update.message.reply_text(
            safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
        )

    async def cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk — assess trade risk for current conditions."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Assessing trade risk...")
        
        ctx = SkillContext()
        # 1. Analysis (for ATR and levels)
        res_ta = await self.orchestrator.run_skill("technical_analysis", "full", context=ctx)
        if not res_ta.success:
            await update.message.reply_text(f"❌ Analysis failed: {res_ta.error}")
            return

        # 2. Risk Assessment
        result = await self.orchestrator.run_skill("risk_management", "assess_trade", context=ctx)
        
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        # RiskManagementSkill needs formatting too? 
        # It currently returns data dict. Let's start by just dumping it or I should add formatting to Risk skill.
        # For now, let's use the raw data if formatted missing, but ideally I add formatting to Risk skill.
        formatted = result.metadata.get("formatted", self._format_risk(result.data))
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    def _format_risk(self, data: dict) -> str:
        # Fallback formatter if skill doesn't provide one
        lines = ["🛡️ *Risk Assessment*"]
        lines.append(f"Approved: {'✅' if data.get('approved') else '❌'}")
        lines.append(f"Size: `{data.get('position_size', 0):.2f}` lots")
        lines.append(f"SL: `{data.get('stop_loss', 0):.5f}`")
        lines.append(f"TP: `{data.get('take_profit', 0):.5f}`")
        lines.append(f"Risk: `{data.get('risk_pips', 0):.1f}` pips")
        return "\n".join(lines)

    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades — show open paper trades."""
        if not await self._check_auth(update):
            return

        result = await self.orchestrator.run_skill(
            "trade_journal",
            "get_journal",
            status="open",
            limit=50,
        )
        if not result.success:
            result = await self.orchestrator.run_skill("signal_executor", "list_trades")
            if not result.success:
                await update.message.reply_text(f"❌ {result.error}")
                return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance — show trading stats."""
        if not await self._check_auth(update):
            return

        result = await self.orchestrator.run_skill("performance_analytics", "get_snapshot")
        if not result.success:
            await update.message.reply_text(f"❌ {result.error}")
            return

        formatted = result.metadata.get("formatted", str(result.data))
        await update.message.reply_text(safe_markdown(formatted), parse_mode="Markdown")

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

        chat_id = update.effective_chat.id
        lang = self._preferred_language(chat_id, question)
        market_status = await self._get_market_status()
        if self._is_market_status_question(question):
            reply = self._format_market_status_reply(market_status, lang)
            await update.message.reply_text(reply, parse_mode="Markdown")
            return

        price = await self.price_provider.get_price()
        h1_candles = await self.price_provider.get_candles("H1")
        ta = self.technical.analyze(h1_candles) if h1_candles is not None else {}
        sr = self.levels.find_support_resistance(h1_candles) if h1_candles is not None else {}

        answer = await self.agent.ask(
            question=question,
            current_price=str(price.get("price", "N/A")),
            current_bias=ta.get("overall_bias", "N/A"),
            support=str(sr.get("support", ["N/A"])[:2]),
            resistance=str(sr.get("resistance", ["N/A"])[:2]),
            market_status=f"{market_status.get('status', 'N/A')} — {market_status.get('reason', 'N/A')} — {market_status.get('current_time_et', 'N/A')}",
        )
        await update.message.reply_text(safe_markdown(truncate(answer)), parse_mode="Markdown")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free-form text messages — treat as questions."""
        if not await self._check_auth(update):
            return

        text = update.message.text
        if not text:
            return

        await update.message.reply_text("🤔 Thinking...")

        chat_id = update.effective_chat.id
        lang = self._preferred_language(chat_id, text)
        market_status = await self._get_market_status()
        if self._is_market_status_question(text):
            reply = self._format_market_status_reply(market_status, lang)
            await update.message.reply_text(reply, parse_mode="Markdown")
            return

        price = await self.price_provider.get_price()
        answer = await self.agent.ask(
            question=text,
            current_price=str(price.get("price", "N/A")),
            market_status=f"{market_status.get('status', 'N/A')} — {market_status.get('reason', 'N/A')} — {market_status.get('current_time_et', 'N/A')}",
        )
        await update.message.reply_text(safe_markdown(truncate(answer)), parse_mode="Markdown")

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
            "cmd:report": "Generating report...",
            "cmd:levels": "Loading levels...",
            "cmd:patterns": "Scanning patterns...",
            "cmd:strategy": "Analyzing strategy...",
            "cmd:risk": "Assessing risk...",
            "cmd:trades": "Loading trades...",
            "cmd:performance": "Loading performance...",
            "cmd:accuracy": "Loading accuracy...",
            "cmd:settings": "Loading settings...",
            "cmd:health": "Loading health...",
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
            result = await self.orchestrator.run_skill("signal_executor", "list_trades")
            text = result.metadata.get("formatted", str(result.data))
            text = self._format_for_user(chat_id, text)
            await bot.send_message(chat_id, safe_markdown(text), parse_mode="Markdown")
            return

        if cmd_name == "performance":
            result = await self.orchestrator.run_skill("performance_analytics", "get_snapshot")
            text = result.metadata.get("formatted", str(result.data))
            text = self._format_for_user(chat_id, text)
            await bot.send_message(chat_id, safe_markdown(text), parse_mode="Markdown")
            return

        if cmd_name == "calendar":
            result = await self.orchestrator.run_skill("fundamental_analysis", "get_calendar")
            text = result.metadata.get("formatted", str(result.data))
            text = self._format_for_user(chat_id, text)
            await bot.send_message(chat_id, safe_markdown(text), parse_mode="Markdown")
            return

        if cmd_name == "price":
            result = await self.orchestrator.run_skill("market_data", "get_price")
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
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 Analysis", callback_data="cmd:analysis"),
                    InlineKeyboardButton("📈 Chart", callback_data="cmd:chart"),
                    InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
                ],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
            ])
            await bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode="Markdown")
            return

        if cmd_name == "analysis":
            tf = self._preferred_timeframe(chat_id)
            await bot.send_message(chat_id, f"⏳ Running {tf} technical analysis...")
            result = await self.orchestrator.run_skill("technical_analysis", "analyze", timeframe=tf)
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            formatted = result.metadata.get("formatted", str(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📈 Chart", callback_data="cmd:chart"),
                    InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
                    InlineKeyboardButton("🔮 Forecast", callback_data="cmd:forecast"),
                ],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
            ])
            await bot.send_message(
                chat_id, safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
            )
            return

        if cmd_name == "chart":
            tf = self._preferred_timeframe(chat_id)
            await bot.send_message(chat_id, f"⏳ Generating {tf} chart...")
            candles = await self.price_provider.get_candles(tf, count=80)
            if candles is None:
                await bot.send_message(chat_id, "❌ Could not fetch candle data.")
                return
            chart_path = generate_chart(candles, tf)
            if chart_path:
                with open(chart_path, "rb") as f:
                    await bot.send_photo(
                        chat_id, photo=InputFile(f), caption=f"📊 EUR/USD — {tf} Chart"
                    )
            else:
                await bot.send_message(chat_id, "❌ Chart generation failed.")
            return

        if cmd_name == "signals":
            tf = self._preferred_timeframe(chat_id)
            await bot.send_message(chat_id, f"⏳ Generating {tf} signals...")
            ctx = SkillContext()
            res_ta = await self.orchestrator.run_skill(
                "technical_analysis", "full", context=ctx, timeframe=tf
            )
            if not res_ta.success:
                await bot.send_message(chat_id, f"❌ Analysis failed: {res_ta.error}")
                return
            result = await self.orchestrator.run_skill(
                "trading_strategy", "detect_signal", context=ctx
            )
            if not result.success:
                await bot.send_message(chat_id, f"❌ Result generation failed: {result.error}")
                return
            formatted = result.metadata.get("formatted", str(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🛡️ Risk", callback_data="cmd:risk"),
                    InlineKeyboardButton("📋 Trades", callback_data="cmd:trades"),
                ],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
            ])
            await bot.send_message(
                chat_id, safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
            )
            return

        if cmd_name == "forecast":
            await bot.send_message(chat_id, "⏳ Generating AI forecast for 24 hours...")
            result = await self.forecaster.generate_forecast("24 hours")
            header = (
                "🔮 *EUR/USD Forecast (24 hours)*\n\n"
                f"Direction: {'🟢 BULLISH' if result['direction'] == 'BULLISH' else '🔴 BEARISH' if result['direction'] == 'BEARISH' else '⚪ NEUTRAL'}\n"
                f"Confidence: {result['confidence']:.0f}%\n"
                f"{'─' * 25}\n\n"
            )
            full_msg = self._format_for_user(chat_id, header + result["text"])
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 Analysis", callback_data="cmd:analysis"),
                    InlineKeyboardButton("🎯 Signals", callback_data="cmd:signals"),
                ],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
            ])
            await bot.send_message(
                chat_id, safe_markdown(full_msg), reply_markup=keyboard, parse_mode="Markdown"
            )
            return

        if cmd_name == "news":
            await bot.send_message(chat_id, "⏳ Fetching EUR/USD news...")
            result = await self.orchestrator.run_skill("fundamental_analysis", "get_news")
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            formatted = result.metadata.get("formatted", str(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📅 Calendar", callback_data="cmd:calendar"),
                    InlineKeyboardButton("🔮 Forecast", callback_data="cmd:forecast"),
                ],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
            ])
            await bot.send_message(
                chat_id, safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
            )
            return

        if cmd_name == "report":
            await bot.send_message(chat_id, "⏳ Generating comprehensive report using skills pipeline...")
            tf = self._preferred_timeframe(chat_id)
            ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe=tf)
            lines = [
                "📋 *EuroScope Skills Report*",
                f"🕐 Generated at {ctx.market_data.get('price', {}).get('timestamp', 'N/A')}\n",
            ]
            price = ctx.market_data.get("price", {})
            if price:
                lines.append(f"💱 *Price*: `{price['price']}` ({price['direction']} {price['change_pct']:+.3f}%)")
                lines.append(f"   Range: `{price['low']}` — `{price['high']}` ({price['spread_pips']} pips)\n")
            ta = ctx.analysis.get("indicators", {})
            if ta:
                bias = ta.get("overall_bias", "N/A")
                icon = {"Bullish": "🟢", "Bearish": "🔴"}.get(bias, "⚪")
                rsi_val = ta.get("indicators", {}).get("RSI", {}).get("value", "?")
                lines.append(f"📊 *Technical Bias*: {icon} {bias} (RSI: {rsi_val})")
            sig = ctx.signals
            if sig and sig.get("direction") != "NONE":
                lines.append(f"🎯 *Signal*: {sig.get('direction')} (Score: {sig.get('score', 0):+d})")
            risk = ctx.risk
            if risk:
                lines.append(f"�️ *Risk*: {'Approved ✅' if risk.get('approved') else 'Rejected ❌'}")
                lines.append(f"   SL: `{risk.get('stop_loss')}` | TP: `{risk.get('take_profit')}`")
            report = self._format_for_user(chat_id, "\n".join(lines))
            await bot.send_message(chat_id, safe_markdown(report), parse_mode="Markdown")
            return

        if cmd_name == "levels":
            await bot.send_message(chat_id, "⏳ Calculating key levels...")
            result = await self.orchestrator.run_skill("technical_analysis", "find_levels")
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            formatted = result.metadata.get("formatted", str(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            await bot.send_message(chat_id, safe_markdown(formatted), parse_mode="Markdown")
            return

        if cmd_name == "patterns":
            await bot.send_message(chat_id, "⏳ Scanning for patterns...")
            result = await self.orchestrator.run_skill("technical_analysis", "detect_patterns")
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            formatted = result.metadata.get("formatted", str(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            await bot.send_message(chat_id, safe_markdown(formatted), parse_mode="Markdown")
            return

        if cmd_name == "strategy":
            await bot.send_message(chat_id, "⏳ Analyzing market regime...")
            ctx = SkillContext()
            res_ta = await self.orchestrator.run_skill("technical_analysis", "full", context=ctx)
            if not res_ta.success:
                await bot.send_message(chat_id, f"❌ Analysis failed: {res_ta.error}")
                return
            result = await self.orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            formatted = result.metadata.get("formatted", str(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🛡️ Risk Check", callback_data="cmd:risk"),
                    InlineKeyboardButton("🎯 Signal", callback_data="cmd:signals"),
                ],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu:main")],
            ])
            await bot.send_message(
                chat_id, safe_markdown(formatted), reply_markup=keyboard, parse_mode="Markdown"
            )
            return

        if cmd_name == "risk":
            await bot.send_message(chat_id, "⏳ Assessing trade risk...")
            ctx = SkillContext()
            res_ta = await self.orchestrator.run_skill("technical_analysis", "full", context=ctx)
            if not res_ta.success:
                await bot.send_message(chat_id, f"❌ Analysis failed: {res_ta.error}")
                return
            result = await self.orchestrator.run_skill("risk_management", "assess_trade", context=ctx)
            if not result.success:
                await bot.send_message(chat_id, f"❌ {result.error}")
                return
            formatted = result.metadata.get("formatted", self._format_risk(result.data))
            formatted = self._format_for_user(chat_id, formatted)
            await bot.send_message(chat_id, safe_markdown(formatted), parse_mode="Markdown")
            return

        if cmd_name == "accuracy":
            report = self.memory.get_accuracy_report()
            report = self._format_for_user(chat_id, report)
            await bot.send_message(chat_id, safe_markdown(report), parse_mode="Markdown")
            return

        if cmd_name == "health":
            result = await self.orchestrator.run_skill("monitoring", "runtime_stats")
            text = result.metadata.get("formatted", "⚠️ Could not fetch health stats.")
            text = self._format_for_user(chat_id, text)
            await bot.send_message(chat_id, safe_markdown(text), parse_mode="Markdown")
            return

        # For data-heavy commands, just prompt the user
        await bot.send_message(
            chat_id,
            f"💡 Use `/{cmd_name}` command directly for full results.",
            parse_mode="Markdown",
        )

    # ─── Bot Setup ───────────────────────────────────────────

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler — logs and notifies the user."""
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ An internal error occurred. Please try again later."
                )
            except Exception:
                pass  # if reply itself fails, nothing more to do

    def build_app(self) -> Application:
        """Build and configure the Telegram bot application."""
        app = Application.builder() \
            .token(self.config.telegram.token) \
            .post_init(self.post_init) \
            .post_shutdown(self.post_shutdown) \
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
            "macro": self.cmd_macro,
            "backtest": self.cmd_backtest,
            "report": self.cmd_report,
            "accuracy": self.cmd_accuracy,
            "alert": self.cmd_alert,
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

        # Global error handler — catches all unhandled exceptions
        app.add_error_handler(self._error_handler)

        return app

    async def post_init(self, application: Application):
        """Called after bot is initialized, before polling starts."""
        # 1. Register commands to appear in the Telegram menu button
        cmds = [
            BotCommand("start", "Start the bot"),
            BotCommand("menu", "Show interactive menu"),
            BotCommand("price", "EUR/USD real-time price"),
            BotCommand("analysis", "Technical analysis (H1/H4)"),
            BotCommand("chart", "Generate candle chart"),
            BotCommand("signals", "Trading signals"),
            BotCommand("forecast", "AI-powered forecast"),
            BotCommand("macro", "Macro interest rates & yields"),
            BotCommand("backtest", "Run strategy backtest"),
            BotCommand("news", "Latest news (DuckDuckGo)"),
            BotCommand("health", "System status"),
            BotCommand("alert", "Set price level alert"),
            BotCommand("settings", "Bot preferences & alerts"),
            BotCommand("help", "List all commands"),
        ]
        await application.bot.set_my_commands(cmds)

        # 2. Start automation services
        asyncio.create_task(self.heartbeat.start())
        asyncio.create_task(self.cron.start())

        # 3. Schedule learning tasks
        self.cron.schedule("resolve_patterns", TaskFrequency.HOURLY, self._task_resolve_patterns)
        self.cron.schedule("daily_tuning", TaskFrequency.DAILY, self._task_daily_tuning, delay=3600)
        self.cron.schedule("weekly_reflection", TaskFrequency.WEEKLY, self._task_weekly_reflection, delay=7200)

        logger.info("⚡ Background services & Commands registered.")

    async def post_shutdown(self, application: Application):
        """Gracefully stop background services on shutdown."""
        logger.info("Shutting down background services...")
        await self.heartbeat.stop()
        await self.cron.stop()
        logger.info("✅ Background services stopped.")

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /health — system health and runtime stats."""
        if not await self._check_auth(update):
            return

        result = await self.orchestrator.run_skill("monitoring", "runtime_stats")
        text = result.metadata.get("formatted", "⚠️ Could not fetch health stats.")
        await update.message.reply_text(safe_markdown(text), parse_mode="Markdown")

    # ─── Background Learning Tasks ───────────────────────────

    async def _task_resolve_patterns(self):
        """Periodically resolve pending patterns using latest price."""
        logger.info("Cron: Running pattern resolution...")
        price_data = await self.price_provider.get_price()
        if "error" in price_data:
            return

        current_price = price_data["price"]
        self.pattern_tracker.resolve_pending(current_price)
        self.memory.resolve_pending_predictions(current_price)
        logger.info("Cron: Pattern resolution complete.")

    async def _task_daily_tuning(self):
        """Analyze trade history once a day and report recommendations."""
        logger.info("Cron: Running daily strategy tuning...")
        report = self.adaptive_tuner.format_report()
        
        # Broadcast to all authorized users
        await self.notifications.broadcast_message(
            f"🧠 *Daily Strategy Optimization*\n\n{report}",
            parse_mode="Markdown"
        )
        logger.info("Cron: Daily tuning complete.")

    async def _task_weekly_reflection(self):
        logger.info("Cron: Running weekly reflection...")
        accuracy = self.storage.get_accuracy_stats(30)
        patterns = self.pattern_tracker.get_success_rates()
        stats = self.storage.get_trade_journal_stats()
        tuner = self.adaptive_tuner.analyze()

        lines = [
            "Weekly Reflection",
            f"Prediction accuracy (30d): {accuracy.get('accuracy', 0)}% ({accuracy.get('total', 0)})",
            f"Trades: {stats.get('total', 0)} | Win rate: {stats.get('win_rate', 0)}% | Avg PnL: {stats.get('avg_pnl', 0):+.1f}p",
        ]

        if patterns:
            top = sorted(patterns.values(), key=lambda x: x["success_rate"], reverse=True)[:3]
            weak = sorted(patterns.values(), key=lambda x: x["success_rate"])[:2]
            lines.append("Top patterns: " + ", ".join(f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in top))
            lines.append("Weak patterns: " + ", ".join(f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in weak))

        if tuner.get("ready") and tuner.get("recommendations"):
            lines.append("Tuning focus: " + ", ".join(r["param"] for r in tuner["recommendations"][:3]))

        insight = " | ".join(lines)
        self.memory.save_insight(insight)
        if self.vector_memory:
            self.vector_memory.store_insight(insight, tags=["reflection", "weekly"])
        self.workspace.refresh_memory(self.storage)
        self.workspace.refresh_identity(self.storage)
        logger.info("Cron: Weekly reflection complete.")

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
