import json
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, List, Dict

from sqlalchemy import select, update, delete, desc, text, func, cast, Date
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
                timeframe=timeframe, direction=direction, confidence=confidence,
                reasoning=reasoning, target_price=target_price
            )
            session.add(pred)
            await session.flush()
            return pred.id

    async def resolve_prediction(self, prediction_id: int, actual_outcome: str, accuracy_score: float) -> None:
        async for session in self.db.get_session():
            stmt = update(Prediction).where(Prediction.id == prediction_id).values(
                actual_outcome=actual_outcome, accuracy_score=accuracy_score, resolved_at=utc_now()
            )
            await session.execute(stmt)

    async def get_unresolved_predictions(self) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(Prediction).where(Prediction.resolved_at.is_(None))
            result = await session.execute(stmt)
            return [{"id": p.id, "timestamp": p.timestamp.isoformat(), "timeframe": p.timeframe, "direction": p.direction, "confidence": p.confidence, "reasoning": p.reasoning, "target_price": p.target_price} for p in result.scalars().all()]

    async def get_accuracy_stats(self) -> dict:
        async for session in self.db.get_session():
            stmt = select(Prediction.accuracy_score).where(Prediction.accuracy_score.is_not(None))
            result = await session.execute(stmt)
            scores = result.scalars().all()
            if not scores: return {"overall_accuracy": 0.0, "total_resolved": 0}
            return {"overall_accuracy": sum(scores) / len(scores), "total_resolved": len(scores)}

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
            return [{"id": a.id, "created_at": a.created_at.isoformat(), "condition": a.condition, "target_value": a.target_value, "chat_id": a.chat_id} for a in result.scalars().all()]

    async def trigger_alert(self, alert_id: int) -> None:
        async for session in self.db.get_session():
            stmt = update(Alert).where(Alert.id == alert_id).values(triggered=True, triggered_at=utc_now())
            await session.execute(stmt)

    async def get_user_alerts(self, chat_id: int) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(Alert).where(Alert.chat_id == chat_id, Alert.triggered == False)
            result = await session.execute(stmt)
            return [{"id": a.id, "created_at": a.created_at.isoformat(), "condition": a.condition, "target_value": a.target_value} for a in result.scalars().all()]

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
            if not pref: return {}
            return {"chat_id": pref.chat_id, "risk_tolerance": pref.risk_tolerance, "preferred_timeframe": pref.preferred_timeframe, "alert_on_signals": pref.alert_on_signals, "alert_on_news": pref.alert_on_news, "alert_min_confidence": pref.alert_min_confidence, "daily_report_enabled": pref.daily_report_enabled, "daily_report_hour": pref.daily_report_hour, "language": pref.language, "max_signals_per_day": pref.max_signals_per_day, "compact_mode": pref.compact_mode, "backtest_slippage_enabled": pref.backtest_slippage_enabled}

    async def save_user_preferences(self, chat_id: int, prefs: dict) -> None:
        async for session in self.db.get_session():
            stmt = select(UserPreference).where(UserPreference.chat_id == chat_id)
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()
            if not pref:
                pref = UserPreference(chat_id=chat_id)
                session.add(pref)
            for k, v in prefs.items():
                if hasattr(pref, k) and k not in ("id", "chat_id"):
                    setattr(pref, k, v)

    # ── Market Notes ─────────────────────────────────────────

    async def add_note(self, category: str, content: str, metadata: dict = None) -> int:
        async for session in self.db.get_session():
            note = MarketNote(category=category, content=content, metadata_json=metadata)
            session.add(note)
            await session.flush()
            return note.id

    async def get_recent_notes(self, limit: int = 10, category: str = None) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(MarketNote).order_by(desc(MarketNote.timestamp)).limit(limit)
            if category:
                stmt = stmt.where(MarketNote.category == category)
            result = await session.execute(stmt)
            return [{"id": n.id, "timestamp": n.timestamp.isoformat(), "category": n.category, "content": n.content, "metadata": n.metadata_json} for n in result.scalars().all()]

    # ── Trading Signals ──────────────────────────────────────

    async def save_signal(self, direction: str, entry_price: float, stop_loss: float, take_profit: float, confidence: float, timeframe: str, source: str = "system", reasoning: str = "", risk_reward_ratio: float = 0.0) -> int:
        async for session in self.db.get_session():
            sig = TradingSignal(direction=direction, entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit, confidence=confidence, timeframe=timeframe, source=source, reasoning=reasoning, risk_reward_ratio=risk_reward_ratio)
            session.add(sig)
            await session.flush()
            return sig.id

    async def update_signal_status(self, signal_id: int, status: str, pnl_pips: float = 0.0) -> None:
        async for session in self.db.get_session():
            values = {"status": status, "pnl_pips": pnl_pips}
            if status in ("closed_win", "closed_loss", "cancelled"):
                values["closed_at"] = utc_now()
            stmt = update(TradingSignal).where(TradingSignal.id == signal_id).values(**values)
            await session.execute(stmt)

    async def update_signal_sl(self, signal_id: int, new_sl: float) -> None:
        async for session in self.db.get_session():
            stmt = update(TradingSignal).where(TradingSignal.id == signal_id).values(stop_loss=new_sl)
            await session.execute(stmt)

    async def get_signals(self, status: str = None, limit: int = 50) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(TradingSignal).order_by(desc(TradingSignal.created_at)).limit(limit)
            if status:
                stmt = stmt.where(TradingSignal.status == status)
            result = await session.execute(stmt)
            return [{"id": s.id, "created_at": s.created_at.isoformat(), "direction": s.direction, "entry_price": s.entry_price, "stop_loss": s.stop_loss, "take_profit": s.take_profit, "confidence": s.confidence, "timeframe": s.timeframe, "status": s.status, "pnl_pips": s.pnl_pips, "risk_reward_ratio": s.risk_reward_ratio, "reasoning": s.reasoning, "closed_at": s.closed_at.isoformat() if s.closed_at else None} for s in result.scalars().all()]

    # ── Trade Journal ────────────────────────────────────────

    async def save_trade_journal(self, direction: str, entry_price: float, stop_loss: float, take_profit: float, strategy: str = "", timeframe: str = "H1", regime: str = "", confidence: float = 0.0, indicators_snapshot: dict = None, patterns_snapshot: list = None, reasoning: str = "", causal_chain: str = None) -> int:
        async for session in self.db.get_session():
            trade = TradeJournal(direction=direction, entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit, strategy=strategy, timeframe=timeframe, regime=regime, confidence=confidence, indicators_snapshot=indicators_snapshot or {}, patterns_snapshot=patterns_snapshot or [], reasoning=reasoning, causal_chain=causal_chain)
            session.add(trade)
            await session.flush()
            return trade.id

    async def update_trade_journal_sl(self, trade_id: int, new_sl: float) -> None:
        async for session in self.db.get_session():
            stmt = update(TradeJournal).where(TradeJournal.id == trade_id).values(stop_loss=new_sl)
            await session.execute(stmt)

    async def close_trade_journal(self, trade_id: int, exit_price: float, pnl_pips: float, is_win: bool) -> None:
        async for session in self.db.get_session():
            stmt = update(TradeJournal).where(TradeJournal.id == trade_id).values(exit_price=exit_price, pnl_pips=pnl_pips, is_win=is_win, closed_at=utc_now(), status="closed")
            await session.execute(stmt)

    async def get_trade_journal(self, limit: int = 50, status: str = None) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(TradeJournal).order_by(desc(TradeJournal.timestamp)).limit(limit)
            if status:
                stmt = stmt.where(TradeJournal.status == status)
            result = await session.execute(stmt)
            return [{"id": t.id, "timestamp": t.timestamp.isoformat(), "direction": t.direction, "entry_price": t.entry_price, "exit_price": t.exit_price, "stop_loss": t.stop_loss, "take_profit": t.take_profit, "pnl_pips": t.pnl_pips, "is_win": bool(t.is_win), "strategy": t.strategy, "timeframe": t.timeframe, "regime": t.regime, "confidence": t.confidence, "indicators_snapshot": t.indicators_snapshot, "patterns_snapshot": t.patterns_snapshot, "causal_chain": t.causal_chain, "reasoning": t.reasoning, "status": t.status, "closed_at": t.closed_at.isoformat() if t.closed_at else None} for t in result.scalars().all()]

    async def get_trade_with_causal(self, trade_id: int) -> Optional[dict]:
        async for session in self.db.get_session():
            stmt = select(TradeJournal).where(TradeJournal.id == trade_id)
            result = await session.execute(stmt)
            t = result.scalar_one_or_none()
            if not t: return None
            return {"id": t.id, "timestamp": t.timestamp.isoformat(), "direction": t.direction, "pnl_pips": t.pnl_pips, "strategy": t.strategy, "causal_chain": t.causal_chain, "reasoning": t.reasoning, "is_win": bool(t.is_win)}

    async def get_trade_journal_stats(self, period_days: int = 30) -> dict:
        cutoff = utc_now() - timedelta(days=period_days)
        async for session in self.db.get_session():
            stmt = select(TradeJournal).where(TradeJournal.status == "closed", TradeJournal.timestamp >= cutoff)
            result = await session.execute(stmt)
            trades = result.scalars().all()
            if not trades:
                return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0, "profit_factor": 0.0}
            wins = [t for t in trades if t.is_win]
            gross_profit = sum(t.pnl_pips for t in wins)
            gross_loss = sum(abs(t.pnl_pips) for t in trades if not t.is_win)
            return {"total_trades": len(trades), "win_rate": len(wins) / len(trades), "total_pnl": sum(t.pnl_pips for t in trades), "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf")}

    async def get_trade_journal_for_date(self, target_date: str) -> List[dict]:
        # simplified for date matching
        async for session in self.db.get_session():
            stmt = select(TradeJournal).where(cast(TradeJournal.timestamp, Date) == datetime.fromisoformat(target_date).date())
            result = await session.execute(stmt)
            return [{"id": t.id, "timestamp": t.timestamp.isoformat(), "direction": t.direction, "pnl_pips": t.pnl_pips, "is_win": bool(t.is_win), "strategy": t.strategy} for t in result.scalars().all()]

    async def get_trade_journal_for_period(self, start_date: str, end_date: str) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(TradeJournal).where(TradeJournal.timestamp >= datetime.fromisoformat(start_date), TradeJournal.timestamp <= datetime.fromisoformat(end_date))
            result = await session.execute(stmt)
            return [{"id": t.id, "timestamp": t.timestamp.isoformat(), "direction": t.direction, "pnl_pips": t.pnl_pips, "is_win": bool(t.is_win), "strategy": t.strategy} for t in result.scalars().all()]

    # ── Transaction Logs ─────────────────────────────────────

    async def log_transaction(self, action: str, payload: dict, status: str = "pending") -> int:
        async for session in self.db.get_session():
            t = TransactionLog(action=action, payload=json.dumps(payload), status=status)
            session.add(t)
            await session.flush()
            return t.id

    async def update_transaction_status(self, tx_id: int, status: str) -> None:
        async for session in self.db.get_session():
            stmt = update(TransactionLog).where(TransactionLog.id == tx_id).values(status=status)
            await session.execute(stmt)

    async def get_pending_transactions(self) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(TransactionLog).where(TransactionLog.status == "pending")
            result = await session.execute(stmt)
            return [{"id": t.id, "action": t.action, "payload": json.loads(t.payload), "status": t.status} for t in result.scalars().all()]

    # ── News & Performance ───────────────────────────────────

    async def save_news_event(self, title: str, source: str, url: str = None, description: str = None, impact_score: float = 0.0, sentiment: str = "neutral", sentiment_score: float = 0.0, currency_impact: str = None, published_at: str = None) -> int:
        async for session in self.db.get_session():
            pub_date = datetime.fromisoformat(published_at) if published_at else None
            news = NewsEvent(title=title, source=source, url=url, description=description, impact_score=impact_score, sentiment=sentiment, sentiment_score=sentiment_score, currency_impact=currency_impact, published_at=pub_date)
            session.add(news)
            await session.flush()
            return news.id

    async def get_recent_news(self, limit: int = 10, min_impact: float = 0.0) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(NewsEvent).where(NewsEvent.impact_score >= min_impact).order_by(desc(NewsEvent.fetched_at)).limit(limit)
            result = await session.execute(stmt)
            return [{"id": n.id, "title": n.title, "source": n.source, "url": n.url, "impact_score": n.impact_score, "sentiment": n.sentiment, "published_at": n.published_at.isoformat() if n.published_at else None} for n in result.scalars().all()]

    async def save_performance_metric(self, period: str, metrics: dict) -> int:
        async for session in self.db.get_session():
            pm = PerformanceMetric(period=period, **{k: v for k, v in metrics.items() if hasattr(PerformanceMetric, k)})
            session.add(pm)
            await session.flush()
            return pm.id

    async def get_latest_metrics(self, limit: int = 10) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(PerformanceMetric).order_by(desc(PerformanceMetric.calculated_at)).limit(limit)
            result = await session.execute(stmt)
            return [{"id": m.id, "period": m.period, "win_rate": m.win_rate, "total_pnl_pips": m.total_pnl_pips, "profit_factor": m.profit_factor, "sharpe_ratio": m.sharpe_ratio, "calculated_at": m.calculated_at.isoformat()} for m in result.scalars().all()]

    # ── Pattern Stats ────────────────────────────────────────

    async def save_pattern_detection(self, pattern_name: str, timeframe: str, predicted_direction: str, price_at_detection: float, causal_chain: str = None) -> int:
        async for session in self.db.get_session():
            p = PatternStat(pattern_name=pattern_name, timeframe=timeframe, predicted_direction=predicted_direction, price_at_detection=price_at_detection, causal_chain=causal_chain, detected_at=utc_now())
            session.add(p)
            await session.flush()
            return p.id

    async def resolve_pattern(self, pattern_id: int, actual_outcome: str, is_success: bool, price_at_resolution: float, causal_chain: str = None) -> None:
        async for session in self.db.get_session():
            stmt = update(PatternStat).where(PatternStat.id == pattern_id).values(actual_outcome=actual_outcome, is_success=is_success, price_at_resolution=price_at_resolution, resolved_at=utc_now())
            if causal_chain:
                stmt = stmt.values(causal_chain=causal_chain)
            await session.execute(stmt)

    async def get_pattern_success_rates(self, timeframe: str = None) -> dict:
        async for session in self.db.get_session():
            stmt = select(PatternStat).where(PatternStat.resolved_at.is_not(None))
            if timeframe: stmt = stmt.where(PatternStat.timeframe == timeframe)
            result = await session.execute(stmt)
            patterns = result.scalars().all()
            stats = {}
            for p in patterns:
                if p.pattern_name not in stats: stats[p.pattern_name] = {"success": 0, "total": 0}
                stats[p.pattern_name]["total"] += 1
                if p.is_success: stats[p.pattern_name]["success"] += 1
            return {k: {"win_rate": v["success"]/v["total"], "count": v["total"]} for k, v in stats.items()}

    async def get_unresolved_patterns(self) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(PatternStat).where(PatternStat.resolved_at.is_(None))
            result = await session.execute(stmt)
            return [{"id": p.id, "pattern_name": p.pattern_name, "timeframe": p.timeframe, "predicted_direction": p.predicted_direction, "price_at_detection": p.price_at_detection, "detected_at": p.detected_at.isoformat()} for p in result.scalars().all()]

    async def get_resolved_patterns(self, limit: int = 50) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(PatternStat).where(PatternStat.resolved_at.is_not(None)).order_by(desc(PatternStat.resolved_at)).limit(limit)
            result = await session.execute(stmt)
            return [{"id": p.id, "pattern_name": p.pattern_name, "is_success": p.is_success} for p in result.scalars().all()]

    async def get_similar_patterns(self, pattern_name: str, timeframe: str, limit: int = 5) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(PatternStat).where(PatternStat.pattern_name == pattern_name, PatternStat.timeframe == timeframe, PatternStat.resolved_at.is_not(None)).order_by(desc(PatternStat.resolved_at)).limit(limit)
            result = await session.execute(stmt)
            return [{"id": p.id, "is_success": p.is_success, "causal_chain": p.causal_chain} for p in result.scalars().all()]

    # ── Learning & Threads ───────────────────────────────────

    async def save_learning_insight(self, trade_id: str, accuracy: float, factors: list, recommendations: list) -> int:
        async for session in self.db.get_session():
            ins = LearningInsight(trade_id=trade_id, accuracy=accuracy, factors=factors, recommendations=recommendations)
            session.add(ins)
            await session.flush()
            return ins.id

    async def get_recent_learning_insights(self, limit: int = 5) -> List[dict]:
        async for session in self.db.get_session():
            stmt = select(LearningInsight).order_by(desc(LearningInsight.timestamp)).limit(limit)
            result = await session.execute(stmt)
            return [{"id": i.id, "trade_id": i.trade_id, "accuracy": i.accuracy, "factors": i.factors, "recommendations": i.recommendations, "timestamp": i.timestamp.isoformat()} for i in result.scalars().all()]

    async def save_user_thread(self, chat_id: int, topic_key: str, thread_id: int) -> None:
        async for session in self.db.get_session():
            stmt = select(UserThread).where(UserThread.chat_id == chat_id, UserThread.topic_key == topic_key)
            result = await session.execute(stmt)
            ut = result.scalar_one_or_none()
            if ut: ut.thread_id = thread_id
            else: session.add(UserThread(chat_id=chat_id, topic_key=topic_key, thread_id=thread_id))

    async def get_user_thread(self, chat_id: int, topic_key: str) -> Optional[int]:
        async for session in self.db.get_session():
            stmt = select(UserThread).where(UserThread.chat_id == chat_id, UserThread.topic_key == topic_key)
            result = await session.execute(stmt)
            ut = result.scalar_one_or_none()
            return ut.thread_id if ut else None

    async def get_all_user_threads(self, chat_id: int) -> dict:
        async for session in self.db.get_session():
            stmt = select(UserThread).where(UserThread.chat_id == chat_id)
            result = await session.execute(stmt)
            return {ut.topic_key: ut.thread_id for ut in result.scalars().all()}

    async def backup_database(self, dest_dir: str = "backups") -> str:
        # SQLite specific backup logic, safe to ignore or adapt for Postgres via pg_dump
        if "sqlite" in str(self.db.engine.url):
            dest = Path(dest_dir)
            dest.mkdir(parents=True, exist_ok=True)
            db_path = str(self.db.engine.url).replace("sqlite+aiosqlite:///", "")
            backup_file = dest / f"euroscope_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(db_path, backup_file)
            return str(backup_file)
        return "PostgreSQL backups should be handled via pg_dump or managed services PITR."
