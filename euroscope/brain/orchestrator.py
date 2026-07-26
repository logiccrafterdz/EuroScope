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
from .debate_engine import DebateEngine
from .risk_debate import RiskDebate
from .decision_log import DecisionLog
from .reflector import Reflector

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

    def __init__(self, storage=None, registry=None, config=None, llm_router=None,
                 forecast_tracker=None, regime_engine=None, adaptive_tuner=None):
        # V2: Skills system
        self.registry = registry or SkillsRegistry()
        self.storage = storage
        self.config = config
        if not registry:
             self.registry.discover()
        self.chain = SkillChain(self.registry)
        self.conflict_arbiter = ConflictArbiter(
            forecast_tracker=forecast_tracker,
            regime_engine=regime_engine
        )
        self.adaptive_tuner = adaptive_tuner
        self.vector_memory: Optional[VectorMemory] = None
        self.global_context = SkillContext()
        self.alerts = None
        
        # Debate Engine components
        self.llm_router = llm_router
        self.debate_engine = DebateEngine(self.llm_router) if self.llm_router else None
        self.risk_debate = RiskDebate(self.llm_router) if self.llm_router else None
        self.reflector = Reflector(self.llm_router) if self.llm_router else None
        self.decision_log = DecisionLog(storage=self.storage, reflector=self.reflector)

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

    def _inject_tuned_params(self, context: SkillContext):
        """
        Load tuned parameters from AdaptiveTuner and inject into context.
        Downstream skills (trading_strategy, risk_management) can read
        context.metadata["tuned_params"] to override defaults.
        """
        if not self.adaptive_tuner:
            return
        tuned = self.adaptive_tuner.load_tuned_params()
        if tuned:
            context.metadata["tuned_params"] = tuned
            logger.debug(f"Injected tuned params: {list(tuned.keys())}")

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
            resolution = await self.conflict_arbiter.resolve(context)
            
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

    # ─── Pipeline Sub-Steps (extracted from God method) ───────

    async def _handle_emergency_mode(self, context: SkillContext, base_tf: str, now: float) -> bool:
        """Check emergency mode. Returns True if emergency is active (caller should return early)."""
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
            return True
        return False

    async def _run_mtf_confirmation(self, context: SkillContext, base_tf: str) -> None:
        """Fetch higher-timeframe bias (D1/W1) for multi-timeframe confirmation."""
        higher_tf = "D1" if base_tf in ("H1", "H4", "M15", "M30") else "W1"
        mtf_ctx = SkillContext()
        mtf_params = {"market_data": {"timeframe": higher_tf, "count": 150}}
        try:
            await self._execute_pipeline([
                ("market_data", "get_candles"),
                ("technical_analysis", "full")
            ], mtf_ctx, mtf_params)
            mtf_bias = mtf_ctx.analysis.get("indicators", {}).get("overall_bias", "neutral")
            context.metadata["mtf_bias"] = mtf_bias
            context.metadata["mtf_timeframe"] = higher_tf
            logger.info(f"MTF Context ({higher_tf}): {mtf_bias}")
        except Exception as e:
            logger.warning(f"Failed to fetch MTF Context: {e}")

    async def _run_cot_filter(self, ctx: SkillContext) -> None:
        """Apply COT positioning filter — may flip signal or reduce confidence."""
        signal_dir = ctx.signals.get("direction", "")
        if signal_dir not in ("BUY", "SELL"):
            return
        try:
            cot_skill = self.registry.get("cot_positioning")
            if not cot_skill:
                return
            cot_ctx = SkillContext()
            cot_ctx.analysis = ctx.analysis
            cot_ctx.signals = dict(ctx.signals)
            cot_result = await cot_skill.safe_execute(cot_ctx, "filter_signal", direction=signal_dir)
            if cot_result.success and cot_result.data:
                action = cot_result.data.get("action", "no_filter")
                if action == "contrarian_signal":
                    old_dir = ctx.signals["direction"]
                    new_dir = "SELL" if old_dir == "BUY" else "BUY"
                    ctx.signals["direction"] = new_dir
                    ctx.signals["verdict"] = new_dir
                    logger.info(f"COT FILTER: Flipped signal {old_dir} → {new_dir} (extreme positioning)")
                elif action == "wait_for_timing":
                    ctx.signals["confidence"] = ctx.signals.get("confidence", 0) * 0.7
                    logger.info("COT FILTER: Reduced confidence (timing not confirmed)")
                ctx.metadata["cot_filter"] = cot_result.data
        except Exception as e:
            logger.warning(f"COT filter failed (non-blocking): {e}")

    async def _run_debate_layer(self, ctx: SkillContext) -> None:
        """Run multi-agent investment + risk debate if conditions are met."""
        if not (self.config and self.config.debate_enabled and self.debate_engine and self.risk_debate):
            return

        signal_confidence = ctx.signals.get("confidence", 0)
        signal_direction = ctx.signals.get("direction", "NEUTRAL")

        min_conf = self.config.debate_min_confidence
        regime = ctx.metadata.get("regime", "ranging")
        session = ctx.metadata.get("session_regime", "unknown")
        if regime == "volatile":
            min_conf *= 1.15
        if session == "asian":
            min_conf *= 1.10
        if session == "overlap":
            min_conf *= 0.90

        if signal_direction not in ["BUY", "SELL"] or signal_confidence < min_conf:
            return

        logger.info(f"Triggering Multi-Agent Debate for {signal_direction} (Confidence: {signal_confidence}%)")

        past = await self.decision_log.get_past_context(n_recent=5)
        ctx.metadata["past_reflections"] = past

        debate_result = await self.debate_engine.run_investment_debate(ctx, signal_direction)
        ctx.metadata["investment_debate"] = debate_result

        judgment = debate_result.get("judgment", {})
        new_direction = judgment.get("final_direction", "HOLD")
        new_confidence = judgment.get("confidence", 0)

        if new_direction != signal_direction:
            logger.info(f"Debate engine overruled strategy: {signal_direction} -> {new_direction}")

        ctx.signals["direction"] = new_direction
        ctx.signals["verdict"] = new_direction
        ctx.signals["confidence"] = new_confidence

        if new_direction in ["BUY", "SELL"]:
            risk_result = await self.risk_debate.run_risk_debate(ctx, judgment)
            ctx.metadata["risk_debate"] = risk_result
            ctx.metadata["debate_risk_profile"] = risk_result.get("final_profile", {})

        decision_id = await self.decision_log.store_decision(
            context=ctx, decision=judgment, debate_transcript=debate_result
        )
        ctx.metadata["decision_id"] = decision_id

    def _persist_market_state(self, ctx: SkillContext, base_tf: str) -> dict:
        """Infer market state, detect regime shifts, persist to storage."""
        market_state = self._infer_market_state(ctx) or {}
        if not market_state:
            return market_state

        ctx.metadata.update(market_state)
        prev_state = ctx.metadata.get("previous_market_state", {})
        if prev_state and prev_state.get("regime") and prev_state.get("regime") != market_state.get("regime"):
            shift_msg = f"Shift from {prev_state.get('regime')} to {market_state.get('regime')}"
            ctx.metadata["regime_shift"] = shift_msg
            logger.warning(f"MARKET REGIME SHIFT DETECTED ({base_tf}): {shift_msg}")

        if self.storage:
            import asyncio
            market_state_copy = dict(market_state)
            market_state_copy["updated_at"] = datetime.now(UTC).isoformat()
            asyncio.ensure_future(self.storage.save_json(f"market_state_{base_tf}", market_state_copy))

        return market_state

    def _store_in_vector_memory(self, ctx: SkillContext, market_params: dict, market_state: dict) -> None:
        """Store analysis results in vector memory for future context retrieval."""
        if not self.vector_memory or not ctx.analysis:
            return
        import json
        formatted = ctx.metadata.get("formatted", "")
        if not formatted:
            summary_data = {
                "signals": ctx.signals,
                "market_state": market_state,
                "technical_bias": ctx.metadata.get("technical_bias"),
                "pattern_signal": ctx.metadata.get("pattern_signal"),
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
                },
            )

    # ─── Main Pipeline ───────────────────────────────────────

    async def run_full_analysis_pipeline(self, context: SkillContext = None,
                                   **market_params) -> SkillContext:
        """
        Complete analysis pipeline using skills.
        Runs: session → emergency → MTF → decision → COT → debate → risk → state → memory
        """
        if context is None:
            context = self.global_context

        base_tf = market_params.get("timeframe", "H1") if market_params else "H1"
        if self.storage:
            prev_state = await self.storage.load_json(f"market_state_{base_tf}") or {}
            context.metadata["previous_market_state"] = prev_state

        await self.run_skill("session_context", "detect", context=context)
        self._inject_tuned_params(context)

        now_val = context.metadata.get("now")
        if isinstance(now_val, datetime):
            now = now_val.timestamp()
        else:
            now = now_val or datetime.now(UTC).timestamp()

        if await self._handle_emergency_mode(context, base_tf, now):
            return context

        params = {"market_data": market_params} if market_params else {}

        await self._run_mtf_confirmation(context, base_tf)

        pipeline = [
            ("market_data", "get_candles"),
            ("market_data", "get_correlation"),
            ("liquidity_awareness", "analyze"),
            ("fundamental_analysis", "get_macro"),
            ("fundamental_analysis", "get_sentiment"),
            ("technical_analysis", "full"),
            ("uncertainty_assessment", "assess"),
            ("trading_strategy", "detect_signal"),
        ]
        ctx = await self._execute_pipeline(pipeline, context, params)

        raw_conf = ctx.signals.get("confidence", 0)
        if raw_conf > 1.0:
            ctx.signals["confidence"] = raw_conf / 100.0

        await self._run_cot_filter(ctx)
        await self._run_debate_layer(ctx)

        ctx = await self._execute_pipeline([("risk_management", "assess_trade")], ctx, params)

        if ctx.metadata.get("debate_risk_profile") and ctx.risk:
            debate_risk = ctx.metadata["debate_risk_profile"]
            ctx.risk["lots"] = debate_risk.get("position_size_lots", ctx.risk.get("lots"))
            ctx.risk["stop_loss"] = debate_risk.get("stop_loss_pips", ctx.risk.get("stop_loss"))
            ctx.risk["take_profit"] = debate_risk.get("take_profit_pips", ctx.risk.get("take_profit"))
            ctx.risk["reasoning"] = f"DEBATE CONSENSUS: {debate_risk.get('reasoning', '')}"

        market_state = self._persist_market_state(ctx, base_tf)

        if market_state.get("regime") in ("trending", "breakout") or market_state.get("volatility") == "high":
            await self.run_pipeline([("fundamental_analysis", "full")], ctx)

        self._store_in_vector_memory(ctx, market_params, market_state)

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
        Calls the full skills pipeline with optional market context override.
        """
        # Run pipeline, passing market_context if provided
        ctx = await self.run_full_analysis_pipeline(**market_context)
        
        # Build a compatible dict
        consensus = ctx.signals or {"verdict": "neutral", "confidence": 0}
        
        return {
            "consensus": consensus,
            "specialists": ctx.history,
            "risk_assessment": ctx.risk or {"approved": True},
            "formatted": ctx.metadata.get("formatted", "Analysis complete."),
        }

    # ── Agent Core API ────────────────────────────────────────

    async def run_scan(self, context: SkillContext = None) -> SkillContext:
        """
        Lightweight market scan — price + session detection only.
        Used by Agent Core for fast tick updates (<2s).
        """
        if context is None:
            context = self.global_context

        # Only price + session — no heavy analysis
        scan_pipeline = [
            ("market_data", "get_price"),
            ("session_context", "detect"),
        ]
        return await self._execute_pipeline(scan_pipeline, context)

    async def get_quick_state(self, context: SkillContext = None) -> dict:
        """
        Returns a quick snapshot of the current market state
        without running the full analysis pipeline.
        Used by Agent Core for status checks and conditional logic.
        """
        if context is None:
            context = self.global_context

        # Get price
        price = 0.0
        price_res = await self.run_skill("market_data", "get_price", context=context)
        if price_res.success and isinstance(price_res.data, dict):
            price = price_res.data.get("price", 0.0)

        # Get session
        session_res = await self.run_skill("session_context", "detect", context=context)
        session = context.metadata.get("active_session", "unknown")

        # Get cached regime from global context
        regime = context.metadata.get("regime", "unknown")
        volatility = context.metadata.get("volatility", "unknown")

        # Open trades
        open_trades = []
        try:
            trades_res = await self.run_skill("signal_executor", "list_trades", context=context)
            if trades_res.success and trades_res.data:
                open_trades = [t for t in trades_res.data if str(t.get("status", "")).upper() == "OPEN"]
        except Exception as e:
            logger.debug(f"Failed to query open trades: {e}")

        return {
            "price": price,
            "session": session,
            "regime": regime,
            "volatility": volatility,
            "open_trades": len(open_trades),
            "has_open_trades": len(open_trades) > 0,
        }

