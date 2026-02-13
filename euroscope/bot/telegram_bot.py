"""
EuroScope Telegram Bot

Handles all user interactions through Telegram commands.
"""

import asyncio
import logging
from typing import Optional

from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from ..config import Config
from ..brain.agent import Agent
from ..brain.memory import Memory
from ..data.provider import PriceProvider
from ..data.news import NewsEngine
from ..data.calendar import EconomicCalendar
from ..data.storage import Storage
from ..analysis.technical import TechnicalAnalyzer
from ..analysis.patterns import PatternDetector
from ..analysis.levels import LevelAnalyzer
from ..analysis.signals import SignalGenerator
from ..forecast.engine import Forecaster
from ..utils.charts import generate_chart
from ..utils.formatting import truncate

logger = logging.getLogger("euroscope.bot")


class EuroScopeBot:
    """Telegram bot for EUR/USD analysis."""

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

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        if not self.config.telegram.allowed_users:
            return True  # No restrictions if empty
        return user_id in self.config.telegram.allowed_users

    async def _check_auth(self, update: Update) -> bool:
        """Check authorization and reply if not allowed."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("🔒 Unauthorized. Contact the bot admin.")
            return False
        return True

    # ─── Command Handlers ───────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not await self._check_auth(update):
            return

        welcome = (
            "🌐 *EuroScope — EUR/USD Expert Bot*\n\n"
            "I'm your personal AI assistant specialized exclusively in EUR/USD.\n\n"
            "📋 *Available Commands:*\n"
            "├ /price — Current price & daily stats\n"
            "├ /analysis — Full technical analysis\n"
            "├ /chart [tf] — Candlestick chart\n"
            "├ /patterns — Detected chart patterns\n"
            "├ /levels — Support/resistance & Fibonacci\n"
            "├ /signals — Trading signals\n"
            "├ /news — Latest EUR/USD news\n"
            "├ /calendar — Economic events\n"
            "├ /forecast — AI directional forecast\n"
            "├ /report — Comprehensive daily report\n"
            "├ /accuracy — My prediction track record\n"
            "└ /ask [question] — Ask me anything about EUR/USD\n\n"
            "💡 _Just type any message to chat with me about EUR/USD!_"
        )
        await update.message.reply_text(welcome, parse_mode="Markdown")

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
        await update.message.reply_text(msg, parse_mode="Markdown")

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

        # Price
        price = self.price_provider.get_price()

        # Multi-timeframe analysis
        analyses = {}
        for tf in ["H1", "H4", "D1"]:
            candles = self.price_provider.get_candles(tf)
            if candles is not None:
                analyses[tf] = self.technical.analyze(candles)

        # Signals
        h1_candles = self.price_provider.get_candles("H1")
        sig = self.signals.generate_signals(h1_candles, "H1") if h1_candles is not None else None

        # Levels
        d1_candles = self.price_provider.get_candles("D1", 100)
        sr = self.levels.find_support_resistance(d1_candles) if d1_candles is not None else {}

        # Build report
        lines = [
            "📋 *EUR/USD Daily Report*",
            f"🕐 Generated at {price.get('timestamp', 'N/A')}\n",
        ]

        # Price section
        if "error" not in price:
            lines.append(f"💱 *Price*: `{price['price']}` ({price['direction']} {price['change_pct']:+.3f}%)")
            lines.append(f"   Range: `{price['low']}` — `{price['high']}` ({price['spread_pips']} pips)\n")

        # Multi-TF bias
        lines.append("📊 *Multi-Timeframe Bias*")
        for tf, ta in analyses.items():
            bias = ta.get("overall_bias", "N/A")
            icon = {"Bullish": "🟢", "Bearish": "🔴"}.get(bias, "⚪")
            rsi_val = ta.get("indicators", {}).get("RSI", {}).get("value", "?")
            lines.append(f"   {tf}: {icon} {bias} (RSI: {rsi_val})")
        lines.append("")

        # Signal
        if sig and sig.get("signal") != "NONE":
            lines.append(f"🎯 *Signal*: {sig['emoji']} {sig['signal']} (score: {sig['score']:+d})")
            lines.append("")

        # Levels
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

        # Treat any text message as a question to the AI
        await update.message.reply_text("🤔 Thinking...")

        price = self.price_provider.get_price()
        answer = await self.agent.ask(
            question=text,
            current_price=str(price.get("price", "N/A")),
        )
        await update.message.reply_text(truncate(answer), parse_mode="Markdown")

    # ─── Bot Setup ──────────────────────────────────────────────

    def build_app(self) -> Application:
        """Build and configure the Telegram bot application."""
        app = Application.builder().token(self.config.telegram.token).build()

        # Register command handlers
        commands = {
            "start": self.cmd_start,
            "help": self.cmd_start,
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
            "ask": self.cmd_ask,
        }

        for cmd, handler in commands.items():
            app.add_handler(CommandHandler(cmd, handler))

        # Free-form message handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        return app

    def run(self):
        """Start the Telegram bot polling."""
        if not self.config.telegram.token:
            logger.error("Telegram token not configured!")
            return

        logger.info("🌐 EuroScope bot starting...")
        app = self.build_app()
        app.run_polling(drop_pending_updates=True)
