---
name: trading_strategy
description: Multi-strategy signal generation with confluence scoring
---

# 🎯 Trading Strategy Skill

## What It Does
Detects trading signals using multiple strategies (Trend Following, Mean Reversion, Breakout) with multi-indicator confluence scoring.

## Actions
- `detect_signal` — Run strategy detection on current market conditions
- `list_strategies` — List available strategies

## Strategies
| Strategy | Logic |
|----------|-------|
| Trend Following | EMA crossover + MACD + ADX confirmation |
| Mean Reversion | Bollinger + RSI oversold/overbought |
| Breakout | Channel break + volatility expansion |
