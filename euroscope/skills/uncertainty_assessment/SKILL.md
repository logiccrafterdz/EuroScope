---
name: uncertainty_assessment
description: Quantifies cognitive uncertainty for trading signals
---

# 🧭 Uncertainty Assessment Skill

## What It Does
Computes a combined uncertainty score from technical signals and behavioral similarity to past analyses.

## Actions
- `assess` — Calculate uncertainty score, confidence adjustment, and high-uncertainty flag

## Inputs
- Current indicators, patterns, and last 20 candles from context

## Returns
- `uncertainty_score`, `confidence_adjustment`, `high_uncertainty`, `market_regime`
