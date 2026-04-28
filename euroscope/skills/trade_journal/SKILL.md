---
name: trade_journal
description: >
  Records every trade with full market context snapshots (indicators, patterns,
  regime, causal chain) and provides aggregate performance analysis per strategy.
  Use this skill when a trade is opened or closed — it captures the complete
  decision context for post-trade learning. Also use when the user asks to review
  past trades, when generating performance breakdowns, or when the continuous
  learning loop needs trade outcome data. Every rejected trade is also logged
  here for counterfactual analysis ("what would have happened if we traded?").
---

# 📓 Trade Journal Skill

## What It Does
The institutional-grade trade ledger. Goes far beyond simple P&L tracking —
every trade entry captures a full snapshot of the market context at the moment
of decision: which indicators fired, what patterns were detected, what regime
the market was in, and the complete causal reasoning chain.

When trades close, the skill triggers the **continuous learning loop**:
1. Extracts learning insights via `PostTradeAnalyzer`
2. Stores regime snapshots in `VectorMemory` for future pattern matching
3. Updates accuracy data for the prediction tracker

This creates a self-improving system where past trade outcomes directly
influence future decision quality.

## When To Use
- Automatically when `signal_executor.open_trade` executes (logs the trade)
- When a trade is closed — `close_trade` triggers the learning pipeline
- When the user asks "show me my trades" or "what did I trade this week?"
- When generating strategy-specific performance breakdowns
- For counterfactual analysis of rejected trades

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `log_trade` | Record a new trade with full context | `direction`, `entry_price` | `stop_loss`, `take_profit`, `strategy`, `timeframe`, `regime`, `confidence`, `indicators`, `patterns`, `reasoning`, `causal_chain` |
| `close_trade` | Close a trade and trigger learning | `trade_id`, `exit_price`, `pnl_pips` | `is_win` (auto-detected from pnl) |
| `get_journal` | Retrieve journal entries | — | `strategy`, `status`, `limit` (default 50) |
| `get_stats` | Aggregate statistics | — | `strategy` (filter) |

## Context Captured Per Trade

Every journal entry stores:
```json
{
  "direction": "BUY",
  "entry_price": 1.08750,
  "stop_loss": 1.08500,
  "take_profit": 1.09125,
  "strategy": "trend_following",
  "timeframe": "H1",
  "regime": "trending",
  "confidence": 72.5,
  "indicators_snapshot": {
    "RSI": 42.3, "MACD_hist": 0.00023, "ADX": 32,
    "ATR_pips": 8.2, "EMA_trend": "bullish"
  },
  "patterns_snapshot": [
    {"pattern": "head_and_shoulders", "signal": "bearish", "confidence": 0.62}
  ],
  "reasoning": "EMA bullish crossover + MACD confirmation",
  "causal_chain": {
    "trigger": "technical_signal",
    "price_reaction": "strong_break",
    "indicator_response": "confirmed",
    "liquidity_aligned": true,
    "data_quality": "complete"
  }
}
```

## Continuous Learning Loop (on close_trade)

```
close_trade ──→ PostTradeAnalyzer.analyze_trade_outcome()
                      ↓
               Storage.save_learning_insight()
                      ↓ (accuracy, key_factors, recommendations)
               VectorMemory.store_regime_snapshot()
                      ↓ (state + outcome for future matching)
               trading_strategy can query similar regimes
```

### Learning Insight Structure
```json
{
  "accuracy": 0.85,
  "key_factors": ["strong_adx", "liquidity_aligned", "london_session"],
  "recommendations": ["Continue trend_following during london with ADX>30"]
}
```

## Journal Display Format
```
📓 Trade Journal

✅ #42 BUY @ 1.08750 [trend_following] +25.0p
  ↳ Causal: technical_signal / strong_break / confirmed / WIN

❌ #41 SELL @ 1.09100 [mean_reversion] -12.5p
  ↳ Causal: rsi_extreme / weak_break / diverged / LOSS

⏳ #43 BUY @ 1.08800 [breakout] +0.0p (open)
```

## Edge Cases & Degraded Modes
- **Storage unavailable**: Returns `success=False`. Cannot journal without persistence.
- **PostTradeAnalyzer import fails**: Trade closes successfully but learning insight is not saved. Logged as error.
- **VectorMemory unavailable**: Regime snapshot not stored. Logged as debug. Does not affect trade closure.
- **Malformed causal_chain**: Parsed defensively — string JSON is auto-parsed, non-dict defaults to empty.
- **Missing indicators**: Saved as empty dict. Journal entry still created.

## Integration Chain
```
signal_executor.open_trade ──→ trade_journal.log_trade
                                      ↓
signal_executor.close_trade ──→ trade_journal.close_trade
                                      ↓
                               PostTradeAnalyzer (learning)
                                      ↓
                               VectorMemory (regime storage)
                                      ↓
                               performance_analytics (stats)
```

## Runtime Dependencies
- `Storage` — for trade persistence (SQLite)
- `PostTradeAnalyzer` — for learning insight extraction (on close)
- `VectorMemory` — optional, for regime snapshot storage
