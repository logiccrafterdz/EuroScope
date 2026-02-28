"""
EuroScope Telegram Bot V2

Interactive bot with inline keyboards, new commands for trading brain,
and integrated notification system.
"""
import asyncio
import logging
import re
import os
import traceback
from datetime import datetime
from typing import Optional
from aiohttp import web
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
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
from ..trading.capital_provider import CapitalProvider
from ..trading.capital_ws import CapitalWebsocketClient
from ..utils.charts import generate_chart
from ..utils.formatting import truncate, safe_markdown, rich_header, thematic_divider, priority_label, progress_bar
from .rate_limiter import RateLimiter
from .user_settings import UserSettings
from .notification_manager import NotificationManager
from ..brain.briefing_engine import BriefingEngine
from ..analytics.evolution_tracker import EvolutionTracker
from ..skills.registry import SkillsRegistry
from ..skills.base import SkillContext
from ..workspace import WorkspaceManager
from ..automation import HeartbeatService, EventBus, SmartAlerts, AlertChannel, setup_default_alerts, CronScheduler, TaskFrequency, SignalExecutorSubscriber, AlertSuppressionSubscriber, TelegramEmergencySubscriber
from ..automation.daily_tracker import DailyTracker
from .api_server import APIServer
from .handlers.commands import CommandHandlers
logger = logging.getLogger('euroscope.bot')

