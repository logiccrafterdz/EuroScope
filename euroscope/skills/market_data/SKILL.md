---
name: market_data
description: Fetches real-time and historical EUR/USD price data
---

# 📊 Market Data Skill

## What It Does
Fetches current EUR/USD price quotes and historical OHLCV candles from multiple providers with automatic fallback.

## Actions
- `get_price` — Current bid/ask/mid price + daily change stats
- `get_candles` — Historical OHLCV candle data for any timeframe

## Parameters
| Action | Param | Type | Default | Description |
|--------|-------|------|---------|-------------|
| get_price | — | — | — | No params needed |
| get_candles | timeframe | str | "H1" | M15, H1, H4, D1 |
| get_candles | count | int | 100 | Number of candles |

## Dependencies
- `euroscope.data.providers` — PriceProvider

## Example Usage
```python
result = skill.execute(ctx, "get_price")
# result.data = {"price": 1.0875, "change": -0.0012, ...}

result = skill.execute(ctx, "get_candles", timeframe="H4", count=200)
# result.data = DataFrame with Open/High/Low/Close/Volume
```
