---
name: deviation_monitor
description: >
  Detects sudden market regime shifts by monitoring three anomaly channels:
  volume spikes, volatility explosions, and price velocity surges. When a
  deviation is detected, it triggers emergency mode which halts all trading
  for a session-appropriate duration. Also detects concept drift (systematic
  performance degradation). This skill runs continuously via EventBus tick
  subscriptions — it does NOT need to be called manually. It is the automated
  safety net that protects the system from black swan events and structural
  market changes.
---

# 🚨 Deviation Monitor Skill

## What It Does
The automated early warning system. Subscribes to 30-second tick events
and continuously monitors market data for anomalies that signal a regime
shift — sudden spikes in volume, volatility, or price velocity that
indicate the market has fundamentally changed character.

When a deviation is detected, the skill:
1. Sets `emergency_mode=True` in the global context
2. Persists the emergency state to storage (survives restarts)
3. Emits a `market.regime_shift` event on the EventBus
4. Logs the deviation to the trade journal for post-mortem analysis

It also monitors for **concept drift** — when the system's recent
win rate drops significantly below its historical baseline, indicating
that the trading logic is no longer effective in current conditions.

## When To Use
- **Automatically** — subscribes to `tick.30s` events via EventBus
- Manual `start` action to initialize the subscription
- The system handles everything else autonomously

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `start` | Subscribe to tick events and begin monitoring | — | — |

> This skill is event-driven. After `start`, it runs autonomously
> on every 30-second tick. No manual invocation needed.

## Three Anomaly Detection Channels

### 1. Volume Spike
Detects when current volume exceeds the 5-period moving average by a
session-specific threshold:

| Session | Threshold | Trigger |
|---------|----------|---------|
| Asian | 3.0× | Current volume > 3× the 5-bar SMA |
| London | 4.5× | Current volume > 4.5× the 5-bar SMA |
| New York | 4.0× | Current volume > 4× the 5-bar SMA |
| Overlap | 5.0× | Current volume > 5× the 5-bar SMA |

### 2. Volatility Spike
Detects when ATR(14) exceeds its 10-period moving average:

| Session | Threshold | What It Detects |
|---------|----------|-----------------|
| Asian | 2.5× | Unusual range expansion during quiet hours |
| London/NY | 3.5× | Extreme volatility beyond normal session range |
| Overlap | 4.0× | Very extreme — only triggers during unusual events |

### 3. Price Velocity
Detects rapid price movement as a percentage of current price:

| Session | Threshold | Calculation |
|---------|----------|-------------|
| Asian | 0.15% | max(|close[-1] - close[-3]|, |close[-1] - close[-2]|) / close[-1] × 100 |
| London | 0.21% | Same formula, higher tolerance |
| Overlap | 0.27% | Same formula, highest tolerance |
| New York | 0.24% | Same formula |

## Concept Drift Detection

Monitors the system's own performance for systematic degradation:

```
Conditions for concept drift alert:
1. At least 50 historical trades (baseline established)
2. At least 20 recent trades available
3. Recent win rate < 50% of historical win rate
4. Recent win rate < 30% absolute

Emergency duration: 24 hours (full day halt)
```

This catches scenarios where market structure has changed enough that
the trading strategies are no longer effective.

## Emergency Mode Behavior

When triggered, emergency mode:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Duration (Asian)** | 300s (5 min) | Quick recovery — low volatility session |
| **Duration (London/NY)** | 300s (5 min) | Standard recovery period |
| **Duration (Overlap)** | 480s (8 min) | Peak volatility — longer cooldown |
| **Duration (Weekend)** | 86,400s (24h) | Market closed — wait for open |
| **Duration (Concept Drift)** | 86,400s (24h) | Systematic issue — full day halt |

### What Emergency Mode Blocks
- `signal_executor` → Guard #2 blocks all new trades
- `trading_strategy` → Falls back to technical-only mode
- New OODA cycles continue but no execution occurs

### Persistence
Emergency state is persisted to storage via `save_json("emergency_mode_state", ...)`.
If the system restarts during an emergency, the state is restored.

## Cooldown
After triggering, the monitor enforces a **600-second cooldown** before
checking again. This prevents alert storms during sustained volatility.

## Examples

### Example 1: Volume Spike During London
```json
{
  "trigger": "volume_spike",
  "magnitude": 4.8,
  "details": [{"type": "volume_spike", "magnitude": 4.8}],
  "session": "london"
}
→ Emergency mode for 300 seconds
→ Event emitted: market.regime_shift
→ Logged to trade journal as ALERT
```

### Example 2: Concept Drift Detected
```json
{
  "trigger": "concept_drift",
  "magnitude": 0.25,
  "details": [{"type": "win_rate_drop", "recent": 0.20, "historical": 0.55}],
  "session": "london"
}
→ Emergency mode for 86,400 seconds (24 hours)
→ System halts all trading until strategies are reviewed
```

## Edge Cases & Degraded Modes
- **No market data buffer**: Attempts auto-fetch via market_data skill. If that fails, skips check cycle.
- **Insufficient candles** (<3): Skips deviation check for this cycle. Logs warning.
- **No EventBus**: `start` action succeeds but no subscription occurs. Skill is inert.
- **Storage unavailable**: Emergency mode still activates in-memory but won't persist across restarts.
- **Volume column missing**: Volume spike check skipped. Volatility and velocity still checked.

## Integration Chain
```
EventBus (tick.30s) ──→ deviation_monitor._check_once()
                              ↓ (deviation detected)
                       context.metadata["emergency_mode"] = True
                              ↓
                       signal_executor (blocked)
                       trading_strategy (fallback mode)
                              ↓
                       trade_journal (ALERT logged)
                       EventBus (market.regime_shift emitted)
```

## Runtime Dependencies
- `EventBus` — for tick subscription (event-driven monitoring)
- `MarketDataSkill` — for candle buffer access and auto-fetch
- `Storage` — for emergency state persistence and concept drift detection
- `GlobalContext` — for reading/writing emergency flags
