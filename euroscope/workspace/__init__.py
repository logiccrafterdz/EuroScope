"""
Workspace Manager — Reads/writes workspace config files for LLM context.

Provides the system's identity, soul, tools, memory, heartbeat,
and user preferences as structured context for the brain.
"""

import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from ..skills.registry import SkillsRegistry

logger = logging.getLogger("euroscope.workspace")

_DEFAULT_WORKSPACE = Path(__file__).resolve().parent.parent.parent / "workspace"


class WorkspaceManager:
    """
    Manages the workspace/ directory — reads markdown configs,
    writes runtime state, and builds LLM system prompts.
    """

    FILES = ["IDENTITY.md", "SOUL.md", "TOOLS.md", "MEMORY.md",
             "HEARTBEAT.md", "USER.md"]

    def __init__(self, workspace_dir: Path = None):
        self.workspace_dir = workspace_dir or _DEFAULT_WORKSPACE
        self._cache: dict[str, str] = {}

    def _read(self, filename: str) -> str:
        """Read a workspace file, with caching."""
        if filename in self._cache:
            return self._cache[filename]
        path = self.workspace_dir / filename
        if not path.exists():
            logger.warning(f"Workspace file not found: {path}")
            return ""
        content = path.read_text(encoding="utf-8")
        self._cache[filename] = content
        return content

    def _write(self, filename: str, content: str):
        """Write a workspace file and update cache."""
        path = self.workspace_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._cache[filename] = content

    # ── Public API ───────────────────────────────────────────

    @property
    def identity(self) -> str:
        return self._read("IDENTITY.md")

    @property
    def soul(self) -> str:
        return self._read("SOUL.md")

    @property
    def tools(self) -> str:
        return self._read("TOOLS.md")

    @property
    def memory(self) -> str:
        return self._read("MEMORY.md")

    @property
    def heartbeat(self) -> str:
        return self._read("HEARTBEAT.md")

    @property
    def user(self) -> str:
        return self._read("USER.md")

    def refresh_tools(self, registry: SkillsRegistry):
        """Regenerate TOOLS.md from current SkillsRegistry."""
        header = "# Available Tools\n\n> Auto-generated from SkillsRegistry.\n\n"
        tools_content = header + registry.get_tools_prompt()
        self._write("TOOLS.md", tools_content)
        logger.info("TOOLS.md refreshed from SkillsRegistry")

    def update_heartbeat(self, components: dict[str, dict]):
        """
        Update HEARTBEAT.md with component statuses.

        Args:
            components: {"name": {"status": "✅ Online", "last_check": "..."}}
        """
        lines = [
            "# Heartbeat\n",
            f"Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n",
            "| Component | Status | Last Check |",
            "|-----------|--------|------------|",
        ]
        for name, info in components.items():
            status = info.get("status", "❓ Unknown")
            checked = info.get("last_check", "—")
            lines.append(f"| {name} | {status} | {checked} |")
        self._write("HEARTBEAT.md", "\n".join(lines))

    def append_memory(self, entry: str):
        """Append a new entry to MEMORY.md under Recent Analyses."""
        current = self._read("MEMORY.md")
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        new_entry = f"\n- [{timestamp}] {entry}"
        if "## Recent Analyses" in current:
            current = current.replace(
                "## Recent Analyses\n_Populated at runtime._",
                f"## Recent Analyses{new_entry}",
                1,
            )
            if new_entry not in current:
                # Already has entries, append after header
                idx = current.index("## Recent Analyses")
                end = current.find("\n## ", idx + 1)
                if end == -1:
                    current += new_entry
                else:
                    current = current[:end] + new_entry + "\n" + current[end:]
        else:
            current += new_entry
        self._write("MEMORY.md", current)

    def refresh_memory(self, storage=None):
        """
        Refresh MEMORY.md with latest learning insights.

        Pulls from: prediction accuracy, pattern stats, tuning recommendations.
        """
        from ..learning.pattern_tracker import PatternTracker
        from ..learning.adaptive_tuner import AdaptiveTuner
        from ..brain.memory import Memory
        from ..data.storage import Storage as _Storage

        storage = storage or _Storage()
        memory = Memory(storage)
        tracker = PatternTracker(storage)
        tuner = AdaptiveTuner(storage)

        lines = [
            "# Memory\n",
            f"> Auto-refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n",
        ]

        # 1. Prediction accuracy
        learning = memory.get_learning_context()
        if learning and "No sufficient" not in learning:
            lines.append("## Prediction Accuracy\n")
            lines.append(learning + "\n")

        # 2. Pattern success rates
        rates = tracker.get_success_rates()
        if rates:
            lines.append("## Pattern Performance\n")
            for key, data in sorted(rates.items(),
                                     key=lambda x: x[1]["success_rate"],
                                     reverse=True):
                icon = "🟢" if data["success_rate"] >= 60 else "🔴"
                lines.append(
                    f"- {icon} `{data['pattern']}` ({data['timeframe']}): "
                    f"{data['success_rate']}% ({data['successes']}/{data['total']})"
                )
            lines.append("")

        # 3. Tuning recommendations
        result = tuner.analyze()
        if result["ready"] and result["recommendations"]:
            lines.append("## Tuning Suggestions\n")
            for rec in result["recommendations"]:
                lines.append(f"- `{rec['param']}` → {rec['action']}: {rec['reason']}")
            lines.append("")

        # 4. Preserved: recent analyses
        current = self._read("MEMORY.md")
        if "## Recent Analyses" in current:
            idx = current.index("## Recent Analyses")
            lines.append(current[idx:])

        self._write("MEMORY.md", "\n".join(lines))
        logger.info("MEMORY.md refreshed with learning insights")

    def refresh_identity(self, storage=None):
        from ..learning.pattern_tracker import PatternTracker
        from ..brain.memory import Memory
        from ..data.storage import Storage as _Storage

        storage = storage or _Storage()
        memory = Memory(storage)
        tracker = PatternTracker(storage)
        stats = storage.get_trade_journal_stats()

        accuracy = storage.get_accuracy_stats(30)
        accuracy_line = (
            f"Prediction accuracy (30d): {accuracy.get('accuracy', 0)}% "
            f"({accuracy.get('total', 0)} predictions)"
        )

        top_patterns = []
        rates = tracker.get_success_rates()
        if rates:
            sorted_rates = sorted(rates.values(), key=lambda x: x["success_rate"], reverse=True)
            top_patterns = sorted_rates[:3]

        best_strategy = None
        by_strategy = stats.get("by_strategy", {})
        if by_strategy:
            best_strategy = max(by_strategy.items(), key=lambda x: x[1]["win_rate"])[0]

        lines = [
            "## Adaptive Profile",
            accuracy_line,
        ]
        if best_strategy:
            lines.append(f"Best-performing strategy: {best_strategy}")
        if top_patterns:
            patterns_text = ", ".join(f"{p['pattern']} {p['timeframe']} ({p['success_rate']}%)" for p in top_patterns)
            lines.append(f"Top patterns: {patterns_text}")

        identity = self._read("IDENTITY.md")
        updated = self._upsert_section(identity, "## Adaptive Profile", "\n".join(lines))
        self._write("IDENTITY.md", updated)
        logger.info("IDENTITY.md refreshed with adaptive profile")

    @staticmethod
    def _upsert_section(text: str, header: str, section_text: str) -> str:
        if header not in text:
            return text.rstrip() + "\n\n" + section_text.strip() + "\n"

        start = text.index(header)
        next_header = text.find("\n## ", start + len(header))
        if next_header == -1:
            return text[:start].rstrip() + "\n\n" + section_text.strip() + "\n"

        return text[:start].rstrip() + "\n\n" + section_text.strip() + "\n\n" + text[next_header:].lstrip()

    def build_system_prompt(self) -> str:
        """
        Build a complete system prompt from all workspace files.
        Used as the system message for LLM-driven analysis.
        """
        sections = [
            self.identity,
            self.soul,
            self.tools,
            self.memory,
            self.user,
        ]
        return "\n\n---\n\n".join(s for s in sections if s)

    def clear_cache(self):
        """Clear in-memory cache to force re-reads."""
        self._cache.clear()

