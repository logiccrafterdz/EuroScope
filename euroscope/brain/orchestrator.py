"""
Orchestrator — Skills-Based Multi-Agent Coordinator (V2)

Replaces hard-coded specialists with SkillsRegistry-driven
dynamic tool calling and skills chaining.
"""

import logging
from typing import Optional

from ..skills.base import SkillContext, SkillResult
from ..skills.registry import SkillsRegistry

from .llm_router import LLMRouter
from .vector_memory import VectorMemory

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
        self.vector_memory: Optional[VectorMemory] = None

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
        return await self.chain.run(steps, context, params)

    async def run_full_analysis_pipeline(self, context: SkillContext = None,
                                   **market_params) -> SkillContext:
        """
        Complete analysis pipeline using skills.
        Runs: market_data → technical_analysis → risk_management → trading_strategy
        """
        steps = [
            ("market_data", "get_candles"),
            ("technical_analysis", "full"),
            ("risk_management", "assess_trade"),
            ("trading_strategy", "detect_signal"),
        ]
        params = {"market_data": market_params} if market_params else {}
        ctx = await self.run_pipeline(steps, context, params)

        # Store in vector memory if available
        if self.vector_memory and ctx.analysis:
            formatted = ctx.metadata.get("formatted", "")
            if formatted:
                self.vector_memory.store_analysis(
                    formatted,
                    metadata={
                        "timeframe": market_params.get("timeframe", "H1"),
                        "overall_bias": ctx.analysis.get("indicators", {}).get("overall_bias", "NEUTRAL")
                    }
                )

        return ctx

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

