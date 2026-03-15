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
            
        help_text = f"{rich_header('EuroScope Help Terminal', 'main')}\n\n├ `/price` — Live Market Pulse\n├ `/analysis` — Deep Tech Analytics\n├ `/forecast` — Neural Directional Insight\n├ `/signals` — High-Conviction IDEAs\n├ `/news` — Macro Intelligence\n├ `/calendar` — Economic Events\n├ `/report` — Daily PDF Dossier\n├ `/settings` — Preference Console\n├ `/menu` — Main Terminal\n│\n├ 🤖 *Agent Commands*\n├ `/agent_status` — Agent Core State\n├ `/conviction` — Active Trading Theses\n└ `/session_plan` — Today's Game Plan\n\n{thematic_divider()}\n💡 _Just type any market question to chat with the Expert AI!_"
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

    async def cmd_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command — show active price alerts."""
        if not await self.bot._check_auth(update):
            return
            
        chat_id = update.effective_chat.id
        settings_ui = getattr(self.bot, "user_settings", None)
        if not settings_ui:
            await self.bot._reply(update, "⚠️ Settings UI not initialized.", parse_mode="Markdown")
            return
            
        text, keyboard = await settings_ui.build_alerts_keyboard(chat_id)
        
        # Remove the 'Back to Settings' button since they accessed this directly
        if keyboard and keyboard.inline_keyboard and len(keyboard.inline_keyboard) > 0:
            last_row = keyboard.inline_keyboard[-1]
            if last_row and "Back to Settings" in last_row[0].text:
                keyboard.inline_keyboard.pop()
                
        await self.bot._reply(update, text, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_delete_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_alert command — delete a specific alert by ID."""
        if not await self.bot._check_auth(update):
            return
            
        if not context.args or not context.args[0].isdigit():
            await self.bot._reply(update, "⚠️ Usage: `/delete_alert <id>`\nUse `/alerts` to see your active alert IDs.", parse_mode="Markdown")
            return
            
        alert_id = int(context.args[0])
        try:
            await self.bot.container.storage.delete_alert(alert_id)
            await self.bot._reply(update, f"🗑️ Alert `{alert_id}` has been deleted.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error deleting alert: {e}")
            await self.bot._reply(update, "⚠️ Failed to delete alert. It may not exist.", parse_mode="Markdown")

    # ── Agent Core Commands ───────────────────────────────────

    async def cmd_agent_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /agent_status — show Agent Core state and world model summary."""
        if not await self.bot._check_auth(update):
            return

        agent_core = getattr(self.bot, "agent_core", None)
        if not agent_core:
            await self.bot._reply(update, "⚠️ Agent Core is not active yet.", parse_mode="Markdown")
            return

        try:
            state = agent_core.state.value if hasattr(agent_core.state, 'value') else str(agent_core.state)
            tick_count = getattr(agent_core, 'tick_count', 0)
            
            # World Model summary
            wm = getattr(agent_core, 'world_model', None)
            wm_summary = wm.get_summary() if wm else "No world model data"
            
            # Conviction count
            ct = getattr(agent_core, 'conviction_tracker', None)
            active_convictions = len(ct.get_active()) if ct and hasattr(ct, 'get_active') else 0
            
            text = (
                f"🤖 *Agent Core Status*\n\n"
                f"├ State: `{state}`\n"
                f"├ Tick Count: `{tick_count}`\n"
                f"├ Active Convictions: `{active_convictions}`\n"
                f"└ World Model: ✅ Loaded\n\n"
                f"📊 *World Model Snapshot:*\n"
                f"```\n{wm_summary[:800]}\n```"
            )
            await self.bot._reply(update, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Agent status command failed: {e}", exc_info=True)
            await self.bot._reply(update, f"⚠️ Error fetching agent status: {e}")

    async def cmd_conviction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /conviction — show active trading convictions."""
        if not await self.bot._check_auth(update):
            return

        agent_core = getattr(self.bot, "agent_core", None)
        ct = getattr(agent_core, 'conviction_tracker', None) if agent_core else None
        
        if not ct:
            await self.bot._reply(update, "⚠️ Conviction Tracker is not active.", parse_mode="Markdown")
            return

        try:
            active = ct.get_active() if hasattr(ct, 'get_active') else []
            
            if not active:
                await self.bot._reply(
                    update, 
                    "📋 *No Active Convictions*\n\nThe agent has no active trading theses at the moment. "
                    "New convictions will form when the agent identifies strong multi-source evidence.",
                    parse_mode="Markdown"
                )
                return

            parts = ["🎯 *Active Trading Convictions*\n"]
            for i, conv in enumerate(active, 1):
                direction = getattr(conv, 'direction', 'unknown')
                thesis = getattr(conv, 'thesis', 'N/A')
                confidence = getattr(conv, 'confidence', 0)
                emoji = "🟢" if "bull" in direction.lower() else "🔴" if "bear" in direction.lower() else "⚪"
                
                parts.append(
                    f"{emoji} *Conviction #{i}*\n"
                    f"├ Direction: `{direction}`\n"
                    f"├ Confidence: `{confidence:.0f}%`\n"
                    f"└ Thesis: _{thesis[:150]}_\n"
                )

            text = "\n".join(parts)
            await self.bot._reply(update, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Conviction command failed: {e}", exc_info=True)
            await self.bot._reply(update, f"⚠️ Error: {e}")

    async def cmd_session_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /session_plan — show today's trading game plan."""
        if not await self.bot._check_auth(update):
            return

        agent_core = getattr(self.bot, "agent_core", None)
        planner = getattr(agent_core, 'session_planner', None) if agent_core else None
        
        if not planner:
            await self.bot._reply(update, "⚠️ Session Planner is not active.", parse_mode="Markdown")
            return

        try:
            # Try to get the latest plan
            plan = getattr(planner, 'current_plan', None)
            
            if not plan:
                await self.bot._reply(
                    update,
                    "📋 *No Session Plan Available*\n\n"
                    "No game plan has been generated yet for the current session. "
                    "Plans are automatically created before London and New York sessions open.",
                    parse_mode="Markdown"
                )
                return

            session_name = getattr(plan, 'session_name', 'Unknown')
            briefing = getattr(plan, 'briefing_text', 'No briefing available')
            scenarios = getattr(plan, 'scenarios', [])
            
            parts = [
                f"📋 *{session_name} Session Game Plan*\n",
                f"_{briefing}_\n",
            ]
            
            if scenarios:
                parts.append("*Scenarios:*")
                for j, sc in enumerate(scenarios, 1):
                    name = sc.get('name', f'Scenario {j}')
                    condition = sc.get('condition', 'N/A')
                    direction = sc.get('direction', '?')
                    entry = sc.get('entry_zone', '?')
                    parts.append(
                        f"\n*{j}. {name}*\n"
                        f"├ If: _{condition}_\n"
                        f"├ Direction: `{direction}`\n"
                        f"└ Entry Zone: `{entry}`"
                    )

            text = "\n".join(parts)
            await self.bot._reply(update, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Session plan command failed: {e}", exc_info=True)
            await self.bot._reply(update, f"⚠️ Error: {e}")
