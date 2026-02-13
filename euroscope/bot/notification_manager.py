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

    def set_bot(self, bot: Bot):
        """Set the bot instance for sending messages."""
        self._bot = bot

    # ─── Scheduled Reports ───────────────────────────────────

    def schedule_daily_reports(self, job_queue, chat_ids: list[int]):
        """
        Schedule daily reports for each user based on their preferences.

        Args:
            job_queue: Telegram's JobQueue
            chat_ids: List of authorized user chat IDs
        """
        for chat_id in chat_ids:
            prefs = self.storage.get_user_preferences(chat_id)
            if not prefs:
                self.storage.save_user_preferences(chat_id)
                prefs = self.storage.get_user_preferences(chat_id)

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
        """Job callback for daily report. Sends a prompt to generate report."""
        chat_id = context.job.data["chat_id"]

        if not self._bot:
            logger.warning("Bot not set, cannot send daily report")
            return

        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=(
                    "📋 *Scheduled Daily Report*\n\n"
                    "Use /report to generate your comprehensive daily analysis.\n"
                    "Or tap the button below!"
                ),
                parse_mode="Markdown",
            )
            logger.info(f"Sent daily report notification to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send daily report to {chat_id}: {e}")

    # ─── Signal Alerts ───────────────────────────────────────

    async def notify_signal_closed(self, chat_id: int, signal_result: dict):
        """
        Send alert when a signal's SL or TP is hit.

        Args:
            chat_id: Telegram chat to notify
            signal_result: Dict from SignalExecutor.close_signal()
        """
        if not self._bot:
            return

        prefs = self.storage.get_user_preferences(chat_id)
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
            await self._bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send signal alert to {chat_id}: {e}")

    # ─── Price Alerts ────────────────────────────────────────

    async def check_price_alerts(self, current_price: float):
        """Check all active price alerts and notify if triggered."""
        if not self._bot:
            return

        alerts = self.storage.get_active_alerts()
        for alert in alerts:
            triggered = False
            condition = alert.get("condition", "")
            target = alert.get("target_value", 0)

            if condition == "above" and current_price >= target:
                triggered = True
            elif condition == "below" and current_price <= target:
                triggered = True

            if triggered:
                self.storage.trigger_alert(alert["id"])
                chat_id = alert.get("chat_id")
                if chat_id:
                    try:
                        await self._bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"🔔 *Price Alert*\n\n"
                                f"EUR/USD {'crossed above' if condition == 'above' else 'dropped below'} "
                                f"`{target}`\n"
                                f"Current: `{current_price}`"
                            ),
                            parse_mode="Markdown",
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

        prefs = self.storage.get_user_preferences(chat_id)
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
                await self._bot.send_message(
                    chat_id=chat_id, text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.error(f"Failed to send news alert to {chat_id}: {e}")

    # ─── Utility ─────────────────────────────────────────────

    def get_notification_stats(self) -> dict:
        """Get summary of notification configuration."""
        return {
            "bot_connected": self._bot is not None,
        }
