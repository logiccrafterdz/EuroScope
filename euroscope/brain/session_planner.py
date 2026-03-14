"""
Session Planner — The Agent's Daily Game Plan

Before each major trading session (London, New York), the agent creates
a structured Session Plan — exactly like a prop trader's morning prep.
This plan guides decisions during the session and provides a briefing
for the user.

Part of the EuroScope Agent Transformation (Phase 4).
"""

import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional, Any

from .world_model import WorldModel
from .conviction import ConvictionTracker

logger = logging.getLogger("euroscope.brain.session_planner")


@dataclass
class TradeScenario:
    """A pre-planned trading scenario."""
    name: str                           # e.g., "Trend Continuation Long"
    condition: str                      # e.g., "Price tests 1.0850 support and rejects"
    direction: str                      # "BUY" or "SELL"
    entry_zone: str                     # "1.0845 - 1.0855"
    invalidation_level: float = 0.0     # Where the scenario fails
    target_level: float = 0.0           # Where to take profit
    conviction_id: str = ""             # Linked conviction


@dataclass
class SessionPlan:
    """The agent's game plan for a specific trading session."""
    session_name: str                   # "London", "New York", "Asian"
    date_str: str                       # "2024-03-24"
    created_at: float = field(default_factory=time.time)
    status: str = "active"              # "active", "completed", "skipped"

    # Market Context
    starting_price: float = 0.0
    regime: str = ""                    # "trending", "ranging"
    bias: str = "neutral"               # "bullish", "bearish"
    volatility_expectation: str = "normal"

    # Key Levels
    support_levels: list[float] = field(default_factory=list)
    resistance_levels: list[float] = field(default_factory=list)
    key_zones: list[str] = field(default_factory=list)

    # Catalysts
    macro_events: list[dict] = field(default_factory=list)
    high_impact_warning: bool = False

    # Agent's Stance
    active_convictions: list[dict] = field(default_factory=list)
    risk_budget_pct: float = 1.0        # How much risk is allocated to this session
    allowed_directions: list[str] = field(default_factory=lambda: ["BUY", "SELL"])

    # Trade Scenarios
    scenarios: list[TradeScenario] = field(default_factory=list)

    # Summary
    briefing_text: str = ""


