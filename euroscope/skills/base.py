"""
BaseSkill — Abstract base class for all EuroScope Skills.

Every skill extends BaseSkill and provides:
- Self-documenting SKILL.md
- Typed execute() with SkillResult
- Validated actions via capabilities
- Auto-discoverable by SkillsRegistry
"""

import inspect
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("euroscope.skills.base")


class SkillCategory(str, Enum):
    """Categories for grouping skills."""
    DATA = "data"
    ANALYSIS = "analysis"
    TRADING = "trading"
    ANALYTICS = "analytics"
    SYSTEM = "system"


@dataclass
class SkillResult:
    """
    Unified result from any skill execution.

    Every skill returns this, making chaining and error handling uniform.
    """
    success: bool = True
    data: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)
    next_skill: Optional[str] = None  # Suggest next skill in chain

    def __bool__(self):
        return self.success


@dataclass
class SkillContext:
    """
    Shared context passed through a skill execution chain.

    Accumulates data as each skill adds its results.
    """
    market_data: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)
    signals: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)
    user_prefs: dict = field(default_factory=dict)
    open_positions: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # Previous skill results

    def add_result(self, skill_name: str, result: SkillResult):
        """Record a skill's result in the chain history."""
        self.history.append({
            "skill": skill_name,
            "success": result.success,
            "data": result.data,
            "error": result.error,
        })

    def get_result(self, skill_name: str) -> Optional[dict]:
        """Retrieve a previous skill's result by name."""
        for entry in reversed(self.history):
            if entry["skill"] == skill_name:
                return entry
        return None


class BaseSkill(ABC):
    """
    Abstract base class for all EuroScope skills.

    Subclasses must implement:
    - name, description, emoji, category, version, capabilities
    - execute(context, action, **params) -> SkillResult
    """

    # ── Identity (override in subclass) ──────────────────────

    name: str = "base"
    description: str = "Base skill"
    emoji: str = "🔧"
    category: SkillCategory = SkillCategory.SYSTEM
    version: str = "1.0.0"
    capabilities: list[str] = []

    def __init__(self):
        self._skill_md: Optional[str] = None

    # ── Core API ─────────────────────────────────────────────

    @abstractmethod
    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        """
        Execute a skill action.

        Args:
            context: Shared context with accumulated data
            action: Which capability to invoke (must be in self.capabilities)
            **params: Action-specific parameters

        Returns:
            SkillResult with success/data/error
        """
        ...

    def validate(self, action: str, **params) -> bool:
        """Check if the action is valid for this skill."""
        return action in self.capabilities

    # ── Self-Documentation ───────────────────────────────────

    def get_skill_card(self) -> str:
        """
        Return a card-format description for LLM consumption.

        Includes name, description, capabilities, and SKILL.md content.
        """
        caps = "\n".join(f"  - {c}" for c in self.capabilities)
        card = (
            f"{self.emoji} **{self.name}** (v{self.version})\n"
            f"Category: {self.category.value}\n"
            f"Description: {self.description}\n"
            f"Capabilities:\n{caps}"
        )

        # Append SKILL.md if available
        skill_md = self._read_skill_md()
        if skill_md:
            card += f"\n\n--- SKILL.md ---\n{skill_md}"

        return card

    def get_short_description(self) -> str:
        """One-line summary for menus and lists."""
        return f"{self.emoji} {self.name}: {self.description}"

    def _read_skill_md(self) -> Optional[str]:
        """Read SKILL.md from the skill's directory."""
        if self._skill_md is not None:
            return self._skill_md

        # SKILL.md lives in the same directory as the skill module
        try:
            skill_file = Path(os.path.abspath(
                self.__class__.__module__.replace(".", os.sep)
            )).parent / "SKILL.md"

            if skill_file.exists():
                self._skill_md = skill_file.read_text(encoding="utf-8")
            else:
                self._skill_md = ""
        except Exception:
            self._skill_md = ""

        return self._skill_md

    # ── Utilities ────────────────────────────────────────────

    async def safe_execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        """Execute with error handling — never raises."""
        if not self.validate(action, **params):
            return SkillResult(
                success=False,
                error=f"Unknown action '{action}'. Available: {self.capabilities}",
            )
        try:
            maybe_result = self.execute(context, action, **params)
            result = await maybe_result if inspect.isawaitable(maybe_result) else maybe_result
            context.add_result(self.name, result)
            return result
        except Exception as e:
            logger.error(f"[{self.name}] {action} failed: {e}")
            error_result = SkillResult(success=False, error=str(e))
            context.add_result(self.name, error_result)
            return error_result

    def __repr__(self):
        return f"<Skill:{self.name} v{self.version} [{self.category.value}]>"
