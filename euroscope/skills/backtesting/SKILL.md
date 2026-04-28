---
name: backtesting
description: >
  Replays trading strategies against historical price data with realistic
  execution simulation (slippage, commission). Supports single-strategy runs,
  multi-strategy comparison, and walk-forward analysis. Use this skill when
  the user asks to backtest a strategy, when comparing strategy performance
  over historical data, when validating a new strategy before live deployment,
  or when the agent needs evidence-based strategy selection. Can auto-fetch
  historical candles from the price provider if none are supplied.
---

# 🔬 Backtesting Skill

## What It Does
The scientific testing lab for trading strategies. Takes historical OHLCV
candle data and replays each strategy against it, simulating realistic
execution with configurable slippage and commission costs. Produces
institutional-grade performance metrics for each strategy.

Supports three modes of operation:
1. **Single strategy run** — Test one strategy in isolation
2. **Multi-strategy comparison** — Compare all strategies side-by-side
3. **Walk-forward analysis** — Rolling window validation to detect overfitting

## When To Use
- When the user asks "how would trend_following have performed last month?"
- Before deploying a new strategy — validate it against historical data first
- When comparing strategies to select the best one for current conditions
- For walk-forward validation to ensure a strategy isn't overfit
- When generating evidence-based strategy recommendations

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `run` / `run_backtest` | Run backtest for a strategy | — | `candles` (DataFrame), `days` (int, default 30), `strategy_filter` (str), `lookback` (int, default 50), `slippage` (float, default 1.5), `commission` (float, default 0.7), `slippage_enabled` (bool) |
| `compare` | Compare all strategies | `candles` (DataFrame) | `strategies` (list), `slippage`, `commission`, `slippage_enabled` |
| `walk_forward` | Rolling window validation | `candles` (DataFrame) | `strategy`, `window_size` (default 500), `step_size` (default 100), `slippage`, `commission` |
| `format_result` | Format a BacktestResult for display | `result` (BacktestResult) | — |

## Execution Simulation

### Slippage Model
Each trade entry/exit is adjusted by configurable slippage:
- **Default**: 1.5 pips (realistic for EUR/USD during normal conditions)
- **Configurable**: User can adjust via `slippage` parameter
- **Disable**: Set `slippage_enabled=False` for ideal execution comparison

### Commission Model
Per-trade round-trip commission:
- **Default**: 0.7 pips (typical ECN broker cost)
- **Applied**: Deducted from each trade's P&L

### Auto-Fetch
When no candles are provided, the skill automatically fetches from the
price provider:
```
candles = provider.get_candles("H1", count=days × 24)
```

## Walk-Forward Analysis

Prevents overfitting by testing on rolling windows:
```
Window 1: [candle 0..500]    → run strategy → metrics
Window 2: [candle 100..600]  → run strategy → metrics
Window 3: [candle 200..700]  → run strategy → metrics
...
```

If metrics are consistent across windows → strategy is robust.
If metrics vary wildly → strategy may be overfit to specific conditions.

## Output Metrics (per strategy)

| Metric | Description |
|--------|-------------|
| `total_trades` | Number of trades generated |
| `win_rate` | Percentage of winning trades |
| `total_pnl` | Net P&L in pips (after slippage + commission) |
| `profit_factor` | Gross profit / gross loss |
| `sharpe_ratio` | Risk-adjusted return |
| `max_drawdown` | Worst peak-to-trough decline |
| `avg_win` | Average winning trade (pips) |
| `avg_loss` | Average losing trade (pips) |

## Examples

### Example 1: Compare All Strategies (30 days)
```
Action: run, days=30
Output:
🔬 Backtest Comparison (30 days, 720 candles)

  Trend Following:  42 trades, 58% WR, +87.3 pips, PF 1.42, Sharpe 1.1
  Mean Reversion:   28 trades, 53% WR, +21.5 pips, PF 1.15, Sharpe 0.6
  Breakout:         15 trades, 46% WR, -12.8 pips, PF 0.89, Sharpe -0.2

  Winner: trend_following
```

### Example 2: Walk-Forward Validation
```
Action: walk_forward, strategy="trend_following", window_size=500, step_size=100
Output:
  Window 1: 12 trades, 58% WR, +22.1 pips
  Window 2: 10 trades, 60% WR, +18.5 pips
  Window 3: 14 trades, 57% WR, +25.0 pips
  → Consistent performance across windows ✅
```

## Edge Cases & Degraded Modes
- **No candles provided + no provider**: Returns `success=False` with "No historical data available".
- **Insufficient candles for lookback**: Strategy generates fewer signals. Not an error — just less data.
- **Strategy filter not found**: Returns empty result. Check `list_strategies` for valid names.
- **All trades losing**: Returns valid metrics with negative P&L. This is valuable information.

## Integration Chain
```
market_data (candle fetch) ──→ backtesting ──→ performance report
                                    ↓
                             strategy selection recommendation
                                    ↓
                             trading_strategy (informed by backtest results)
```

## Runtime Dependencies
- `BacktestEngine` — internal computation engine
- `PriceProvider` — optional, for auto-fetching candles when none supplied
