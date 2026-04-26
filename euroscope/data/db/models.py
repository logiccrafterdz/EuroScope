from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, JSON, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    timeframe: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    accuracy_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class TransactionLog(Base):
    __tablename__ = "transaction_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    action: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    condition: Mapped[str] = mapped_column(Text)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    chat_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

class MarketNote(Base):
    __tablename__ = "market_notes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    category: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)

class Memory(Base):
    __tablename__ = "memory"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

class TradingSignal(Base):
    __tablename__ = "trading_signals"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    direction: Mapped[str] = mapped_column(String(20))
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    timeframe: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50), default="system")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_reward_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pips: Mapped[float] = mapped_column(Float, default=0.0)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class NewsEvent(Base):
    __tablename__ = "news_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment: Mapped[str] = mapped_column(String(50), default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    currency_impact: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(50))
    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    winning_signals: Mapped[int] = mapped_column(Integer, default=0)
    losing_signals: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl_pips: Mapped[float] = mapped_column(Float, default=0.0)
    avg_pnl_pips: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pips: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    avg_risk_reward: Mapped[float] = mapped_column(Float, default=0.0)
    best_trade_pips: Mapped[float] = mapped_column(Float, default=0.0)
    worst_trade_pips: Mapped[float] = mapped_column(Float, default=0.0)
    avg_trade_duration_hours: Mapped[float] = mapped_column(Float, default=0.0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class UserPreference(Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(String(20), default="medium")
    preferred_timeframe: Mapped[str] = mapped_column(String(20), default="H1")
    alert_on_signals: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_news: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_min_confidence: Mapped[float] = mapped_column(Float, default=60.0)
    daily_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_report_hour: Mapped[int] = mapped_column(Integer, default=8)
    language: Mapped[str] = mapped_column(String(10), default="en")
    max_signals_per_day: Mapped[int] = mapped_column(Integer, default=5)
    compact_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    backtest_slippage_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

class TradeJournal(Base):
    __tablename__ = "trade_journal"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    direction: Mapped[str] = mapped_column(String(20))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pips: Mapped[float] = mapped_column(Float, default=0.0)
    is_win: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy: Mapped[str] = mapped_column(String(100), default="")
    timeframe: Mapped[str] = mapped_column(String(20), default="H1")
    regime: Mapped[str] = mapped_column(String(50), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    indicators_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    patterns_snapshot: Mapped[list[Any]] = mapped_column(JSON, default=list)
    causal_chain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open")

class PatternStat(Base):
    __tablename__ = "pattern_stats"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pattern_name: Mapped[str] = mapped_column(String(100), index=True)
    timeframe: Mapped[str] = mapped_column(String(20))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    predicted_direction: Mapped[str] = mapped_column(String(20))
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    price_at_detection: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_at_resolution: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    causal_chain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class LearningInsight(Base):
    __tablename__ = "learning_insights"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(50))
    accuracy: Mapped[float] = mapped_column(Float)
    factors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    recommendations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class UserThread(Base):
    __tablename__ = "user_threads"
    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    thread_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
