---
name: fundamental_analysis
description: News sentiment, economic calendar, and central bank data for EUR/USD
---

# 📰 Fundamental Analysis Skill

## What It Does
Gathers and analyzes fundamental data: news sentiment, economic calendar events, and central bank rate differentials.

## Actions
- `get_news` — Fetch latest EUR/USD news with sentiment scores
- `get_calendar` — Upcoming economic events (NFP, ECB, Fed, CPI, GDP)
- `get_sentiment` — Aggregated news sentiment summary
- `full` — All fundamental data combined

## Dependencies
- `euroscope.data.news` — NewsEngine
- `euroscope.data.calendar` — EconomicCalendar
