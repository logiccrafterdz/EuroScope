import logging
from datetime import datetime, timezone
import math

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult
from ...data.calendar import EconomicCalendar, EconomicEvent

logger = logging.getLogger("euroscope.skills.macro_calendar")


class MacroCalendarSkill(BaseSkill):
    name = "macro_calendar"
    description = "Advanced calendar event tracking, impact assessment, and countdowns"
    emoji = "📆"
    category = SkillCategory.DATA
    version = "1.0.0"
    capabilities = ["get_upcoming", "check_impact", "time_to_event"]

    def __init__(self, calendar: EconomicCalendar = None):
        super().__init__()
        self._calendar = calendar or EconomicCalendar()

    def set_calendar(self, calendar: EconomicCalendar):
        self._calendar = calendar

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_upcoming":
            return await self._get_upcoming(context, **params)
        elif action == "check_impact":
            return await self._check_impact(context, **params)
        elif action == "time_to_event":
            return await self._time_to_event(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_upcoming(self, context: SkillContext, **params) -> SkillResult:
        try:
            impact_filter = params.get("impact")
            events = self._calendar.get_all_events()
            
            if impact_filter:
                events = [e for e in events if e.impact.lower() == impact_filter.lower()]
                
            formatted = self._calendar.format_calendar(events)
            data = [
                {
                    "name": e.name,
                    "currency": e.currency,
                    "impact": e.impact,
                    "description": e.description,
                    "typical_effect": e.typical_effect
                } for e in events
            ]
            
            context.analysis["upcoming_events"] = data
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            logger.error(f"Failed to get upcoming events: {e}")
            return SkillResult(success=False, error=str(e))

    async def _check_impact(self, context: SkillContext, **params) -> SkillResult:
        """
        Check if a high impact event is imminent (within 30 minutes).
        Currently simulates the time_to_event logic since the underlying calendar is static.
        """
        try:
            # For a fully dynamic calendar, we would compare event.time to datetime.now()
            # Here we provide the architectural foundation for it.
            simulated_minutes = params.get("simulated_minutes_to_event")
            
            imminent_events = []
            if simulated_minutes is not None and simulated_minutes <= 30:
                # Simulate an imminent high impact event if requested
                high_impact = self._calendar.get_high_impact_events()
                if high_impact:
                    imminent_events.append(high_impact[0])
            
            halt_recommended = len(imminent_events) > 0
            
            data = {
                "halt_recommended": halt_recommended,
                "imminent_events": [e.name for e in imminent_events],
                "reason": "High impact event within 30 minutes" if halt_recommended else "Clear"
            }
            
            # Inject into context for other skills
            context.metadata["macro_halt"] = halt_recommended
            
            formatted = "🚨 *MACRO HALT RECOMMENDED*" if halt_recommended else "✅ Macro Clear"
            if halt_recommended:
                formatted += f"\nImminent: {', '.join(data['imminent_events'])}"
                
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _time_to_event(self, context: SkillContext, **params) -> SkillResult:
        """Calculate time remaining until a specific event."""
        event_name = params.get("event_name")
        if not event_name:
            return SkillResult(success=False, error="event_name parameter is required")
            
        try:
            events = self._calendar.get_all_events()
            target = next((e for e in events if e.name.lower() == event_name.lower()), None)
            
            if not target:
                return SkillResult(success=False, error=f"Event not found: {event_name}")
                
            # Dynamic calendar would return actual delta. Mocking for now.
            simulated_minutes = params.get("simulated_minutes_to_event", 120)
            
            data = {
                "event": target.name,
                "minutes_remaining": simulated_minutes,
                "impact": target.impact
            }
            
            return SkillResult(success=True, data=data)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
