"""
Agent Core — The Autonomous EUR/USD Specialist

The central state machine that replaces the passive chatbot loop
as the system's heartbeat. Continuously scans, analyzes, forms
convictions, and acts — like a senior prop trader on the desk.

States:
    IDLE → SCANNING → ANALYZING → CONVICTION_FORMING → DECIDING → EXECUTING → MONITORING → REVIEWING

Part of the EuroScope Agent Transformation (Phase 3).
"""

import asyncio
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional, Any, Callable

from .world_model import WorldModel
from .conviction import ConvictionTracker, Conviction, Evidence

logger = logging.getLogger("euroscope.brain.agent_core")


# ── Agent States ──────────────────────────────────────────────

class AgentState(str, Enum):
    """Agent state machine states."""
    IDLE = "idle"                            # Waiting (off-hours, weekend)
    SCANNING = "scanning"                    # Quick market scan
    ANALYZING = "analyzing"                  # Deep pipeline analysis
    CONVICTION_FORMING = "conviction_forming" # Building/updating thesis
    DECIDING = "deciding"                    # Evaluating whether to act
    EXECUTING = "executing"                  # Opening/closing trades
    MONITORING = "monitoring"                # Watching open positions
    REVIEWING = "reviewing"                  # Post-trade review / learning


class AgentActionType(str, Enum):
    """Types of actions the agent can take."""
    NONE = "none"
    ALERT_USER = "alert_user"
    OPEN_TRADE = "open_trade"
    CLOSE_TRADE = "close_trade"
    UPDATE_CONVICTION = "update_conviction"
    CREATE_CONVICTION = "create_conviction"
    INVALIDATE_CONVICTION = "invalidate_conviction"
    SESSION_BRIEFING = "session_briefing"
    MARKET_PULSE = "market_pulse"


@dataclass
class AgentAction:
    """An action produced by the agent's reasoning."""
    action_type: AgentActionType
    priority: str = "medium"          # "critical", "high", "medium", "low"
    data: dict = field(default_factory=dict)
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentCycleStats:
    """Statistics for a single agent cycle."""
    state_transitions: list = field(default_factory=list)
    duration_seconds: float = 0.0
    actions_produced: int = 0
    skills_invoked: int = 0
    conviction_events: int = 0
    error: str = ""


# ── Agent Core ────────────────────────────────────────────────

