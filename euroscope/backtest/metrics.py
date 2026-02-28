"""
Backtest Metrics

Calculates institutional-grade performance metrics from a list of simulated
offline positions, applying realistic degradation via ExecutionSimulator data.
"""

from typing import List
import numpy as np

from .offline_executor import OfflinePosition

class BacktestMetrics:
    def __init__(self, initial_balance: float, positions: List[OfflinePosition]):
        self.initial_balance = initial_balance
        self.positions = sorted(positions, key=lambda p: p.close_time) if positions else []
        
    def generate_tear_sheet(self) -> str:
        """Generate a formatted performance summary."""
        if not self.positions:
            return "No trades executed during backtest period."
            
        total_trades = len(self.positions)
        winning_trades = [p for p in self.positions if p.pnl_pips > 0]
        losing_trades = [p for p in self.positions if p.pnl_pips <= 0]
        
        win_rate = len(winning_trades) / total_trades * 100
        
        # PnL calculations
        # Rough proxy: pip_value = 10 USD per standard lot
        pip_value = 10.0
        
        gross_profit = sum(p.pnl_pips * p.size * pip_value for p in winning_trades)
        gross_loss = sum(abs(p.pnl_pips) * p.size * pip_value for p in losing_trades)
        net_profit = gross_profit - gross_loss
        
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        final_balance = self.initial_balance + net_profit
        return_pct = (net_profit / self.initial_balance) * 100
        
        # Drawdown calculation
        equity_curve = [self.initial_balance]
        current_equity = self.initial_balance
        for p in self.positions:
            current_equity += p.pnl_pips * p.size * pip_value
            equity_curve.append(current_equity)
            
        peak = self.initial_balance
        max_dd_pct = 0.0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd_pct:
                max_dd_pct = dd
                
        # Execution Cost Drag
        total_slippage_pips = sum(p.exit_result.slippage_pips + p.entry_result.slippage_pips for p in self.positions if p.exit_result)
        total_spread_pips = sum(p.exit_result.spread_cost_pips + p.entry_result.spread_cost_pips for p in self.positions if p.exit_result)
        
        execution_drag_usd = (total_slippage_pips + total_spread_pips) * (sum(p.size for p in self.positions) / len(self.positions) if self.positions else 0) * pip_value
        
        lines = [
            "===========================================================",
            "        EUROSCOPE BACKTEST TEAR SHEET (OFFLINE)            ",
            "===========================================================",
            f"Total Trades:        {total_trades}",
            f"Win Rate:            {win_rate:.1f}%",
            f"Net Profit:          ${net_profit:.2f} ({return_pct:.2f}%)",
            f"Profit Factor:       {profit_factor:.2f}",
            f"Max Drawdown:        {max_dd_pct:.2f}%",
            "-----------------------------------------------------------",
            "EXECUTION DEGRADATION ANALYSIS",
            f"Avg Slippage Drop:   {total_slippage_pips/total_trades:.2f} pips/trade",
            f"Avg Spread Cost:     {total_spread_pips/total_trades:.2f} pips/trade",
            f"Est. Friction Drag:  ${execution_drag_usd:.2f} (embedded in net profit)",
            "==========================================================="
        ]
        
        return "\n".join(lines)
