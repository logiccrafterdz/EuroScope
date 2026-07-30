"""
Test Suite 3: Trading Layer — RiskManager, ExecutionSimulator
Tests: Position sizing, SL/TP calculation, drawdown, execution simulation
"""

import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

RESULTS = []

def log(test_name, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    RESULTS.append((test_name, status, detail))
    print(f"  {icon} {test_name}" + (f" — {detail}" if detail else ""))


async def test_risk_manager_default_config():
    """Test 1: RiskManager default config creation"""
    from euroscope.trading.risk_manager import RiskManager, RiskConfig
    rm = RiskManager()
    cfg = rm.config
    checks = []
    if cfg.account_balance == 10000.0: checks.append("balance=10000")
    if cfg.risk_per_trade == 1.0: checks.append("risk=1%")
    if cfg.max_daily_drawdown == 3.0: checks.append("dd=3%")
    if cfg.max_open_trades == 3: checks.append("max_trades=3")
    if cfg.default_rr_ratio == 2.0: checks.append("rr=2.0")
    if len(checks) == 5:
        log("RiskManager default config", "PASS", ", ".join(checks))
    else:
        log("RiskManager default config", "FAIL", f"only {len(checks)}/5 defaults correct")


async def test_risk_manager_position_sizing_30pip():
    """Test 2: RiskManager position sizing with 30 pip stop"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    lots = rm.calculate_position_size(stop_pips=30)
    expected = round(10000 * 0.01 / (30 * 10), 2)  # 100 / 300 = 0.33
    if lots == expected:
        log("Position sizing (30 pip)", "PASS", f"lots={lots} (expected {expected})")
    else:
        log("Position sizing (30 pip)", "FAIL", f"lots={lots} (expected {expected})")


async def test_risk_manager_position_sizing_10pip():
    """Test 3: RiskManager position sizing with 10 pip stop"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    lots = rm.calculate_position_size(stop_pips=10)
    expected = round(10000 * 0.01 / (10 * 10), 2)  # 100 / 100 = 1.0
    if lots == expected:
        log("Position sizing (10 pip)", "PASS", f"lots={lots} (expected {expected})")
    else:
        log("Position sizing (10 pip)", "FAIL", f"lots={lots} (expected {expected})")


async def test_risk_manager_atr_stop_buy():
    """Test 4: RiskManager ATR stop calculation (BUY)"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    sl = rm.calculate_atr_stop(atr=0.005, direction="BUY", entry_price=1.08500)
    expected = round(1.08500 - 0.005 * 1.5, 5)
    if sl == expected:
        log("ATR stop (BUY)", "PASS", f"sl={sl} (expected {expected})")
    else:
        log("ATR stop (BUY)", "FAIL", f"sl={sl} (expected {expected})")


async def test_risk_manager_atr_stop_sell():
    """Test 5: RiskManager ATR stop calculation (SELL)"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    sl = rm.calculate_atr_stop(atr=0.005, direction="SELL", entry_price=1.08500)
    expected = round(1.08500 + 0.005 * 1.5, 5)
    if sl == expected:
        log("ATR stop (SELL)", "PASS", f"sl={sl} (expected {expected})")
    else:
        log("ATR stop (SELL)", "FAIL", f"sl={sl} (expected {expected})")


async def test_risk_manager_take_profit_buy():
    """Test 6: RiskManager take profit calculation (BUY)"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    entry = 1.08500
    sl = 1.07750
    tp = rm.calculate_take_profit(entry, sl, "BUY")
    risk_distance = abs(entry - sl)
    expected = round(entry + risk_distance * 2.0, 5)
    if tp == expected:
        log("Take profit (BUY)", "PASS", f"tp={tp} (expected {expected})")
    else:
        log("Take profit (BUY)", "FAIL", f"tp={tp} (expected {expected})")


async def test_risk_manager_take_profit_sell():
    """Test 7: RiskManager take profit calculation (SELL)"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    entry = 1.08500
    sl = 1.09250
    tp = rm.calculate_take_profit(entry, sl, "SELL")
    risk_distance = abs(entry - sl)
    expected = round(entry - risk_distance * 2.0, 5)
    if tp == expected:
        log("Take profit (SELL)", "PASS", f"tp={tp} (expected {expected})")
    else:
        log("Take profit (SELL)", "FAIL", f"tp={tp} (expected {expected})")


async def test_risk_manager_full_assessment_buy():
    """Test 8: RiskManager full trade assessment (BUY with ATR)"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    risk = rm.assess_trade("BUY", 1.08500, atr=0.005)
    checks = []
    if risk.direction == "BUY": checks.append("dir=BUY")
    if risk.entry_price == 1.08500: checks.append("entry=1.08500")
    if risk.stop_loss < risk.entry_price: checks.append("sl<entry")
    if risk.take_profit > risk.entry_price: checks.append("tp>entry")
    if risk.position_size > 0: checks.append(f"size={risk.position_size}")
    if risk.risk_score >= 1 and risk.risk_score <= 10: checks.append(f"score={risk.risk_score}")
    if len(checks) == 6:
        log("Full assessment (BUY ATR)", "PASS", ", ".join(checks))
    else:
        log("Full assessment (BUY ATR)", "FAIL", f"only {len(checks)}/6 checks passed: {checks}")


async def test_risk_manager_full_assessment_sell():
    """Test 9: RiskManager full trade assessment (SELL with ATR)"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    risk = rm.assess_trade("SELL", 1.08500, atr=0.005)
    checks = []
    if risk.direction == "SELL": checks.append("dir=SELL")
    if risk.entry_price == 1.08500: checks.append("entry=1.08500")
    if risk.stop_loss > risk.entry_price: checks.append("sl>entry")
    if risk.take_profit < risk.entry_price: checks.append("tp<entry")
    if risk.position_size > 0: checks.append(f"size={risk.position_size}")
    if len(checks) == 5:
        log("Full assessment (SELL ATR)", "PASS", ", ".join(checks))
    else:
        log("Full assessment (SELL ATR)", "FAIL", f"only {len(checks)}/5 checks passed: {checks}")


async def test_risk_manager_drawdown_tracking():
    """Test 10: RiskManager drawdown tracking updates daily PnL"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    await rm.record_trade_result(50.0)
    if rm._daily_pnl == 50.0:
        log("Drawdown tracking", "PASS", f"daily_pnl={rm._daily_pnl}")
    else:
        log("Drawdown tracking", "FAIL", f"daily_pnl={rm._daily_pnl} (expected 50.0)")
    await rm.record_trade_result(-30.0)
    if rm._daily_pnl == 20.0:
        log("Drawdown tracking (cumulative)", "PASS", f"daily_pnl={rm._daily_pnl}")
    else:
        log("Drawdown tracking (cumulative)", "FAIL", f"daily_pnl={rm._daily_pnl} (expected 20.0)")


async def test_risk_manager_consecutive_losses():
    """Test 11: RiskManager consecutive losses tracking"""
    from euroscope.trading.risk_manager import RiskManager
    rm = RiskManager()
    await rm.record_trade_result(-10.0)
    await rm.record_trade_result(-20.0)
    await rm.record_trade_result(-5.0)
    if rm._consecutive_losses == 3:
        log("Consecutive losses", "PASS", f"streak={rm._consecutive_losses}")
    else:
        log("Consecutive losses", "FAIL", f"streak={rm._consecutive_losses} (expected 3)")
    await rm.record_trade_result(10.0)
    if rm._consecutive_losses == 0:
        log("Consecutive losses reset", "PASS", f"streak={rm._consecutive_losses}")
    else:
        log("Consecutive losses reset", "FAIL", f"streak={rm._consecutive_losses} (expected 0)")


async def test_execution_simulator_entry_buy():
    """Test 12: ExecutionSimulator entry simulation (BUY)"""
    from euroscope.trading.execution_simulator import ExecutionSimulator
    sim = ExecutionSimulator()
    result = sim.simulate_entry("BUY", 1.08500)
    if result.filled and result.fill_price > 1.08500:
        log("Execution entry (BUY)", "PASS", f"fill={result.fill_price} > entry=1.08500, cost={result.total_cost_pips}p")
    else:
        log("Execution entry (BUY)", "FAIL", f"filled={result.filled}, fill={result.fill_price}")


async def test_execution_simulator_entry_sell():
    """Test 13: ExecutionSimulator entry simulation (SELL)"""
    from euroscope.trading.execution_simulator import ExecutionSimulator
    sim = ExecutionSimulator()
    result = sim.simulate_entry("SELL", 1.08500)
    if result.filled and result.fill_price < 1.08500:
        log("Execution entry (SELL)", "PASS", f"fill={result.fill_price} < entry=1.08500, cost={result.total_cost_pips}p")
    else:
        log("Execution entry (SELL)", "FAIL", f"filled={result.filled}, fill={result.fill_price}")


async def test_execution_simulator_exit_slippage():
    """Test 14: ExecutionSimulator exit simulation (stop_loss vs take_profit slippage)"""
    from euroscope.trading.execution_simulator import ExecutionSimulator
    sim = ExecutionSimulator()
    sl_result = sim.simulate_exit("BUY", 1.08500, "stop_loss")
    sim2 = ExecutionSimulator()
    tp_result = sim2.simulate_exit("BUY", 1.08500, "take_profit")
    if sl_result.total_cost_pips >= tp_result.total_cost_pips:
        log("Exit slippage (SL >= TP)", "PASS", f"SL cost={sl_result.total_cost_pips}, TP cost={tp_result.total_cost_pips}")
    else:
        log("Exit slippage (SL >= TP)", "WARN", f"SL cost={sl_result.total_cost_pips} < TP cost={tp_result.total_cost_pips} (unusual)")


async def test_execution_simulator_disabled():
    """Test 15: ExecutionSimulator disabled mode returns exact price"""
    from euroscope.trading.execution_simulator import ExecutionSimulator, ExecutionConfig
    config = ExecutionConfig(enabled=False)
    sim = ExecutionSimulator(config)
    result = sim.simulate_entry("BUY", 1.08500)
    if result.filled and result.fill_price == 1.08500 and result.total_cost_pips == 0:
        log("Execution disabled mode", "PASS", f"fill={result.fill_price} == exact, cost=0")
    else:
        log("Execution disabled mode", "FAIL", f"fill={result.fill_price}, cost={result.total_cost_pips}")


async def test_trading_simulator_defaults():
    """Test 16: TradingSimulator default construction"""
    from euroscope.simulation.trading_simulator import TradingSimulator
    sim = TradingSimulator()
    checks = []
    if sim.initial_balance == 100000.0: checks.append("balance=100k")
    if sim.current_balance == 100000.0: checks.append("current=100k")
    if len(sim.open_trades) == 0: checks.append("open=0")
    if len(sim.closed_trades) == 0: checks.append("closed=0")
    if not sim.is_running: checks.append("not_running")
    if not sim.is_bankrupt: checks.append("not_bankrupt")
    if len(checks) == 6:
        log("TradingSimulator defaults", "PASS", ", ".join(checks))
    else:
        log("TradingSimulator defaults", "FAIL", f"only {len(checks)}/6 checks")


async def test_trading_simulator_open_trade_buy():
    """Test 17: TradingSimulator open BUY trade"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    trade = sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=10000)
    checks = []
    if trade.id == 1: checks.append("id=1")
    if trade.direction == TradeDirection.BUY: checks.append("direction=BUY")
    if trade.entry_price == 1.08500: checks.append("entry=1.08500")
    if trade.stop_loss == 1.08300: checks.append("sl=1.08300")
    if trade.take_profit == 1.08900: checks.append("tp=1.08900")
    if trade.units == 10000: checks.append("units=10000")
    if trade.status.name == "OPEN": checks.append("status=OPEN")
    if len(sim.open_trades) == 1: checks.append("in_open_trades")
    if len(checks) == 8:
        log("Open BUY trade", "PASS", ", ".join(checks))
    else:
        log("Open BUY trade", "FAIL", f"only {len(checks)}/8 checks")


async def test_trading_simulator_open_trade_sell():
    """Test 18: TradingSimulator open SELL trade"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    trade = sim.open_trade(TradeDirection.SELL, 1.08500, 1.08700, 1.08100, units=5000)
    checks = []
    if trade.direction == TradeDirection.SELL: checks.append("direction=SELL")
    if trade.entry_price == 1.08500: checks.append("entry=1.08500")
    if trade.stop_loss == 1.08700: checks.append("sl=1.08700 > entry")
    if trade.take_profit == 1.08100: checks.append("tp=1.08100 < entry")
    if trade.units == 5000: checks.append("units=5000")
    if len(checks) == 5:
        log("Open SELL trade", "PASS", ", ".join(checks))
    else:
        log("Open SELL trade", "FAIL", f"only {len(checks)}/5 checks")


async def test_trading_simulator_validation():
    """Test 19: TradingSimulator input validation"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    passed = 0
    try:
        sim.open_trade("INVALID", 1.08500, 1.08300, 1.08900)
    except ValueError:
        passed += 1
    try:
        sim.open_trade(TradeDirection.BUY, -1.0, 1.08300, 1.08900)
    except ValueError:
        passed += 1
    try:
        sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=0)
    except ValueError:
        passed += 1
    try:
        sim.open_trade(TradeDirection.BUY, 1.08500, 1.08600, 1.08900)  # SL > entry
    except ValueError:
        passed += 1
    try:
        sim.open_trade(TradeDirection.SELL, 1.08500, 1.08400, 1.08900)  # SL < entry for SELL
    except ValueError:
        passed += 1
    if passed == 5:
        log("Input validation", "PASS", f"5/5 invalid inputs rejected")
    else:
        log("Input validation", "FAIL", f"only {passed}/5 rejected")