class EuroScopeAgent:
    """
    The autonomous EUR/USD specialist agent.

    Runs a continuous async loop, maintaining situational awareness
    through the WorldModel and forming trading theses through the
    ConvictionTracker. Communicates decisions through AgentActions.
    """

    # Timing configuration (seconds)
    SCAN_INTERVAL = 60               # Quick scan every 60s
    DEEP_ANALYSIS_INTERVAL = 300     # Full pipeline every 5 min
    CONVICTION_REVIEW_INTERVAL = 180 # Review convictions every 3 min
    MONITORING_INTERVAL = 30         # Monitor open trades every 30s
    IDLE_CHECK_INTERVAL = 120        # Check if should wake up every 2 min

    def __init__(
        self,
        orchestrator,
        config=None,
        storage=None,
        llm_interface=None,
    ):
        self.orchestrator = orchestrator
        self.config = config
        self.storage = storage
        self.llm_interface = llm_interface  # The old Agent class (renamed)

        # Core components
        self.world_model = WorldModel()
        self.conviction_tracker = ConvictionTracker()
        self.state = AgentState.IDLE

        # Timing
        self._last_scan: float = 0
        self._last_deep_analysis: float = 0
        self._last_conviction_review: float = 0
        self._last_monitoring: float = 0
        self._cycle_count: int = 0
        self._started_at: float = 0

        # Action handlers — external code registers callbacks
        self._action_handlers: dict[AgentActionType, list[Callable]] = {}

        # Running state
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._paused: bool = False

        # Stats
        self._total_actions: int = 0
        self._total_errors: int = 0
        self._state_history: list[tuple[float, str]] = []

    # ── Lifecycle ─────────────────────────────────────────────

    async def start(self) -> None:
        """Start the agent's continuous loop."""
        if self._running:
            logger.warning("Agent already running")
            return

        self._running = True
        self._started_at = time.time()

        # Restore state if available
        await self._restore_state()

        logger.info("🤖 EuroScope Agent ONLINE — Autonomous EUR/USD Specialist activated")
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Gracefully stop the agent."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._persist_state()
        logger.info(
            f"🛑 EuroScope Agent OFFLINE after {self._cycle_count} cycles, "
            f"{self._total_actions} actions"
        )

    def pause(self) -> None:
        """Pause the agent (keeps running but skips actions)."""
        self._paused = True
        logger.info("⏸️ Agent paused")

    def resume(self) -> None:
        """Resume the agent."""
        self._paused = False
        logger.info("▶️ Agent resumed")

    # ── Main Loop ─────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """The agent's continuous reasoning loop."""
        while self._running:
            try:
                stats = await self._tick()
                if stats.error:
                    self._total_errors += 1
                    logger.error(f"Agent tick error: {stats.error}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._total_errors += 1
                logger.error(f"Agent loop exception: {e}", exc_info=True)
                await asyncio.sleep(30)  # Back off on error
                continue

            # Dynamic sleep based on state
            sleep_time = self._get_sleep_time()
            await asyncio.sleep(sleep_time)

    async def _tick(self) -> AgentCycleStats:
        """
        One cycle of the agent's reasoning.

        The OODA loop: Observe → Orient → Decide → Act
        """
        stats = AgentCycleStats()
        cycle_start = time.time()
        self._cycle_count += 1

        if self._paused:
            return stats

        try:
            # ── OBSERVE: Update situational awareness ──
            new_state = self._determine_next_state()
            if new_state != self.state:
                self._transition_to(new_state, stats)

            if self.state == AgentState.IDLE:
                # Check if we should wake up
                if self._should_activate():
                    self._transition_to(AgentState.SCANNING, stats)
                else:
                    stats.duration_seconds = time.time() - cycle_start
                    return stats

            # ── SCANNING: Quick market update ──
            if self.state == AgentState.SCANNING:
                await self._do_scan(stats)

                # Check if deep analysis needed
                if self._needs_deep_analysis():
                    self._transition_to(AgentState.ANALYZING, stats)
                else:
                    self._transition_to(AgentState.CONVICTION_FORMING, stats)

            # ── ANALYZING: Full pipeline ──
            if self.state == AgentState.ANALYZING:
                await self._do_deep_analysis(stats)
                self._transition_to(AgentState.CONVICTION_FORMING, stats)

            # ── CONVICTION_FORMING: Update theses ──
            if self.state == AgentState.CONVICTION_FORMING:
                await self._do_conviction_update(stats)

                # Decide what to do next
                if self.world_model.has_open_trades():
                    self._transition_to(AgentState.MONITORING, stats)
                elif self._should_evaluate_trade():
                    self._transition_to(AgentState.DECIDING, stats)
                else:
                    self._transition_to(AgentState.SCANNING, stats)

            # ── DECIDING: Evaluate potential actions ──
            if self.state == AgentState.DECIDING:
                actions = await self._do_decide(stats)
                if any(a.action_type in (AgentActionType.OPEN_TRADE, AgentActionType.CLOSE_TRADE) for a in actions):
                    self._transition_to(AgentState.EXECUTING, stats)
                else:
                    self._transition_to(AgentState.SCANNING, stats)

                for action in actions:
                    await self._dispatch_action(action, stats)

            # ── EXECUTING: Execute trade actions ──
            if self.state == AgentState.EXECUTING:
                # Execution is handled by dispatched actions above
                self._transition_to(AgentState.MONITORING, stats)

            # ── MONITORING: Watch open positions ──
            if self.state == AgentState.MONITORING:
                await self._do_monitoring(stats)
                if not self.world_model.has_open_trades():
                    self._transition_to(AgentState.REVIEWING, stats)
                else:
                    self._transition_to(AgentState.SCANNING, stats)

            # ── REVIEWING: Post-trade learning ──
            if self.state == AgentState.REVIEWING:
                await self._do_review(stats)
                self._transition_to(AgentState.SCANNING, stats)

        except Exception as e:
            stats.error = str(e)
            logger.error(f"Agent tick failed at state {self.state}: {e}", exc_info=True)
            self._transition_to(AgentState.SCANNING, stats)

        stats.duration_seconds = time.time() - cycle_start
        return stats

    # ── State Handlers ────────────────────────────────────────

    async def _do_scan(self, stats: AgentCycleStats) -> None:
        """Quick market scan — price + key indicators."""
        now = time.time()
        if now - self._last_scan < self.SCAN_INTERVAL / 2:
            return  # Too soon

        try:
            # Quick price fetch
            res = await self.orchestrator.run_skill("market_data", "get_price")
            if res.success and "price" in res.data:
                self.world_model.update_price_tick(
                    price=res.data["price"],
                    bid=res.data.get("bid", 0),
                    ask=res.data.get("ask", 0),
                )
                stats.skills_invoked += 1

            # Session detection
            res_session = await self.orchestrator.run_skill("session_context", "detect")
            if res_session.success:
                stats.skills_invoked += 1

            self._last_scan = now
        except Exception as e:
            logger.warning(f"Scan failed: {e}")

    async def _do_deep_analysis(self, stats: AgentCycleStats) -> None:
        """Full analysis pipeline — updates entire world model."""
        try:
            ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe="H1")
            self.world_model.update_from_pipeline(ctx)
            stats.skills_invoked += 5  # Pipeline runs ~5 skills

            # Also update risk state from open trades
            try:
                trades_res = await self.orchestrator.run_skill("signal_executor", "list_trades")
                if trades_res.success and trades_res.data:
                    open_trades = [t for t in trades_res.data if str(t.get("status", "")).upper() == "OPEN"]
                    self.world_model.update_risk_state(open_trades)
            except Exception:
                pass

            self._last_deep_analysis = time.time()
            logger.info(f"Deep analysis complete: {self.world_model.get_compact_summary()}")
        except Exception as e:
            logger.error(f"Deep analysis failed: {e}", exc_info=True)

    async def _do_conviction_update(self, stats: AgentCycleStats) -> None:
        """Update convictions based on latest world model data."""
        # 1. Tick existing convictions (handles invalidation, expiration, etc.)
        events = self.conviction_tracker.tick(self.world_model.price.price)
        stats.conviction_events = len(events)

        for event in events:
            if event["type"] == "invalidated":
                await self._dispatch_action(AgentAction(
                    action_type=AgentActionType.ALERT_USER,
                    priority="high",
                    data=event,
                    reasoning=f"Conviction invalidated: {event.get('reason', '')}",
                ), stats)
            elif event["type"] == "realized":
                await self._dispatch_action(AgentAction(
                    action_type=AgentActionType.ALERT_USER,
                    priority="medium",
                    data=event,
                    reasoning=f"Conviction thesis realized: {event.get('thesis', '')}",
                ), stats)

        # 2. Check if world model delta warrants new evidence
        delta = self.world_model.get_delta()
        if not delta or delta.get("initial"):
            return

        active_convictions = self.conviction_tracker.get_active_convictions()

        # Add evidence to existing convictions based on deltas
        for conv in active_convictions:
            new_evidence = self._generate_evidence_from_delta(conv, delta)
            for ev in new_evidence:
                self.conviction_tracker.add_evidence(conv.id, ev)

        # 3. Check if we should form a new conviction
        if len(active_convictions) < ConvictionTracker.MAX_ACTIVE_CONVICTIONS:
            if self.world_model.has_significant_change():
                await self._consider_new_conviction(stats)

        self._last_conviction_review = time.time()

    async def _do_decide(self, stats: AgentCycleStats) -> list[AgentAction]:
        """Evaluate whether to take action based on convictions + world model."""
        actions = []

        strongest = self.conviction_tracker.get_strongest()
        if not strongest or not strongest.is_active():
            return actions

        # Only act if conviction is strong enough
        if strongest.confidence < ConvictionTracker.MIN_CONFIDENCE_TO_ACT:
            return actions

        # Map conviction direction to trade direction
        trade_direction = "BUY" if strongest.direction == "bullish" else "SELL"

        # Check if we already have a trade in this direction
        for trade in self.world_model.risk.open_trades:
            if trade.get("direction") == trade_direction:
                return actions  # Already positioned

        # Check risk constraints
        if not self.world_model.risk.is_trading_allowed:
            logger.info("Decision: trading blocked by risk constraints")
            return actions

        if self.world_model.risk.open_trade_count >= 3:
            logger.info("Decision: max open trades reached")
            return actions

        # Check opposing conviction
        if self.conviction_tracker.has_opposing_conviction(strongest.direction):
            logger.info("Decision: opposing conviction exists — waiting for resolution")
            return actions

        # Check session — don't open in low-liquidity hours
        if not self.world_model.session.is_high_liquidity:
            logger.debug("Decision: waiting for high-liquidity session")
            return actions

        # Check if near high-impact event
        if self.world_model.is_near_event(minutes_threshold=15):
            logger.info("Decision: high-impact event imminent — standing aside")
            return actions

        # 🟢 All checks passed — propose trade
        actions.append(AgentAction(
            action_type=AgentActionType.OPEN_TRADE,
            priority="high",
            data={
                "direction": trade_direction,
                "conviction_id": strongest.id,
                "conviction_thesis": strongest.thesis,
                "conviction_confidence": strongest.confidence,
                "regime": self.world_model.regime.regime,
                "price": self.world_model.price.price,
            },
            reasoning=(
                f"Opening {trade_direction} based on conviction '{strongest.thesis}' "
                f"({strongest.confidence:.0%} confidence) in {self.world_model.regime.regime} regime"
            ),
        ))

        # Alert user about the decision
        actions.append(AgentAction(
            action_type=AgentActionType.ALERT_USER,
            priority="high",
            data={
                "type": "trade_decision",
                "direction": trade_direction,
                "conviction": strongest.thesis,
                "confidence": strongest.confidence,
                "world_summary": self.world_model.get_compact_summary(),
            },
            reasoning=f"Notifying user of autonomous trade decision",
        ))

        return actions

    async def _do_monitoring(self, stats: AgentCycleStats) -> None:
        """Monitor open positions — check trailing stops, TP/SL proximity."""
        now = time.time()
        if now - self._last_monitoring < self.MONITORING_INTERVAL:
            return

        if not self.world_model.has_open_trades():
            return

        price = self.world_model.price.price
        if not price:
            return

        for trade in self.world_model.risk.open_trades:
            floating_pnl = trade.get("floating_pnl", 0)
            direction = trade.get("direction", "")
            tp = trade.get("take_profit", 0)
            sl = trade.get("stop_loss", 0)

            # Alert on large floating profit
            if floating_pnl > 30:
                await self._dispatch_action(AgentAction(
                    action_type=AgentActionType.ALERT_USER,
                    priority="medium",
                    data={
                        "type": "floating_profit",
                        "trade_id": trade.get("trade_id"),
                        "direction": direction,
                        "pnl_pips": floating_pnl,
                    },
                    reasoning=f"Open trade has +{floating_pnl:.1f} pips — consider partial close",
                ), stats)

            # Alert on approaching TP
            if tp and price:
                dist_to_tp = abs(tp - price) * 10000
                if dist_to_tp < 5:
                    await self._dispatch_action(AgentAction(
                        action_type=AgentActionType.ALERT_USER,
                        priority="low",
                        data={"type": "approaching_tp", "distance_pips": dist_to_tp},
                        reasoning=f"Price {dist_to_tp:.1f} pips from take profit",
                    ), stats)

        self._last_monitoring = now

    async def _do_review(self, stats: AgentCycleStats) -> None:
        """Post-trade review — log what happened and learn."""
        # Check conviction accuracy
        accuracy = self.conviction_tracker.get_accuracy_stats()
        if accuracy["total"] > 0:
            logger.info(
                f"📊 Conviction Review: {accuracy['accuracy']:.1f}% accuracy "
                f"({accuracy['realized']}/{accuracy['total']} realized)"
            )

    # ── Evidence Generation ───────────────────────────────────

    def _generate_evidence_from_delta(self, conv: Conviction, delta: dict) -> list[Evidence]:
        """Generate evidence for a conviction from world model changes."""
        evidence = []

        # Regime change
        if "regime" in delta:
            new_regime = delta["regime"]["new"]
            if conv.direction == "bullish" and new_regime == "trending":
                evidence.append(Evidence(
                    text=f"Market shifted to trending regime (supports bullish thesis)",
                    source="regime",
                    weight=1.5,
                    direction="for",
                ))
            elif conv.direction == "bearish" and new_regime == "trending":
                evidence.append(Evidence(
                    text=f"Market shifted to trending regime",
                    source="regime",
                    weight=1.0,
                    direction="for" if self.world_model.regime.direction == "bearish" else "against",
                ))

        # Bias change
        if "bias" in delta:
            new_bias = delta["bias"]["new"]
            if new_bias == conv.direction:
                evidence.append(Evidence(
                    text=f"Technical bias shifted to {new_bias} (confirms thesis)",
                    source="technical",
                    weight=1.2,
                    direction="for",
                ))
            elif new_bias != "neutral" and new_bias != conv.direction:
                evidence.append(Evidence(
                    text=f"Technical bias shifted to {new_bias} (contradicts thesis)",
                    source="technical",
                    weight=1.5,
                    direction="against",
                ))

        # Direction change
        if "direction" in delta:
            new_dir = delta["direction"]["new"]
            if new_dir == conv.direction:
                evidence.append(Evidence(
                    text=f"Overall direction now {new_dir} (confirms thesis)",
                    source="technical",
                    weight=1.0,
                    direction="for",
                ))
            elif new_dir != "neutral":
                evidence.append(Evidence(
                    text=f"Overall direction flipped to {new_dir} (challenges thesis)",
                    source="technical",
                    weight=1.8,
                    direction="against",
                ))

        # Liquidity sweep
        if "sweep" in delta and delta["sweep"]["new"]:
            evidence.append(Evidence(
                text="Liquidity sweep detected",
                source="liquidity",
                weight=1.5,
                direction="for" if self.world_model.liquidity.liquidity_bias == conv.direction else "against",
            ))

        return evidence

    async def _consider_new_conviction(self, stats: AgentCycleStats) -> None:
        """Use LLM to evaluate whether current conditions warrant a new conviction."""
        if not self.llm_interface:
            # Heuristic-only conviction formation (no LLM)
            self._form_heuristic_conviction()
            return

        # Build prompt for LLM reasoning
        prompt = (
            "Based on the current market state, should the agent form a new conviction?\n\n"
            f"{self.world_model.get_summary()}\n\n"
            f"{self.conviction_tracker.get_summary()}\n\n"
            "If yes, respond with a JSON block:\n"
            '{"form_conviction": true, "thesis": "...", "direction": "bullish/bearish", '
            '"invalidation_level": 0.0, "invalidation_reason": "...", "target_level": 0.0}\n\n'
            "If no, respond with: {\"form_conviction\": false, \"reason\": \"...\"}"
        )

        try:
            response = await self.llm_interface.stateless_chat(
                user_message=prompt,
                system_override=(
                    "You are EuroScope's internal reasoning engine. "
                    "Analyze the world model and decide if a new trading conviction should be formed. "
                    "Be selective — only form convictions with clear evidence. "
                    "Respond ONLY with the JSON as specified."
                ),
            )

            # Parse response
            import json
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group())
                if decision.get("form_conviction"):
                    initial_evidence = self._gather_initial_evidence(decision.get("direction", "neutral"))
                    self.conviction_tracker.create_conviction(
                        thesis=decision.get("thesis", ""),
                        direction=decision.get("direction", "neutral"),
                        initial_evidence=initial_evidence,
                        invalidation_level=decision.get("invalidation_level", 0),
                        invalidation_reason=decision.get("invalidation_reason", ""),
                        target_level=decision.get("target_level", 0),
                        regime=self.world_model.regime.regime,
                    )
                    stats.conviction_events += 1
        except Exception as e:
            logger.warning(f"LLM conviction reasoning failed: {e}")
            self._form_heuristic_conviction()

    def _form_heuristic_conviction(self) -> None:
        """Form a conviction from pure technical heuristics (no LLM needed)."""
        wm = self.world_model

        # Only form if signals are clear
        if wm.technical.adx < 25:
            return  # No clear trend
        if wm.regime.regime not in ("trending", "breakout"):
            return

        direction = wm.regime.direction
        if direction == "neutral":
            return

        # Gather evidence
        evidence = self._gather_initial_evidence(direction)
        if len([e for e in evidence if e.direction == "for"]) < 2:
            return  # Not enough supporting evidence

        # Set invalidation based on S/R levels
        if direction == "bullish" and wm.technical.support_levels:
            invalidation = wm.technical.support_levels[0]
            invalidation_reason = f"Break below support at {invalidation:.5f}"
        elif direction == "bearish" and wm.technical.resistance_levels:
            invalidation = wm.technical.resistance_levels[0]
            invalidation_reason = f"Break above resistance at {invalidation:.5f}"
        else:
            invalidation = 0
            invalidation_reason = ""

        thesis = (
            f"{direction.title()} EUR/USD based on {wm.regime.regime} regime "
            f"(ADX: {wm.technical.adx:.0f}, RSI: {wm.technical.rsi:.0f}, "
            f"bias: {wm.technical.overall_bias})"
        )

        self.conviction_tracker.create_conviction(
            thesis=thesis,
            direction=direction,
            initial_evidence=evidence,
            invalidation_level=invalidation,
            invalidation_reason=invalidation_reason,
            regime=wm.regime.regime,
        )

    def _gather_initial_evidence(self, direction: str) -> list[Evidence]:
        """Gather initial evidence from the world model for a new conviction."""
        evidence = []
        wm = self.world_model

        # Technical bias
        if wm.technical.overall_bias == direction:
            evidence.append(Evidence(
                text=f"Technical bias is {direction}",
                source="technical",
                weight=1.2,
                direction="for",
            ))
        elif wm.technical.overall_bias != "neutral":
            evidence.append(Evidence(
                text=f"Technical bias is {wm.technical.overall_bias} (opposing)",
                source="technical",
                weight=1.0,
                direction="against",
            ))

        # ADX trend strength
        if wm.technical.adx > 30:
            evidence.append(Evidence(
                text=f"Strong trend (ADX: {wm.technical.adx:.0f})",
                source="technical",
                weight=1.3,
                direction="for",
            ))

        # RSI confirmation
        if direction == "bullish" and 40 < wm.technical.rsi < 70:
            evidence.append(Evidence(
                text=f"RSI has room (RSI: {wm.technical.rsi:.0f})",
                source="technical",
                weight=0.8,
                direction="for",
            ))
        elif direction == "bearish" and 30 < wm.technical.rsi < 60:
            evidence.append(Evidence(
                text=f"RSI has room (RSI: {wm.technical.rsi:.0f})",
                source="technical",
                weight=0.8,
                direction="for",
            ))

        # MACD confirmation
        if (direction == "bullish" and wm.technical.macd_histogram > 0) or \
           (direction == "bearish" and wm.technical.macd_histogram < 0):
            evidence.append(Evidence(
                text=f"MACD histogram confirms direction ({wm.technical.macd_histogram:.5f})",
                source="technical",
                weight=1.0,
                direction="for",
            ))

        # Regime confirmation
        if wm.regime.regime == "trending" and wm.regime.direction == direction:
            evidence.append(Evidence(
                text=f"Market in trending regime aligned with {direction} direction",
                source="regime",
                weight=1.5,
                direction="for",
            ))

        # MTF confirmation
        if wm.regime.mtf_bias == direction:
            evidence.append(Evidence(
                text=f"Higher timeframe ({wm.regime.mtf_timeframe}) confirms {direction}",
                source="technical",
                weight=1.5,
                direction="for",
            ))
        elif wm.regime.mtf_bias != "neutral" and wm.regime.mtf_bias != direction:
            evidence.append(Evidence(
                text=f"Higher timeframe ({wm.regime.mtf_timeframe}) is {wm.regime.mtf_bias} (opposing)",
                source="technical",
                weight=1.5,
                direction="against",
            ))

        # Fundamental rate bias
        rate_bias = wm.fundamental.rate_bias.lower()
        if direction == "bullish" and "eur stronger" in rate_bias:
            evidence.append(Evidence(
                text="Rate differential favors EUR strength",
                source="fundamental",
                weight=1.3,
                direction="for",
            ))
        elif direction == "bearish" and "usd stronger" in rate_bias:
            evidence.append(Evidence(
                text="Rate differential favors USD strength",
                source="fundamental",
                weight=1.3,
                direction="for",
            ))

        return evidence

    # ── State Management ──────────────────────────────────────

    def _transition_to(self, new_state: AgentState, stats: AgentCycleStats) -> None:
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        stats.state_transitions.append(f"{old_state.value}→{new_state.value}")
        self._state_history.append((time.time(), new_state.value))

        # Keep history bounded
        if len(self._state_history) > 100:
            self._state_history = self._state_history[-100:]

    def _determine_next_state(self) -> AgentState:
        """Determine what the next state should be based on timing and conditions."""
        now = time.time()

        # If we have open trades, prioritize monitoring
        if self.world_model.has_open_trades() and now - self._last_monitoring > self.MONITORING_INTERVAL:
            return AgentState.MONITORING

        # If it's been a while since deep analysis, do one
        if now - self._last_deep_analysis > self.DEEP_ANALYSIS_INTERVAL:
            return AgentState.ANALYZING

        # Regular scanning
        if now - self._last_scan > self.SCAN_INTERVAL:
            return AgentState.SCANNING

        return self.state

    def _should_activate(self) -> bool:
        """Check if the agent should wake up from IDLE."""
        session = self.world_model.session.active_session
        if session in ("london", "new_york", "overlap"):
            return True
        # Asian session — reduced activity but still scan
        if session == "asian":
            return True
        return False

    def _needs_deep_analysis(self) -> bool:
        """Check if a full pipeline run is needed."""
        now = time.time()
        if now - self._last_deep_analysis > self.DEEP_ANALYSIS_INTERVAL:
            return True
        if self.world_model.has_significant_change():
            return True
        return False

    def _should_evaluate_trade(self) -> bool:
        """Check if conditions warrant trade evaluation."""
        strongest = self.conviction_tracker.get_strongest()
        if not strongest:
            return False
        if strongest.confidence < ConvictionTracker.MIN_CONFIDENCE_TO_ACT:
            return False
        if not self.world_model.session.is_high_liquidity:
            return False
        return True

    def _get_sleep_time(self) -> float:
        """Dynamic sleep based on current conditions."""
        if self.state == AgentState.IDLE:
            return self.IDLE_CHECK_INTERVAL
        if self.world_model.has_open_trades():
            return self.MONITORING_INTERVAL
        if self.world_model.session.overlap_active:
            return 30  # Most active — scan more
        if self.world_model.session.is_high_liquidity:
            return 45
        return 60  # Default

    # ── Action Dispatch ───────────────────────────────────────

    def register_handler(self, action_type: AgentActionType, handler: Callable) -> None:
        """Register an external handler for an action type."""
        self._action_handlers.setdefault(action_type, []).append(handler)

    async def _dispatch_action(self, action: AgentAction, stats: AgentCycleStats) -> None:
        """Dispatch an action to registered handlers."""
        handlers = self._action_handlers.get(action.action_type, [])
        if not handlers:
            logger.debug(f"No handlers for action {action.action_type}: {action.reasoning}")
            return

        for handler in handlers:
            try:
                result = handler(action)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Action handler failed for {action.action_type}: {e}")

        stats.actions_produced += 1
        self._total_actions += 1

    # ── Persistence ───────────────────────────────────────────

    async def _persist_state(self) -> None:
        """Save agent state for recovery."""
        if not self.storage:
            return

        state = {
            "world_model": self.world_model.serialize(),
            "convictions": self.conviction_tracker.serialize(),
            "cycle_count": self._cycle_count,
            "total_actions": self._total_actions,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        try:
            await self.storage.save_json("agent_core_state", state)
            logger.debug("Agent state persisted")
        except Exception as e:
            logger.error(f"Failed to persist agent state: {e}")

    async def _restore_state(self) -> None:
        """Restore agent state from storage."""
        if not self.storage:
            return

        try:
            state = await self.storage.load_json("agent_core_state")
            if not state:
                return

            self.world_model.deserialize(state.get("world_model", {}))
            self.conviction_tracker.deserialize(state.get("convictions", {}))
            self._cycle_count = state.get("cycle_count", 0)
            self._total_actions = state.get("total_actions", 0)
            logger.info("Agent state restored from storage")
        except Exception as e:
            logger.warning(f"Could not restore agent state: {e}")

    # ── Status & Introspection ────────────────────────────────

    def get_status(self) -> dict:
        """Get current agent status for display."""
        uptime = time.time() - self._started_at if self._started_at else 0
        dom_dir, dom_conf = self.conviction_tracker.get_dominant_direction()

        return {
            "state": self.state.value,
            "running": self._running,
            "paused": self._paused,
            "uptime_hours": round(uptime / 3600, 1),
            "cycles": self._cycle_count,
            "total_actions": self._total_actions,
            "total_errors": self._total_errors,
            "world_model_age": round(time.time() - self.world_model._last_full_update, 0) if self.world_model._last_full_update else "never",
            "active_convictions": len(self.conviction_tracker.get_active_convictions()),
            "dominant_direction": dom_dir,
            "dominant_confidence": round(dom_conf, 2),
            "open_trades": self.world_model.risk.open_trade_count,
            "price": self.world_model.price.price,
        }

    def format_status(self) -> str:
        """Format agent status for Telegram display."""
        s = self.get_status()
        state_emoji = {
            "idle": "😴", "scanning": "👁️", "analyzing": "🔬",
            "conviction_forming": "🧠", "deciding": "⚖️", "executing": "⚡",
            "monitoring": "📡", "reviewing": "📝",
        }

        lines = [
            f"🤖 <b>EuroScope Agent Status</b>\n",
            f"State: {state_emoji.get(s['state'], '❓')} <b>{s['state'].upper()}</b>",
            f"Uptime: {s['uptime_hours']}h | Cycles: {s['cycles']}",
            f"Actions: {s['total_actions']} | Errors: {s['total_errors']}",
            f"\n📊 <b>Market</b>",
            f"EUR/USD: {s['price']:.5f}" if s['price'] else "EUR/USD: Loading...",
            f"Open Trades: {s['open_trades']}",
            f"\n🧠 <b>Convictions</b>",
            f"Active: {s['active_convictions']}",
            f"Bias: {s['dominant_direction'].upper()} ({s['dominant_confidence']:.0%})",
        ]

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<EuroScopeAgent state={self.state.value} "
            f"cycles={self._cycle_count} actions={self._total_actions}>"
        )
