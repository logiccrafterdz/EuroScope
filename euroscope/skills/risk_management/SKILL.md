---
name: risk_management
description: Position sizing, stop loss, take profit, and drawdown control
---

# 🛡️ Risk Management Skill

## What It Does
Calculates optimal position sizes, stop-loss/take-profit levels, and performs trade risk assessments.

## Actions
- `assess_trade` — Full risk assessment for a proposed trade
- `position_size` — Calculate position size based on risk tolerance
- `stop_loss` — Calculate stop loss (ATR-based or level-based)
- `take_profit` — Calculate take profit from risk-reward ratio

## Parameters
| Action | Param | Type | Description |
|--------|-------|------|-------------|
| assess_trade | direction | str | "BUY" or "SELL" |
| assess_trade | entry_price | float | Proposed entry price |
| assess_trade | atr | float | Current ATR value |
| position_size | balance | float | Account balance |
| position_size | risk_pct | float | Risk per trade (0.01 = 1%) |
