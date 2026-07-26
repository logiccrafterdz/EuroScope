"""
Multi-Agent Deliberation (The Committee)

DEPRECATED: This module is kept for backward compatibility only.
All conflict deliberation is now handled by DebateEngine.run_conflict_deliberation().
"""

import logging
from typing import Dict, Any

from euroscope.skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.committee")


class DeliberationCommittee:
    """Backward-compatible wrapper — delegates to DebateEngine.run_conflict_deliberation()."""

    def __init__(self, llm_router=None):
        self.llm = llm_router
        logger.warning("DeliberationCommittee is deprecated — use DebateEngine.run_conflict_deliberation() instead")

    async def deliberate(self, context: SkillContext) -> Dict[str, Any]:
        if not self.llm:
            return {"final_direction": "NEUTRAL", "confidence": 0, "reasoning": "No LLM router."}
        from .debate_engine import DebateEngine
        engine = DebateEngine(self.llm)
        return await engine.run_conflict_deliberation(context)
