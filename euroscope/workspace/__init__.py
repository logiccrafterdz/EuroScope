"""
Workspace Manager — Reads/writes workspace config files for LLM context.

Provides the system's identity, soul, tools, memory, heartbeat,
and user preferences as structured context for the brain.
"""

import logging
from datetime import datetime
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
            f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n",
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
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
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

    def build_system_prompt(self) -> str:
        """
        Build a complete system prompt from all workspace files.
        Used as the system message for LLM-driven analysis.
        """
        sections = [
            self.identity,
            self.soul,
            self.tools,
            self.user,
        ]
        return "\n\n---\n\n".join(s for s in sections if s)

    def clear_cache(self):
        """Clear in-memory cache to force re-reads."""
        self._cache.clear()
