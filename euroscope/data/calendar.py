"""
Economic Calendar

Tracks key economic events that impact EUR/USD.
Provides upcoming event schedule and impact ratings.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("euroscope.data.calendar")


@dataclass
class EconomicEvent:
    name: str
    currency: str  # "USD" or "EUR"
    impact: str    # "high", "medium", "low"
    description: str
    typical_effect: str  # How it typically affects EUR/USD


# Key recurring events that heavily impact EUR/USD
MAJOR_EVENTS = [
    EconomicEvent(
        "Non-Farm Payrolls (NFP)", "USD", "high",
        "US jobs report — first Friday of each month",
        "Strong NFP → USD strength → EUR/USD ↓ | Weak NFP → EUR/USD ↑"
    ),
    EconomicEvent(
        "FOMC Interest Rate Decision", "USD", "high",
        "Federal Reserve rate decision — 8 times per year",
        "Rate hike → USD strength → EUR/USD ↓ | Dovish → EUR/USD ↑"
    ),
    EconomicEvent(
        "ECB Interest Rate Decision", "EUR", "high",
        "European Central Bank rate decision — 6 weeks cycle",
        "Rate hike → EUR strength → EUR/USD ↑ | Dovish → EUR/USD ↓"
    ),
    EconomicEvent(
        "US CPI (Inflation)", "USD", "high",
        "Consumer Price Index — monthly, around 13th",
        "Higher CPI → more Fed hikes expected → EUR/USD ↓"
    ),
    EconomicEvent(
        "Eurozone CPI", "EUR", "high",
        "Eurozone harmonized CPI — end of month",
        "Higher CPI → more ECB hikes expected → EUR/USD ↑"
    ),
    EconomicEvent(
        "Fed Chair Powell Speech", "USD", "high",
        "Public remarks by Federal Reserve Chair",
        "Hawkish tone → EUR/USD ↓ | Dovish tone → EUR/USD ↑"
    ),
    EconomicEvent(
        "ECB President Lagarde Speech", "EUR", "high",
        "Public remarks by ECB President",
        "Hawkish tone → EUR/USD ↑ | Dovish tone → EUR/USD ↓"
    ),
    EconomicEvent(
        "US GDP", "USD", "high",
        "Gross Domestic Product — quarterly",
        "Strong GDP → USD bullish → EUR/USD ↓"
    ),
    EconomicEvent(
        "Eurozone GDP", "EUR", "medium",
        "Eurozone GDP — quarterly",
        "Strong GDP → EUR bullish → EUR/USD ↑"
    ),
    EconomicEvent(
        "US PMI (ISM Manufacturing)", "USD", "medium",
        "ISM Manufacturing PMI — first business day of month",
        "Above 50 (expansion) → USD bullish"
    ),
    EconomicEvent(
        "Eurozone PMI", "EUR", "medium",
        "Eurozone Manufacturing/Services PMI — mid-month",
        "Above 50 (expansion) → EUR bullish"
    ),
    EconomicEvent(
        "US Retail Sales", "USD", "medium",
        "Monthly retail sales data",
        "Strong sales → USD strength → EUR/USD ↓"
    ),
    EconomicEvent(
        "US Unemployment Claims", "USD", "low",
        "Weekly initial jobless claims — every Thursday",
        "Rising claims → USD weakness → EUR/USD ↑"
    ),
    EconomicEvent(
        "German IFO Business Climate", "EUR", "medium",
        "Key German business confidence indicator — monthly",
        "Strong data → EUR strength → EUR/USD ↑"
    ),
    EconomicEvent(
        "FOMC Meeting Minutes", "USD", "medium",
        "Detailed minutes from FOMC meeting — 3 weeks after decision",
        "Reveals internal Fed debate — can shift expectations"
    ),
]


class EconomicCalendar:
    """Provides information about key EUR/USD economic events."""

    def __init__(self):
        self.events = MAJOR_EVENTS

    def get_all_events(self) -> list[EconomicEvent]:
        """Get all tracked economic events."""
        return self.events

    def get_upcoming_events(self) -> list[dict]:
        return [
            {
                "time": "TBD",
                "currency": e.currency,
                "impact": e.impact.capitalize(),
                "event": e.name,
                "actual": "",
                "forecast": "",
                "description": e.description,
                "typical_effect": e.typical_effect,
            }
            for e in self.events
        ]

    def get_high_impact_events(self) -> list[EconomicEvent]:
        """Get only high-impact events."""
        return [e for e in self.events if e.impact == "high"]

    def get_events_by_currency(self, currency: str) -> list[EconomicEvent]:
        """Get events for a specific currency (USD or EUR)."""
        return [e for e in self.events if e.currency == currency.upper()]

    def format_calendar(self, events: list[EconomicEvent] = None) -> str:
        """Format events for Telegram display."""
        if events is None:
            events = self.events

        lines = ["📅 *EUR/USD Economic Calendar*\n"]

        # Group by impact
        for impact_level in ["high", "medium", "low"]:
            impact_events = [e for e in events if e.impact == impact_level]
            if not impact_events:
                continue

            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}[impact_level]
            lines.append(f"\n{icon} *{impact_level.upper()} IMPACT*")

            for e in impact_events:
                flag = "🇺🇸" if e.currency == "USD" else "🇪🇺"
                lines.append(f"  {flag} *{e.name}*")
                lines.append(f"     _{e.description}_")
                lines.append(f"     📊 {e.typical_effect}")
                lines.append("")

        return "\n".join(lines)

    def get_context_for_ai(self) -> str:
        """Get calendar summary for the AI brain's context."""
        lines = ["Key EUR/USD economic events and their typical impact:"]
        for e in self.events:
            lines.append(f"- {e.name} ({e.currency}, {e.impact}): {e.typical_effect}")
        return "\n".join(lines)