async def test_trading_simulator_sl_buy():
    """Test 20: TradingSimulator stop-loss triggered (BUY)"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=10000)
    sim.update_trades(1.08250)
    checks = []
    if len(sim.open_trades) == 0: checks.append("open_trades=0")
    if len(sim.closed_trades) == 1: checks.append("closed_trades=1")
    if sim.closed_trades[0].status.name == "CLOSED_LOSS": checks.append("status=CLOSED_LOSS")
    if sim.current_balance < sim.initial_balance: checks.append("balance_decreased")
    if len(checks) == 4:
        log("SL trigger (BUY)", "PASS", ", ".join(checks))
    else:
        log("SL trigger (BUY)", "FAIL", f"only {len(checks)}/4 checks")


async def test_trading_simulator_tp_buy():
    """Test 21: TradingSimulator take-profit triggered (BUY)"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=10000)
    sim.update_trades(1.09000)
    checks = []
    if len(sim.closed_trades) == 1: checks.append("closed_trades=1")
    if sim.closed_trades[0].status.name == "CLOSED_WIN": checks.append("status=CLOSED_WIN")
    if sim.current_balance > sim.initial_balance: checks.append("balance_increased")
    if len(checks) == 3:
        log("TP trigger (BUY)", "PASS", ", ".join(checks))
    else:
        log("TP trigger (BUY)", "FAIL", f"only {len(checks)}/3 checks")


