import pytest
import tempfile
import asyncio
from unittest.mock import AsyncMock

from euroscope.trading.strategy_engine import StrategyEngine
from euroscope.trading.risk_manager import RiskManager, RiskConfig
from euroscope.trading.signal_executor import SignalExecutor
from euroscope.trading.execution_simulator import ExecutionSimulator, ExecutionConfig
from euroscope.data.storage import Storage

@pytest.fixture
def components(tmp_path):
    """Fixture providing all core trading components."""
    db_path = str(tmp_path / "test_lifecycle.db")
    storage = Storage(db_path)
    
    engine = StrategyEngine()
    risk_manager = RiskManager(RiskConfig(account_balance=10000, risk_per_trade=2.0))
    
    # Disable actual paper trading simulation thread to keep test fast and deterministic
    sim = ExecutionSimulator(config=ExecutionConfig(enabled=False))
    executor = SignalExecutor(storage, execution_sim=sim)
    
    return engine, risk_manager, executor, storage


class TestTradingLifecycle:
    """Integrated tests for the Strategy -> Risk -> Execution critical path (L-6)."""

    @pytest.mark.asyncio
    async def test_successful_buy_lifecycle(self, components):
        engine, risk_manager, executor, storage = components

        # 1. Market Context (Bullish Trend)
        indicators = {
            "adx": 35, "rsi": 55, "overall_bias": "bullish",
            "macd": {"histogram_latest": 0.002},
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        
        # 2. Strategy Engine detects signal
        signal = engine.detect_strategy(indicators, levels)
        assert signal.direction == "BUY"
        assert signal.strategy == "trend_following"
        
        # 3. Risk Manager assesses the trade based on signal
        trade_risk = risk_manager.assess_trade(
            direction=signal.direction,
            entry_price=levels["current_price"],
            atr=0.0050
        )
        assert trade_risk.approved is True
        assert trade_risk.stop_loss < levels["current_price"]
        assert trade_risk.take_profit > levels["current_price"]
        assert trade_risk.position_size > 0

        # 4. Executor opens the trade
        sig_id = await executor.open_signal(
            direction=trade_risk.direction,
            entry_price=trade_risk.entry_price,
            stop_loss=trade_risk.stop_loss,
            take_profit=trade_risk.take_profit,
            strategy=signal.strategy,
            timeframe="H1",
            confidence=signal.confidence,
            reasoning=signal.reasoning,
            atr=0.0050
        )
        assert sig_id > 0
        
        # Verify it was stored correctly
        open_signals = await executor.get_open_signals()
        assert len(open_signals) == 1
        assert open_signals[0]["direction"] == "BUY"
        assert open_signals[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_risk_manager_blocks_trade(self, components):
        engine, risk_manager, executor, storage = components
        
        # Give risk manager an artificial massive drawdown to trigger a rejection
        risk_manager._daily_pnl = -500.0  # -5% of 10000 
        import datetime
        risk_manager._daily_pnl_date = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

        indicators = {
            "adx": 40, "rsi": 30, "overall_bias": "bearish",
            "macd": {"histogram_latest": -0.005},
        }
        levels = {"current_price": 1.0850, "support": [1.0800], "resistance": [1.0900]}
        
        signal = engine.detect_strategy(indicators, levels)
        assert signal.direction == "SELL"

        trade_risk = risk_manager.assess_trade(
            direction=signal.direction,
            entry_price=levels["current_price"],
            atr=0.0050
        )
        # Risk Manager must block it due to drawdown
        assert trade_risk.approved is False
        assert any("drawdown" in w.lower() for w in trade_risk.warnings)
        
        # If integration script checks `approved`, execution never happens
        open_signals = await executor.get_open_signals()
        assert len(open_signals) == 0

    @pytest.mark.asyncio
    async def test_sideways_market_yields_no_trade(self, components):
        engine, risk_manager, executor, storage = components

        # 1. Market Context (Ranging / No clear trend)
        indicators = {
            "adx": 15, "rsi": 50, "overall_bias": "neutral",
            "macd": {"histogram_latest": 0.000},
        }
        levels = {"current_price": 1.0900}
        
        # 2. Strategy Engine detects signal
        signal = engine.detect_strategy(indicators, levels)
        
        # Should be WAIT
        assert signal.direction == "WAIT"
        
        # Execution flow would stop here, ensuring no junk trades
        assert len(await executor.get_open_signals()) == 0
