"""
EuroScope Data Models

Dataclass models for all core entities: trading signals, news events,
performance metrics, and user preferences.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional


@dataclass
class TradingSignal:
    """A trading signal with entry/exit levels and risk parameters."""
    direction: str              # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float           # 0-100
    timeframe: str              # "M15", "H1", "H4", "D1"
    source: str = "system"      # "system", "ai_agent", "strategy_X"
    status: str = "pending"     # "pending", "active", "closed", "cancelled"
    reasoning: str = ""
    risk_reward_ratio: float = 0.0
    pnl_pips: float = 0.0
    id: Optional[int] = None
    created_at: str = ""
    closed_at: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        if self.stop_loss and self.entry_price and self.take_profit:
            risk = abs(self.entry_price - self.stop_loss)
            reward = abs(self.take_profit - self.entry_price)
            self.risk_reward_ratio = round(reward / risk, 2) if risk > 0 else 0.0


@dataclass
class NewsEvent:
    """A news article or event relevant to EUR/USD."""
    title: str
    source: str                 # "brave", "twitter", "reuters", "ecb", etc.
    url: str = ""
    description: str = ""
    impact_score: float = 0.0   # 0-10 relevance/impact score
    sentiment: str = "neutral"  # "bullish", "bearish", "neutral"
    sentiment_score: float = 0.0  # -1.0 to 1.0
    currency_impact: str = ""   # "USD", "EUR", "both"
    published_at: str = ""
    fetched_at: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(UTC).isoformat()


@dataclass
class PerformanceMetric:
    """Snapshot of trading performance metrics."""
    period: str                 # "daily", "weekly", "monthly"
    total_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    win_rate: float = 0.0       # percentage
    total_pnl_pips: float = 0.0
    avg_pnl_pips: float = 0.0
    max_drawdown_pips: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    avg_risk_reward: float = 0.0
    best_trade_pips: float = 0.0
    worst_trade_pips: float = 0.0
    avg_trade_duration_hours: float = 0.0
    calculated_at: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(UTC).isoformat()
        if self.total_signals > 0:
            self.win_rate = round(self.winning_signals / self.total_signals * 100, 1)


@dataclass
class UserPreference:
    """Per-user configuration and preferences."""
    chat_id: int
    risk_tolerance: str = "medium"    # "low", "medium", "high"
    preferred_timeframe: str = "H1"
    alert_on_signals: bool = True
    alert_on_news: bool = True
    alert_min_confidence: float = 60.0  # minimum signal confidence to alert
    daily_report_enabled: bool = True
    daily_report_hour: int = 8          # UTC hour for daily report
    language: str = "en"                # "en", "ar"
    max_signals_per_day: int = 5
    compact_mode: bool = False
    backtest_slippage_enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
