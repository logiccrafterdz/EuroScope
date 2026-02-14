"""
EuroScope Automation Package — Heartbeat, Cron, Events, Alerts.
"""

from .heartbeat import HeartbeatService
from .cron import CronScheduler, TaskFrequency
from .events import EventBus, Event, SignalExecutorSubscriber, AlertSuppressionSubscriber, TelegramEmergencySubscriber
from .alerts import SmartAlerts, AlertPriority, AlertChannel, setup_default_alerts

__all__ = [
    "HeartbeatService",
    "CronScheduler", "TaskFrequency",
    "EventBus", "Event",
    "SignalExecutorSubscriber", "AlertSuppressionSubscriber", "TelegramEmergencySubscriber",
    "SmartAlerts", "AlertPriority", "AlertChannel", "setup_default_alerts",
]
