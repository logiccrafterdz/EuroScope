"""
Integration Tests — End-to-end testing for the Skills Architecture.

Tests cross-component communication, skill chaining,
error handling, and full pipeline execution.
"""

import sys
import types
import asyncio

# Mock yfinance if not installed
for mod_name in ("yfinance", "mplfinance", "mplfinance.original_flavor",
                 "matplotlib", "matplotlib.pyplot"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from euroscope.skills.base import BaseSkill, SkillCategory, SkillContext, SkillResult
from euroscope.skills.registry import SkillsRegistry
from euroscope.brain.orchestrator import Orchestrator, SkillChain
from euroscope.automation.events import EventBus, Event
from euroscope.automation.alerts import SmartAlerts, setup_default_alerts
from euroscope.automation.heartbeat import HeartbeatService
from euroscope.automation.cron import CronScheduler, TaskFrequency


# ── 6.1 Skills Communication Protocol ───────────────────────

class TestSkillsCommunication:
    """Test that SkillResult flows correctly between skills."""

    def test_context_flows_between_skills(self):
        """SkillContext data set by one skill is available to the next."""
        from euroscope.skills.signal_executor import SignalExecutorSkill

        ctx = SkillContext()
        # Simulate market_data populating context
        ctx.market_data["price"] = {"price": 1.0850, "change": -0.0012}

        # Simulate technical_analysis populating analysis
        ctx.analysis["indicators"] = {
            "overall_bias": "bullish",
            "indicators": {"RSI": {"value": 55}, "ADX": {"value": 30}},
        }

        # Signal executor should be able to read context
        ctx.signals = {"direction": "BUY", "entry_price": 1.0850, "strategy": "trend"}
        ctx.risk = {"stop_loss": 1.0820, "take_profit": 1.0910}

        executor = SignalExecutorSkill()
        result = executor.safe_execute(ctx, "open_trade")
        assert result.success
        assert result.data["direction"] == "BUY"
        assert len(ctx.open_positions) == 1

    def test_result_stored_in_history(self):
        """Each skill execution is recorded in context.history."""
        ctx = SkillContext()
        r = SkillResult(success=True, data={"test": 1})
        ctx.add_result("test_skill", r)
        assert len(ctx.history) == 1
        assert ctx.history[0]["skill"] == "test_skill"

    def test_next_skill_suggestion(self):
        """SkillResult.next_skill correctly suggests the next skill."""
        r = SkillResult(success=True, data={}, next_skill="risk_management")
        assert r.next_skill == "risk_management"

    def test_metadata_passthrough(self):
        """SkillResult.metadata carries extra information."""
        r = SkillResult(success=True, data={}, metadata={"trade_id": "PT-0001"})
        assert r.metadata["trade_id"] == "PT-0001"


# ── 6.2 Data Flow Pipeline ──────────────────────────────────

class TestDataFlowPipeline:
    """Test end-to-end skill chaining via SkillChain and Orchestrator."""

    def test_chain_with_mock_skills(self):
        """SkillChain correctly passes context through multiple skills."""
        reg = SkillsRegistry()
        reg._discovered = True

        # Create two mock skills that read/write context
        skill_a = MagicMock()
        skill_a.name = "a"
        def a_execute(ctx, action, **p):
            ctx.market_data["from_a"] = True
            return SkillResult(success=True, data={"a": 1})
        skill_a.safe_execute = a_execute

        skill_b = MagicMock()
        skill_b.name = "b"
        def b_execute(ctx, action, **p):
            assert ctx.market_data.get("from_a") is True  # Data flows!
            return SkillResult(success=True, data={"b": 2})
        skill_b.safe_execute = b_execute

        reg._skills = {"a": skill_a, "b": skill_b}

        chain = SkillChain(reg)
        ctx = chain.run([("a", "go"), ("b", "go")])
        assert ctx.market_data["from_a"] is True

    def test_orchestrator_pipeline(self):
        """Orchestrator.run_pipeline chains skills correctly."""
        o = Orchestrator()
        ctx = o.run_pipeline([
            ("signal_executor", "list_trades"),
        ])
        assert isinstance(ctx, SkillContext)
        assert len(ctx.history) >= 1

    def test_full_executor_flow(self):
        """Full signal → open → close → history flow."""
        from euroscope.skills.signal_executor import SignalExecutorSkill

        executor = SignalExecutorSkill()
        ctx = SkillContext()
        ctx.signals = {"direction": "SELL", "entry_price": 1.0900, "strategy": "breakout"}
        ctx.risk = {"stop_loss": 1.0930, "take_profit": 1.0840}

        # Open
        r1 = executor.safe_execute(ctx, "open_trade")
        assert r1.success
        trade_id = r1.data["trade_id"]

        # Close with profit
        r2 = executor.safe_execute(ctx, "close_trade",
                                   trade_id=trade_id, exit_price=1.0850)
        assert r2.success
        assert r2.data["pnl_pips"] == 50.0

        # History
        r3 = executor.safe_execute(ctx, "trade_history")
        assert len(r3.data) == 1
        assert r3.data[0]["pnl_pips"] == 50.0


# ── 6.3 Error Handling ──────────────────────────────────────

class TestErrorHandling:
    """Test graceful degradation when skills fail."""

    def test_safe_execute_catches_all(self):
        """safe_execute wraps exceptions into SkillResult errors."""
        class CrashSkill(BaseSkill):
            name = "crash"
            description = "Crashes"
            emoji = "💥"
            category = SkillCategory.SYSTEM
            version = "0.1.0"
            capabilities = ["boom"]
            def execute(self, ctx, action, **p):
                raise RuntimeError("kernel panic")

        s = CrashSkill()
        ctx = SkillContext()
        r = s.safe_execute(ctx, "boom")
        assert not r.success
        assert "kernel panic" in r.error

    def test_chain_continues_on_failure(self):
        """SkillChain doesn't abort on failed skill."""
        reg = SkillsRegistry()
        reg._discovered = True

        fail = MagicMock()
        fail.name = "fail"
        fail.safe_execute.return_value = SkillResult(success=False, error="down")

        ok = MagicMock()
        ok.name = "ok"
        ok.safe_execute.return_value = SkillResult(success=True, data="fine")

        reg._skills = {"fail": fail, "ok": ok}
        chain = SkillChain(reg)
        ctx = chain.run([("fail", "a"), ("ok", "b")])
        ok.safe_execute.assert_called_once()

    def test_chain_skips_missing_skill(self):
        """SkillChain skips unavailable skills gracefully."""
        reg = SkillsRegistry()
        reg._discovered = True
        reg._skills = {}
        chain = SkillChain(reg)
        ctx = chain.run([("nonexistent", "go")])
        assert isinstance(ctx, SkillContext)

    def test_orchestrator_run_skill_not_found(self):
        """Orchestrator returns error for unknown skill."""
        o = Orchestrator()
        r = o.run_skill("fake_skill", "fake_action")
        assert not r.success
        assert "not found" in r.error

    def test_market_data_no_provider_graceful(self):
        """MarketDataSkill fails gracefully without provider."""
        from euroscope.skills.market_data import MarketDataSkill
        s = MarketDataSkill()
        ctx = SkillContext()
        r = s.safe_execute(ctx, "get_price")
        assert not r.success
        assert "provider" in r.error.lower()


# ── 6.4 Cross-Component Integration ─────────────────────────

class TestCrossComponentIntegration:
    """Test automation + skills working together."""

    @pytest.mark.asyncio
    async def test_event_triggers_alert(self):
        """EventBus event triggers SmartAlert check."""
        alerts = SmartAlerts()
        alerts.add_rule("sig_alert",
                       condition=lambda d: d.get("direction") == "BUY",
                       title="Signal", message_template="BUY signal!",
                       cooldown=0)

        bus = EventBus()
        triggered = []

        def on_signal(event):
            result = alerts.check(event.data)
            triggered.extend(result)

        bus.subscribe("signal.new", on_signal)
        bus.emit_sync(Event("signal.new", "strategy", {"direction": "BUY"}))

        assert len(triggered) == 1

    @pytest.mark.asyncio
    async def test_heartbeat_with_skill_check(self):
        """HeartbeatService runs a skill-based health check."""
        hb = HeartbeatService()

        from euroscope.skills.signal_executor import SignalExecutorSkill
        executor = SignalExecutorSkill()

        def skill_check():
            ctx = SkillContext()
            r = executor.safe_execute(ctx, "list_trades")
            return {"status": "healthy" if r.success else "error"}

        hb.register_check("signal_executor", skill_check)
        results = await hb.tick()
        assert results["signal_executor"]["status"] == "healthy"

    def test_registry_provides_tools_for_workspace(self):
        """SkillsRegistry generates LLM tools prompt used by WorkspaceManager."""
        from euroscope.workspace import WorkspaceManager
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            ws = WorkspaceManager(Path(tmp))
            reg = SkillsRegistry()
            reg.discover()

            ws.refresh_tools(reg)
            ws.clear_cache()
            tools = ws.tools
            assert "market_data" in tools
            assert "technical_analysis" in tools

    def test_default_alerts_integrate_with_indicators(self):
        """Default alert rules trigger on indicator data."""
        alerts = SmartAlerts()
        setup_default_alerts(alerts)
        # Reset cooldowns for testing
        for r in alerts.rules.values():
            r.cooldown_seconds = 0

        # RSI overbought should trigger
        triggered = alerts.check({"rsi": 80})
        names = [a.source for a in triggered]
        assert "rsi_overbought" in names

        # Drawdown warning
        triggered2 = alerts.check({"drawdown_pips": 60})
        names2 = [a.source for a in triggered2]
        assert "drawdown_warning" in names2
