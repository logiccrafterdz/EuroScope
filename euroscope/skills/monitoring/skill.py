"""
Monitoring Skill — Wraps HealthMonitor for the skills framework.
"""

from ...analytics.health_monitor import HealthMonitor
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class MonitoringSkill(BaseSkill):
    name = "monitoring"
    description = "System health checks, error tracking, and uptime monitoring"
    emoji = "🏥"
    category = SkillCategory.SYSTEM
    version = "1.0.0"
    capabilities = ["check_health", "track_error", "get_status", "format_dashboard"]

    def __init__(self, storage=None):
        super().__init__()
        self.monitor = HealthMonitor(storage=storage)

    def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "check_health":
            return self._check()
        elif action == "track_error":
            return self._track_error(**params)
        elif action == "get_status":
            return self._status()
        elif action == "format_dashboard":
            return self._dashboard()
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _check(self) -> SkillResult:
        try:
            report = self.monitor.full_check()
            return SkillResult(success=True, data=report)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _track_error(self, **params) -> SkillResult:
        component = params.get("component", "unknown")
        error_msg = params.get("error", "Unknown error")
        self.monitor.record_error(component, error_msg)
        return SkillResult(success=True, data={"tracked": True})

    def _status(self) -> SkillResult:
        try:
            report = self.monitor.full_check()
            return SkillResult(success=True, data={
                "status": report.get("overall_status", "unknown"),
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _dashboard(self) -> SkillResult:
        try:
            report = self.monitor.full_check()
            text = self.monitor.format_health_report(report)
            return SkillResult(success=True, data=text)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
