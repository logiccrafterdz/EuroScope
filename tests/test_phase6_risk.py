import pytest
from unittest.mock import patch
from euroscope.config import Config
from euroscope.skills.base import SkillContext
from euroscope.trading.safety_guardrails import SafetyGuardrail
from euroscope.skills.signal_executor.skill import SignalExecutorSkill, PaperTrade

@pytest.mark.asyncio
async def test_daily_drawdown_guard():
    config = Config()
    config.safety_max_daily_drawdown_pips = 50.0
    guard = SafetyGuardrail(config)
    
    with patch("euroscope.data.storage.Storage.get_trade_journal_for_date") as mock_get:
        # Mock storage to return a negative PnL for today that breaches the 50 pip limit
        mock_get.return_value = [{"pnl_pips": -20.0}, {"pnl_pips": -31.0}]
        
        ctx = SkillContext(signals={"direction": "BUY"})
        blocked, reason = await guard.should_block_signal(ctx)
        
        assert blocked is True
        assert "DAILY DRAWDOWN REACHED" in reason

@pytest.mark.asyncio
async def test_trailing_stop_update_trade():
    executor = SignalExecutorSkill()
    trade = PaperTrade(
        trade_id="PT-0001",
        direction="BUY",
        entry_price=1.0500,
        stop_loss=1.0450,
        take_profit=1.0600
    )
    executor._open.append(trade)
    
    ctx = SkillContext()
    ctx.open_positions.append(trade.__dict__)
    
    # Fire the update_trade action
    res = await executor.execute(ctx, "update_trade", trade_id="PT-0001", stop_loss=1.0550)
    
    assert res.success is True
    assert executor._open[0].stop_loss == 1.0550
    assert ctx.open_positions[0]["stop_loss"] == 1.0550
