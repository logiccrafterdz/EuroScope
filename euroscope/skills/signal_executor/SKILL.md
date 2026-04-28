---
name: signal_executor
description: >
  Converts validated trading signals into paper/live trade orders with full
  lifecycle management (open, monitor, update, close). This is the FINAL skill
  in the trading pipeline — it applies 6 safety guardrails before executing any
  trade and manages the complete trade lifecycle. Use this skill when the agent
  has a BUY/SELL signal that passed risk_management approval. Also use for trade
  management: listing open trades, closing positions, updating stops, and
  reviewing trade history. Includes trade deduplication, emergency halt,
  webhook dispatch, and automatic trade journal logging.
---

# ⚡ Signal Executor Skill

## What It Does
The final execution gateway. Takes a validated and risk-approved trading signal
and converts it into an actual trade order — either paper (simulated) or live
(via broker). Before execution, it runs the signal through 6 independent
safety guardrails. After execution, it logs the trade to the journal,
dispatches webhooks, and manages the trade lifecycle.

This skill also handles ongoing trade management: monitoring open positions
via WebSocket tick streaming, updating stop losses (trailing stops), closing
positions, and maintaining trade history.

## When To Use
- After `risk_management.assess_trade` approves a trade (last step in pipeline)
- When the agent needs to close an open position
- When the user asks "what trades are open?" or "close my trade"
- For WebSocket-driven live monitoring (`process_tick` on incoming prices)
- When updating stop losses on existing positions

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `open_trade` | Execute a new trade from context signals + risk | — | (reads from context) |
| `close_trade` | Close an existing position | `signal_id` or `trade_id` | `exit_price` |
| `list_trades` | Show all currently open positions | — | — |
| `trade_history` | Get completed trade history | — | `limit` (int) |
| `update_trade` | Modify an open trade (e.g., trailing stop) | `signal_id` | `stop_loss`, `take_profit` |

## 6 Safety Guardrails (Execution Gate)

Every trade passes through these checks **in order**. The first failure
blocks execution and logs the rejection to the trade journal:

| # | Guardrail | Check | Block Reason |
|---|-----------|-------|-------------|
| 1 | **SafetyGuardrail** (external) | Spread kill switch, daily loss limit, max concurrent trades | Various safety reasons |
| 2 | **Emergency Halt** | `emergency_mode` flag or timed halt active | "EMERGENCY: market regime shift" |
| 3 | **Paper-Only Mode** | Execution mode must be paper/sim when `paper_trading_only=True` | "PAPER_ONLY: live execution disabled" |
| 4 | **Uncertainty Gate** | `uncertainty_score > 0.65` | "UNCERTAINTY: confidence too low" |
| 5 | **Confidence Gate** | `confidence_adjustment < 0.5` | "CONFIDENCE: signal degraded" |
| 6 | **Risk Approval** | `risk.approved` must not be `False` | "RISK: Trade denied by risk manager checks" |

## Trade Deduplication
Prevents the same signal from being executed twice within 60 seconds:
```
signal_hash = f"{direction}:{round(entry_price, 4)}:{strategy}"
if signal_hash in recent_signals (within 60s) → BLOCKED
```

## Trade Lifecycle

```
Signal → [6 Guardrails] → open_trade → [Journal Log] → [Webhook]
                                            ↓
                                     process_tick (WS)
                                            ↓
                                     update_trade (trailing SL)
                                            ↓
                                     close_trade → [Journal Update] → [Webhook]
```

## Input/Output Contract

### Reads From Context
- `context.signals` — `{direction, entry_price, strategy, confidence, reasoning}`
- `context.risk` — `{stop_loss, take_profit, position_size, approved}`
- `context.market_data["timeframe"]` — For trade logging
- `context.metadata["uncertainty_score"]` — Guard check #4
- `context.metadata["confidence_adjustment"]` — Guard check #5
- `context.metadata["emergency_mode"]` — Guard check #2
- `context.metadata["execution_mode"]` — Guard check #3
- `context.metadata["regime"]` — For journal context
- `context.metadata["spread_pips"]` — For execution simulation
- `context.metadata["causal_chain"]` — For journal learning context

### Writes To Context
- `context.open_positions` — Appends new trade data on successful execution

### Trade Data Structure (Output)
```json
{
  "id": 42,
  "trade_id": "T-42",
  "direction": "BUY",
  "entry_price": 1.08750,
  "stop_loss": 1.08500,
  "take_profit": 1.09125,
  "status": "open",
  "strategy": "trend_following",
  "confidence": 72.5
}
```

## Journal Integration
Every trade event is logged to the trade journal for the learning feedback loop:
- **Opened trades**: Full context snapshot (indicators, patterns, regime, reasoning, causal chain)
- **Rejected trades**: Logged with `status=rejected` and the guardrail reason
- **Closed trades**: Updated with exit price, PnL, and outcome

## Webhook Dispatch
On trade events, webhooks are dispatched to configured endpoints:
- `trade_opened` — New position opened
- `trade_closed` — Position closed with PnL

## Emergency Halt System
The skill can be put into emergency halt mode:
```python
set_emergency_halt(duration_seconds=300)  # 5-minute halt
```
During halt, ALL trade execution is blocked. The halt auto-expires after
the specified duration. Used when deviation_monitor detects extreme
market conditions.

## Examples

### Example 1: Successful Trade Execution
```
Input: BUY signal, 72.5% confidence, SL=1.08500, TP=1.09125
Guards: All 6 passed ✅
Output: Trade T-42 opened at 1.08750
```

### Example 2: Blocked by Uncertainty
```
Input: SELL signal, uncertainty_score=0.72
Guard #4 FAILED: "UNCERTAINTY: confidence too low"
Output: success=False, aborted=True, logged to journal as rejected
```

## Edge Cases & Degraded Modes
- **Storage unavailable**: Creates temporary SQLite DB. Trade journal logging may fail but execution proceeds.
- **Executor not initialized**: Returns `success=False`. Config or storage missing.
- **Duplicate signal within 60s**: Returns `success=False` with "Duplicate signal blocked". Prevents accidental double execution.
- **Broker unavailable (live mode)**: Falls back to paper execution if configured.
- **Webhook dispatch fails**: Logged as warning but does NOT affect trade execution.
- **Emergency mode active**: All trades blocked until halt expires or is manually cleared.

## Integration Chain
```
trading_strategy ──→ risk_management ──→ signal_executor
                                              ↓
                                       trade_journal (auto-log)
                                              ↓
                                       performance_analytics (outcome tracking)
```

## Runtime Dependencies
- `Storage` — for trade persistence and journal (auto-creates temp DB if missing)
- `Config` — for paper/live mode, safety thresholds
- `SafetyGuardrail` — for spread kill switch, daily loss limits
- `SignalExecutor` — internal executor for order management
- `ExecutionSimulator` — for slippage/fill simulation
- `WebhookDispatcher` — for external notifications
- `EventBus` — optional, for system-wide trade event broadcasting
