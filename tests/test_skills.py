"""
Tests for Skills Framework — BaseSkill, SkillsRegistry, and all 9 Skills.
"""

import sys
import types

# Mock yfinance + mplfinance if not installed
for mod_name in ("yfinance", "mplfinance", "mplfinance.original_flavor", "matplotlib", "matplotlib.pyplot"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

import pytest
from unittest.mock import MagicMock, patch
from euroscope.skills.base import BaseSkill, SkillCategory, SkillContext, SkillResult


# ── SkillResult Tests ────────────────────────────────────────

class TestSkillResult:
    def test_success_is_truthy(self):
        r = SkillResult(success=True, data={"price": 1.08})
        assert r
        assert r.success
        assert r.data == {"price": 1.08}

    def test_failure_is_falsy(self):
        r = SkillResult(success=False, error="API down")
        assert not r
        assert r.error == "API down"

    def test_next_skill_suggestion(self):
        r = SkillResult(success=True, data={}, next_skill="technical_analysis")
        assert r.next_skill == "technical_analysis"


# ── SkillContext Tests ───────────────────────────────────────

class TestSkillContext:
    def test_empty_context(self):
        ctx = SkillContext()
        assert ctx.market_data == {}
        assert ctx.history == []

    def test_add_and_get_result(self):
        ctx = SkillContext()
        r = SkillResult(success=True, data={"price": 1.08})
        ctx.add_result("market_data", r)
        entry = ctx.get_result("market_data")
        assert entry is not None
        assert entry["skill"] == "market_data"
        assert entry["success"] is True

    def test_get_missing_result(self):
        ctx = SkillContext()
        assert ctx.get_result("nonexistent") is None


# ── BaseSkill Tests ──────────────────────────────────────────

class TestBaseSkill:
    class DummySkill(BaseSkill):
        name = "dummy"
        description = "A test skill"
        emoji = "🧪"
        category = SkillCategory.SYSTEM
        version = "0.1.0"
        capabilities = ["do_thing", "do_other", "fail"]

        async def execute(self, context, action, **params):
            if action == "do_thing":
                return SkillResult(success=True, data="done")
            elif action == "fail":
                raise ValueError("Boom")
            return SkillResult(success=False, error="unknown")

    def test_validate_known_action(self):
        s = self.DummySkill()
        assert s.validate("do_thing")
        assert s.validate("do_other")

    def test_validate_unknown_action(self):
        s = self.DummySkill()
        assert not s.validate("fly")

    @pytest.mark.asyncio
    async def test_safe_execute_success(self):
        s = self.DummySkill()
        ctx = SkillContext()
        r = await s.safe_execute(ctx, "do_thing")
        assert r.success
        assert r.data == "done"
        assert len(ctx.history) == 1

    @pytest.mark.asyncio
    async def test_safe_execute_unknown_action(self):
        s = self.DummySkill()
        ctx = SkillContext()
        r = await s.safe_execute(ctx, "fly")
        assert not r.success
        assert "Unknown action" in r.error

    @pytest.mark.asyncio
    async def test_safe_execute_catches_exception(self):
        s = self.DummySkill()
        ctx = SkillContext()
        r = await s.safe_execute(ctx, "fail")
        assert not r.success
        assert "Boom" in r.error
        assert len(ctx.history) == 1

    def test_get_skill_card(self):
        s = self.DummySkill()
        card = s.get_skill_card()
        assert "dummy" in card
        assert "do_thing" in card
        assert "🧪" in card

    def test_repr(self):
        s = self.DummySkill()
        assert "dummy" in repr(s)
        assert "system" in repr(s)


# ── SkillsRegistry Tests ────────────────────────────────────

class TestSkillsRegistry:
    def test_manual_register(self):
        from euroscope.skills.registry import SkillsRegistry
        reg = SkillsRegistry()
        dummy = TestBaseSkill.DummySkill()
        reg.register(dummy)
        assert "dummy" in reg
        assert len(reg) == 1
        assert reg.get("dummy") is dummy

    def test_unregister(self):
        from euroscope.skills.registry import SkillsRegistry
        reg = SkillsRegistry()
        dummy = TestBaseSkill.DummySkill()
        reg.register(dummy)
        reg.unregister("dummy")
        assert "dummy" not in reg

    def test_list_by_category(self):
        from euroscope.skills.registry import SkillsRegistry
        reg = SkillsRegistry()
        reg._discovered = True
        dummy = TestBaseSkill.DummySkill()
        reg.register(dummy)
        system_skills = reg.list_by_category(SkillCategory.SYSTEM)
        assert len(system_skills) >= 1

    def test_tools_prompt(self):
        from euroscope.skills.registry import SkillsRegistry
        reg = SkillsRegistry()
        reg._discovered = True
        dummy = TestBaseSkill.DummySkill()
        reg.register(dummy)
        prompt = reg.get_tools_prompt()
        assert "dummy" in prompt
        assert "System" in prompt

    def test_discover_finds_skills(self):
        from euroscope.skills.registry import SkillsRegistry
        reg = SkillsRegistry()
        discovered = reg.discover()
        # Should find at least some of our 9 skills
        assert len(discovered) >= 1
        assert isinstance(discovered, list)


# ── Individual Skill Import Tests ────────────────────────────

class TestSkillImports:
    def test_market_data_skill(self):
        from euroscope.skills.market_data import MarketDataSkill
        s = MarketDataSkill()
        assert s.name == "market_data"
        assert "get_price" in s.capabilities

    def test_technical_analysis_skill(self):
        from euroscope.skills.technical_analysis import TechnicalAnalysisSkill
        s = TechnicalAnalysisSkill()
        assert s.name == "technical_analysis"
        assert "full" in s.capabilities

    def test_fundamental_analysis_skill(self):
        from euroscope.skills.fundamental_analysis import FundamentalAnalysisSkill
        s = FundamentalAnalysisSkill()
        assert s.name == "fundamental_analysis"

    def test_risk_management_skill(self):
        from euroscope.skills.risk_management import RiskManagementSkill
        s = RiskManagementSkill()
        assert s.name == "risk_management"

    def test_trading_strategy_skill(self):
        from euroscope.skills.trading_strategy import TradingStrategySkill
        s = TradingStrategySkill()
        assert s.name == "trading_strategy"

    def test_signal_executor_skill(self):
        from euroscope.skills.signal_executor import SignalExecutorSkill
        s = SignalExecutorSkill()
        assert s.name == "signal_executor"

    def test_backtesting_skill(self):
        from euroscope.skills.backtesting import BacktestingSkill
        s = BacktestingSkill()
        assert s.name == "backtesting"

    def test_performance_analytics_skill(self):
        from euroscope.skills.performance_analytics import PerformanceAnalyticsSkill
        s = PerformanceAnalyticsSkill()
        assert s.name == "performance_analytics"

    def test_monitoring_skill(self):
        from euroscope.skills.monitoring import MonitoringSkill
        s = MonitoringSkill(storage=MagicMock())
        assert s.name == "monitoring"


# ── Skill Execution Tests ───────────────────────────────────

class TestSkillExecution:
    @pytest.mark.asyncio
    async def test_market_data_no_provider(self):
        from euroscope.skills.market_data import MarketDataSkill
        s = MarketDataSkill()
        ctx = SkillContext()
        r = await s.safe_execute(ctx, "get_price")
        assert not r.success
        assert "provider" in r.error.lower()

    @pytest.mark.asyncio
    async def test_signal_executor_open_close(self):
        from euroscope.skills.signal_executor import SignalExecutorSkill
        s = SignalExecutorSkill()
        ctx = SkillContext()
        ctx.signals = {"direction": "BUY", "entry_price": 1.0850, "strategy": "trend_following"}
        ctx.risk = {"stop_loss": 1.0820, "take_profit": 1.0910}
        ctx.metadata["session_regime"] = "overlap"
        ctx.metadata["macro_quality"] = "complete"

        # Open
        r = await s.safe_execute(ctx, "open_trade")
        assert r.success
        assert r.data["direction"] == "BUY"
        trade_id = r.data["trade_id"]

        # List
        r2 = await s.safe_execute(ctx, "list_trades")
        assert r2.success
        assert len(r2.data) == 1

        # Close
        r3 = await s.safe_execute(ctx, "close_trade", trade_id=trade_id, exit_price=1.0900)
        assert r3.success
        assert r3.data["pnl_pips"] == 50.0

        # History
        r4 = await s.safe_execute(ctx, "trade_history")
        assert r4.success
        assert len(r4.data) == 1

    @pytest.mark.asyncio
    async def test_signal_executor_aborts_on_uncertainty(self):
        from euroscope.skills.signal_executor import SignalExecutorSkill
        s = SignalExecutorSkill()
        ctx = SkillContext()
        ctx.signals = {"direction": "BUY", "entry_price": 1.0850, "strategy": "trend_following"}
        ctx.risk = {"stop_loss": 1.0820, "take_profit": 1.0910}
        ctx.metadata["uncertainty_score"] = 0.7
        ctx.metadata["session_regime"] = "overlap"
        ctx.metadata["macro_quality"] = "complete"

        r = await s.safe_execute(ctx, "open_trade")
        assert not r.success
        assert r.error == "UNCERTAINTY: confidence too low"

    @pytest.mark.asyncio
    async def test_trading_strategy_list(self):
        from euroscope.skills.trading_strategy import TradingStrategySkill
        s = TradingStrategySkill()
        ctx = SkillContext()
        r = await s.safe_execute(ctx, "list_strategies")
        assert r.success
        assert "trend_following" in r.data

    @pytest.mark.asyncio
    async def test_trading_strategy_blocks_on_high_uncertainty(self):
        from euroscope.skills.trading_strategy import TradingStrategySkill
        s = TradingStrategySkill()
        ctx = SkillContext()
        ctx.analysis["indicators"] = {
            "overall_bias": "bullish",
            "indicators": {
                "ADX": {"value": 30},
                "RSI": {"value": 55},
                "MACD": {"histogram": 0.0001},
            },
        }
        ctx.analysis["levels"] = {"current_price": 1.0950, "support": [], "resistance": []}
        ctx.metadata["confidence_adjustment"] = 0.8
        ctx.metadata["high_uncertainty"] = True

        r = await s.safe_execute(ctx, "detect_signal")
        assert r.success
        assert r.data["direction"] == "WAIT"
        assert r.data["blocking_reason"] == "high_uncertainty_without_macro_confirmation"

    @pytest.mark.asyncio
    async def test_monitoring_track_error(self):
        from euroscope.skills.monitoring import MonitoringSkill
        s = MonitoringSkill(storage=MagicMock())
        ctx = SkillContext()
        r = await s.safe_execute(ctx, "track_error", component="test", error="test error")
        assert r.success

    def test_registry_discover_all_nine(self):
        from euroscope.skills.registry import SkillsRegistry
        reg = SkillsRegistry()
        names = reg.discover()
        assert len(names) >= 9
        expected = [
            "market_data", "technical_analysis", "fundamental_analysis",
            "risk_management", "trading_strategy", "signal_executor",
            "backtesting", "performance_analytics", "monitoring",
        ]
        for exp in expected:
            assert exp in names, f"Skill '{exp}' not discovered"
