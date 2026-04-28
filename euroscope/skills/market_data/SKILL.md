---
name: market_data
description: >
  Fetches real-time and historical EUR/USD price data with provider failover.
  Use this skill at the START of every analysis pipeline or OODA observe phase.
  Invoke automatically when the agent needs current price, candle data, market
  open/close status, or cross-pair correlation. This is the data foundation —
  almost every other skill depends on its output.
---

# 📊 Market Data Skill

## What It Does
The data gateway for the entire EuroScope pipeline. Fetches live EUR/USD
bid/ask quotes, historical OHLCV candle data across multiple timeframes,
market open/close status, and cross-pair correlations. Supports automatic
provider failover (OANDA → Tiingo → cache) and WebSocket tick volume injection.

This skill also performs **causal impact detection** — when an abnormal price
spike (≥15 pips) is detected in the latest candle, it flags the event in
context metadata so downstream skills (fundamental_analysis, uncertainty_assessment)
can prioritize explaining the cause.

## When To Use
- **Always first** in any analysis or trading pipeline
- When the agent needs to answer "what is the current EUR/USD price?"
- When any downstream skill requires candle data (technical_analysis, liquidity_awareness, etc.)
- At the start of each OODA loop cycle (Observe phase)
- When checking if the forex market is currently open before placing trades
- When comparing EUR/USD movement against GBP/USD or USD/CHF for confirmation

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_price` | Current bid/ask/mid price + daily change | — | — |
| `get_candles` | Historical OHLCV candle data | — | `timeframe` (str, default "H1"), `count` (int, default 250), `symbol` (str, default "EUR_USD") |
| `check_market_status` | Is the forex market open right now? | — | — |
| `get_correlation` | Pearson correlation vs other pairs | — | `timeframe`, `count`, `base_symbol`, `compare_symbols` (list) |

## Input/Output Contract

### Reads From Context
- Nothing — this is the first skill in the chain

### Writes To Context
- `context.market_data["price"]` — `{price, bid, ask, change, change_pct, ...}`
- `context.market_data["candles"]` — pandas DataFrame with Open/High/Low/Close/Volume
- `context.market_data["timeframe"]` — active timeframe string (e.g., "H1")
- `context.market_data["tick_volume_5m"]` — live tick volume from WebSocket (if available)
- `context.market_data["correlation"]` — `{GBP_USD: 0.82, USD_CHF: -0.71}`
- `context.metadata["market_status"]` — `{is_open, status, reason}`
- `context.metadata["causal_trigger"]` — set when ≥15 pip spike detected

## Examples

### Example 1: Get Current Price
```
Action: get_price
Output: {price: 1.08750, bid: 1.08748, ask: 1.08752, change: -0.00120, change_pct: -0.11}
Next skill: technical_analysis
```

### Example 2: Fetch H4 Candles for Analysis
```
Action: get_candles, timeframe="H4", count=200
Output: DataFrame[200 rows × 5 cols] — Open, High, Low, Close, Volume
Next skill: technical_analysis
```

### Example 3: Cross-Pair Correlation
```
Action: get_correlation, compare_symbols=["GBP_USD", "USD_CHF"]
Output: {GBP_USD: 0.823, USD_CHF: -0.714}
```

## Edge Cases & Degraded Modes
- **Provider unavailable**: Returns `success=False` with error message. Upstream should retry or use cached data.
- **No candle data returned**: Returns `success=False`. Technical analysis cannot proceed.
- **Market closed**: `check_market_status` returns `is_open=False`. Signal executor should block new trades.
- **Abnormal spike detected**: Sets `causal_trigger` in metadata. Does NOT block execution — downstream skills decide how to react.
- **WebSocket unavailable**: Falls back gracefully, sets `tick_volume_5m=0`.

## Integration Chain
```
market_data → technical_analysis → liquidity_awareness → risk_management → signal_executor
     ↓
session_context (parallel)
     ↓
correlation_monitor (parallel)
```

## Runtime Dependencies
- `PriceProvider` — injected via `set_provider()`
- `WebSocketClient` — optional, injected via `set_ws_client()`