async def test_trading_simulator_sl_sell():
    """Test 22: TradingSimulator stop-loss triggered (SELL)"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    sim.open_trade(TradeDirection.SELL, 1.08500, 1.08700, 1.08100, units=10000)
    sim.update_trades(1.08800)
    checks = []
    if len(sim.closed_trades) == 1: checks.append("closed=1")
    if sim.closed_trades[0].status.name == "CLOSED_LOSS": checks.append("status=CLOSED_LOSS")
    if sim.current_balance < sim.initial_balance: checks.append("balance_decreased")
    if len(checks) == 3:
        log("SL trigger (SELL)", "PASS", ", ".join(checks))
    else:
        log("SL trigger (SELL)", "FAIL", f"only {len(checks)}/3 checks")


async def test_trading_simulator_tp_sell():
    """Test 23: TradingSimulator take-profit triggered (SELL)"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    sim.open_trade(TradeDirection.SELL, 1.08500, 1.08700, 1.08100, units=10000)
    sim.update_trades(1.08000)
    checks = []
    if len(sim.closed_trades) == 1: checks.append("closed=1")
    if sim.closed_trades[0].status.name == "CLOSED_WIN": checks.append("status=CLOSED_WIN")
    if sim.current_balance > sim.initial_balance: checks.append("balance_increased")
    if len(checks) == 3:
        log("TP trigger (SELL)", "PASS", ", ".join(checks))
    else:
        log("TP trigger (SELL)", "FAIL", f"only {len(checks)}/3 checks")


