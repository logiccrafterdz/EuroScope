"""
BaseSkill — Abstract base class for all EuroScope Skills.

Every skill extends BaseSkill and provides:
- Self-documenting SKILL.md
- Typed execute() with SkillResult
- Validated actions via capabilities
- Auto-discoverable by SkillsRegistry
"""

import asyncio
import inspect
import logging
import os
import re
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
    status: str = "success"
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
    dependencies: list[str] = []  # Skills that should run before this one
    execution_timeout: int = 30  # Default timeout in seconds

    def __init__(self):
        self._skill_md: Optional[str] = None
        self._frontmatter: Optional[dict] = None

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
        deps = ", ".join(self.dependencies) if self.dependencies else "none"
        trigger_desc = self.get_trigger_description()
        card = (
            f"{self.emoji} **{self.name}** (v{self.version})\n"
            f"Category: {self.category.value}\n"
            f"Description: {trigger_desc}\n"
            f"Dependencies: {deps}\n"
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

    def get_trigger_description(self) -> str:
        """
        Return the rich description optimized for LLM triggering.

        Prefers the SKILL.md frontmatter description (which is longer
        and trigger-oriented per Anthropic's standard) over the terse
        Python class attribute.
        """
        self._ensure_frontmatter()
        if self._frontmatter and self._frontmatter.get("description"):
            return self._frontmatter["description"]
        return self.description

    def health_contract(self) -> dict:
        """
        Return a dict describing what this skill needs to be healthy.

        Override in subclasses to declare runtime dependencies.
        The monitoring skill uses this to proactively check all skills.
        """
        return {
            "requires_provider": False,
            "requires_storage": False,
            "requires_config": False,
            "requires_event_bus": False,
        }

    def _read_skill_md(self) -> Optional[str]:
        """Read SKILL.md from the skill's directory."""
        if self._skill_md is not None:
            return self._skill_md

        try:
            skill_file = Path(inspect.getfile(self.__class__)).parent / "SKILL.md"

            if skill_file.exists():
                self._skill_md = skill_file.read_text(encoding="utf-8")
            else:
                self._skill_md = ""
        except Exception as e:
            logger.debug(f"[{self.name}] Failed to read SKILL.md: {e}")
            self._skill_md = ""

        return self._skill_md

    def _ensure_frontmatter(self):
        """Parse YAML frontmatter from SKILL.md if not already done."""
        if self._frontmatter is not None:
            return

        content = self._read_skill_md()
        if not content or not content.strip().startswith("---"):
            self._frontmatter = {}
            return

        try:
            # Extract YAML between first two --- delimiters
            match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if not match:
                self._frontmatter = {}
                return

            yaml_block = match.group(1)
            parsed = {}
            for line in yaml_block.split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if value:  # Only set non-empty values
                        parsed[key] = value
            self._frontmatter = parsed
        except Exception as e:
            logger.debug(f"[{self.name}] Failed to parse SKILL.md frontmatter: {e}")
            self._frontmatter = {}

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
            if inspect.isawaitable(maybe_result):
                try:
                    result = await asyncio.wait_for(maybe_result, timeout=self.execution_timeout)
                except asyncio.TimeoutError:
                    error_msg = f"Timed out after {self.execution_timeout}s"
                    logger.error(f"[{self.name}] {action} failed: {error_msg}")
                    error_result = SkillResult(success=False, error=error_msg)
                    context.add_result(self.name, error_result)
                    return error_result
            else:
                result = maybe_result
            
            context.add_result(self.name, result)
            return result
        except Exception as e:
            logger.error(f"[{self.name}] {action} failed: {e}")
            error_result = SkillResult(success=False, error=str(e))
            context.add_result(self.name, error_result)
            return error_result

    def __repr__(self):
        return f"<Skill:{self.name} v{self.version} [{self.category.value}]>"
