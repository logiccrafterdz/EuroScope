"""
SkillsRegistry — Auto-discovery, loading, and querying of Skills.

Scans the skills/ directory for subfolders containing SKILL.md,
loads the skill class, and provides query/formatting APIs.
"""

import importlib
import logging
import os
from pathlib import Path
from typing import Optional

from .base import BaseSkill, SkillCategory

logger = logging.getLogger("euroscope.skills.registry")


class SkillsRegistry:
    """
    Central registry that discovers, loads, and manages all skills.

    Usage:
        registry = SkillsRegistry()
        registry.discover()
        market = registry.get("market_data")
        result = market.safe_execute(ctx, "get_price")
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._discovered = False

    # ── Discovery ────────────────────────────────────────────

    def discover(self) -> list[str]:
        """
        Scan skills/ directory for skill packages.

        A valid skill package is a subdirectory that:
        1. Contains a SKILL.md file
        2. Contains a skill.py with a class extending BaseSkill

        Returns:
            List of discovered skill names
        """
        skills_dir = Path(__file__).parent
        discovered = []

        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(("_", ".")):
                continue

            skill_md = entry / "SKILL.md"
            skill_py = entry / "skill.py"

            if not skill_md.exists():
                continue

            # Try to load the skill module
            try:
                skill = self._load_skill(entry.name)
                if skill:
                    self._skills[skill.name] = skill
                    discovered.append(skill.name)
                    logger.info(f"Discovered skill: {skill}")
            except Exception as e:
                logger.warning(f"Failed to load skill '{entry.name}': {e}")

        self._discovered = True
        logger.info(f"Registry: {len(discovered)} skills discovered")
        return discovered

    def _load_skill(self, folder_name: str) -> Optional[BaseSkill]:
        """
        Import and instantiate a skill from its folder.

        Looks for the first BaseSkill subclass in skills.<folder>.skill
        """
        module_path = f"euroscope.skills.{folder_name}.skill"
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.warning(f"Cannot import {module_path}: {e}")
            return None

        # Find the first BaseSkill subclass in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type)
                    and issubclass(attr, BaseSkill)
                    and attr is not BaseSkill):
                return attr()

        logger.warning(f"No BaseSkill subclass found in {module_path}")
        return None

    # ── Query API ────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseSkill]:
        """Get a skill by name."""
        if not self._discovered:
            self.discover()
        return self._skills.get(name)

    def list_all(self) -> list[BaseSkill]:
        """List all registered skills."""
        if not self._discovered:
            self.discover()
        return list(self._skills.values())

    def list_by_category(self, category: SkillCategory) -> list[BaseSkill]:
        """Filter skills by category."""
        return [s for s in self.list_all() if s.category == category]

    def list_names(self) -> list[str]:
        """List all registered skill names."""
        return list(self._skills.keys())

    # ── Registration API ─────────────────────────────────────

    def register(self, skill: BaseSkill):
        """Manually register a skill (useful for testing)."""
        self._skills[skill.name] = skill
        logger.info(f"Manually registered: {skill}")

    def unregister(self, name: str):
        """Remove a skill from the registry."""
        self._skills.pop(name, None)

    # ── LLM Formatting ───────────────────────────────────────

    def get_tools_prompt(self) -> str:
        """
        Generate a prompt section describing all available skills.

        This is injected into the LLM system prompt so it understands
        what tools/skills are available.
        """
        if not self._discovered:
            self.discover()

        if not self._skills:
            return "No skills available."

        lines = ["# Available Skills\n"]
        by_cat: dict[str, list[BaseSkill]] = {}

        for skill in self._skills.values():
            cat = skill.category.value
            by_cat.setdefault(cat, []).append(skill)

        for cat, skills in sorted(by_cat.items()):
            lines.append(f"\n## {cat.title()}")
            for skill in skills:
                caps = ", ".join(skill.capabilities)
                lines.append(
                    f"- {skill.emoji} **{skill.name}** — {skill.description} "
                    f"[actions: {caps}]"
                )

        return "\n".join(lines)

    def get_skill_cards(self) -> str:
        """Get detailed cards for all skills (for LLM deep context)."""
        cards = []
        for skill in self.list_all():
            cards.append(skill.get_skill_card())
        return "\n\n---\n\n".join(cards)

    # ── Dunder ────────────────────────────────────────────────

    def __len__(self):
        return len(self._skills)

    def __contains__(self, name: str):
        return name in self._skills

    def __repr__(self):
        return f"<SkillsRegistry: {len(self._skills)} skills>"
