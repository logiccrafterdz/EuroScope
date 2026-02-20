"""
Tests for risk manager: position sizing, stop loss, drawdown control.
"""

from datetime import datetime, UTC

import pytest

from euroscope.trading.risk_manager import RiskManager, RiskConfig, TradeRisk
from euroscope.skills.base import SkillContext
from euroscope.skills.risk_management.skill import RiskManagementSkill
from euroscope.bot.telegram_bot import EuroScopeBot


# ── Position Sizing ──────────────────────────────────────

class TestPositionSizing:

    def test_standard_position(self):
        rm = RiskManager(RiskConfig(account_balance=10000, risk_per_trade=1.0))
        # Risk $100, 30-pip stop, $10/pip → 100/(30*10) = 0.33 lots
        lots = rm.calculate_position_size(30)
        assert lots == 0.33

    def test_wider_stop_smaller_position(self):
        rm = RiskManager(RiskConfig(account_balance=10000, risk_per_trade=1.0))
        lots_30 = rm.calculate_position_size(30)
        lots_60 = rm.calculate_position_size(60)
        assert lots_60 < lots_30

    def test_zero_stop_returns_zero(self):
        rm = RiskManager()
        assert rm.calculate_position_size(0) == 0.0

    def test_negative_stop_returns_zero(self):
        rm = RiskManager()
        assert rm.calculate_position_size(-10) == 0.0

    def test_minimum_position(self):
        rm = RiskManager(RiskConfig(account_balance=100, risk_per_trade=0.5))
        lots = rm.calculate_position_size(200)  # Very small position
        assert lots == 0.01  # Minimum micro lot

    def test_max_position_capped(self):
        rm = RiskManager(RiskConfig(account_balance=10_000_000, risk_per_trade=10))
        lots = rm.calculate_position_size(1)  # Huge position
        assert lots <= 10.0


# ── Stop Loss ────────────────────────────────────────────

class TestStopLoss:

    def test_atr_stop_buy(self):
        rm = RiskManager()
        sl = rm.calculate_atr_stop(0.0050, "BUY", 1.0900)
        assert sl < 1.0900  # Stop below entry for BUY
        assert sl == pytest.approx(1.0825, abs=0.0001)

    def test_atr_stop_sell(self):
        rm = RiskManager()
        sl = rm.calculate_atr_stop(0.0050, "SELL", 1.0900)
        assert sl > 1.0900  # Stop above entry for SELL

    def test_level_stop_buy(self):
        rm = RiskManager()
        sl = rm.calculate_level_stop("BUY", 1.0950,
                                      support_levels=[1.0900, 1.0850],
                                      resistance_levels=[1.1000])
        assert sl is not None
        assert sl < 1.0900  # Below support + buffer

    def test_level_stop_sell(self):
        rm = RiskManager()
        sl = rm.calculate_level_stop("SELL", 1.0950,
                                      support_levels=[1.0900],
                                      resistance_levels=[1.1000, 1.1050])
        assert sl is not None
        assert sl > 1.1000  # Above resistance + buffer

    def test_level_stop_no_levels(self):
        rm = RiskManager()
        sl = rm.calculate_level_stop("BUY", 1.0950,
                                      support_levels=[],
                                      resistance_levels=[])
        assert sl is None


# ── Take Profit ──────────────────────────────────────────

class TestTakeProfit:

    def test_buy_tp_above_entry(self):
        rm = RiskManager()
        tp = rm.calculate_take_profit(1.0900, 1.0870, "BUY", rr_ratio=2.0)
        assert tp > 1.0900

    def test_sell_tp_below_entry(self):
        rm = RiskManager()
        tp = rm.calculate_take_profit(1.0900, 1.0930, "SELL", rr_ratio=2.0)
        assert tp < 1.0900

    def test_rr_ratio_applied(self):
        rm = RiskManager()
        tp = rm.calculate_take_profit(1.0900, 1.0870, "BUY", rr_ratio=3.0)
        expected = 1.0900 + 3 * (1.0900 - 1.0870)  # 1.0990
        assert tp == pytest.approx(expected, abs=0.0001)


# ── Full Trade Assessment ────────────────────────────────

class TestAssessTrade:

    def test_basic_buy_assessment(self):
        rm = RiskManager()
        trade = rm.assess_trade("BUY", 1.0900, atr=0.0050)
        assert isinstance(trade, TradeRisk)
        assert trade.direction == "BUY"
        assert trade.stop_loss < 1.0900
        assert trade.take_profit > 1.0900
        assert trade.position_size > 0
        assert trade.approved is True

    def test_basic_sell_assessment(self):
        rm = RiskManager()
        trade = rm.assess_trade("SELL", 1.0900, atr=0.0050)
        assert trade.direction == "SELL"
        assert trade.stop_loss > 1.0900
        assert trade.take_profit < 1.0900

    def test_risk_score_range(self):
        rm = RiskManager()
        trade = rm.assess_trade("BUY", 1.0900, atr=0.0050)
        assert 1 <= trade.risk_score <= 10

    def test_drawdown_blocks_trade(self):
        rm = RiskManager(RiskConfig(max_daily_drawdown=3.0))
        rm._daily_pnl = -350  # > 3% of 10000
        rm._daily_pnl_date = __import__("datetime").datetime.now(UTC).strftime("%Y-%m-%d")
        trade = rm.assess_trade("BUY", 1.0900, atr=0.0050)
        assert trade.approved is False
        assert any("drawdown" in w.lower() for w in trade.warnings)

    def test_max_trades_blocks(self):
        rm = RiskManager(RiskConfig(max_open_trades=3))
        rm._open_trade_count = 3
        trade = rm.assess_trade("BUY", 1.0900, atr=0.0050)
        assert trade.approved is False

    def test_fallback_stop_when_no_atr(self):
        rm = RiskManager()
        trade = rm.assess_trade("BUY", 1.0900)  # No ATR, no levels
        assert trade.stop_loss < 1.0900
        assert any("fallback" in w.lower() for w in trade.warnings)


