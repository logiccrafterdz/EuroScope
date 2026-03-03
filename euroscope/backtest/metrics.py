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
        
        # Risk-Adjusted Metrics
        # Assuming returns are calculated per trade for simplicity (in a real scenario, this would be daily/monthly returns)
        trade_returns_pct = [(p.pnl_pips * p.size * pip_value) / self.initial_balance * 100 for p in self.positions]
        
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
        
        if len(trade_returns_pct) > 1:
            mean_return = np.mean(trade_returns_pct)
            std_dev = np.std(trade_returns_pct)
            
            # Annualization factor approximation (assuming ~252 trades/year for daily trading)
            # In a real system, this should be time-based. We'll use a fixed multiplier for demonstration.
            ann_factor = np.sqrt(252) 
            
            if std_dev > 0:
                sharpe_ratio = (mean_return / std_dev) * ann_factor
                
            downside_returns = [r for r in trade_returns_pct if r < 0]
            if downside_returns:
                downside_std_dev = np.std(downside_returns)
                if downside_std_dev > 0:
                    sortino_ratio = (mean_return / downside_std_dev) * ann_factor
                    
        if max_dd_pct > 0:
            # Assuming return_pct is total return, annualized for Calmar would be needed. 
            # Using total return for simplicity in this tear sheet context.
            calmar_ratio = return_pct / max_dd_pct
            
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
            "RISK-ADJUSTED METRICS",
            f"Sharpe Ratio:        {sharpe_ratio:.2f}",
            f"Sortino Ratio:       {sortino_ratio:.2f}",
            f"Calmar Ratio:        {calmar_ratio:.2f}",
            "-----------------------------------------------------------",
            "EXECUTION DEGRADATION ANALYSIS",
            f"Avg Slippage Drop:   {total_slippage_pips/total_trades:.2f} pips/trade",
            f"Avg Spread Cost:     {total_spread_pips/total_trades:.2f} pips/trade",
            f"Est. Friction Drag:  ${execution_drag_usd:.2f} (embedded in net profit)",
            "==========================================================="
        ]
        
        return "\n".join(lines)