class EuroScopeBot:
    """Telegram bot for EUR/USD analysis — V3 Skills-Based."""
    TOPICS = {'radar': {'name': '📍 Liquidity Radar', 'icon': '🎯'}, 'reports': {'name': '📊 Analysis Reports', 'icon': '📋'}, 'news': {'name': '📰 News & Macro', 'icon': '📅'}, 'settings': {'name': '⚙️ Bot Settings', 'icon': '🛠️'}}

    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage()
        self.daily_tracker = DailyTracker(storage=self.storage)
        self.api = APIServer(self)
        self.commands = CommandHandlers(self)
        self.orchestrator = Orchestrator()
        self.registry = self.orchestrator.registry
        self.workspace = WorkspaceManager()
        self.bus = EventBus()
        self.alerts = SmartAlerts()
        setup_default_alerts(self.alerts)
        self.heartbeat = HeartbeatService(interval=300, event_bus=self.bus)
        self.cron = CronScheduler(config=config, bot=self)
        self.user_settings = UserSettings(self.storage)
        self.notifications = NotificationManager(self.storage)
        self.notifications.set_orchestrator(self.orchestrator)
        self.rate_limiter = RateLimiter(max_requests=config.rate_limit_requests, window_minutes=config.rate_limit_window_minutes)
        self.alerts.register_handler(AlertChannel.TELEGRAM, self._on_alert_triggered)
        from ..data.multi_provider import MultiSourceProvider
        self.price_provider = MultiSourceProvider(
            alphavantage_key=config.data.alphavantage_key,
            tiingo_key=config.data.tiingo_key,
            oanda_key=config.data.oanda_api_key,
            oanda_account=config.data.oanda_account_id,
            oanda_practice=config.data.oanda_practice,
            capital_key=config.data.capital_api_key,
            capital_identifier=config.data.capital_identifier,
            capital_password=config.data.capital_password
        )
        self.broker = CapitalProvider(
            api_key=config.data.capital_api_key,
            identifier=config.data.capital_identifier,
            password=config.data.capital_password
        ) if config.data.capital_api_key else None
        self.ws_client = CapitalWebsocketClient(self.broker) if self.broker else None
        
        self.router = LLMRouter.from_config(
            primary_key=config.llm.api_key, 
            primary_base=config.llm.api_base, 
            primary_model=config.llm.model, 
            fallback_key=config.llm.fallback_api_key, 
            fallback_base=config.llm.fallback_api_base, 
            fallback_model=config.llm.fallback_model
        )
        
        # Core Components
        self.storage = self.storage or Storage()
        self.registry = SkillsRegistry()
        self.memory = Memory(self.storage)
        self.vector_memory = VectorMemory(storage=self.storage)
        self.orchestrator = Orchestrator(storage=self.storage, registry=self.registry)
        
        # Tracking & Learning (Shared Storage)
        self.pattern_tracker = PatternTracker(storage=self.storage)
        self.adaptive_tuner = AdaptiveTuner(storage=self.storage)
        self.evolution_tracker = EvolutionTracker(storage=self.storage)
        self.daily_tracker = DailyTracker(storage=self.storage)
        self.briefing_engine = BriefingEngine(self.config, storage=self.storage)
        
        # Domain Services
        self.price_provider = MultiSourceProvider(
            alphavantage_key=config.data.alphavantage_key,
            tiingo_key=config.data.tiingo_key,
            oanda_key=config.data.oanda_api_key,
            oanda_account=config.data.oanda_account_id,
            oanda_practice=config.data.oanda_practice,
            capital_key=config.data.capital_api_key,
            capital_identifier=config.data.capital_identifier,
            capital_password=config.data.capital_password
        )
        self.news_engine = NewsEngine(config.data.brave_api_key, storage=self.storage)
        self.calendar = EconomicCalendar()
        self.macro_provider = FundamentalDataProvider(config.data.fred_api_key)
        self.risk_manager = RiskManager(storage=self.storage)
        
        # Bot Logic & UI (Order is critical: Agent first, then components that need it)
        self.agent = Agent(config.llm, router=self.router, vector_memory=self.vector_memory, orchestrator=self.orchestrator)
        self.forecaster = Forecaster(self.agent, self.memory, self.orchestrator, pattern_tracker=self.pattern_tracker)
        self.agent.forecaster = self.forecaster
        
        self.user_settings = UserSettings(self.storage)
        self.notifications = NotificationManager(self.storage)
        
        # Automation & Scheduling
        self.bus = EventBus()
        self.heartbeat = HeartbeatService(interval=300, event_bus=self.bus)
        self.cron = CronScheduler(config=config, bot=self, storage=self.storage)
        self.bot_settings = {
            'risk_per_trade': 1.0,
            'max_daily_loss': 3.0,
            'auto_trading_enabled': False
        }
        # Load Mini App Settings
        risk_manager = RiskManager()
        try:
            import json, os
            settings_path = os.path.join(self.config.data_dir, 'bot_settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    s_data = json.load(f)
                    self.bot_settings.update(s_data)
                    risk_manager.config.risk_per_trade = float(self.bot_settings.get('risk_per_trade', 1.0))
                    risk_manager.config.max_daily_loss = float(self.bot_settings.get('max_daily_loss', 3.0))
                    logger.debug(f"Bot: Loaded persistent settings (Risk: {risk_manager.config.risk_per_trade}%, Max Loss: {risk_manager.config.max_daily_loss}%, AutoTrade: {self.bot_settings.get('auto_trading_enabled')})")
        except Exception as e:
            logger.warning(f"Bot: Error loading bot_settings.json: {e}")

        market_data_skill = self.registry.get('market_data')
        # Inject shared storage into Orchestrator/Skills Discovery
        self.orchestrator.inject_dependencies(
            storage=self.storage,
            vector_memory=self.vector_memory,
            memory=self.memory,
            config=self.config,
            provider=self.price_provider, 
            broker=self.broker,
            macro_provider=self.macro_provider, 
            news_engine=self.news_engine, 
            calendar=self.calendar, 
            agent=self.agent, 
            pattern_tracker=self.pattern_tracker, 
            adaptive_tuner=self.adaptive_tuner, 
            risk_manager=risk_manager, 
            event_bus=self.bus, 
            heartbeat=self.heartbeat, 
            market_data_skill=market_data_skill, 
            global_context=self.orchestrator.global_context
        )
        signal_executor_skill = self.registry.get('signal_executor')
        self._signal_executor_subscriber = SignalExecutorSubscriber(signal_executor_skill)
        self._alert_suppression_subscriber = AlertSuppressionSubscriber(self.alerts)
        self._telegram_emergency_subscriber = TelegramEmergencySubscriber(self._send_emergency_message, self.config.telegram.allowed_users or [])
        self.bus.subscribe('market.regime_shift', self._signal_executor_subscriber.handle)
        self.bus.subscribe('market.regime_shift', self._alert_suppression_subscriber.handle)
        self.bus.subscribe('market.regime_shift', self._telegram_emergency_subscriber.handle)

    def _on_alert_triggered(self, alert):
        """Callback for SmartAlerts — sends to allowed users."""
        try:
            loop = asyncio.get_running_loop()
            allowed = self.config.telegram.allowed_users or []
            targets = list(set(allowed + self.config.proactive_alert_chat_ids))
            loop.create_task(self.notifications.broadcast_alert(alert, chat_ids=targets))
        except RuntimeError:
            logger.warning('Alert triggered outside event loop — skipped.')

    async def _send_emergency_message(self, chat_ids: list[int], text: str):
        await self.notifications.broadcast_message(chat_ids, text)

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        if not self.config.telegram.allowed_users:
            return True
        return user_id in self.config.telegram.allowed_users

    async def _check_auth(self, update: Update) -> bool:
        """Check authorization and reply if not allowed."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text('🔒 Unauthorized. Contact the bot admin.')
            return False
        if not await self._check_rate_limit(update):
            return False
        return True

    async def _check_rate_limit(self, update: Update) -> bool:
        chat = update.effective_chat
        if not chat:
            return True
        chat_id = chat.id
        if str(chat_id) in self.config.admin_chat_ids:
            return True
        try:
            allowed, remaining = await self.rate_limiter.is_allowed(chat_id)
            if not allowed:
                message = f'⚠️ <b>Rate limit exceeded</b>\nPlease wait {self.config.rate_limit_window_minutes} minute(s) before sending another command.\nLimit: {self.config.rate_limit_requests} commands per minute.'
                if update.effective_message:
                    await update.effective_message.reply_text(message, parse_mode='HTML')
                logger.warning(f'Blocked {chat_id} for rate limit violation')
                return False
            return True
        except Exception:
            logger.error('Rate limiter failed — allowing request for availability')
            return True

    async def _get_thread(self, chat_id: int, key: str) -> Optional[int]:
        """Helper to get thread ID for a topic."""
        return self.storage.get_user_thread(chat_id, key)

    def _is_compact_mode(self, chat_id: int) -> bool:
        prefs = self.user_settings.get_prefs(chat_id)
        return bool(prefs.get('compact_mode'))

    def _format_for_user(self, chat_id: int, text: str, max_length: int=4096) -> str:
        if self._is_compact_mode(chat_id):
            return truncate(text, max_length=1200)
        return truncate(text, max_length=max_length)

    def _preferred_timeframe(self, chat_id: int) -> str:
        prefs = self.user_settings.get_prefs(chat_id)
        return (prefs.get('preferred_timeframe') or 'H1').upper()

    def _preferred_language(self, chat_id: int, text: str='') -> str:
        return 'en'

    def _is_market_status_question(self, text: str) -> bool:
        t = (text or '').lower()
        english = ['market', 'open', 'closed', 'session', 'trading hours', 'weekend']
        return any((k in t for k in english))

    async def _get_market_status(self) -> dict:
        result = await self.orchestrator.run_skill('market_data', 'check_market_status')
        return result.data if result.success else {}

    def _translate_market_reason(self, reason: str) -> str:
        return reason or ''

    def _format_market_status_reply(self, data: dict, lang: str) -> str:
        is_open = data.get('is_open')
        time_et = data.get('current_time_et', 'N/A')
        reason = data.get('reason', '')
        return f"🕒 *EUR/USD Market Status:*\n\nThe market is *{('OPEN' if is_open else 'CLOSED')}* right now.\n\n⏱️ Current time (ET): `{time_et}`\n📝 Reason: {reason or 'N/A'}\n\n🧭 Main sessions (GMT):\n• London: 07:00 - 16:00\n• New York: 12:00 - 21:00\n"

    async def _ensure_private_topics(self, chat_id: int, bot: 'Bot'):
        """Ensure all specialized topics exist in user's private chat."""
        existing = self.storage.get_all_user_threads(chat_id)
        if len(existing) == len(self.TOPICS):
            return existing
        threads = existing.copy()
        for key, info in self.TOPICS.items():
            if key not in threads:
                try:
                    topic = await bot.create_forum_topic(chat_id=chat_id, name=info['name'], icon_custom_emoji_id=None)
                    thread_id = topic.message_thread_id
                    self.storage.save_user_thread(chat_id, key, thread_id)
                    threads[key] = thread_id
                    logger.info(f'Created topic {key} (ID: {thread_id}) for chat {chat_id}')
                except Exception as e:
                    logger.warning(f'Could not create topic {key} for {chat_id}: {e}')
        return threads

        # Command handlers have been moved to handlers/commands.py
    def _format_risk(self, data: dict) -> str:
        lines = ['🛡️ *Risk Assessment*']
        lines.append(f"Approved: {('✅' if data.get('approved') else '❌')}")
        lines.append(f"Size: `{data.get('position_size', 0):.2f}` lots")
        lines.append(f"SL: `{data.get('stop_loss', 0):.5f}`")
        lines.append(f"TP: `{data.get('take_profit', 0):.5f}`")
        lines.append(f"Risk: `{data.get('risk_pips', 0):.1f}` pips")
        return '\n'.join(lines)

    @staticmethod
    def _format_summary_date(date_value: str) -> str:
        if not date_value:
            return 'N/A'
        try:
            return datetime.strptime(date_value, '%Y-%m-%d').strftime('%b %d')
        except ValueError:
            return date_value

    @staticmethod
    def _format_percent(value: float) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return '0%'
        if numeric <= 1.0:
            numeric *= 100
        return f'{numeric:.0f}%'

    @staticmethod
    def _format_summary_time(timestamp: str) -> str:
        if not timestamp:
            return ''
        text = str(timestamp)
        if text.endswith('Z'):
            text = text[:-1]
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return ''
        return parsed.strftime('%H:%M UTC')

    async def _reply(self, update: Update, text: str, topic_key: str=None, **kwargs):
        """Topic-aware reply helper with Markdown fallback."""
        chat_id = update.effective_chat.id
        thread_id = None
        if topic_key:
            thread_id = self.storage.get_user_thread(chat_id, topic_key)
        try:
            if update.message:
                return await update.message.reply_text(text, message_thread_id=thread_id, **kwargs)
            else:
                return await update.get_bot().send_message(chat_id=chat_id, text=text, message_thread_id=thread_id, **kwargs)
        except Exception as e:
            if 'parse' in str(e).lower() and kwargs.get('parse_mode'):
                logger.warning(f'Markdown parsing failed, falling back to plain text: {e}')
                kwargs.pop('parse_mode')
                clean_text = text.replace('*', '').replace('_', '').replace('`', '')
                if update.message:
                    return await update.message.reply_text(clean_text, message_thread_id=thread_id, **kwargs)
                else:
                    return await update.get_bot().send_message(chat_id=chat_id, text=clean_text, message_thread_id=thread_id, **kwargs)
            logger.error(f'Reply failed: {e}', exc_info=True)
            raise e

    async def _reply_photo(self, update: Update, photo, caption: str=None, topic_key: str=None, **kwargs):
        chat_id = update.effective_chat.id
        thread_id = None
        if topic_key:
            thread_id = self.storage.get_user_thread(chat_id, topic_key)
        if update.message:
            return await update.message.reply_photo(photo=photo, caption=caption, message_thread_id=thread_id, **kwargs)
        return await update.get_bot().send_photo(chat_id=chat_id, photo=photo, caption=caption, message_thread_id=thread_id, **kwargs)

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler — logs and notifies the user."""
        logger.error(f'Unhandled exception: {context.error}', exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text('⚠️ An internal error occurred. Please try again later.')
            except Exception:
                pass

    def build_app(self) -> Application:
        """Build and configure the Telegram bot application."""
        app = Application.builder().token(self.config.telegram.token).post_init(self.post_init).post_shutdown(self.post_shutdown).build()
        commands = {'start': self.commands.cmd_start, 'help': self.commands.cmd_help, 'id': self.commands.cmd_id, 'health': self.commands.cmd_health, 'data_health': self.commands.cmd_data_health}
        for cmd, handler in commands.items():
            app.add_handler(CommandHandler(cmd, handler))
        app.add_error_handler(self._error_handler)
        return app

    async def post_init(self, application: Application):
        """Called after bot is initialized, before polling starts."""
        self.application = application
        self.cron.set_bot(self)
        if self.config.telegram.web_app_url:
            try:
                await asyncio.wait_for(application.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text='Zenith v4', web_app=WebAppInfo(url=self.config.telegram.web_app_url))), timeout=10.0)
            except Exception as e:
                logger.warning(f'Failed to set chat menu button (timeout/network error): {e}')
        cmds = [BotCommand('start', 'Launch EuroScope Dashboard'), BotCommand('help', 'List all commands'), BotCommand('id', 'Get your Telegram Chat ID'), BotCommand('health', 'System status'), BotCommand('data_health', 'Check API & Data sources')]
        try:
            await asyncio.wait_for(application.bot.set_my_commands(cmds), timeout=10.0)
        except Exception as e:
            logger.warning(f'Failed to set bot commands (timeout/network error): {e}')
        self._bg_tasks = set()
        heartbeat_task = asyncio.create_task(self.heartbeat.start())
        self._bg_tasks.add(heartbeat_task)
        heartbeat_task.add_done_callback(self._bg_tasks.discard)

        async def tick_job(context: ContextTypes.DEFAULT_TYPE):
            try:
                await self.cron._tick()
            except Exception as e:
                logger.error(f'Cron loop tick failed: {e}')
        if application.job_queue:
            application.job_queue.run_repeating(tick_job, interval=self.cron.tick_interval, first=self.cron.tick_interval, name='euroscope_cron_ticker', job_kwargs={'misfire_grace_time': 10})
            logger.info('Cron ticking delegated to JobQueue')
        else:
            logger.warning('JobQueue not available, falling back to standalone cron loop')
            cron_task = asyncio.create_task(self.cron.start())
            self._bg_tasks.add(cron_task)
            cron_task.add_done_callback(self._bg_tasks.discard)
        self.cron.schedule('resolve_patterns', TaskFrequency.HOURLY, self._task_resolve_patterns)
        self.cron.schedule('daily_tuning', TaskFrequency.DAILY, self._task_daily_tuning, delay=3600)
        self.cron.schedule('weekly_reflection', TaskFrequency.WEEKLY, self._task_weekly_reflection, delay=7200)
        self.cron.schedule('daily_trading_journal', TaskFrequency.DAILY, self.daily_tracker.run, delay=self.cron._seconds_until(23, 55))
        self.cron.schedule('daily_briefing', TaskFrequency.DAILY, self._task_daily_briefing, delay=self.cron._seconds_until(7, 0))
        api_task = asyncio.create_task(self.api.start())
        self._bg_tasks.add(api_task)
        api_task.add_done_callback(self._bg_tasks.discard)

        # Capital.com WebSocket Integration
        signal_executor_skill = self.registry.get('signal_executor')
        if signal_executor_skill:
            await signal_executor_skill.initialize()
            logger.info("SignalExecutor initialized (Risk state loaded).")

        if self.ws_client:
            logger.info("Starting Capital.com WebSocket Stream...")
            ws_success = await self.ws_client.connect()
            if ws_success:
                await self.ws_client.subscribe(["EURUSD"])
                if signal_executor_skill:
                    signal_executor_skill.start_streaming(self.ws_client)
                    logger.info("Real-time Tick Stream INTEGRATED with SignalExecutor.")
            else:
                logger.error("Failed to connect Capital.com WebSocket stream.")

        logger.info('⚡ Background services & Commands registered.')

    async def post_shutdown(self, application: Application):
        """Gracefully stop background services on shutdown."""
        logger.info('Shutting down background services...')
        await self.heartbeat.stop()
        await self.cron.stop()
        logger.info('✅ Background services stopped.')

    # Command handlers extracted to handlers/commands.py    async def _task_resolve_patterns(self):
        """Periodically resolve pending patterns using latest price."""
        logger.info('Cron: Running pattern resolution...')
        price_data = await self.price_provider.get_price()
        if 'error' in price_data:
            return
        current_price = price_data['price']
        self.pattern_tracker.resolve_pending(current_price)
        self.memory.resolve_pending_predictions(current_price)
        logger.info('Cron: Pattern resolution complete.')

    async def _task_daily_tuning(self):
        """Analyze trade history once a day and report recommendations."""
        logger.info('Cron: Running daily strategy tuning...')
        report = self.adaptive_tuner.format_report()
        await self.notifications.broadcast_message(f'🧠 *Daily Strategy Optimization*\n\n{report}', parse_mode='Markdown')
        logger.info('Cron: Daily tuning complete.')

    async def _task_weekly_reflection(self):
        logger.info('Cron: Running weekly reflection...')
        accuracy = self.storage.get_accuracy_stats(30)
        patterns = self.pattern_tracker.get_success_rates()
        stats = self.storage.get_trade_journal_stats()
        tuner = self.adaptive_tuner.analyze()
        lines = ['Weekly Reflection', f"Prediction accuracy (30d): {accuracy.get('accuracy', 0)}% ({accuracy.get('total', 0)})", f"Trades: {stats.get('total', 0)} | Win rate: {stats.get('win_rate', 0)}% | Avg PnL: {stats.get('avg_pnl', 0):+.1f}p"]
        if patterns:
            top = sorted(patterns.values(), key=lambda x: x['success_rate'], reverse=True)[:3]
            weak = sorted(patterns.values(), key=lambda x: x['success_rate'])[:2]
            lines.append('Top patterns: ' + ', '.join((f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in top)))
            lines.append('Weak patterns: ' + ', '.join((f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in weak)))
        if tuner.get('ready') and tuner.get('recommendations'):
            lines.append('Tuning focus: ' + ', '.join((r['param'] for r in tuner['recommendations'][:3])))
        insight = ' | '.join(lines)
        self.memory.save_insight(insight)
        if self.vector_memory:
            self.vector_memory.store_insight(insight, tags=['reflection', 'weekly'])
        self.workspace.refresh_memory(self.storage)
        self.workspace.refresh_identity(self.storage)
        logger.info('Cron: Weekly reflection complete.')

    async def _task_daily_briefing(self):
        """Generate and broadcast the morning briefing."""
        logger.info('Cron: Running daily briefing...')
        report = await self.briefing_engine.generate_briefing()
        chat_ids = self.config.proactive_alert_chat_ids
        if chat_ids:
            await self.notifications.broadcast_message(report, chat_ids=chat_ids, parse_mode='HTML')
        logger.info('Cron: Daily briefing sent.')

    # API Server endpoints extracted to api_server.py

    def run(self):
        """Start the Telegram bot and the integrated API server."""
        if not self.config.telegram.token:
            logger.error('Telegram token not configured!')
            return
        logger.info('🌐 EuroScope Zenith starting...')
        app = self.build_app()
        self.notifications.set_bot(app.bot)
        if self.config.telegram.allowed_users:
            self.notifications.schedule_daily_reports(app.job_queue, self.config.telegram.allowed_users)
        app.run_polling(drop_pending_updates=True)