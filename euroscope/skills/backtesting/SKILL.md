---
name: backtesting
description: Historical strategy replay and performance measurement
---

# 🔬 Backtesting Skill

## What It Does
Replays historical candle data through StrategyEngine + RiskManager to simulate trades and measure strategy performance.

## Actions
- `run` — Run backtest with realistic simulation (slippage, commission)
- `compare` — Compare multiple strategies with realistic costs
- `walk_forward` — Perform Walk-Forward analysis on sliding windows
- `format_result` — Format backtest result for Telegram display

## Parameters
- `slippage` — Expected slippage in pips (default: 0.5)
- `commission` — Expected commission in pips (default: 0.7)
- `window_size` — Sliding window size for Walk-Forward (default: 500)
- `step_size` — Step size for Walk-Forward (default: 100)

## Returns
- total_trades, wins, losses, win_rate
- total_pnl, avg_pnl, profit_factor
- sharpe_ratio, max_drawdown
- equity_curve, trade list