class SessionPlanner:
    """
    Creates and manages session plans for the agent.

    Typically called by the Agent Core right before London open
    (07:00 UTC) and New York open (12:00 UTC).
    """

    def __init__(self, llm_interface=None):
        self.llm_interface = llm_interface
        self.current_plan: Optional[SessionPlan] = None
        self.history: list[SessionPlan] = []

    async def generate_plan(
        self,
        session_name: str,
        world_model: WorldModel,
        conviction_tracker: ConvictionTracker,
    ) -> Optional[SessionPlan]:
        """
        Generate a new game plan for the upcoming session.
        Uses the LLM to synthesize data into actionable scenarios.
        """
        logger.info(f"Generating session plan for: {session_name}")

        today_str = datetime.now(UTC).strftime("%Y-%m-%d")

        # Basic context extraction
        plan = SessionPlan(
            session_name=session_name,
            date_str=today_str,
            starting_price=world_model.price.price,
            regime=world_model.regime.regime,
            bias=world_model.technical.overall_bias,
            volatility_expectation=world_model.regime.volatility,
            support_levels=world_model.technical.support_levels[:3],
            resistance_levels=world_model.technical.resistance_levels[:3],
        )

        # Extract macro events for today
        for event in world_model.fundamental.upcoming_events:
            event_date = str(event.get("time", ""))[:10]  # rough check
            if event_date == today_str or event.get("minutes_to_event", 999) < 1440:
                plan.macro_events.append(event)
                if event.get("impact") == "high":
                    plan.high_impact_warning = True

        # Extract active convictions
        for conv in conviction_tracker.get_active_convictions():
            plan.active_convictions.append({
                "id": conv.id,
                "direction": conv.direction,
                "thesis": conv.thesis,
                "confidence": conv.confidence,
            })

        # Set allowed directions based on convictions and regime
        dom_dir, conf = conviction_tracker.get_dominant_direction()
        if dom_dir != "neutral" and conf > 0.6:
            # Strong bias -> trade only with bias
            plan.allowed_directions = [dom_dir.upper()]
        elif world_model.regime.regime == "trending":
            # Trending -> trade with trend
            plan.allowed_directions = [world_model.regime.direction.upper()]
        else:
            # Ranging -> trade both sides
            plan.allowed_directions = ["BUY", "SELL"]

        # If LLM is available, use it to generate scenarios and briefing
        if self.llm_interface:
            try:
                await self._enrich_plan_with_llm(plan, world_model, conviction_tracker)
            except Exception as e:
                logger.error(f"Failed to enrich session plan with LLM: {e}")
                self._generate_heuristic_scenarios(plan)
        else:
            self._generate_heuristic_scenarios(plan)

        # Build fallback briefing if LLM failed
        if not plan.briefing_text:
            plan.briefing_text = self._format_basic_briefing(plan)

        # Archive old plan and set new one
        if self.current_plan:
            self.current_plan.status = "completed"
            self.history.append(self.current_plan)
            # Keep history bounded
            if len(self.history) > 10:
                self.history = self.history[-10:]

        self.current_plan = plan
        logger.info(f"Session plan generated: {len(plan.scenarios)} scenarios, directions: {plan.allowed_directions}")
        return plan

    async def _enrich_plan_with_llm(
        self,
        plan: SessionPlan,
        world_model: WorldModel,
        conviction_tracker: ConvictionTracker,
    ) -> None:
        """Use LLM to generate trade scenarios and a briefing text."""

        system_prompt = (
            "You are EuroScope's internal Session Planning engine. "
            "Your job is to act like a senior prop trader creating a game plan "
            "for the upcoming trading session. Define 1-3 specific 'If-Then' scenarios "
            "and write a short, punchy briefing."
        )

        user_prompt = (
            f"Create a session plan for the {plan.session_name} session.\n\n"
            f"--- Context ---\n"
            f"{world_model.get_summary()}\n\n"
            f"{conviction_tracker.get_summary()}\n\n"
            f"Allowed Directions: {plan.allowed_directions}\n\n"
            "--- Task ---\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            "{\n"
            "  \"briefing_text\": \"A 3-4 sentence professional summary of the game plan.\",\n"
            "  \"key_zones\": [\"1.0850 - 1.0860 (Support)\", \"1.0920 (Resistance)\"],\n"
            "  \"scenarios\": [\n"
            "    {\n"
            "      \"name\": \"Trend Continuation Long\",\n"
            "      \"condition\": \"Price dips into London open, tests 1.0850 and rejects\",\n"
            "      \"direction\": \"BUY\",\n"
            "      \"entry_zone\": \"1.0850 - 1.0855\",\n"
            "      \"invalidation_level\": 1.0830,\n"
            "      \"target_level\": 1.0900\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        response = await self.llm_interface.stateless_chat(
            user_message=user_prompt,
            system_override=system_prompt,
        )

        # Parse JSON
        import json
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())

            plan.briefing_text = data.get("briefing_text", "")
            plan.key_zones = data.get("key_zones", [])

            scenarios_data = data.get("scenarios", [])
            for s_data in scenarios_data:
                # Filter scenarios to match allowed directions
                direction = str(s_data.get("direction", "")).upper()
                if direction in plan.allowed_directions:
                    scenario = TradeScenario(
                        name=s_data.get("name", "Trade Setup"),
                        condition=s_data.get("condition", ""),
                        direction=direction,
                        entry_zone=s_data.get("entry_zone", ""),
                        invalidation_level=float(s_data.get("invalidation_level", 0)),
                        target_level=float(s_data.get("target_level", 0)),
                    )
                    plan.scenarios.append(scenario)

    def _generate_heuristic_scenarios(self, plan: SessionPlan) -> None:
        """Fallback to generate basic scenarios without LLM."""
        plan.key_zones = []

        # Add support zone
        if plan.support_levels:
            s1 = plan.support_levels[0]
            plan.key_zones.append(f"{s1:.5f} (Immediate Support)")
            if "BUY" in plan.allowed_directions:
                plan.scenarios.append(TradeScenario(
                    name="Support Bounce",
                    condition=f"Price tests {s1:.5f} support level and forms bullish reversal pattern",
                    direction="BUY",
                    entry_zone=f"{s1:.5f} - {s1 + 0.0010:.5f}",
                    invalidation_level=s1 - 0.0020,
                    target_level=s1 + 0.0050,
                ))

        # Add resistance zone
        if plan.resistance_levels:
            r1 = plan.resistance_levels[0]
            plan.key_zones.append(f"{r1:.5f} (Immediate Resistance)")
            if "SELL" in plan.allowed_directions:
                plan.scenarios.append(TradeScenario(
                    name="Resistance Rejection",
                    condition=f"Price tests {r1:.5f} resistance level and forms bearish reversal pattern",
                    direction="SELL",
                    entry_zone=f"{r1 - 0.0010:.5f} - {r1:.5f}",
                    invalidation_level=r1 + 0.0020,
                    target_level=r1 - 0.0050,
                ))

    def _format_basic_briefing(self, plan: SessionPlan) -> str:
        """Create a basic text briefing."""
        bias_str = "Bullish" if "BUY" in plan.allowed_directions and "SELL" not in plan.allowed_directions else \
                   "Bearish" if "SELL" in plan.allowed_directions and "BUY" not in plan.allowed_directions else \
                   "Neutral/Two-Sided"

        return (
            f"Entering the {plan.session_name} session "
            f"in a {plan.regime} regime from {plan.starting_price:.5f}. "
            f"The game plan is {bias_str}. "
            f"Watching {len(plan.scenarios)} specific trade scenarios."
        )

    def get_current_plan_formatted(self) -> str:
        """Format the current plan for Telegram display."""
        if not self.current_plan:
            return "No active session plan."

        plan = self.current_plan

        lines = [
            f"📋 <b>{plan.session_name.upper()} SESSION PLAN</b>",
            f"<i>{plan.date_str}</i>\n",
            f"<b>Briefing:</b>",
            f"{plan.briefing_text}\n",
        ]

        if plan.high_impact_warning:
            lines.append("⚠️ <b>CAUTION: High impact macro events scheduled during this session.</b>\n")

        lines.append("🗺️ <b>Key Zones:</b>")
        for zone in plan.key_zones:
            lines.append(f"• {zone}")

        if not plan.key_zones:
            lines.append("• Not specified")

        lines.append("\n🎯 <b>Trade Scenarios:</b>")
        for idx, s in enumerate(plan.scenarios, 1):
            icon = "🟢" if s.direction == "BUY" else "🔴"
            lines.append(f"<b>{idx}. {icon} {s.name}</b>")
            lines.append(f"   <i>If:</i> {s.condition}")
            lines.append(f"   <i>Zone:</i> {s.entry_zone}")
            lines.append(f"   <i>Invalidation:</i> {s.invalidation_level:.5f}")
            lines.append("")

        if not plan.scenarios:
            lines.append("No specific setups planned. Wait and see.")

        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────

    def serialize(self) -> dict:
        return {
            "current_plan": asdict(self.current_plan) if self.current_plan else None,
            "history_count": len(self.history),
        }

    def deserialize(self, data: dict) -> None:
        if not data:
            return

        plan_data = data.get("current_plan")
        if plan_data:
            scenarios = []
            for s in plan_data.pop("scenarios", []):
                scenarios.append(TradeScenario(**s))
            
            self.current_plan = SessionPlan(**plan_data)
            self.current_plan.scenarios = scenarios

        logger.info(f"SessionPlanner restored (has plan: {self.current_plan is not None})")
