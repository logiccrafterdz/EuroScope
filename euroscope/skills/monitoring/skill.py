"""
Monitoring Skill — System health, uptime, and resource tracking.
"""

import os
import time
import psutil

from ...analytics.health_monitor import HealthMonitor
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

_START_TIME = time.time()


class MonitoringSkill(BaseSkill):
    name = "monitoring"
    description = "System health checks, error tracking, uptime and resource monitoring"
    emoji = "🏥"
    category = SkillCategory.SYSTEM
    version = "2.0.0"
    capabilities = ["check_health", "track_error", "get_status", "format_dashboard", "runtime_stats"]

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
        elif action == "runtime_stats":
            return self._runtime_stats()
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

    def _runtime_stats(self) -> SkillResult:
        """Get process-level runtime stats: uptime, memory, CPU."""
        try:
            uptime_sec = time.time() - _START_TIME
            hours, remainder = divmod(int(uptime_sec), 3600)
            minutes, seconds = divmod(remainder, 60)

            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)
            cpu_pct = process.cpu_percent(interval=0.1)

            stats = {
                "uptime_seconds": round(uptime_sec, 1),
                "uptime_formatted": f"{hours}h {minutes}m {seconds}s",
                "memory_mb": round(mem_mb, 1),
                "cpu_percent": cpu_pct,
                "pid": os.getpid(),
            }

            lines = [
                "🏥 *Runtime Stats*\n",
                f"⏱ Uptime: {stats['uptime_formatted']}",
                f"💾 Memory: {stats['memory_mb']} MB",
                f"🖥 CPU: {stats['cpu_percent']}%",
                f"🔧 PID: {stats['pid']}",
            ]

            return SkillResult(
                success=True,
                data=stats,
                metadata={"formatted": "\n".join(lines)},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

