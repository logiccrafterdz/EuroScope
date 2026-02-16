import pytest
from euroscope.analytics.backtest_engine import BacktestEngine

def test_backtest_simulation_costs():
    """Test that slippage and commissions are applied correctly."""
    engine = BacktestEngine()
    
    # Create a simple winning trade
    # Entry 1.0500, Exit 1.0600 (100 pips)
    # Costs: 0.5 slippage + 0.5 commission = 1.0 pip
    # Expected: 99.0 pips
    
    candles = [
        {"timestamp": "2024-01-01 00:00", "open": 1.0500, "high": 1.0510, "low": 1.0490, "close": 1.0500, "volume": 100},
        {"timestamp": "2024-01-01 01:00", "open": 1.0500, "high": 1.0610, "low": 1.0490, "close": 1.0600, "volume": 100},
    ]
    
    # Mock some data to ensure strategy triggers or just mock the trade
    # Actually, simpler to test _check_exit directly
    from euroscope.analytics.backtest_engine import BacktestTrade
    
    trade = BacktestTrade(direction="BUY", entry_price=1.0500, stop_loss=1.0400, take_profit=1.0600)
    
    # Test with costs
    closed = engine._check_exit(trade, high=1.0610, low=1.0500, bar_idx=1, slippage=0.5, commission=0.5)
    
    assert closed is not None
    assert closed.pnl_pips == 99.0 # (1.0600 - 1.0500) * 10000 - 1.0
    assert closed.is_win is True

def test_walk_forward_split():
    """Test that walk_forward_analysis splits data correctly."""
    engine = BacktestEngine()
    
    # 200 candles
    candles = [{"close": 1.0 + i/10000, "high": 1.0 + i/10000 + 0.0001, "low": 1.0 + i/10000 - 0.0001, "open": 1.0} for i in range(200)]
    
    # Window 100, Step 50
    # Expected windows: [0:100], [50:150], [100:200]
    results = engine.walk_forward_analysis(candles, strategy="trend_following", window_size=100, step_size=50)
    
    assert len(results) == 3
    assert results[0].bars_tested == 100
    assert results[1].bars_tested == 100
    assert results[2].bars_tested == 100

@pytest.mark.asyncio
async def test_backtesting_skill_integration():
    """Test that BacktestingSkill exposes the new capability."""
    from euroscope.skills.backtesting.skill import BacktestingSkill
    from euroscope.skills.base import SkillContext
    
    skill = BacktestingSkill()
    context = SkillContext()
    
    # 200 candles
    candles = [{"close": 1.0 + i/10000, "high": 1.0 + i/10000 + 0.0001, "low": 1.0 + i/10000 - 0.0001, "open": 1.0} for i in range(200)]
    
    result = await skill.execute(context, "walk_forward", candles=candles, strategy="trend_following", window_size=100, step_size=50)
    
    assert result.success is True
    assert len(result.data) == 3
    for res in result.data:
        assert "win_rate" in res
        assert "total_pnl" in res
