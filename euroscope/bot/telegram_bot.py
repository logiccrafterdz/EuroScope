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
from ..trading.strategy_engine import StrategyEngine
from ..trading.signal_executor import SignalExecutor
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
logger = logging.getLogger('euroscope.bot')

class EuroScopeBot:
    """Telegram bot for EUR/USD analysis — V3 Skills-Based."""
    TOPICS = {'radar': {'name': '📍 Liquidity Radar', 'icon': '🎯'}, 'reports': {'name': '📊 Analysis Reports', 'icon': '📋'}, 'news': {'name': '📰 News & Macro', 'icon': '📅'}, 'settings': {'name': '⚙️ Bot Settings', 'icon': '🛠️'}}

    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage()
        self.daily_tracker = DailyTracker(storage=self.storage)
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
        self.price_provider = MultiSourceProvider(alphavantage_key=config.data.alphavantage_key, tiingo_key=config.data.tiingo_key)
        self.macro_provider = FundamentalDataProvider(config.data.fred_api_key)
        self.news_engine = NewsEngine(config.data.brave_api_key, self.storage)
        self.calendar = EconomicCalendar()
        self.router = LLMRouter.from_config(primary_key=config.llm.api_key, primary_base=config.llm.api_base, primary_model=config.llm.model, fallback_key=config.llm.fallback_api_key, fallback_base=config.llm.fallback_api_base, fallback_model=config.llm.fallback_model)
        self.vector_memory = VectorMemory()
        self.agent = Agent(config.llm, router=self.router, vector_memory=self.vector_memory, orchestrator=self.orchestrator)
        self.memory = Memory(self.storage)
        self.pattern_tracker = PatternTracker(self.storage)
        self.adaptive_tuner = AdaptiveTuner(self.storage)
        self.forecaster = Forecaster(self.agent, self.memory, self.orchestrator, pattern_tracker=self.pattern_tracker)
        self.agent.forecaster = self.forecaster
        self.briefing_engine = BriefingEngine(self.storage)
        self.evolution_tracker = EvolutionTracker(self.storage)
        self.orchestrator.set_alerts(self.alerts)
        market_data_skill = self.registry.get('market_data')
        self.orchestrator.inject_dependencies(provider=self.price_provider, macro_provider=self.macro_provider, news_engine=self.news_engine, calendar=self.calendar, storage=self.storage, agent=self.agent, vector_memory=self.vector_memory, pattern_tracker=self.pattern_tracker, adaptive_tuner=self.adaptive_tuner, risk_manager=RiskManager(), event_bus=self.bus, heartbeat=self.heartbeat, market_data_skill=market_data_skill, global_context=self.orchestrator.global_context, config=self.config)
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

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start — show interactive menu."""
        if not await self._check_auth(update):
            return
        chat_id = update.effective_chat.id
        await self._ensure_private_topics(chat_id, context.bot)
        keyboard = None
        if self.config.telegram.web_app_url:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('🚀 OPEN EUROSCOPE DASHBOARD', web_app=WebAppInfo(url=self.config.telegram.web_app_url))]])
        await self._reply(update, f"{rich_header('Welcome to EuroScope Zenith', 'main')}\n\nI am your elite EUR/USD financial intelligence partner. Leveraging neural forecasting and institutional-grade analytics.\n\n{thematic_divider()}\n⚡ *READY FOR EXECUTION*\n\n💡 _Click the button below to launch the Zenith Web Dashboard._", reply_markup=keyboard, parse_mode='Markdown')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help — show all commands."""
        if not await self._check_auth(update):
            return
        help_text = f"{rich_header('EuroScope Help Terminal', 'main')}\n\n├ `/price` — Live Market Pulse\n├ `/analysis` — Deep Tech Analytics\n├ `/forecast` — Neural Directional Insight\n├ `/signals` — High-Conviction IDEAs\n├ `/news` — Macro Intelligence\n├ `/calendar` — Economic Events\n├ `/report` — Daily PDF Dossier\n├ `/settings` — Preference Console\n└ `/menu` — Main Terminal\n\n{thematic_divider()}\n💡 _Just type any market question to chat with the Expert AI!_"
        await self._reply(update, help_text, parse_mode='Markdown')

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
        commands = {'start': self.cmd_start, 'help': self.cmd_help, 'id': self.cmd_id, 'health': self.cmd_health, 'data_health': self.cmd_data_health}
        for cmd, handler in commands.items():
            app.add_handler(CommandHandler(cmd, handler))
        app.add_handler(CallbackQueryHandler(self.callback_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
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
        api_task = asyncio.create_task(self.start_api_server())
        self._bg_tasks.add(api_task)
        api_task.add_done_callback(self._bg_tasks.discard)
        logger.info('⚡ Background services & Commands registered.')

    async def post_shutdown(self, application: Application):
        """Gracefully stop background services on shutdown."""
        logger.info('Shutting down background services...')
        await self.heartbeat.stop()
        await self.cron.stop()
        logger.info('✅ Background services stopped.')

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /health — system health and runtime stats."""
        if not await self._check_auth(update):
            return
        result = await self.orchestrator.run_skill('monitoring', 'runtime_stats')
        text = result.metadata.get('formatted', '⚠️ Could not fetch health stats.')
        await self._reply(update, safe_markdown(text), parse_mode='Markdown')

    async def cmd_data_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current data source health status (Phase 2D)."""
        if not await self._check_auth(update):
            return
        ecb_status = '✅ Online' if self.macro_provider.fred_api_key else '❌ Offline (No Key)'
        fred_status = '✅ Online' if self.macro_provider.fred_api_key else '❌ Offline (No Key)'
        tiingo_status = '✅ Online' if self.config.data.tiingo_key else '❌ Offline'
        alphavantage_status = '✅ Online' if self.config.data.alphavantage_key else '❌ Offline'
        message = f'📊 *Data Source Health Status*\n\n🏦 *FRED API*: {fred_status}\n🇪🇺 *ECB Data*: {ecb_status} (via FRED)\n📈 *Tiingo*: {tiingo_status}\n💹 *AlphaVantage*: {alphavantage_status}\n📰 *News Engine*: ✅ Online\n📅 *Economic Calendar*: ✅ Online\n\n💡 _Detailed logs available in /health_'
        await self._reply(update, message, parse_mode='Markdown')

    async def cmd_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /id command — show user's chat ID."""
        chat_id = update.effective_chat.id
        await update.message.reply_text(f'🆔 *Your Chat ID*: `{chat_id}`\n\nUse this ID in your `.env` file under `EUROSCOPE_PROACTIVE_CHAT_IDS` to receive proactive alerts.', parse_mode='Markdown')

    async def _task_resolve_patterns(self):
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

    @web.middleware
    async def _cors_middleware(self, request, handler):
        """Middleware to handle CORS headers and preflight requests."""
        if request.method == 'OPTIONS':
            response = web.Response()
        else:
            try:
                response = await handler(request)
            except Exception as e:
                logger.error(f'API Error ({request.path}): {e}')
                response = web.json_response({'success': False, 'error': str(e)}, status=500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        return response

    async def _api_summary(self, request):
        """API endpoint for live price and sentiment summary."""
        logger.debug('API: Fetching market summary...')
        result = await self.orchestrator.run_skill('market_data', 'get_price')
        if not result.success:
            return web.json_response({'success': False, 'error': result.error})
        data = result.data
        resp = {'success': True, 'symbol': 'EUR/USD', 'price': data.get('price', 0), 'change': data.get('change', 0), 'change_pct': data.get('change_pct', 0), 'high': data.get('high'), 'low': data.get('low'), 'open': data.get('open'), 'range_pips': data.get('spread_pips', 0), 'sentiment': 'bullish' if data.get('change', 0) >= 0 else 'bearish', 'timestamp': datetime.now().isoformat()}
        logger.debug(f"API: Summary response sent for {resp['price']}")
        return web.json_response(resp)

    async def _api_status(self, request):
        """API endpoint for market status, sessions and trading hours."""
        logger.debug('API: Fetching market status and session context...')
        ctx = SkillContext()
        result_mkt = await self.orchestrator.run_skill('market_data', 'check_market_status')
        mkt_data = result_mkt.data if result_mkt.success else {'status': 'Closed'}
        res_session = await self.orchestrator.run_skill('session_context', 'detect', context=ctx)
        session_data = res_session.data if res_session.success else {'session_regime': 'unknown'}
        return web.json_response({'success': True, 'data': {'status': mkt_data.get('status', 'Closed'), 'session': session_data.get('session_regime', 'unknown').upper(), 'rules': session_data.get('session_rules', {}), 'timestamp': datetime.now().isoformat()}})

    async def _api_forecast(self, request):
        """API endpoint for deep AI forecasting and reasoning."""
        logger.debug('API: Running deep AI forecast...')
        try:
            tf = request.query.get('timeframe', '24 hours')
            result = await self.forecaster.generate_forecast(tf)
            return web.json_response({'success': True, 'data': {'direction': result.get('direction', 'NEUTRAL'), 'confidence': result.get('confidence', 0) / 100, 'reasoning': result.get('text', ''), 'timeframe': tf, 'price': result.get('price'), 'timestamp': datetime.now().isoformat()}})
        except Exception as e:
            logger.error(f'API forecast error: {e}')
            return web.json_response({'success': False, 'error': str(e), 'data': {'direction': 'NEUTRAL', 'confidence': 0, 'reasoning': 'Forecasting engine error.'}})

    async def _api_macro(self, request):
        """API endpoint for fundamental macro data (FRED/ECB)."""
        logger.debug('API: Fetching fundamental macro overview...')
        ctx = SkillContext()
        res = await self.orchestrator.run_skill('fundamental_analysis', 'get_macro', context=ctx)
        if not res.success:
            return web.json_response({'success': False, 'partial': True, 'error': res.error, 'data': {'macro_impact': 'NEUTRAL', 'macro_data': {}}})
        return web.json_response({'success': True, 'data': res.data, 'formatted': res.metadata.get('formatted', '')})

    async def _api_signals(self, request):
        """API endpoint for recent trading signals."""
        logger.debug('API: Fetching recent signals...')
        signals = self.storage.get_signals(limit=5)
        return web.json_response({'success': True, 'signals': signals})

    async def _api_trades(self, request):
        """API endpoint for active open trades (Phase 5)."""
        logger.debug('API: Fetching open trades...')
        res = await self.orchestrator.run_skill('signal_executor', 'list_trades')
        if not res.success:
            return web.json_response({'success': False, 'error': res.error, 'trades': []})
        return web.json_response({'success': True, 'trades': res.data})

    async def _api_history(self, request):
        """API endpoint for closed trade history (Phase 5)."""
        logger.debug('API: Fetching closed trade history...')
        res = await self.orchestrator.run_skill('signal_executor', 'trade_history')
        if not res.success:
            return web.json_response({'success': False, 'error': res.error, 'history': []})
        history = res.data[-20:] if res.data else []
        history.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return web.json_response({'success': True, 'history': history})

    async def _api_scan_signals(self, request):
        """API endpoint to actively scan for and generate new trading signals."""
        logger.debug('API: Actively scanning for new signals (Mini App request)...')
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            ta_res = await self.orchestrator.run_skill('technical_analysis', 'analyze', context=ctx, timeframe='H1')
            if not ta_res.success:
                return web.json_response({'success': False, 'error': f'TA failed: {ta_res.error}'})
            strat_res = await self.orchestrator.run_skill('trading_strategy', 'detect_signal', context=ctx)
            if not strat_res.success:
                return web.json_response({'success': False, 'error': f'Strategy failed: {strat_res.error}'})
            signal_data = strat_res.data
            direction = signal_data.get('direction', 'WAIT')
            confidence = signal_data.get('confidence', 0)
            if direction in ('BUY', 'SELL') and confidence >= 50:
                exec_res = await self.orchestrator.run_skill('signal_executor', 'open_trade', context=ctx)
                if exec_res.success:
                    return web.json_response({'success': True, 'signal': exec_res.data, 'message': f'Found {direction} opportunity!'})
                else:
                    return web.json_response({'success': False, 'error': f'Signal generation aborted by guardrails: {exec_res.error}', 'signal': signal_data})
            else:
                return web.json_response({'success': False, 'message': 'No high-confidence opportunities currently available. Please exercise patience.'})
        except Exception as e:
            import traceback
            logger.error(f'API: Error scanning signals: {e}\n{traceback.format_exc()}')
            return web.json_response({'success': False, 'error': str(e)})

    async def _api_alerts(self, request):
        """API endpoint for active price alerts."""
        logger.debug('API: Fetching active alerts...')
        alerts = self.storage.get_active_alerts()
        return web.json_response({'success': True, 'alerts': alerts})

    async def _api_analysis(self, request):
        """API endpoint for technical analysis snapshot."""
        logger.debug('API: Running real-time technical analysis...')
        ctx = SkillContext()
        res_ta = await self.orchestrator.run_skill('technical_analysis', 'analyze', context=ctx, timeframe='H1')
        if not res_ta.success:
            logger.warning(f'API: Analysis skill partial failure: {res_ta.error}')
            return web.json_response({'success': False, 'partial': True, 'error': res_ta.error, 'data': {'indicators': {}, 'overall_bias': 'NEUTRAL'}})
        logger.debug('API: Technical analysis snapshot delivered.')
        return web.json_response({'success': True, 'data': res_ta.data, 'formatted': res_ta.metadata.get('formatted')})

    async def _api_candles(self, request):
        """API endpoint for chart data (OHLC) with strict time sorting."""
        timeframe = request.query.get('timeframe', 'H1')
        logger.debug(f'API: Fetching {timeframe} candles for chart...')
        try:
            result = await self.orchestrator.run_skill('market_data', 'get_candles', timeframe=timeframe, count=100)
            if not result.success:
                logger.warning(f'API: Candle skill failed: {result.error}')
                return web.json_response({'success': False, 'candles': [], 'error': result.error})
            df = result.data
            if df is None or df.empty:
                return web.json_response({'success': False, 'candles': [], 'error': 'Empty data'})
            df = df.sort_index()
            candles = []
            for idx, row in df.iterrows():
                try:
                    candles.append({'time': int(idx.timestamp()), 'open': float(row['Open']), 'high': float(row['High']), 'low': float(row['Low']), 'close': float(row['Close'])})
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug(f'API: Skipping malformed candle at {idx}: {e}')
                    continue
            logger.debug(f'API: Delivered {len(candles)} candles for {timeframe}')
            return web.json_response({'success': True, 'candles': candles, 'count': len(candles)})
        except Exception as e:
            logger.error(f'API: Critical error in _api_candles: {e}')
            return web.json_response({'success': False, 'error': str(e), 'candles': []})

    async def _api_backtest(self, request):
        """API endpoint for backtesting dashboard data."""
        logger.debug('API: Running backtest...')
        strategy = request.query.get('strategy', None)
        timeframe = request.query.get('timeframe', 'H1')
        try:
            from .telegram_bot import SkillContext
        except ImportError:
            from ..skills.base import SkillContext
        try:
            ctx = SkillContext()
            result = await self.orchestrator.run_skill('market_data', 'get_candles', context=ctx, timeframe=timeframe, count=500)
            if not result.success or result.data is None or result.data.empty:
                return web.json_response({'success': False, 'error': 'No candle data available'})
            df = result.data
            candles = []
            for _, row in df.iterrows():
                try:
                    candles.append({'open': float(row['Open']), 'high': float(row['High']), 'low': float(row['Low']), 'close': float(row['Close']), 'volume': float(row.get('Volume', 0))})
                except (ValueError, TypeError):
                    continue
            if len(candles) < 60:
                return web.json_response({'success': False, 'error': f'Need 60+ candles, have {len(candles)}'})
            from ..analytics.backtest_engine import BacktestEngine
            engine = BacktestEngine()
            bt_result = engine.run(candles, strategy_filter=strategy)
            return web.json_response({'success': True, 'data': {'strategy': bt_result.strategy, 'total_trades': bt_result.total_trades, 'wins': bt_result.wins, 'losses': bt_result.losses, 'win_rate': round(bt_result.win_rate, 1), 'total_pnl': round(bt_result.total_pnl, 1), 'avg_pnl': round(bt_result.avg_pnl, 1), 'max_drawdown': round(bt_result.max_drawdown, 1), 'profit_factor': round(bt_result.profit_factor, 2), 'sharpe_ratio': round(bt_result.sharpe_ratio, 2), 'best_trade': round(bt_result.best_trade, 1), 'worst_trade': round(bt_result.worst_trade, 1), 'equity_curve': bt_result.equity_curve[-50:], 'bars_tested': bt_result.bars_tested}})
        except Exception as e:
            logger.error(f'API: Backtest error: {e}')
            return web.json_response({'success': False, 'error': str(e)})

    async def _api_performance(self, request):
        """API endpoint for trading performance dashboard."""
        logger.debug('API: Fetching performance data...')
        try:
            stats = self.storage.get_trade_journal_stats()
            from ..learning.adaptive_tuner import AdaptiveTuner
            tuner = AdaptiveTuner(storage=self.storage)
            tuning = tuner.analyze()
            return web.json_response({'success': True, 'data': {'stats': stats, 'tuning': tuning}})
        except Exception as e:
            logger.error(f'API: Performance error: {e}')
            return web.json_response({'success': False, 'error': str(e)})

    async def _api_briefing(self, request):
        """API endpoint for voice briefing."""
        logger.debug('API: Generating market briefing...')
        try:
            from ..analytics.voice_briefing import VoiceBriefingEngine
            engine = VoiceBriefingEngine(orchestrator=self.orchestrator, storage=self.storage)
            briefing = await engine.generate_briefing()
            return web.json_response({'success': True, 'data': engine.format_for_api(briefing)})
        except Exception as e:
            logger.error(f'API: Briefing error: {e}')
            return web.json_response({'success': False, 'error': str(e)})

    async def _api_patterns(self, request):
        """API endpoint for detected chart patterns."""
        logger.debug('API: Fetching active patterns...')
        try:
            from .telegram_bot import SkillContext
        except ImportError:
            from ..skills.base import SkillContext
        try:
            ctx = SkillContext()
            result = await self.orchestrator.run_skill('technical_analysis', 'analyze', context=ctx, timeframe='H1')
            if not result.success:
                return web.json_response({'success': False, 'error': result.error})
            
            # The pattern skill output is nested in the technical analysis result
            ta_data = result.data
            patterns = ta_data.get('patterns', [])
            return web.json_response({'success': True, 'data': patterns})
        except Exception as e:
            logger.error(f'API: Patterns error: {e}')
            return web.json_response({'success': False, 'error': str(e)})

    async def _api_levels(self, request):
        """API endpoint for support/resistance levels."""
        logger.debug('API: Fetching key levels...')
        try:
            from .telegram_bot import SkillContext
        except ImportError:
            from ..skills.base import SkillContext
        try:
            ctx = SkillContext()
            result = await self.orchestrator.run_skill('technical_analysis', 'analyze', context=ctx, timeframe='H1')
            if not result.success:
                return web.json_response({'success': False, 'error': result.error})
            
            ta_data = result.data
            levels = ta_data.get('levels', {})
            return web.json_response({'success': True, 'data': levels})
        except Exception as e:
            logger.error(f'API: Levels error: {e}')
            return web.json_response({'success': False, 'error': str(e)})
            
    async def _api_settings(self, request):
        """API endpoint to get or update user settings/risk parameters."""
        # For simplicity in V4, global risk params
        if request.method == 'GET':
            try:
                # Stubbing settings API - integrating properly in the next steps
                return web.json_response({'success': True, 'data': {
                    'risk_per_trade': 1.0,
                    'max_daily_loss': 3.0,
                    'auto_trading_enabled': False
                }})
            except Exception as e:
                return web.json_response({'success': False, 'error': str(e)})
        else:
            return web.json_response({'success': False, 'error': 'Method not allowed'})


    async def _api_health(self, request):
        """Standard health check endpoint."""
        return web.Response(text='OK', content_type='text/plain')

    async def _serve_mini_app(self, request):
        """Serve the Zenith Terminal Mini App directly from the bot server."""
        mini_app_path = os.path.join(os.path.dirname(__file__), 'mini_app', 'index.html')
        if os.path.exists(mini_app_path):
            return web.FileResponse(mini_app_path, headers={'Content-Type': 'text/html; charset=utf-8'})
        return web.Response(text='Mini App not found', status=404)

    async def start_api_server(self):
        """Run the AIOHTTP server as a background task with robust error handling."""
        try:
            app = web.Application(middlewares=[self._cors_middleware])
            app.add_routes([
                web.get('/', self._serve_mini_app), 
                web.get('/app', self._serve_mini_app), 
                web.get('/healthz', self._api_health), 
                web.get('/api/summary', self._api_summary), 
                web.get('/api/signals', self._api_signals), 
                web.get('/api/scan_signals', self._api_scan_signals), 
                web.get('/api/alerts', self._api_alerts), 
                web.get('/api/analysis', self._api_analysis), 
                web.get('/api/candles', self._api_candles), 
                web.get('/api/status', self._api_status), 
                web.get('/api/forecast', self._api_forecast), 
                web.get('/api/macro', self._api_macro), 
                web.get('/api/backtest', self._api_backtest), 
                web.get('/api/performance', self._api_performance), 
                web.get('/api/briefing', self._api_briefing), 
                web.get('/api/trades', self._api_trades), 
                web.get('/api/history', self._api_history),
                web.get('/api/patterns', self._api_patterns),
                web.get('/api/levels', self._api_levels),
                web.get('/api/settings', self._api_settings)
            ])
            port = int(os.getenv('PORT', 8080))
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            logger.info(f'📡 Zenith API + Mini App at: http://0.0.0.0:{port}')
            logger.info(f'📱 Mini App URL: http://0.0.0.0:{port}/app')
            await site.start()
        except Exception as e:
            logger.error(f'❌ API Server CRASH: {e}')
            logger.error(traceback.format_exc())

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