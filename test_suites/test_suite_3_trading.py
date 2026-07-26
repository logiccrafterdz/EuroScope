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
