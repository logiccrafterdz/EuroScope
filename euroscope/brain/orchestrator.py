"""
Orchestrator — Skills-Based Multi-Agent Coordinator (V2)

Replaces hard-coded specialists with SkillsRegistry-driven
dynamic tool calling and skills chaining.
"""

import logging
import time
from datetime import datetime, timedelta, UTC
from typing import Optional, List

from ..skills.base import SkillContext, SkillResult
from ..skills.registry import SkillsRegistry

from .llm_router import LLMRouter
from .vector_memory import VectorMemory
from .conflict_arbiter import ConflictArbiter

logger = logging.getLogger("euroscope.brain.orchestrator")


class SkillChain:
    """
    Pipeline that executes a sequence of skills, passing SkillContext through.

    Each skill's output feeds into the next skill's context automatically.
    Supports error fallback (skip failed skill, continue chain).
    """

    def __init__(self, registry: SkillsRegistry):
        self.registry = registry

    async def run(self, steps: list[tuple[str, str]], context: SkillContext = None,
            params: dict = None) -> SkillContext:
        """
        Execute a chain of (skill_name, action) steps.
        """
        if context is None:
            context = SkillContext()
        if params is None:
            params = {}

        for skill_name, action in steps:
            skill = self.registry.get(skill_name)
            if not skill:
                logger.warning(f"SkillChain: skill '{skill_name}' not found, skipping")
                continue

            step_params = params.get(skill_name, {})
            result = await skill.safe_execute(context, action, **step_params)

            if not result.success:
                logger.warning(
                    f"SkillChain: {skill_name}.{action} failed: {result.error}"
                )

        return context


