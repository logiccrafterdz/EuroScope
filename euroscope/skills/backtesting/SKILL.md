---
name: backtesting
description: Historical strategy replay and performance measurement
---

# 🔬 Backtesting Skill

## What It Does
Replays historical candle data through StrategyEngine + RiskManager to simulate trades and measure strategy performance.

## Actions
- `run` — Run backtest on historical candles (optionally filtered by strategy)
- `compare` — Compare multiple strategies on the same data set
- `format_result` — Format backtest result for Telegram display

## Returns
- total_trades, wins, losses, win_rate
- total_pnl, avg_pnl, profit_factor
- sharpe_ratio, max_drawdown
- equity_curve, trade list
