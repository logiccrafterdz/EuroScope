---
name: liquidity_awareness
description: Detects liquidity zones and infers market intent. Invoke after session context and price data are available.
---

# 💧 Liquidity Awareness Skill

## What It Does
Analyzes recent OHLCV candles to identify liquidity zones and infer market intent for downstream skills.

## Actions
- `analyze` — Detect zones and infer intent

## Outputs
- `context.metadata["liquidity_zones"]`
- `context.metadata["market_intent"]`
- `context.metadata["liquidity_aware"]`
