---
name: portfolio_context
description: >
  Tracks portfolio health, overall margin utilization, daily drawdown, and active
  directional exposure. Use this skill to evaluate whether the account has reached
  its daily loss limit and to assess total net exposure before taking new positions.
---

# 💼 Portfolio Context Skill

## What It Does
Acts as the overarching risk supervisor for the entire account. While `risk_management`
deals with per-trade sizing and stop losses, `portfolio_context` evaluates the holistic
health of the portfolio. It calculates the net long/short exposure across all active
trades and monitors cumulative daily PnL against the maximum allowable daily drawdown.

## When To Use
- During the OODA loop prior to execution to verify daily limits have not been breached.
- When generating reports to show current account exposure.
- By `trading_strategy` to know if we are over-exposed in one direction.

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `assess_health` | Evaluate daily drawdown and overall health | — | — |
| `get_exposure` | Calculate total net directional exposure | — | — |

## Integration Chain
```
trade_journal ──→ portfolio_context ──→ risk_management (adjust sizing)
                                      ↓
                                signal_executor (halt if drawdown breached)
```

## Edge Cases
- **Storage missing**: Cannot fetch daily PnL or active trades. Returns error.
- **Config missing**: Defaults to an internal hardcoded max daily drawdown (-50 pips).