async def test_trading_simulator_get_status():
    """Test 24: TradingSimulator get_status output"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator(initial_balance=50000.0)
    status = sim.get_status()
    checks = []
    if status["balance"] == 50000.0: checks.append("balance=50000")
    if status["initial_balance"] == 50000.0: checks.append("init=50000")
    if status["open_trades"] == 0: checks.append("open=0")
    if status["closed_trades"] == 0: checks.append("closed=0")
    if status["win_rate"] == 0: checks.append("win_rate=0")
    if status["is_bankrupt"] is False: checks.append("not_bankrupt")
    if "trades" in status and len(status["trades"]) == 0: checks.append("trades=[]")
    if len(checks) == 7:
        log("get_status (empty)", "PASS", ", ".join(checks))
    else:
        log("get_status (empty)", "FAIL", f"only {len(checks)}/7 checks")

    sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=10000)
    sim.update_trades(1.09000)
    status = sim.get_status()
    checks = []
    if status["open_trades"] == 0: checks.append("open=0")
    if status["closed_trades"] == 1: checks.append("closed=1")
    if status["winning_trades"] == 1: checks.append("wins=1")
    if status["total_pnl"] > 0: checks.append("pnl>0")
    if len(status["trades"]) == 1: checks.append("trades=1")
    if len(checks) == 5:
        log("get_status (after trade)", "PASS", ", ".join(checks))
    else:
        log("get_status (after trade)", "FAIL", f"only {len(checks)}/5 checks")


async def test_trading_simulator_execution_integration():
    """Test 25: TradingSimulator with ExecutionSimulator costs"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    from euroscope.trading.execution_simulator import ExecutionSimulator
    sim = TradingSimulator(
        initial_balance=100000.0,
        execution_simulator=ExecutionSimulator()
    )
    sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=10000)
    sim.update_trades(1.08250)
    closed = sim.closed_trades[0]
    checks = []
    if closed.entry_cost_pips > 0: checks.append(f"entry_cost={closed.entry_cost_pips:.1f}")
    if closed.exit_cost_pips > 0: checks.append(f"exit_cost={closed.exit_cost_pips:.1f}")
    if closed.entry_cost_pips + closed.exit_cost_pips > 0: checks.append("total_cost>0")
    if closed.pnl < 0: checks.append("pnl_negative")
    if len(checks) == 4:
        log("ExecutionSim integration", "PASS", ", ".join(checks))
    else:
        log("ExecutionSim integration", "FAIL", f"only {len(checks)}/4 checks: {checks}")


