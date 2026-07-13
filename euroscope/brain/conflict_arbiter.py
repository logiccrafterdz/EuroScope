"""
Conflict Arbiter — Intelligence Layer for Decision Synthesis.
Resolves conflicts between tools using weights and context.
Phase 3 Part 2: Upgraded with Multi-Agent Deliberation hook.
Phase 4: Integrated ForecastTracker adaptive weights + Evidence Diversity scoring.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.conflict_arbiter")


class ConflictArbiter:
    """
    Resolves conflicts between tools using market context, historical accuracy, and session awareness.
    If conflicts are too strong, it escalates to the Deliberation Committee.
    """

    # Base weights — blended with ForecastTracker adaptive weights at runtime
    BASE_WEIGHTS = {
        "liquidity_awareness": 0.30,
        "technical_analysis": 0.25,
        "pattern_detection": 0.15,
        "fundamental_analysis": 0.10,
        "trading_strategy": 0.20,
    }

    # Skill name mapping: ConflictArbiter tool name → ForecastTracker skill name
    _FORECAST_KEY_MAP = {
        "liquidity_awareness": "liquidity_awareness",
        "technical_analysis": "technical_analysis",
        "pattern_detection": "multi_timeframe_confluence",
        "fundamental_analysis": "fundamental_analysis",
        "trading_strategy": "session_context",
    }

    def __init__(self, llm_router=None, forecast_tracker=None, regime_engine=None):
        self.llm_router = llm_router
        self.forecast_tracker = forecast_tracker
        self.regime_engine = regime_engine
        self._last_committee_time = 0.0  # epoch timestamp
        self._committee_cooldown_sec = 3600  # 1 hour
        
    async def resolve(self, context: SkillContext) -> Dict[str, Any]:
        """
        Analyzes all tool outputs and produces a coherent decision.
        """
        signals = self._collect_signals(context)
        weighted_signals = self._apply_weights(signals, context)
        decision = await self._synthesize_decision(signals, weighted_signals, context)
        return decision
    
    def _collect_signals(self, context: SkillContext) -> Dict[str, str]:
        signals = {}
        tool_mapping = {
            "liquidity_awareness": "liquidity_signal",
            "technical_analysis": "technical_bias",
            "pattern_detection": "pattern_signal",
            "fundamental_analysis": "fundamental_bias"
        }
        
        for tool, key in tool_mapping.items():
            val = context.metadata.get(key)
            if val:
                signals[tool] = val.upper()
        
        if context.signals.get("direction"):
            signals["trading_strategy"] = context.signals["direction"].upper()
            
        return signals

    def _apply_weights(self, signals: Dict[str, str], context: SkillContext) -> Dict[str, float]:
        """
        Compute per-tool weights using:
        1. Static base weights
        2. ForecastTracker adaptive weights (performance-based)
        3. Session modifiers
        4. Regime modifiers
        """
        session = context.metadata.get("session_regime", "unknown").lower()
        regime = context.metadata.get("regime", "unknown").lower()

        weights = dict(self.BASE_WEIGHTS)

        # Blend with ForecastTracker adaptive weights if available
        if self.forecast_tracker:
            ft_weights = self.forecast_tracker.get_weights()
            if ft_weights:
                for tool, base_w in weights.items():
                    ft_key = self._FORECAST_KEY_MAP.get(tool)
                    if ft_key and ft_key in ft_weights:
                        # Normalize FT weight around 1.0 (it already is)
                        # Blend: 60% base + 40% adaptive performance
                        adaptive_factor = ft_weights[ft_key]
                        weights[tool] = base_w * (0.6 + 0.4 * adaptive_factor)
                logger.debug(f"Adaptive weights blended: {weights}")

        active_weights = {k: v for k, v in weights.items() if k in signals}

        # Session modifiers
        if session == "asian":
            if "pattern_detection" in active_weights: active_weights["pattern_detection"] *= 0.6
            if "technical_analysis" in active_weights: active_weights["technical_analysis"] *= 0.8
        elif session == "overlap":
            if "technical_analysis" in active_weights: active_weights["technical_analysis"] *= 1.2
            if "pattern_detection" in active_weights: active_weights["pattern_detection"] *= 1.1

        # Regime modifiers — use RegimeAdaptiveEngine if available for nuanced adjustments
        if self.regime_engine and regime in ("trending", "ranging", "breakout", "volatile"):
            profile = self.regime_engine.get_profile(regime)
            # Map regime indicator weights to arbiter tool adjustments
            # Trending: EMA/MACD/ADX high → boost technical_analysis
            # Ranging: RSI/BB high → boost pattern_detection (mean-reversion patterns)
            momentum_avg = sum(profile.indicator_weights.get(k, 1.0) for k in ("EMA", "MACD", "ADX")) / 3
            oscillator_avg = sum(profile.indicator_weights.get(k, 1.0) for k in ("RSI", "BB")) / 2

            if "technical_analysis" in active_weights:
                active_weights["technical_analysis"] *= momentum_avg
            if "pattern_detection" in active_weights:
                active_weights["pattern_detection"] *= oscillator_avg
            # Volatile regime: suppress all directional signals
            if regime == "volatile":
                for tool in active_weights:
                    if tool != "liquidity_awareness":
                        active_weights[tool] *= 0.8
        else:
            # Fallback: hardcoded regime modifiers
            if regime == "ranging":
                if "pattern_detection" in active_weights: active_weights["pattern_detection"] *= 0.5
            elif regime == "trending":
                if "technical_analysis" in active_weights: active_weights["technical_analysis"] *= 1.3

        total = sum(active_weights.values())
        if total == 0: return {}
        return {k: v/total for k, v in active_weights.items()}
    
    async def _synthesize_decision(self, signals: Dict[str, str], weighted_signals: Dict[str, float], context: SkillContext) -> Dict[str, Any]:
        if not weighted_signals:
            return {
                "final_direction": "NEUTRAL",
                "confidence": 0.0,
                "primary_evidence": "No actionable signals found.",
                "conflicts_resolved": [],
                "reasoning": "No actionable signals found.",
                "evidence_diversity": 0.0,
            }

        votes = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        for tool, weight in weighted_signals.items():
            raw = signals.get(tool, "NEUTRAL")
            direction = "NEUTRAL"
            if "BUY" in raw or "BULLISH" in raw: direction = "BUY"
            elif "SELL" in raw or "BEARISH" in raw: direction = "SELL"
            votes[direction] += weight
        
        final_direction = max(votes, key=votes.get)
        confidence = votes[final_direction]

        # Compute evidence diversity — penalize when winning signals come from
        # correlated sources (e.g. technical + pattern both derived from OHLCV)
        evidence_diversity = self._compute_evidence_diversity(
            final_direction, signals, weighted_signals
        )
        context.metadata["evidence_diversity"] = evidence_diversity

        # Diversity penalty: low diversity means false consensus from redundant sources
        if evidence_diversity < 0.5 and confidence > 0.5:
            logger.warning(
                f"Low evidence diversity ({evidence_diversity:.2f}) — "
                f"confidence {confidence:.2f} may be inflated from correlated sources"
            )
            confidence *= (0.7 + 0.3 * evidence_diversity)  # scale down by diversity
        
        # Check if we have strong conflicting forces
        # Only meaningful when we have a directional winner
        conflict_ratio = 0.0
        if final_direction in ("BUY", "SELL"):
            opposite = "SELL" if final_direction == "BUY" else "BUY"
            conflict_ratio = votes.get(opposite, 0)
        
        # Phase 3 Multi-Agent Hook:
        # If there is high conflict (>0.25 opposition) or the winning vote is very weak (<0.45)
        # we trigger the multi-agent deliberation.
        # Use regime-aware threshold when RegimeAdaptiveEngine is available
        weak_threshold = 0.45
        if self.regime_engine and regime in ("trending", "ranging", "breakout", "volatile"):
            profile = self.regime_engine.get_profile(regime)
            # Map regime confidence_threshold (0-100) to deliberation threshold (0-1)
            weak_threshold = profile.confidence_threshold / 100.0 * 0.85  # scale down slightly

        needs_deliberation = False
        if confidence > 0 and confidence < weak_threshold:
            needs_deliberation = True
        elif conflict_ratio > 0.25 and final_direction != "NEUTRAL":
            needs_deliberation = True
            
        if needs_deliberation:
            # Cooldown: max 1 committee call per hour
            elapsed = time.time() - self._last_committee_time
            if elapsed < self._committee_cooldown_sec:
                logger.info(f"Committee on cooldown ({int(self._committee_cooldown_sec - elapsed)}s remaining). Using statistical vote.")
            else:
                # We attempt to use the Deliberation Committee
                from euroscope.brain.multi_agent import DeliberationCommittee
                from euroscope.container import get_container
                container = get_container()
                llm = self.llm_router or (container.router if container else None)
                
                if llm:
                    committee = DeliberationCommittee(llm)
                    committee_verdict = await committee.deliberate(context)
                    self._last_committee_time = time.time()
                    logger.info("Committee override applied.")
                    committee_verdict["conflicts_resolved"] = self._list_conflicts(committee_verdict["final_direction"], weighted_signals, context)
                    committee_verdict["evidence_diversity"] = evidence_diversity
                    return committee_verdict
                else:
                    logger.warning("Could not instantiate Multi-Agent Committee: No LLM router.")

        if confidence < 0.35:
            final_direction = "NEUTRAL"
            
        primary_evidence = self._explain_decision(final_direction, weighted_signals, context)
        conflicts_resolved = self._list_conflicts(final_direction, weighted_signals, context)
        
        return {
            "final_direction": final_direction,
            "confidence": confidence,
            "primary_evidence": primary_evidence,
            "conflicts_resolved": conflicts_resolved,
            "reasoning": f"{primary_evidence} (Confidence: {confidence:.0%}, Diversity: {evidence_diversity:.0%})",
            "evidence_diversity": evidence_diversity,
        }
    
    def _compute_evidence_diversity(
        self,
        final_direction: str,
        signals: Dict[str, str],
        weighted_signals: Dict[str, float],
    ) -> float:
        """
        Compute evidence diversity score (0.0–1.0).

        Checks whether the winning signals come from statistically independent
        information sources. If technical_analysis and pattern_detection both
        vote BUY, the diversity is low because both derive from OHLCV data.

        Diversity categories:
          - independent: liquidity, fundamental, session_context
          - price_derived: technical, pattern, trading_strategy
        """
        if final_direction not in ("BUY", "SELL"):
            return 1.0  # neutral is always "diverse"

        INDEPENDENT_SOURCES = {"liquidity_awareness", "fundamental_analysis"}
        PRICE_DERIVED_SOURCES = {"technical_analysis", "pattern_detection", "trading_strategy"}

        winning_tools = []
        for tool, direction in signals.items():
            raw_upper = direction.upper()
            dir_match = (
                ("BUY" in raw_upper or "BULLISH" in raw_upper) and final_direction == "BUY"
            ) or (
                ("SELL" in raw_upper or "BEARISH" in raw_upper) and final_direction == "SELL"
            )
            if dir_match and tool in weighted_signals:
                winning_tools.append(tool)

        if len(winning_tools) <= 1:
            return 1.0  # single source = full diversity

        independent_count = sum(1 for t in winning_tools if t in INDEPENDENT_SOURCES)
        price_derived_count = sum(1 for t in winning_tools if t in PRICE_DERIVED_SOURCES)

        # If all winning tools are from the same information family → low diversity
        if independent_count == 0 and price_derived_count >= 2:
            # All price-derived — heavily penalize
            return max(0.2, 1.0 - (price_derived_count - 1) * 0.25)
        if price_derived_count == 0 and independent_count >= 2:
            # All independent — good diversity
            return 1.0
        if independent_count >= 1 and price_derived_count >= 1:
            # Mixed sources — good diversity
            return 0.9

        return 0.7  # fallback

    def _explain_decision(self, direction: str, weights: Dict[str, float], context: SkillContext) -> str:
        session = context.metadata.get("session_regime", "unknown")
        if direction == "NEUTRAL": return "No strong consensus or trend detected"
        if weights.get("liquidity_awareness", 0) > 0.3: return f"Liquidity flow shows high weight in {session} session"
        elif weights.get("technical_analysis", 0) > 0.25: return f"Technical indicators show strong {direction} bias"
        return f"Consensus for {direction} from multiple tools"

    def _list_conflicts(self, final_dir: str, weights: Dict[str, float], context: SkillContext) -> List[str]:
        conflicts = []
        signals = self._collect_signals(context)
        for tool, direction in signals.items():
            simple_dir = "NEUTRAL"
            if "BUY" in direction or "BULLISH" in direction: simple_dir = "BUY"
            elif "SELL" in direction or "BEARISH" in direction: simple_dir = "SELL"
            
            if simple_dir != final_dir and simple_dir != "NEUTRAL":
                conflicts.append(f"Overrode {tool} {direction} in favor of {final_dir}")
        return conflicts
