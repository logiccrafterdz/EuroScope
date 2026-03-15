"""
EuroScope Telegram Bot V2

Interactive bot with inline keyboards, new commands for trading brain,
and integrated notification system.
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import BotCommand
from telegram.error import Conflict
from ..config import Config
from ..container import ServiceContainer
from ..utils.formatting import truncate
from ..automation import HeartbeatService, EventBus, SmartAlerts, AlertChannel, setup_default_alerts, CronScheduler, TaskFrequency, SignalExecutorSubscriber, AlertSuppressionSubscriber, TelegramEmergencySubscriber
from ..automation.daily_tracker import DailyTracker
from .api_server import APIServer
from .handlers.commands import CommandHandlers
from .handlers.tasks import BotTasks
logger = logging.getLogger('euroscope.bot')

class EuroScopeBot:
    """Telegram bot for EUR/USD analysis — V3 Skills-Based."""
    TOPICS = {'radar': {'name': '📍 Liquidity Radar', 'icon': '🎯'}, 'reports': {'name': '📊 Analysis Reports', 'icon': '📋'}, 'news': {'name': '📰 News & Macro', 'icon': '📅'}, 'settings': {'name': '⚙️ Bot Settings', 'icon': '🛠️'}}

    def __init__(self, container: ServiceContainer):
        self.container = container
        self.config = container.config
        
        # 1. Base Infrastructure (Shared Storage)
        self.storage = container.storage
        self.bus = container.bus
        self.registry = container.registry
        self.alerts = container.alerts
        self.rate_limiter = container.rate_limiter
        
        # 2. Core Brain Components
        self.memory = container.memory
        self.vector_memory = container.vector_memory
        self.orchestrator = container.orchestrator
        self.router = container.router
        
        # 3. Intelligence Layers
        self.agent = container.agent
        self.forecaster = container.forecaster
        
        # 4. Domain & Data Services
        self.price_provider = container.price_provider
        self.broker = container.broker
        self.ws_client = container.ws_client
        self.news_engine = container.news_engine
        self.calendar = container.calendar
        self.macro_provider = container.macro_provider
        self.risk_manager = container.risk_manager
        
        # 5. Tracking & Analytics
        self.pattern_tracker = container.pattern_tracker
        self.adaptive_tuner = container.adaptive_tuner
        self.evolution_tracker = container.evolution_tracker
        self.daily_tracker = container.daily_tracker
        self.briefing_engine = container.briefing_engine
        
        # 6. User Management & Notifications
        self.user_settings = container.user_settings
        self.notifications = container.notifications
        self.workspace = container.workspace
        
        # 7. UI, Interface & Scheduling
        self.api = APIServer(self)
        self.commands = CommandHandlers(self)
        self.tasks = BotTasks(self)
        self.heartbeat = HeartbeatService(interval=300, event_bus=self.bus)
        self.cron = CronScheduler(config=self.config, bot=self, storage=self.storage)
        
        # 8. Subscription Handlers
        self.alerts.register_handler(AlertChannel.TELEGRAM, self._on_alert_triggered)
        self.bot_settings = {
            'risk_per_trade': 1.0,
            'max_daily_loss': 3.0,
            'auto_trading_enabled': False
        }
        # Load Mini App Settings
        # Load Persistent Settings (Risk, AutoTrade)
        try:
            import json
            settings_path = os.path.join(self.config.data_dir, 'bot_settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    s_data = json.load(f)
                    self.bot_settings.update(s_data)
                    self.risk_manager.config.risk_per_trade = float(self.bot_settings.get('risk_per_trade', 1.0))
                    self.risk_manager.config.max_daily_loss = float(self.bot_settings.get('max_daily_loss', 3.0))
                    logger.debug(f"Bot: Loaded persistent settings (Risk: {self.risk_manager.config.risk_per_trade}%, Max Loss: {self.risk_manager.config.max_daily_loss}%, AutoTrade: {self.bot_settings.get('auto_trading_enabled')})")
        except Exception as e:
            logger.warning(f"Bot: Error loading bot_settings.json: {e}")

        market_data_skill = self.registry.get('market_data')
        # Inject shared dependencies into Orchestrator/Skills system
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
            risk_manager=self.risk_manager, 
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
        await self.notifications.broadcast_message(chat_ids, text, parse_mode='HTML')

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
        return await self.storage.get_user_thread(chat_id, key)

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
        existing = await self.storage.get_all_user_threads(chat_id)
        if len(existing) == len(self.TOPICS):
            return existing
        threads = existing.copy()
        for key, info in self.TOPICS.items():
            if key not in threads:
                try:
                    topic = await bot.create_forum_topic(chat_id=chat_id, name=info['name'], icon_custom_emoji_id=None)
                    thread_id = topic.message_thread_id
                    await self.storage.save_user_thread(chat_id, key, thread_id)
                    threads[key] = thread_id
                    logger.info(f'Created topic {key} (ID: {thread_id}) for chat {chat_id}')
                except Exception as e:
                    logger.warning(f'Could not create topic {key} for {chat_id}: {e}')
        return threads

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
            thread_id = await self.storage.get_user_thread(chat_id, topic_key)
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
            thread_id = await self.storage.get_user_thread(chat_id, topic_key)
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
        commands = {
            'start': self.commands.cmd_start, 'help': self.commands.cmd_help, 
            'id': self.commands.cmd_id, 'health': self.commands.cmd_health, 
            'data_health': self.commands.cmd_data_health,
            'agent_status': self.commands.cmd_agent_status,
            'conviction': self.commands.cmd_conviction,
            'session_plan': self.commands.cmd_session_plan,
        }
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
            await self.tasks.tick_job(context)
            
        if application.job_queue:
            application.job_queue.run_repeating(tick_job, interval=self.cron.tick_interval, first=self.cron.tick_interval, name='euroscope_cron_ticker', job_kwargs={'misfire_grace_time': 10})
            logger.info('Cron ticking delegated to JobQueue')
        else:
            logger.warning('JobQueue not available, falling back to standalone cron loop')
            cron_task = asyncio.create_task(self.cron.start())
            self._bg_tasks.add(cron_task)
            cron_task.add_done_callback(self._bg_tasks.discard)
            

        self.cron.schedule('weekly_reflection', TaskFrequency.WEEKLY, self.tasks.task_weekly_reflection, delay=7200)
        self.cron.schedule('daily_trading_journal', TaskFrequency.DAILY, self.daily_tracker.run, delay=self.cron._seconds_until(23, 55))
        self.cron.schedule('daily_briefing', TaskFrequency.DAILY, self.tasks.task_daily_briefing, delay=self.cron._seconds_until(7, 0))
        
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
        
        # Close all data and service sessions safely
        for service_name, service in [
            ("price_provider", self.price_provider),
            ("storage", self.storage),
            ("news_engine", self.news_engine),
            ("macro_provider", self.macro_provider),
            ("risk_manager", self.risk_manager),
            ("ws_client", getattr(self, "ws_client", None)),
            ("webhooks", getattr(self.api, "webhooks", None) if hasattr(self, "api") else None),
        ]:
            if service and hasattr(service, 'close'):
                try:
                    res = service.close()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    logger.warning(f"Shutdown: {service_name} close failed: {e}")
        
        logger.info('✅ Background services stopped.')

    # Command handlers extracted to handlers/commands.py

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
        try:
            app.run_polling(drop_pending_updates=True)
        except Conflict as e:
            logger.error(f"Telegram polling conflict: {e}")
            return
        except Exception:
            logger.exception("Telegram polling crashed")
            raise