# ── Trade Result Tracking ────────────────────────────────

class TestTradeTracking:

    def test_consecutive_losses(self):
        rm = RiskManager()
        rm.record_trade_result(-20)
        rm.record_trade_result(-15)
        assert rm._consecutive_losses == 2

    def test_win_resets_streak(self):
        rm = RiskManager()
        rm.record_trade_result(-20)
        rm.record_trade_result(-15)
        rm.record_trade_result(30)  # Win resets
        assert rm._consecutive_losses == 0

    def test_daily_pnl_accumulates(self):
        rm = RiskManager()
        rm.record_trade_result(30)
        rm.record_trade_result(-20)
        assert rm._daily_pnl == 10

    def test_format_risk(self):
        rm = RiskManager()
        trade = rm.assess_trade("BUY", 1.0900, atr=0.0050)
        formatted = rm.format_risk(trade)
        assert "Risk Assessment" in formatted
        assert "BUY" in formatted


@pytest.mark.asyncio
async def test_risk_management_skill_maps_trade_risk_fields():
    rm = RiskManager()
    skill = RiskManagementSkill()
    skill.set_risk_manager(rm)
    ctx = SkillContext()
    result = await skill.execute(
        ctx, "assess_trade", direction="BUY", entry_price=1.0900, atr=0.0050
    )
    assert result.success
    assert "risk_pips" in result.data
    assert "reward_pips" in result.data
    assert "risk_reward_ratio" in result.data
    assert "reason" in result.data


@pytest.mark.asyncio
async def test_risk_command_formatting_no_crash():
    rm = RiskManager()
    skill = RiskManagementSkill()
    skill.set_risk_manager(rm)
    ctx = SkillContext()
    result = await skill.execute(
        ctx, "assess_trade", direction="BUY", entry_price=1.0900, atr=0.0050
    )
    bot = EuroScopeBot.__new__(EuroScopeBot)
    formatted = EuroScopeBot._format_risk(bot, result.data)
    assert "Risk Assessment" in formatted


class TestAdaptiveRiskManagement:
    @pytest.mark.asyncio
    async def test_stop_beyond_liquidity_zone(self):
        skill = RiskManagementSkill()
        ctx = SkillContext()
        ctx.metadata["session_regime"] = "london"
        ctx.metadata["liquidity_zones"] = [{"price_level": 1.0900}]
        result = await skill.execute(
            ctx, "assess_trade", direction="BUY", entry_price=1.0950, atr=0.0010
        )
        assert result.success
        assert result.data["stop_loss"] <= 1.0900 - 0.0010

    @pytest.mark.asyncio
    async def test_reject_stop_inside_noise_band(self):
        skill = RiskManagementSkill()
        ctx = SkillContext()
        ctx.metadata["session_regime"] = "asian"
        result = await skill.execute(
            ctx, "assess_trade", direction="BUY", entry_price=1.0950, atr=0.0020
        )
        assert result.success
        assert ctx.metadata["risk_assessment"]["rejection_reason"] == "stop_inside_noise_band"

    def test_session_based_sizing(self):
        skill = RiskManagementSkill()
        sizing_asian = skill._calculate_dynamic_size(
            base_position_size=1.0,
            session_regime="asian",
            intent_confidence=0.9,
            base_risk_pct=1.0,
            recent_drawdown=0.0,
        )
        sizing_overlap = skill._calculate_dynamic_size(
            base_position_size=1.0,
            session_regime="overlap",
            intent_confidence=0.9,
            base_risk_pct=1.0,
            recent_drawdown=0.0,
        )
        assert sizing_asian["adjusted_risk_pct"] == 0.6
        assert sizing_overlap["adjusted_risk_pct"] == 1.2

    @pytest.mark.asyncio
    async def test_reject_high_drawdown(self):
        skill = RiskManagementSkill()
        skill.manager._daily_pnl = -600.0
        skill.manager._daily_pnl_date = datetime.now(UTC).strftime("%Y-%m-%d")
        ctx = SkillContext()
        ctx.metadata["session_regime"] = "london"
        ctx.metadata["market_intent"] = {"confidence": 0.9}
        result = await skill.execute(
            ctx, "assess_trade", direction="BUY", entry_price=1.0950, atr=0.0010
        )
        assert result.success
        assert ctx.metadata["risk_assessment"]["rejection_reason"] == "excessive_drawdown"

    def test_missing_context_defaults(self):
        skill = RiskManagementSkill()
        adaptive = skill._calculate_adaptive_stop(
            direction="BUY",
            entry_price=1.1000,
            atr=0.0010,
            liquidity_zones=[],
            session_regime="unknown",
        )
        sizing = skill._calculate_dynamic_size(
            base_position_size=1.0,
            session_regime="unknown",
            intent_confidence=None,
            base_risk_pct=1.0,
            recent_drawdown=0.0,
        )
        assert adaptive["buffer_pips"] == 15.0
        assert sizing["session_multiplier"] == 0.8
