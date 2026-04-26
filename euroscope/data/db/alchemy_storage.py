import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from sqlalchemy import select, update, delete, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from euroscope.data.db.engine import DatabaseManager
from euroscope.data.db.models import (
    Prediction, TransactionLog, Alert, MarketNote, Memory,
    TradingSignal, NewsEvent, PerformanceMetric, UserPreference,
    TradeJournal, PatternStat, LearningInsight, UserThread
)

logger = logging.getLogger("euroscope.data.db.alchemy_storage")

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class SQLAlchemyStorage:
    """Async SQLAlchemy-based storage for EuroScope."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def close(self):
        await self.db.close()

    # ── Memory (Key-Value) ───────────────────────────────────

    async def set_memory(self, key: str, value: str) -> None:
        async for session in self.db.get_session():
            stmt = select(Memory).where(Memory.key == key)
            result = await session.execute(stmt)
            mem = result.scalar_one_or_none()
            if mem:
                mem.value = value
                mem.updated_at = utc_now()
            else:
                mem = Memory(key=key, value=value)
                session.add(mem)

    async def get_memory(self, key: str) -> Optional[str]:
        async for session in self.db.get_session():
            stmt = select(Memory).where(Memory.key == key)
            result = await session.execute(stmt)
            mem = result.scalar_one_or_none()
            return mem.value if mem else None

    async def save_json(self, key: str, data: Any) -> None:
        await self.set_memory(key, json.dumps(data))

    async def load_json(self, key: str, default: Any = None) -> Any:
        val = await self.get_memory(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return default
        return default

    # ── Predictions ──────────────────────────────────────────

    async def save_prediction(self, timeframe: str, direction: str, confidence: float, reasoning: str = "", target_price: float = None) -> int:
        async for session in self.db.get_session():
            pred = Prediction(
                timeframe=timeframe,
                direction=direction,
                confidence=confidence,
                reasoning=reasoning,
                target_price=target_price
            )
            session.add(pred)
            await session.flush()
            return pred.id

    async def resolve_prediction(self, prediction_id: int, actual_outcome: str, accuracy_score: float) -> None:
        async for session in self.db.get_session():
            stmt = update(Prediction).where(Prediction.id == prediction_id).values(
                actual_outcome=actual_outcome,
                accuracy_score=accuracy_score,
                resolved_at=utc_now()
            )
            await session.execute(stmt)

    async def get_unresolved_predictions(self) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(Prediction).where(Prediction.resolved_at.is_(None))
            result = await session.execute(stmt)
            return [
                {
                    "id": p.id,
                    "timestamp": p.timestamp.isoformat(),
                    "timeframe": p.timeframe,
                    "direction": p.direction,
                    "confidence": p.confidence,
                    "reasoning": p.reasoning,
                    "target_price": p.target_price
                } for p in result.scalars().all()
            ]

    async def get_accuracy_stats(self) -> dict:
        async for session in self.db.get_session():
            stmt = select(Prediction.accuracy_score).where(Prediction.accuracy_score.is_not(None))
            result = await session.execute(stmt)
            scores = result.scalars().all()
            
            if not scores:
                return {"overall_accuracy": 0.0, "total_resolved": 0}
            
            return {
                "overall_accuracy": sum(scores) / len(scores),
                "total_resolved": len(scores)
            }

    # ── Alerts ───────────────────────────────────────────────

    async def add_alert(self, condition: str, target_value: float, chat_id: int = None) -> int:
        async for session in self.db.get_session():
            alert = Alert(condition=condition, target_value=target_value, chat_id=chat_id)
            session.add(alert)
            await session.flush()
            return alert.id

    async def get_active_alerts(self) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(Alert).where(Alert.triggered == False)
            result = await session.execute(stmt)
            return [
                {
                    "id": a.id, "created_at": a.created_at.isoformat(),
                    "condition": a.condition, "target_value": a.target_value, "chat_id": a.chat_id
                } for a in result.scalars().all()
            ]

    async def trigger_alert(self, alert_id: int) -> None:
        async for session in self.db.get_session():
            stmt = update(Alert).where(Alert.id == alert_id).values(triggered=True, triggered_at=utc_now())
            await session.execute(stmt)

    async def get_user_alerts(self, chat_id: int) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(Alert).where(Alert.chat_id == chat_id, Alert.triggered == False)
            result = await session.execute(stmt)
            return [
                {
                    "id": a.id, "created_at": a.created_at.isoformat(),
                    "condition": a.condition, "target_value": a.target_value
                } for a in result.scalars().all()
            ]

    async def delete_alert(self, alert_id: int) -> None:
        async for session in self.db.get_session():
            stmt = delete(Alert).where(Alert.id == alert_id)
            await session.execute(stmt)

    # ── User Preferences ─────────────────────────────────────

    async def get_user_preferences(self, chat_id: int) -> dict:
        async for session in self.db.get_session():
            stmt = select(UserPreference).where(UserPreference.chat_id == chat_id)
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()
            if not pref:
                return {}
            return {
                "chat_id": pref.chat_id,
                "risk_tolerance": pref.risk_tolerance,
                "preferred_timeframe": pref.preferred_timeframe,
                "alert_on_signals": pref.alert_on_signals,
                "alert_on_news": pref.alert_on_news,
                "alert_min_confidence": pref.alert_min_confidence,
                "daily_report_enabled": pref.daily_report_enabled,
                "daily_report_hour": pref.daily_report_hour,
                "language": pref.language,
                "max_signals_per_day": pref.max_signals_per_day,
                "compact_mode": pref.compact_mode,
                "backtest_slippage_enabled": pref.backtest_slippage_enabled
            }

    async def save_user_preferences(self, chat_id: int, prefs: dict) -> None:
        async for session in self.db.get_session():
            stmt = select(UserPreference).where(UserPreference.chat_id == chat_id)
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()
            
            if not pref:
                pref = UserPreference(chat_id=chat_id)
                session.add(pref)
                
            for k, v in prefs.items():
                if hasattr(pref, k) and k != "id" and k != "chat_id":
                    setattr(pref, k, v)
                    
    # ── Trading Signals & Journal (Skeleton to be expanded) ───

    async def get_signals(self, limit: int = 50) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(TradingSignal).order_by(desc(TradingSignal.created_at)).limit(limit)
            result = await session.execute(stmt)
            return [
                {
                    "id": s.id, "created_at": s.created_at.isoformat(),
                    "direction": s.direction, "entry_price": s.entry_price,
                    "stop_loss": s.stop_loss, "take_profit": s.take_profit,
                    "confidence": s.confidence, "timeframe": s.timeframe,
                    "status": s.status, "pnl_pips": s.pnl_pips
                } for s in result.scalars().all()
            ]
