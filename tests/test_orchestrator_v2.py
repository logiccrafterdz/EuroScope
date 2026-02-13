"""
Tests for Phase 3 (Orchestrator V2) and Phase 4 (Workspace System).
"""

import sys
import types
import tempfile
from pathlib import Path

# Mock yfinance if not installed
for mod_name in ("yfinance", "mplfinance", "mplfinance.original_flavor", "matplotlib", "matplotlib.pyplot"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

import pytest
from unittest.mock import MagicMock, patch
from euroscope.skills.base import SkillCategory, SkillContext, SkillResult


# ── SkillChain Tests ─────────────────────────────────────────

class TestSkillChain:
    def test_chain_basic(self):
        from euroscope.brain.orchestrator import SkillChain
        from euroscope.skills.registry import SkillsRegistry

        reg = SkillsRegistry()
        reg._discovered = True  # skip auto-discover

        # Register a mock skill
        mock_skill = MagicMock()
        mock_skill.name = "test_skill"
        mock_skill.safe_execute.return_value = SkillResult(success=True, data={"foo": 1})

        reg._skills["test_skill"] = mock_skill

        chain = SkillChain(reg)
        ctx = chain.run([("test_skill", "do_thing")])

        assert isinstance(ctx, SkillContext)
        mock_skill.safe_execute.assert_called_once()

    def test_chain_missing_skill(self):
        from euroscope.brain.orchestrator import SkillChain
        from euroscope.skills.registry import SkillsRegistry

        reg = SkillsRegistry()
        reg._discovered = True

        chain = SkillChain(reg)
        ctx = chain.run([("nonexistent", "do_thing")])
        assert isinstance(ctx, SkillContext)  # Doesn't crash

    def test_chain_failed_step_continues(self):
        from euroscope.brain.orchestrator import SkillChain
        from euroscope.skills.registry import SkillsRegistry

        reg = SkillsRegistry()
        reg._discovered = True

        fail_skill = MagicMock()
        fail_skill.name = "fail"
        fail_skill.safe_execute.return_value = SkillResult(success=False, error="boom")
        ok_skill = MagicMock()
        ok_skill.name = "ok"
        ok_skill.safe_execute.return_value = SkillResult(success=True, data="good")

        reg._skills["fail"] = fail_skill
        reg._skills["ok"] = ok_skill

        chain = SkillChain(reg)
        ctx = chain.run([("fail", "a"), ("ok", "b")])
        ok_skill.safe_execute.assert_called_once()


# ── Orchestrator V2 Tests ────────────────────────────────────

class TestOrchestratorV2:
    def test_run_skill(self):
        from euroscope.brain.orchestrator import Orchestrator
        o = Orchestrator()
        ctx = SkillContext()
        # signal_executor is simple and works without injection
        r = o.run_skill("signal_executor", "list_trades", ctx)
        assert r.success

    def test_run_pipeline(self):
        from euroscope.brain.orchestrator import Orchestrator
        o = Orchestrator()
        ctx = o.run_pipeline([
            ("signal_executor", "list_trades"),
        ])
        assert isinstance(ctx, SkillContext)

    def test_get_available_skills(self):
        from euroscope.brain.orchestrator import Orchestrator
        o = Orchestrator()
        prompt = o.get_available_skills()
        assert "market_data" in prompt
        assert "technical_analysis" in prompt

    def test_legacy_run_analysis_still_works(self):
        from euroscope.brain.orchestrator import Orchestrator
        o = Orchestrator()
        context = {
            "indicators": {"indicators": {
                "RSI": {"value": 55}, "MACD": {"histogram": 0.001},
                "EMA": {"short": 1.085, "long": 1.083},
                "ADX": {"value": 30},
            }, "overall_bias": "bullish"},
            "patterns": [],
            "levels": {"current_price": 1.085, "support": [1.080], "resistance": [1.090]},
            "macro": {"rate_differential": 0.5, "yield_spread": 0.3},
            "calendar": [],
            "sentiment_summary": {"score": 0.2, "article_count": 5},
            "news_articles": [],
        }
        result = o.run_analysis(context)
        assert "consensus" in result
        assert "specialists" in result
        assert "formatted" in result


# ── WorkspaceManager Tests ───────────────────────────────────

class TestWorkspaceManager:
    @pytest.fixture
    def ws_dir(self, tmp_path):
        """Create a temp workspace with all 6 files."""
        files = {
            "IDENTITY.md": "# Identity\nI am EuroScope.",
            "SOUL.md": "# Soul\nSafety first.",
            "TOOLS.md": "# Tools\nPlaceholder.",
            "MEMORY.md": "# Memory\n\n## Recent Analyses\n_Populated at runtime._\n\n## Notable Events\n_Updated._",
            "HEARTBEAT.md": "# Heartbeat\nOK.",
            "USER.md": "# User\nRisk 1%.",
        }
        for name, content in files.items():
            (tmp_path / name).write_text(content, encoding="utf-8")
        return tmp_path

    def test_read_identity(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(ws_dir)
        assert "EuroScope" in ws.identity

    def test_read_soul(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(ws_dir)
        assert "Safety" in ws.soul

    def test_read_missing_file(self, tmp_path):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(tmp_path)
        assert ws.identity == ""

    def test_build_system_prompt(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(ws_dir)
        prompt = ws.build_system_prompt()
        assert "EuroScope" in prompt
        assert "Safety" in prompt
        assert "Risk 1%" in prompt

    def test_refresh_tools(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        from euroscope.skills.registry import SkillsRegistry
        ws = WorkspaceManager(ws_dir)
        reg = SkillsRegistry()
        reg._discovered = True

        mock_skill = MagicMock()
        mock_skill.name = "test_skill"
        mock_skill.category = SkillCategory.DATA
        mock_skill.get_skill_card.return_value = "[test_skill] card"
        reg._skills["test_skill"] = mock_skill

        ws.refresh_tools(reg)
        ws.clear_cache()  # Force re-read

        tools_content = ws.tools
        assert "test_skill" in tools_content

    def test_update_heartbeat(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(ws_dir)
        ws.update_heartbeat({
            "Price API": {"status": "✅ Online", "last_check": "12:00"},
            "Database": {"status": "❌ Offline", "last_check": "12:01"},
        })
        ws.clear_cache()
        hb = ws.heartbeat
        assert "Price API" in hb
        assert "✅ Online" in hb
        assert "❌ Offline" in hb

    def test_append_memory(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(ws_dir)
        ws.append_memory("Analyzed EUR/USD — bullish bias H4")
        ws.clear_cache()
        mem = ws.memory
        assert "bullish bias" in mem

    def test_caching(self, ws_dir):
        from euroscope.workspace import WorkspaceManager
        ws = WorkspaceManager(ws_dir)
        _ = ws.identity
        # Modify file directly
        (ws_dir / "IDENTITY.md").write_text("Changed!", encoding="utf-8")
        # Cache still returns old value
        assert "EuroScope" in ws.identity
        # After clear, returns new value
        ws.clear_cache()
        assert ws.identity == "Changed!"