async def test_trading_simulator_bankruptcy():
    """Test 26: TradingSimulator bankruptcy protection"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    cb_balance = []
    def on_bankruptcy(bal):
        cb_balance.append(bal)

    sim = TradingSimulator(initial_balance=100.0, minimum_balance=0.0)
    sim.on_bankruptcy = on_bankruptcy
    sim.open_trade(TradeDirection.BUY, 1.08500, 1.08000, 1.09000, units=50000)
    sim.update_trades(1.07900)
    checks = []
    if sim.is_bankrupt: checks.append("is_bankrupt")
    if not sim.is_running: checks.append("stopped")
    if sim.current_balance <= 0: checks.append("balance_depleted")
    if len(cb_balance) == 1: checks.append("callback_fired")
    try:
        sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900)
    except RuntimeError:
        checks.append("new_trades_blocked")
    if len(checks) == 5:
        log("Bankruptcy protection", "PASS", ", ".join(checks))
    else:
        log("Bankruptcy protection", "FAIL", f"only {len(checks)}/5 checks: {checks}")


async def test_trading_simulator_multiple_trades():
    """Test 27: TradingSimulator handles multiple concurrent trades"""
    from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection
    sim = TradingSimulator()
    sim.open_trade(TradeDirection.BUY, 1.08500, 1.08300, 1.08900, units=10000)
    sim.open_trade(TradeDirection.SELL, 1.08500, 1.08700, 1.08100, units=5000)
    checks = []
    if len(sim.open_trades) == 2: checks.append("open=2")
    if sim.open_trades[0].direction == TradeDirection.BUY: checks.append("trade0=BUY")
    if sim.open_trades[1].direction == TradeDirection.SELL: checks.append("trade1=SELL")

    # Only BUY hits SL, SELL stays open
    sim.update_trades(1.08250)
    if len(sim.open_trades) == 1: checks.append("open_after=1")
    if len(sim.closed_trades) == 1: checks.append("closed=1")
    if sim.closed_trades[0].direction == TradeDirection.BUY: checks.append("closed_is_BUY")
    if sim.open_trades[0].direction == TradeDirection.SELL: checks.append("remaining_is_SELL")
    if len(checks) == 7:
        log("Multiple concurrent trades", "PASS", ", ".join(checks))
    else:
        log("Multiple concurrent trades", "FAIL", f"only {len(checks)}/7 checks: {checks}")


async def main():
    print("\n" + "="*60)
    print("  SUITE 3: TRADING LAYER TESTS")
    print("="*60)

    tests = [
        test_risk_manager_default_config,
        test_risk_manager_position_sizing_30pip,
        test_risk_manager_position_sizing_10pip,
        test_risk_manager_atr_stop_buy,
        test_risk_manager_atr_stop_sell,
        test_risk_manager_take_profit_buy,
        test_risk_manager_take_profit_sell,
        test_risk_manager_full_assessment_buy,
        test_risk_manager_full_assessment_sell,
        test_risk_manager_drawdown_tracking,
        test_risk_manager_consecutive_losses,
        test_execution_simulator_entry_buy,
        test_execution_simulator_entry_sell,
        test_execution_simulator_exit_slippage,
        test_execution_simulator_disabled,
        test_trading_simulator_defaults,
        test_trading_simulator_open_trade_buy,
        test_trading_simulator_open_trade_sell,
        test_trading_simulator_validation,
        test_trading_simulator_sl_buy,
        test_trading_simulator_tp_buy,
        test_trading_simulator_sl_sell,
        test_trading_simulator_tp_sell,
        test_trading_simulator_get_status,
        test_trading_simulator_execution_integration,
        test_trading_simulator_bankruptcy,
        test_trading_simulator_multiple_trades,
    ]

    for test_fn in tests:
        await test_fn()

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for _, s, _ in RESULTS if s == "WARN")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    total = len(RESULTS)

    print(f"\n{'─'*60}")
    print(f"  RESULTS: {passed}✅ {failed}❌ {warned}⚠️ {skipped}⏭️ / {total} total")
    print(f"{'─'*60}\n")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
