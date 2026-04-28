---
name: macro_calendar
description: >
  Advanced economic event tracking, impact assessment, and countdowns.
  Use this skill to fetch upcoming macroeconomic events, check if high-impact
  announcements (like NFP, FOMC) are imminent, and trigger trading halts
  to protect the portfolio from extreme event-driven volatility.
---

# 📆 Macro Calendar Skill

## What It Does
Provides dynamic, time-aware tracking of macroeconomic events. It goes beyond simple
event listing by evaluating the impact of upcoming events and calculating countdowns.
It can recommend trading halts if a high-impact event (e.g., Central Bank rate decision)
is within a critical time window (e.g., 30 minutes).

## When To Use
- When planning the trading session to know what events to avoid.
- Continuously during the OODA loop to check for imminent "trading halt" conditions.
- When generating daily or weekly macro briefings.

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_upcoming` | Fetch upcoming events | — | `impact` (str: high, medium, low) |
| `check_impact` | Check if high impact event is imminent | — | `simulated_minutes_to_event` |
| `time_to_event` | Countdown to a specific event | `event_name` (str) | `simulated_minutes_to_event` |

## Integration Chain
```
macro_calendar.check_impact ──→ uncertainty_assessment (behavioral layer)
                                 ↓
                          signal_executor (halt execution)
```

## Edge Cases
- **Missing API Connection**: If the underlying calendar provider fails, returns empty events without halting to prevent false positives.
- **Unrecognized Event**: `time_to_event` safely returns an error if the requested event is not tracked.
