"""
Notification Manager — Scheduled Reports & Real-Time Alerts

Handles:
- Daily scheduled reports via Telegram JobQueue
- Signal SL/TP hit alerts
- Price level alerts
- High-impact news forwarding
"""

import logging
from datetime import time as dt_time
from typing import Optional

from telegram import Bot
from telegram.ext import ContextTypes

from ..data.storage import Storage

logger = logging.getLogger("euroscope.bot.notifications")


class NotificationManager:
    """
    Manages scheduled and event-driven notifications.

    Uses Telegram's JobQueue for scheduling and direct Bot API
    for real-time alerts.
    """

    def __init__(self, storage: Storage):
        self.storage = storage
        self._bot: Optional[Bot] = None
        self._orchestrator = None

    def set_bot(self, bot: Bot):
        """Set the bot instance for sending messages."""
        self._bot = bot

    def set_orchestrator(self, orchestrator):
        """Set the orchestrator for running analysis skills."""
        self._orchestrator = orchestrator

    # ─── Scheduled Reports ───────────────────────────────────

    async def schedule_daily_reports(self, job_queue, chat_ids: list[int]):
        """
        Schedule daily reports for each user based on their preferences.

        Args:
            job_queue: Telegram's JobQueue
            chat_ids: List of authorized user chat IDs
        """
        for chat_id in chat_ids:
            prefs = await self.storage.get_user_preferences(chat_id)
            if not prefs:
                await self.storage.save_user_preferences(chat_id)
                prefs = await self.storage.get_user_preferences(chat_id)

            if not prefs or not prefs.get("daily_report_enabled"):
                continue

            hour = prefs.get("daily_report_hour", 8)
            job_queue.run_daily(
                self._daily_report_job,
                time=dt_time(hour=hour, minute=0),
                chat_id=chat_id,
                name=f"daily_report_{chat_id}",
                data={"chat_id": chat_id},
            )
            logger.info(f"Scheduled daily report for chat {chat_id} at {hour:02d}:00 UTC")

    async def _daily_report_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Job callback for daily report. Sends a smart briefing summary."""
        chat_id = context.job.data["chat_id"]
        if not self._bot:
            return

        # Fetch basic context for briefing
        price_text = "Price data unavailable"
        news_text = "No major news headlines"

        if self._orchestrator:
            try:
                # 1. Get current price
                p_res = await self._orchestrator.run_skill("market_data", "get_price")
                if p_res.success:
                    price_text = f"Current: `{p_res.data.get('price', '?')}` (`{p_res.data.get('bid', '?')}` / `{p_res.data.get('ask', '?')}`)"
                
                # 2. Get top news
                n_res = await self._orchestrator.run_skill("fundamental_analysis", "get_news", limit=3)
                if n_res.success and n_res.data:
                    news_text = "\n".join([f"• {a['title']}" for a in n_res.data[:3]])
            except Exception as e:
                logger.error(f"Error gathering daily briefing data: {e}")

        msg = (
            "🌅 *Your Morning Briefing*\n\n"
            "📊 *Market Overview*\n"
            f"EUR/USD: {price_text}\n\n"
            "📰 *Top Headlines*\n"
            f"{news_text}\n\n"
            "💡 _Use /report for a deep AI analysis._"
        )

        try:
            thread_id = await self.storage.get_user_thread(chat_id, "reports")
            await self._bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                message_thread_id=thread_id
            )
            logger.info(f"Sent smart morning briefing to {chat_id} (Thread: {thread_id})")
        except Exception as e:
            logger.error(f"Failed to send daily report to {chat_id}: {e}")

    # ─── Signal Alerts ───────────────────────────────────────

    async def notify_new_signal(self, chat_id: int, signal: dict):
        """
        Notify user of a new signal, respecting confidence thresholds.
        """
        if not self._bot:
            return

        prefs = await self.storage.get_user_preferences(chat_id)
        if prefs and not prefs.get("alert_on_signals"):
            return

        # Check confidence threshold
        min_conf = prefs.get("alert_min_confidence", 60.0)
        signal_conf = signal.get("confidence", 0.0)
        if signal_conf < min_conf:
            logger.info(f"Signal {signal.get('id')} confidence ({signal_conf}) below threshold ({min_conf}) for chat {chat_id}. Skipping notify.")
            return

        msg = (
            f"🚀 *New Trading Signal*\n\n"
            f"#{signal['id']} *{signal['direction']}* @ `{signal['entry_price']}`\n"
            f"🛑 SL: `{signal['stop_loss']}`\n"
            f"🎯 TP: `{signal['take_profit']}`\n"
            f"🧠 Confidence: `{signal_conf}%`\n"
            f"📊 Timeframe: `{signal['timeframe']}`\n\n"
            f"📝 *Reasoning*: {signal.get('reasoning', 'No reasoning provided.')}"
        )

        try:
            # Signals go to the Radar topic (or a dedicated signals topic if we added one)
            # In our current TOPICS, radar is for sweeps and sensitive alerts. 
            # Let's use radar for signals too for now, or the main chat if preferred.
            # Approved plan says: "Radar for sweeps and sensitivealerts". 
            # Let's route signals to Radar.
            thread_id = await self.storage.get_user_thread(chat_id, "radar")
            await self._bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="Markdown",
                message_thread_id=thread_id
            )
        except Exception as e:
            logger.error(f"Failed to send new signal alert to {chat_id}: {e}")

    async def notify_signal_closed(self, chat_id: int, signal_result: dict):
        """
        Send alert when a signal's SL or TP is hit.

        Args:
            chat_id: Telegram chat to notify
            signal_result: Dict from SignalExecutor.close_signal()
        """
        if not self._bot:
            return

        prefs = await self.storage.get_user_preferences(chat_id)
        if prefs and not prefs.get("alert_on_signals"):
            return

        pnl = signal_result.get("pnl_pips", 0)
        icon = "✅" if signal_result.get("is_win") else "❌"
        reason = signal_result.get("reason", "unknown").replace("_", " ").title()

        msg = (
            f"🔔 *Signal Alert*\n\n"
            f"{icon} #{signal_result['id']} {signal_result['direction']} closed\n"
            f"📍 Entry: `{signal_result['entry_price']}`\n"
            f"📍 Exit: `{signal_result['exit_price']}`\n"
            f"💰 P/L: `{pnl:+.1f}` pips\n"
            f"📋 Reason: {reason}\n"
            f"🧠 Strategy: {signal_result.get('strategy', 'manual')}"
        )

        try:
            thread_id = await self.storage.get_user_thread(chat_id, "radar")
            await self._bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="Markdown",
                message_thread_id=thread_id
            )
        except Exception as e:
            logger.error(f"Failed to send signal alert to {chat_id}: {e}")

    # ─── Price Alerts ────────────────────────────────────────

    async def check_price_alerts(self, current_price: float):
        """Check all active price alerts and notify if triggered."""
        if not self._bot:
            return

        alerts = await self.storage.get_active_alerts()
        for alert in alerts:
            triggered = False
            condition = alert.get("condition", "")
            target = alert.get("target_value", 0)

            if condition == "above" and current_price >= target:
                triggered = True
            elif condition == "below" and current_price <= target:
                triggered = True

            if triggered:
                await self.storage.trigger_alert(alert["id"])
                chat_id = alert.get("chat_id")
                if chat_id:
                    try:
                        thread_id = await self.storage.get_user_thread(chat_id, "radar")
                        await self._bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"🔔 *Price Alert*\n\n"
                                f"EUR/USD {'crossed above' if condition == 'above' else 'dropped below'} "
                                f"`{target}`\n"
                                f"Current: `{current_price}`"
                            ),
                            parse_mode="Markdown",
                            message_thread_id=thread_id
                        )
                    except Exception as e:
                        logger.error(f"Failed to send price alert to {chat_id}: {e}")

    # ─── News Alerts ─────────────────────────────────────────

    async def notify_high_impact_news(self, chat_id: int, articles: list[dict]):
        """
        Forward high-impact news articles.

        Only sends to users with alert_on_news enabled.
        """
        if not self._bot:
            return

        prefs = await self.storage.get_user_preferences(chat_id)
        if prefs and not prefs.get("alert_on_news"):
            return

        high_impact = [a for a in articles if a.get("sentiment_score", 0) > 0.5
                       or a.get("sentiment_score", 0) < -0.5]

        if not high_impact:
            return

        for article in high_impact[:3]:  # Max 3 alerts
            sentiment = article.get("sentiment", "neutral")
            icon = "🟢" if sentiment == "bullish" else "🔴" if sentiment == "bearish" else "⚪"

            msg = (
                f"📰 *High-Impact News*\n\n"
                f"{icon} {article.get('title', 'No title')}\n"
                f"Sentiment: {sentiment.title()} "
                f"({article.get('sentiment_score', 0):+.2f})\n"
            )
            if article.get("url"):
                msg += f"\n🔗 [Read more]({article['url']})"

            try:
                thread_id = await self.storage.get_user_thread(chat_id, "news")
                await self._bot.send_message(
                    chat_id=chat_id, text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Failed to send news alert to {chat_id}: {e}")

    # ─── Alert Broadcasting ──────────────────────────────────

    async def broadcast_alert(self, alert: object, chat_ids: Optional[list[int]] = None):
        """
        Broadcast a SmartAlert to all authorized users.

        Args:
            alert: The Alert object (from automation.alerts)
            chat_ids: Optional list of chat IDs to target. If None, uses storage to find all users.
        """
        if not self._bot:
            return

        # Fallback to all users who have preferences set if no chat_ids provided
        if not chat_ids:
            # We don't have a direct 'get_all_chat_ids' but we can infer from user_preferences table
            rows = await self.storage._query_rows("SELECT chat_id FROM user_preferences")
            chat_ids = [row["chat_id"] for row in rows]

        if not chat_ids:
            logger.warning("No users found to broadcast alert to.")
            return

        priority_emoji = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔥"
        }.get(getattr(alert, "priority", "medium").value, "🔔")

        msg = (
            f"{priority_emoji} *{getattr(alert, 'title', 'Alert')}*\n\n"
            f"{getattr(alert, 'message', 'No details provided.')}\n\n"
            f"🕒 _UTC: {getattr(alert, 'timestamp', '')[:19].replace('T', ' ')}_"
        )

        for chat_id in chat_ids:
            try:
                # Route to 'radar' topic by default for smart alerts
                thread_id = await self.storage.get_user_thread(chat_id, "radar")
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="Markdown",
                    message_thread_id=thread_id
                )
                logger.debug(f"Broadcasted alert '{getattr(alert, 'title', '')}' to {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send broadcast alert to {chat_id}: {e}")

    # ─── Utility ─────────────────────────────────────────────

    def get_notification_stats(self) -> dict:
        """Get summary of notification configuration."""
        return {
            "bot_connected": self._bot is not None,
        }

    async def broadcast_message(self, chat_ids: list[int], text: str, parse_mode: str = "Markdown"):
        if not self._bot:
            return
        for chat_id in chat_ids:
            try:
                await self._bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except Exception as e:
                logger.error(f"Failed to broadcast message to {chat_id}: {e}")
