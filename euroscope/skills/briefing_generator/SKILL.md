---
name: briefing_generator
description: >
  Synthesizes data from technical, fundamental, and performance skills into cohesive,
  human-readable intelligence reports. Use this skill to generate the daily morning
  briefing or the weekly performance review.
---

# 📰 Briefing Generator Skill

## What It Does
A reporting engine that aggregates data from multiple analytical skills across the system
and formats it into an executive summary. It translates raw metrics (like RSI values, news
sentiment scores, and upcoming calendar events) into a unified narrative report suitable
for Telegram delivery.

## When To Use
- At the start of the trading day to generate a `morning_briefing`.
- At the end of the trading week (Friday close) to generate a `weekly_review`.
- When the user requests a summary of the current market state.

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `generate_morning_briefing` | Synthesizes tech/fund/macro into a daily report | — | — |
| `generate_weekly_review` | Synthesizes performance stats into a weekly review | — | — |

## Integration Chain
```
technical_analysis ───────┐
fundamental_analysis ─────┤
macro_calendar ───────────┼──→ briefing_generator ──→ Telegram message
performance_analytics ────┘
```

## Dependencies
Declares explicit dependencies on `technical_analysis`, `fundamental_analysis`,
`macro_calendar`, and `performance_analytics` to ensure the `SkillsRegistry` executes
them first and populates the `SkillContext` before the briefing is generated.
