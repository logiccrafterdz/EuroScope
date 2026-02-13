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

logger = logging.getLogger("euroscope.bot")


class EuroScopeBot:
    """Telegram bot for EUR/USD analysis — V2 with inline keyboards."""

    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage()
        self.price_provider = PriceProvider()
        self.news_engine = NewsEngine(config.data.brave_api_key)
        self.calendar = EconomicCalendar()
        self.agent = Agent(config.llm)
        self.memory = Memory(self.storage)
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()
        self.signals = SignalGenerator()
        self.forecaster = Forecaster(self.agent, self.memory, self.price_provider, self.news_engine)

        # Phase 3-4 integrations
        self.orchestrator = Orchestrator()
        self.risk_manager = RiskManager()
        self.strategy_engine = StrategyEngine()
        self.signal_executor = SignalExecutor(self.storage)

        # Phase 5
        self.user_settings = UserSettings(self.storage)
        self.notifications = NotificationManager(self.storage)

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
        data = self.price_provider.get_price()

        if "error" in data:
            await update.message.reply_text(f"❌ {data['error']}")
            return

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

        candles = self.price_provider.get_candles(tf)
        if candles is None:
            await update.message.reply_text("❌ Could not fetch candle data.")
            return

        result = self.technical.analyze(candles)
        formatted = self.technical.format_analysis(result, tf)
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

        results = []
        for tf in ["H1", "H4", "D1"]:
            candles = self.price_provider.get_candles(tf)
            if candles is not None:
                found = self.patterns.detect_all(candles)
                for p in found:
                    p["timeframe"] = tf
                results.extend(found)

        formatted = self.patterns.format_patterns(results)
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_levels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /levels command."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Calculating key levels...")

        candles = self.price_provider.get_candles("D1", 100)
        if candles is None:
            await update.message.reply_text("❌ Could not fetch data.")
            return

        sr = self.levels.find_support_resistance(candles)
        fib = self.levels.fibonacci_retracement(candles)
        pivots = self.levels.pivot_points(candles)

        formatted = self.levels.format_levels(sr, fib, pivots)
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signals command."""
        if not await self._check_auth(update):
            return

        tf = context.args[0].upper() if context.args else "H1"
        await update.message.reply_text(f"⏳ Generating {tf} signals...")

        candles = self.price_provider.get_candles(tf)
        if candles is None:
            await update.message.reply_text("❌ Could not fetch data.")
            return

        result = self.signals.generate_signals(candles, tf)
        formatted = self.signals.format_signal(result)
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /news command."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Fetching EUR/USD news...")
        articles = await self.news_engine.get_eurusd_news()
        formatted = self.news_engine.format_news(articles)
        await update.message.reply_text(truncate(formatted), parse_mode="Markdown")

    async def cmd_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /calendar command."""
        if not await self._check_auth(update):
            return

        formatted = self.calendar.format_calendar()
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
        """Handle /report — comprehensive daily report."""
        if not await self._check_auth(update):
            return

        await update.message.reply_text("⏳ Generating comprehensive report... (this may take a moment)")

        price = self.price_provider.get_price()

        analyses = {}
        for tf in ["H1", "H4", "D1"]:
            candles = self.price_provider.get_candles(tf)
            if candles is not None:
                analyses[tf] = self.technical.analyze(candles)

        h1_candles = self.price_provider.get_candles("H1")
        sig = self.signals.generate_signals(h1_candles, "H1") if h1_candles is not None else None

        d1_candles = self.price_provider.get_candles("D1", 100)
        sr = self.levels.find_support_resistance(d1_candles) if d1_candles is not None else {}

        lines = [
            "📋 *EUR/USD Daily Report*",
            f"🕐 Generated at {price.get('timestamp', 'N/A')}\n",
        ]

        if "error" not in price:
            lines.append(f"💱 *Price*: `{price['price']}` ({price['direction']} {price['change_pct']:+.3f}%)")
            lines.append(f"   Range: `{price['low']}` — `{price['high']}` ({price['spread_pips']} pips)\n")

        lines.append("📊 *Multi-Timeframe Bias*")
        for tf, ta in analyses.items():
            bias = ta.get("overall_bias", "N/A")
            icon = {"Bullish": "🟢", "Bearish": "🔴"}.get(bias, "⚪")
            rsi_val = ta.get("indicators", {}).get("RSI", {}).get("value", "?")
            lines.append(f"   {tf}: {icon} {bias} (RSI: {rsi_val})")
        lines.append("")

        if sig and sig.get("signal") != "NONE":
            lines.append(f"🎯 *Signal*: {sig['emoji']} {sig['signal']} (score: {sig['score']:+d})")
            lines.append("")

        if sr.get("support"):
            lines.append(f"🟢 *Support*: {', '.join(f'`{s}`' for s in sr['support'][:3])}")
        if sr.get("resistance"):
            lines.append(f"🔴 *Resistance*: {', '.join(f'`{r}`' for r in sr['resistance'][:3])}")

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

        candles = self.price_provider.get_candles("H1")
        if candles is None:
            await update.message.reply_text("❌ Could not fetch data.")
            return

        ta = self.technical.analyze(candles)
        sr = self.levels.find_support_resistance(candles)
        detected = self.patterns.detect_all(candles)

        indicators = {
            "adx": ta.get("indicators", {}).get("ADX", {}).get("value"),
            "rsi": ta.get("indicators", {}).get("RSI", {}).get("value"),
            "overall_bias": ta.get("overall_bias"),
            "macd": ta.get("indicators", {}).get("MACD", {}),
        }

        levels = {
            "current_price": ta.get("price"),
            "support": sr.get("support", []),
            "resistance": sr.get("resistance", []),
        }

        strategy_sig = self.strategy_engine.detect_strategy(indicators, levels, detected)
        formatted = self.strategy_engine.format_strategy(strategy_sig)

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

        candles = self.price_provider.get_candles("H1")
        if candles is None:
            await update.message.reply_text("❌ Could not fetch data.")
            return

        ta = self.technical.analyze(candles)
        sr = self.levels.find_support_resistance(candles)
        price = ta.get("price", 0)
        atr = ta.get("indicators", {}).get("ATR", {}).get("value")

        # Assess both BUY and SELL
        buy_risk = self.risk_manager.assess_trade(
            "BUY", price, atr=atr,
            support=sr.get("support", []),
            resistance=sr.get("resistance", []),
        )
        sell_risk = self.risk_manager.assess_trade(
            "SELL", price, atr=atr,
            support=sr.get("support", []),
            resistance=sr.get("resistance", []),
        )

        msg = (
            f"{self.risk_manager.format_risk(buy_risk)}\n\n"
            f"{'─' * 25}\n\n"
            f"{self.risk_manager.format_risk(sell_risk)}"
        )
        await update.message.reply_text(truncate(msg), parse_mode="Markdown")

    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades — show open paper trades."""
        if not await self._check_auth(update):
            return

        formatted = self.signal_executor.format_open_signals()
        await update.message.reply_text(formatted, parse_mode="Markdown")

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance — show trading stats."""
        if not await self._check_auth(update):
            return

        formatted = self.signal_executor.format_performance()
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
            text = self.signal_executor.format_open_signals()
            await bot.send_message(chat_id, text, parse_mode="Markdown")
            return

        if cmd_name == "performance":
            text = self.signal_executor.format_performance()
            await bot.send_message(chat_id, text, parse_mode="Markdown")
            return

        if cmd_name == "calendar":
            text = self.calendar.format_calendar()
            await bot.send_message(chat_id, truncate(text), parse_mode="Markdown")
            return

        if cmd_name == "price":
            data = self.price_provider.get_price()
            if "error" in data:
                await bot.send_message(chat_id, f"❌ {data['error']}")
                return
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
        app = Application.builder().token(self.config.telegram.token).build()

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
        }

        for cmd, handler in commands.items():
            app.add_handler(CommandHandler(cmd, handler))

        # Callback query handler for inline buttons
        app.add_handler(CallbackQueryHandler(self.callback_handler))

        # Free-form message handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        return app

    def run(self):
        """Start the Telegram bot polling."""
        if not self.config.telegram.token:
            logger.error("Telegram token not configured!")
            return

        logger.info("🌐 EuroScope bot V2 starting...")
        app = self.build_app()

        # Set up notifications
        self.notifications.set_bot(app.bot)
        if self.config.telegram.allowed_users:
            self.notifications.schedule_daily_reports(
                app.job_queue, self.config.telegram.allowed_users
            )

        app.run_polling(drop_pending_updates=True)
