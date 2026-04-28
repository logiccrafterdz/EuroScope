---
name: performance_analytics
description: >
  Computes real-time trading performance metrics including Sharpe ratio, Sortino
  ratio, max drawdown, win rate, profit factor, and expectancy. Provides breakdowns
  by strategy, session, and day-of-week. Use this skill when the user asks about
  trading performance, when generating daily/weekly reports, when comparing strategy
  effectiveness, or when the agent needs to assess whether the current approach is
  profitable. Also used by risk_management to check drawdown levels.
---

# 📊 Performance Analytics Skill

## What It Does
Transforms raw trade history into actionable performance intelligence.
Computes institutional-grade metrics that tell you not just whether you're
profitable, but WHY — which strategies work, which sessions perform best,
and whether risk-adjusted returns justify the trading approach.

## When To Use
- When the user asks "how am I doing?" or requests a performance report
- For daily/weekly automated briefings
- When comparing strategy effectiveness (trend vs mean reversion vs breakout)
- When risk_management needs current drawdown data
- For Telegram `/stats` or `/performance` commands

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `compute_metrics` | Calculate metrics from a trade list | `trades` (list) | — |
| `get_snapshot` | Full performance snapshot from storage | — | `period` ("all", "7d", "30d") |
| `breakdown` | Performance breakdown by dimension | `trades` (list) | `by` ("strategy" / "session" / "day") |
| `format_report` | Generate formatted Telegram report | `trades` (list) | — |

## Metrics Computed

| Metric | Formula | What It Tells You |
|--------|---------|-------------------|
| **Win Rate** | wins / total × 100 | Basic success percentage |
| **Total PnL** | Σ(pnl_pips) | Absolute profitability |
| **Sharpe Ratio** | mean(returns) / std(returns) × √252 | Risk-adjusted return (annualized) |
| **Sortino Ratio** | mean(returns) / downside_std × √252 | Downside risk-adjusted return |
| **Max Drawdown** | max peak-to-trough decline (pips) | Worst losing streak severity |
| **Profit Factor** | gross_profit / gross_loss | Reward per unit of risk |
| **Expectancy** | (win_rate × avg_win) - (loss_rate × avg_loss) | Expected pips per trade |

## Breakdown Dimensions

### By Strategy
Separates performance by `trend_following`, `mean_reversion`, `breakout`
to identify which strategies are working in current market conditions.

### By Session
Shows performance by `asian`, `london`, `overlap`, `newyork` to identify
optimal trading hours.

### By Day of Week
Performance by Monday-Friday to detect day-of-week patterns.

## Edge Cases & Degraded Modes
- **No storage configured**: Returns `success=False`. Cannot compute without trade data.
- **Empty trade list**: Returns zero metrics. Not an error — just no data yet.
- **Division by zero**: Handled internally (Sharpe=0 when std=0, PF=0 when no losses).

## Integration Chain
```
trade_journal ──→ performance_analytics ──→ briefing (formatted report)
signal_executor ─┘                              ↓
                                         risk_management (drawdown check)
```

## Runtime Dependencies
- `PerformanceAnalytics` engine — internal computation
- `Storage` — for `get_snapshot` action (reads from DB)
