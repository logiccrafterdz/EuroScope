"""
Background Tasks and Cron Jobs for EuroScope Zenith.

Extracted from telegram_bot.py to improve modularity.
"""

import logging
from telegram.ext import ContextTypes

logger = logging.getLogger('euroscope.bot.tasks')


class BotTasks:
    """
    Handles all background cron jobs and scheduled tasks.
    """

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.config = bot_instance.config

    async def tick_job(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            await self.bot.cron._tick()
        except Exception as e:
            logger.error(f'Cron loop tick failed: {e}')

    async def task_resolve_patterns(self):
        """Periodically resolve pending patterns using latest price."""
        logger.info('Cron: Running pattern resolution...')
        price_data = await self.bot.price_provider.get_price()
        if 'error' in price_data:
            return
        current_price = price_data['price']
        await self.bot.pattern_tracker.resolve_pending(current_price)
        await self.bot.memory.resolve_pending_predictions(current_price)
        logger.info('Cron: Pattern resolution complete.')

    async def task_daily_tuning(self):
        """Analyze trade history once a day and report recommendations."""
        logger.info('Cron: Running daily strategy tuning...')
        report = await self.bot.adaptive_tuner.format_report()
        chat_ids = getattr(self.config, 'proactive_alert_chat_ids', []) or getattr(self.config.telegram, 'allowed_users', []) or []
        if chat_ids:
            await self.bot.notifications.broadcast_message(chat_ids, f'🧠 *Daily Strategy Optimization*\n\n{report}', parse_mode='Markdown')
        logger.info('Cron: Daily tuning complete.')

    async def task_weekly_reflection(self):
        logger.info('Cron: Running weekly reflection...')
        accuracy = await self.bot.storage.get_accuracy_stats(30)
        patterns = await self.bot.pattern_tracker.get_success_rates()
        stats = await self.bot.storage.get_trade_journal_stats()
        tuner = await self.bot.adaptive_tuner.analyze()
        lines = ['Weekly Reflection', f"Prediction accuracy (30d): {accuracy.get('accuracy', 0)}% ({accuracy.get('total', 0)})", f"Trades: {stats.get('total', 0)} | Win rate: {stats.get('win_rate', 0)}% | Avg PnL: {stats.get('avg_pnl', 0):+.1f}p"]
        if patterns:
            top = sorted(patterns.values(), key=lambda x: x['success_rate'], reverse=True)[:3]
            weak = sorted(patterns.values(), key=lambda x: x['success_rate'])[:2]
            lines.append('Top patterns: ' + ', '.join((f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in top)))
            lines.append('Weak patterns: ' + ', '.join((f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in weak)))
        if tuner.get('ready') and tuner.get('recommendations'):
            lines.append('Tuning focus: ' + ', '.join((r['param'] for r in tuner['recommendations'][:3])))
        insight = ' | '.join(lines)
        await self.bot.memory.save_insight(insight)
        if self.bot.vector_memory:
            self.bot.vector_memory.store_insight(insight, tags=['reflection', 'weekly'])
        await self.bot.workspace.refresh_memory(self.bot.storage)
        await self.bot.workspace.refresh_identity(self.bot.storage)
        logger.info('Cron: Weekly reflection complete.')

    async def task_daily_briefing(self):
        """Generate and broadcast the morning briefing."""
        logger.info('Cron: Running daily briefing...')
        report = await self.bot.briefing_engine.generate_briefing()
        chat_ids = self.config.proactive_alert_chat_ids
        if chat_ids:
            await self.bot.notifications.broadcast_message(report, chat_ids=chat_ids, parse_mode='HTML')
        logger.info('Cron: Daily briefing sent.')
