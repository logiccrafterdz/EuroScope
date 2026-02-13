---
name: signal_executor
description: Converts signals to paper trade orders with tracking
---

# ⚡ Signal Executor Skill

## What It Does
Takes trading signals and converts them to virtual (paper) or real orders. Tracks open/closed positions.

## Actions
- `open_trade` — Open a new paper trade from a signal
- `close_trade` — Close an existing trade at current price
- `list_trades` — List all open positions
- `trade_history` — Closed trade history
