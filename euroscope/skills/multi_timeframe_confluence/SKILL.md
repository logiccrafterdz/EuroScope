# Multi-Timeframe Confluence Skill

## Overview
Analyzes EUR/USD across multiple timeframes (M15, H1, H4, D1) simultaneously
to find confluence signals — where multiple timeframes agree on direction.

## Actions
- `confluence`: Run full multi-timeframe analysis and return alignment score
- `check_alignment`: Quick check if timeframes are aligned (bullish/bearish/mixed)

## How It Works
1. Fetches candle data for each timeframe (M15, H1, H4, D1)
2. Computes key indicators (RSI, MACD, EMA trend) on each
3. Scores alignment: +1 for each aligned timeframe, -1 for conflicting
4. Returns a confidence-weighted confluence verdict

## Integration
- Uses `PriceProvider` for data fetching
- Uses `TechnicalAnalyzer` for indicator computation
- Feeds results into `SkillContext.analysis["confluence"]`