class Orchestrator:
    """
    Coordinates skills to produce analysis.

    V2: Uses SkillsRegistry for dynamic skill discovery and SkillChain
    for pipeline execution. Purely skills-based.
    """

    def __init__(self):
        # V2: Skills system
        self.registry = SkillsRegistry()
        self.registry.discover()
        self.chain = SkillChain(self.registry)
        self.conflict_arbiter = ConflictArbiter()
        self.vector_memory: Optional[VectorMemory] = None
        self.global_context = SkillContext()
        self.alerts = None

    def set_alerts(self, alerts):
        self.alerts = alerts

    def inject_dependencies(self, **deps):
        """
        Inject shared dependencies into all registered skills.
        """
        if "vector_memory" in deps:
            self.vector_memory = deps["vector_memory"]
        for skill in self.registry.list_all():
            for key, val in deps.items():
                setter = getattr(skill, f"set_{key}", None)
                if setter:
                    setter(val)

    # ── V2 Skills API ────────────────────────────────────────

    async def run_skill(self, skill_name: str, action: str,
                   context: SkillContext = None, **params) -> SkillResult:
        """Execute a single skill action."""
        if context is None:
            context = SkillContext()

        skill = self.registry.get(skill_name)
        if not skill:
            return SkillResult(success=False, error=f"Skill '{skill_name}' not found")

        return await skill.safe_execute(context, action, **params)

    async def run_pipeline(self, steps: list[tuple[str, str]],
                      context: SkillContext = None,
                      params: dict = None) -> SkillContext:
        """Execute a skill chain pipeline."""
        return await self._execute_pipeline(steps, context, params)

    async def _execute_pipeline(self, pipeline: List[tuple[str, str]], 
                               context: SkillContext = None, params: dict = None) -> SkillContext:
        """
        Executes pipeline with explicit dependency validation and conflict resolution.
        """
        if context is None:
            context = SkillContext()
        params = params or {}
        
        for skill_name, action in pipeline:
            # Dependency Validation: Risk Management requires signal direction
            if skill_name == "risk_management":
                direction = context.signals.get("direction")
                if not direction or direction == "NEUTRAL":
                    logger.error("Risk management requires signal direction — ensure trading_strategy runs first")
                    continue
            
            result = await self.run_skill(skill_name, action, context=context, **params.get(skill_name, {}))
            
            # Handle skill rejection (e.g., insufficient data)
            if result.status == "rejected":
                logger.warning(f"Skill {skill_name} rejected: {result.metadata.get('rejection_reason')}")
                if skill_name == "technical_analysis":
                    logger.warning("Aborting pipeline: critical dependency 'technical_analysis' rejected")
                    break
            
            # Phase 2C: Fundamental Data Quality Monitoring
            if skill_name == "fundamental_analysis":
                quality = result.metadata.get("quality", "complete")
                if quality != "complete":
                    context.metadata["data_quality_warning"] = True
                    context.metadata["data_quality_details"] = {
                        "quality": quality,
                        "warnings": result.metadata.get("warnings", [])
                    }
                    logger.warning(f"Operating with {quality} macro data")

        # Conflict Resolution Phase
        if self._has_conflicting_signals(context):
            resolution = self.conflict_arbiter.resolve(context)
            
            # Adjust confidence based on overall data quality
            final_conf = self._calculate_final_confidence(resolution["confidence"], context)
            
            # Inject unified decision into context
            context.metadata["final_direction"] = resolution["final_direction"]
            context.metadata["final_confidence"] = final_conf
            context.metadata["decision_reasoning"] = resolution["reasoning"]
            context.metadata["conflicts_resolved"] = resolution["conflicts_resolved"]

            # Also update signals for downstream consumers
            context.signals["verdict"] = resolution["final_direction"]
            context.signals["confidence"] = final_conf
            
            logger.info(f"Decision: {resolution['final_direction']} ({final_conf:.0%}) - {resolution['reasoning']}")
            
        return context

    def _calculate_final_confidence(self, base_confidence: float, context: SkillContext) -> float:
        """Apply penalties based on data quality (Phase 2C)."""
        if context.metadata.get("data_quality_warning"):
            quality = context.metadata["data_quality_details"].get("quality")
            if quality == "partial_eu" or quality == "partial_us":
                base_confidence *= 0.8  # 20% penalty
            elif quality == "minimal":
                base_confidence *= 0.5  # 50% penalty
        
        return max(0.0, min(1.0, base_confidence))

    def _has_conflicting_signals(self, context: SkillContext) -> bool:
        """Detect if multiple tools provided contradictory signals."""
        signals = []
        # Check specific metadata keys used in conflict arbiter
        keys = ["liquidity_signal", "technical_bias", "pattern_signal", "fundamental_bias"]
        for key in keys:
            val = context.metadata.get(key)
            if val:
                # Normalize
                if "BUY" in val.upper() or "BULLISH" in val.upper(): signals.append("BUY")
                elif "SELL" in val.upper() or "BEARISH" in val.upper(): signals.append("SELL")
                else: signals.append("NEUTRAL")
        
        # Also check trading strategy signal
        strat = context.signals.get("direction")
        if strat:
            signals.append(strat.upper())
            
        # Filter neutral out for conflict detection
        active = [s for s in signals if s != "NEUTRAL"]
        return len(set(active)) > 1

    async def run_full_analysis_pipeline(self, context: SkillContext = None,
                                   **market_params) -> SkillContext:
        """
        Complete analysis pipeline using skills.
        Runs: market_data → technical_analysis → risk_management → trading_strategy
        """
        if context is None:
            context = self.global_context

        # 1. Detect session context first (needed by all safety checks)
        await self.run_skill("session_context", "detect", context=context)

        now_val = context.metadata.get("now")
        if isinstance(now_val, datetime):
            now = now_val.timestamp()
        else:
            now = now_val or datetime.now(UTC).timestamp()

        emergency_until = context.metadata.get("emergency_until", 0)
        if emergency_until and now >= emergency_until:
            context.metadata["emergency_mode"] = False
            context.metadata["emergency_until"] = 0

        if context.metadata.get("emergency_mode"):
            if self.alerts:
                session = context.metadata.get("session_regime", "unknown")
                suppression_minutes = 8 if session == "overlap" else 5
                suppression_duration = suppression_minutes * 60
                self.alerts.suppress(suppression_duration, base_time=now)
                suppression_until = datetime.fromtimestamp(now, UTC) + timedelta(minutes=suppression_minutes)
                context.metadata["alerts_suppressed_until"] = suppression_until.isoformat()
            if self.registry.get("crisis_analysis"):
                await self.run_pipeline([("crisis_analysis", "full")], context)
            return context

        params = {"market_data": market_params} if market_params else {}

        # 2. Execute decision pipeline
        pipeline = [
            ("market_data", "get_candles"),
            ("liquidity_awareness", "analyze"),
            ("fundamental_analysis", "get_macro"),
            ("technical_analysis", "full"),
            ("uncertainty_assessment", "assess"),
            ("trading_strategy", "detect_signal"),  # Discover direction FIRST
            ("risk_management", "assess_trade"),    # Calculate risk BASED ON direction
        ]
        
        ctx = await self._execute_pipeline(pipeline, context, params)

        market_state = self._infer_market_state(ctx) or {}
        if market_state:
            ctx.metadata.update(market_state)

        if market_state.get("regime") in ("trending", "breakout") or market_state.get("volatility") == "high":
            await self.run_pipeline([("fundamental_analysis", "full")], ctx)

        # Store in vector memory if available
        if self.vector_memory and ctx.analysis:
            formatted = ctx.metadata.get("formatted", "")
            if not formatted:
                import json
                summary_data = {
                    "signals": ctx.signals,
                    "market_state": market_state,
                    "technical_bias": ctx.metadata.get("technical_bias"),
                    "pattern_signal": ctx.metadata.get("pattern_signal")
                }
                formatted = json.dumps(summary_data, indent=2)
                ctx.metadata["formatted"] = formatted

            if formatted:
                self.vector_memory.store_analysis(
                    formatted,
                    metadata={
                        "timeframe": market_params.get("timeframe", "H1"),
                        "overall_bias": ctx.analysis.get("indicators", {}).get("overall_bias", "NEUTRAL"),
                        "regime": ctx.metadata.get("regime", "ranging"),
                        "volatility": ctx.metadata.get("volatility", "unknown"),
                    }
                )

        return ctx

    @staticmethod
    def _infer_market_state(ctx: SkillContext) -> dict:
        indicators = ctx.analysis.get("indicators", {})
        ind = indicators.get("indicators", {})
        adx = ind.get("ADX", {}).get("value")
        atr_pips = ind.get("ATR", {}).get("pips")
        regime = ctx.signals.get("regime")

        if not regime:
            if adx is not None and adx > 25:
                regime = "trending"
            elif adx is not None and adx < 20:
                regime = "ranging"
            else:
                regime = "ranging"

        volatility = "high" if atr_pips is not None and atr_pips >= 12 else "normal"

        return {"regime": regime, "volatility": volatility}

    def get_available_skills(self) -> str:
        """Get LLM-ready description of all available skills."""
        return self.registry.get_tools_prompt()

    def get_skill_cards(self) -> str:
        """Get detailed skill cards for LLM deep context."""
        return self.registry.get_skill_cards()

    # ── Compatibility API ────────────────────────────────────

    async def run_analysis(self, market_context: dict) -> dict:
        """
        Compatible async wrapper for legacy analysis requests.
        Calls the full skills pipeline.
        """
        # Run pipeline
        ctx = await self.run_full_analysis_pipeline()
        
        # Build a compatible dict
        consensus = ctx.signals or {"verdict": "neutral", "confidence": 0}
        
        return {
            "consensus": consensus,
            "specialists": ctx.history,
            "risk_assessment": ctx.risk or {"approved": True},
            "formatted": ctx.metadata.get("formatted", "Analysis complete."),
        }

