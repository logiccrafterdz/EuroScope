"""
User Settings — Per-user Preferences via Telegram UI

Wraps Storage.save_user_preferences/get_user_preferences with
inline keyboard toggles for managing bot behavior.
"""

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..data.storage import Storage

logger = logging.getLogger("euroscope.bot.user_settings")

# Callback data prefixes
SETTINGS_PREFIX = "settings:"
TOGGLE_SIGNAL_ALERTS = f"{SETTINGS_PREFIX}toggle_signals"
TOGGLE_NEWS_ALERTS = f"{SETTINGS_PREFIX}toggle_news"
TOGGLE_DAILY_REPORT = f"{SETTINGS_PREFIX}toggle_report"
SET_TIMEFRAME = f"{SETTINGS_PREFIX}tf:"
SET_RISK = f"{SETTINGS_PREFIX}risk:"
SET_REPORT_HOUR = f"{SETTINGS_PREFIX}hour:"
SETTINGS_BACK = f"{SETTINGS_PREFIX}back"

TIMEFRAMES = ["H1", "H4", "D1"]
RISK_LEVELS = ["low", "medium", "high"]


class UserSettings:
    """Manages per-user preferences with inline keyboard UI."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def get_prefs(self, chat_id: int) -> dict:
        """Get preferences, creating defaults if needed."""
        prefs = self.storage.get_user_preferences(chat_id)
        if not prefs:
            self.storage.save_user_preferences(chat_id)
            prefs = self.storage.get_user_preferences(chat_id)
        return prefs or {}

    # ─── Keyboard Builders ───────────────────────────────────

    def build_settings_keyboard(self, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
        """Build the main settings message and keyboard."""
        prefs = self.get_prefs(chat_id)

        sig_icon = "✅" if prefs.get("alert_on_signals") else "❌"
        news_icon = "✅" if prefs.get("alert_on_news") else "❌"
        report_icon = "✅" if prefs.get("daily_report_enabled") else "❌"

        text = (
            "⚙️ *Settings*\n\n"
            f"📊 Timeframe: *{prefs.get('preferred_timeframe', 'H1')}*\n"
            f"🎯 Risk: *{prefs.get('risk_tolerance', 'medium').title()}*\n"
            f"🔔 Signal Alerts: {sig_icon}\n"
            f"📰 News Alerts: {news_icon}\n"
            f"📋 Daily Report: {report_icon} (at {prefs.get('daily_report_hour', 8):02d}:00 UTC)\n"
            f"📈 Min Confidence: {prefs.get('alert_min_confidence', 60)}%\n"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    f"📊 Timeframe: {prefs.get('preferred_timeframe', 'H1')}",
                    callback_data=f"{SET_TIMEFRAME}cycle"
                ),
                InlineKeyboardButton(
                    f"🎯 Risk: {prefs.get('risk_tolerance', 'medium').title()}",
                    callback_data=f"{SET_RISK}cycle"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{sig_icon} Signal Alerts",
                    callback_data=TOGGLE_SIGNAL_ALERTS
                ),
                InlineKeyboardButton(
                    f"{news_icon} News Alerts",
                    callback_data=TOGGLE_NEWS_ALERTS
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{report_icon} Daily Report",
                    callback_data=TOGGLE_DAILY_REPORT
                ),
                InlineKeyboardButton(
                    f"🕐 Report Hour: {prefs.get('daily_report_hour', 8):02d}:00",
                    callback_data=f"{SET_REPORT_HOUR}cycle"
                ),
            ],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu:main")],
        ]

        return text, InlineKeyboardMarkup(keyboard)

    # ─── Callback Handlers ───────────────────────────────────

    async def handle_callback(self, update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Handle settings-related callbacks.

        Returns True if handled, False otherwise.
        """
        query = update.callback_query
        data = query.data

        if not data.startswith(SETTINGS_PREFIX):
            return False

        chat_id = query.message.chat_id
        prefs = self.get_prefs(chat_id)

        if data == TOGGLE_SIGNAL_ALERTS:
            new_val = 0 if prefs.get("alert_on_signals") else 1
            self.storage.save_user_preferences(chat_id, alert_on_signals=new_val)

        elif data == TOGGLE_NEWS_ALERTS:
            new_val = 0 if prefs.get("alert_on_news") else 1
            self.storage.save_user_preferences(chat_id, alert_on_news=new_val)

        elif data == TOGGLE_DAILY_REPORT:
            new_val = 0 if prefs.get("daily_report_enabled") else 1
            self.storage.save_user_preferences(chat_id, daily_report_enabled=new_val)

        elif data == f"{SET_TIMEFRAME}cycle":
            current = prefs.get("preferred_timeframe", "H1")
            idx = TIMEFRAMES.index(current) if current in TIMEFRAMES else 0
            new_tf = TIMEFRAMES[(idx + 1) % len(TIMEFRAMES)]
            self.storage.save_user_preferences(chat_id, preferred_timeframe=new_tf)

        elif data == f"{SET_RISK}cycle":
            current = prefs.get("risk_tolerance", "medium")
            idx = RISK_LEVELS.index(current) if current in RISK_LEVELS else 1
            new_risk = RISK_LEVELS[(idx + 1) % len(RISK_LEVELS)]
            self.storage.save_user_preferences(chat_id, risk_tolerance=new_risk)

        elif data == f"{SET_REPORT_HOUR}cycle":
            current = prefs.get("daily_report_hour", 8)
            new_hour = (current + 2) % 24  # Cycle by 2-hour increments
            self.storage.save_user_preferences(chat_id, daily_report_hour=new_hour)

        elif data == SETTINGS_BACK:
            # Will be handled by main callback router
            return False

        # Refresh settings display
        text, keyboard = self.build_settings_keyboard(chat_id)
        await query.answer("✅ Updated")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return True
