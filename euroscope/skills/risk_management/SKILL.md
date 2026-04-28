---
name: risk_management
description: >
  Calculates adaptive stop loss (liquidity-aware + session-buffered), dynamic
  position sizing (5 multipliers: session, confidence, drawdown, correlation,
  risk), take profit with realistic risk-reward considering slippage, and full
  trade risk assessments with rejection logic. Use this skill before every trade
  execution — it is the safety gate that sizes positions, places stops beyond
  liquidity zones, and rejects trades that don't meet risk criteria. Invoke after
  technical_analysis and uncertainty_assessment, and before signal_executor.
---

# 🛡️ Risk Management Skill

## What It Does
The safety guardian of every trade. Takes a proposed trade direction and
entry price, then calculates everything needed for safe execution: where
to place the stop loss (beyond liquidity zones with session-appropriate
buffers), how large the position should be (adjusted for 5 independent
risk factors), and whether the trade meets minimum risk-reward requirements.

This skill can **reject trades** that don't pass safety checks, logging
the rejection to the trade journal for learning.

## When To Use
- After `technical_analysis` and `uncertainty_assessment` produce context
- Before `signal_executor.open_trade` — it needs risk data (SL, TP, size)
- When the agent needs to calculate position size for a given risk tolerance
- When the user asks "how much should I risk?" or "where should my stop be?"
- Automatically invoked when `trading_strategy` returns a BUY/SELL signal

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `assess_trade` | Full risk assessment with adaptive stops and sizing | — | `direction`, `entry_price`, `atr`, `avg_atr`, `support`, `resistance` |
| `position_size` | Calculate position size only | — | `balance` (float), `risk_pct` (float), `stop_pips` (float) |
| `stop_loss` | Calculate stop loss only | — | `direction`, `entry_price`, `atr` |
| `take_profit` | Calculate take profit only | — | `direction`, `entry_price`, `stop_loss` |

## Adaptive Stop Loss Algorithm

The stop loss is NOT a fixed ATR multiple — it's a multi-factor placement:

### 1. Session Buffer (Base)
| Session | Buffer (pips) | Rationale |
|---------|--------------|-----------|
| Asian | 8 | Low volatility, tight stops OK |
| London | 12 | Moderate volatility |
| New York | 15 | Higher volatility |
| Overlap | 18 | Peak volatility, widest buffer |
| Default | 15 | Conservative fallback |

### 2. Volatility Buffer
When ATR > 30 pips: `additional_buffer = min(ATR_pips × 0.2, 15.0)`

### 3. Liquidity Zone Placement
If a relevant liquidity zone exists (support below for BUY, resistance above for SELL):
```
stop_loss = zone_price_level ± (10 + session_buffer) pips
```
Otherwise: `stop_loss = entry_price ± session_buffer pips`

### 4. Noise Band Rejection
If `stop_distance < ATR × 0.6` → trade rejected with `stop_inside_noise_band`

## Dynamic Position Sizing (5 Multipliers)

```
adjusted_risk% = base_risk% × session × confidence × drawdown × correlation
position_size = base_size × (adjusted_risk% / config_risk%)
```

| Multiplier | Source | Effect |
|:-----------|:-------|:-------|
| **Session** | session_regime | Asian=0.6×, London/NY=1.0×, Overlap=1.2×, Weekend=0.0× |
| **Confidence** | market_intent.confidence | <0.4=0.0× (blocked), 0.4-0.6=0.6×, 0.6-0.8=0.8×, >0.8=1.0× |
| **Drawdown** | daily_pnl / balance | >5%=0.0× (blocked), >3%=0.5×, else=1.0× |
| **Correlation** | GBP/USD, USD/CHF correlation | 0.5× to 1.5× based on confirmation |
| **Risk pref** | user_prefs.risk_tolerance | low=0.5%, default=1.0%, high=1.5% |

Final risk% is clamped to [0.25%, 2.0%].

## Realistic Risk-Reward Calculation
```
realistic_RR = reward_pips / (risk_pips + slippage_pips)
```
- Normal slippage: 1.5 pips
- Emergency/deviation mode: 4.0 pips
- **Minimum R:R**: 1.3 — trades below this are rejected with `insufficient_risk_reward`

## Rejection Priority Hierarchy

| Priority | Reason | Effect |
|----------|--------|--------|
| 5 | `avoid_weekend` | Weekend/holiday — no trading |
| 4 | `excessive_drawdown` | Daily drawdown > 5% |
| 3 | `risk_limits` / `low_intent_confidence` | Risk manager denied or intent < 0.4 |
| 2 | `stop_inside_noise_band` | Stop too close to price noise |
| 1 | `insufficient_risk_reward` | Realistic R:R < 1.3 |

## Input/Output Contract

### Reads From Context
- `context.signals` — Direction, entry_price from trading_strategy
- `context.analysis["indicators"]` — ATR for stop calculation
- `context.analysis["levels"]` — Support/resistance for stop placement
- `context.metadata["session_regime"]` — Session for sizing and stops
- `context.metadata["liquidity_zones"]` — For liquidity-aware stop placement
- `context.metadata["market_intent"]` — Intent confidence for sizing
- `context.metadata["confidence_adjustment"]` — From uncertainty_assessment
- `context.user_prefs` — Risk tolerance preferences

### Writes To Context
- `context.risk` — Full risk assessment: `{approved, direction, entry_price, stop_loss, take_profit, position_size, risk_pips, reward_pips, risk_reward_ratio, status}`
- `context.metadata["risk_assessment"]` — Detailed breakdown with all multipliers

## Edge Cases & Degraded Modes
- **Missing ATR**: Uses levels-only stop placement. Less precise but functional.
- **No liquidity zones**: Falls back to pure session-buffer stops. Safe but may be caught by noise.
- **Missing intent confidence + strong macro**: Uses macro confidence as floor (0.6).
- **Weekend session**: Automatically rejects with `avoid_weekend`. No position sizing computed.
- **Rejected trade**: Logged to trade journal with full context for learning feedback loop.

## Integration Chain
```
technical_analysis ──→ risk_management ──→ signal_executor
uncertainty_assessment ─┘      ↓
session_context ──────────────→│
liquidity_awareness ──────────→│
```
