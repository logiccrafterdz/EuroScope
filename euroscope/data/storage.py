"""
Async SQLite Storage Layer

Stores predictions, accuracy tracking, alerts, trading signals,
news events, performance metrics, user preferences, and cached data.

Uses aiosqlite for non-blocking async I/O with WAL mode enabled
for concurrent read safety.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger("euroscope.data.storage")


class Storage:
    """Async SQLite-based storage for EuroScope.

    Initialization (table creation) is done synchronously at startup.
    All runtime read/write methods are async using aiosqlite with WAL mode.
    """

    def __init__(self, db_path: str = "data/euroscope.db"):
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Synchronous init for table creation (runs once at startup)
        self._sync_init()

        # Async connection (lazy, opened on first use)
        self._db: Optional[aiosqlite.Connection] = None

    def _sync_init(self):
        """Create tables synchronously at startup."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reasoning TEXT,
                    target_price REAL,
                    actual_outcome TEXT,
                    accuracy_score REAL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    target_value REAL,
                    triggered INTEGER DEFAULT 0,
                    triggered_at TEXT,
                    chat_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS market_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trading_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    confidence REAL NOT NULL,
                    timeframe TEXT NOT NULL,
                    source TEXT DEFAULT 'system',
                    status TEXT DEFAULT 'pending',
                    reasoning TEXT,
                    risk_reward_ratio REAL DEFAULT 0.0,
                    pnl_pips REAL DEFAULT 0.0,
                    closed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS news_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT,
                    description TEXT,
                    impact_score REAL DEFAULT 0.0,
                    sentiment TEXT DEFAULT 'neutral',
                    sentiment_score REAL DEFAULT 0.0,
                    currency_impact TEXT,
                    published_at TEXT,
                    fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period TEXT NOT NULL,
                    total_signals INTEGER DEFAULT 0,
                    winning_signals INTEGER DEFAULT 0,
                    losing_signals INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0.0,
                    total_pnl_pips REAL DEFAULT 0.0,
                    avg_pnl_pips REAL DEFAULT 0.0,
                    max_drawdown_pips REAL DEFAULT 0.0,
                    profit_factor REAL DEFAULT 0.0,
                    sharpe_ratio REAL DEFAULT 0.0,
                    avg_risk_reward REAL DEFAULT 0.0,
                    best_trade_pips REAL DEFAULT 0.0,
                    worst_trade_pips REAL DEFAULT 0.0,
                    avg_trade_duration_hours REAL DEFAULT 0.0,
                    calculated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE NOT NULL,
                    risk_tolerance TEXT DEFAULT 'medium',
                    preferred_timeframe TEXT DEFAULT 'H1',
                    alert_on_signals INTEGER DEFAULT 1,
                    alert_on_news INTEGER DEFAULT 1,
                    alert_min_confidence REAL DEFAULT 60.0,
                    daily_report_enabled INTEGER DEFAULT 1,
                    daily_report_hour INTEGER DEFAULT 8,
                    language TEXT DEFAULT 'en',
                    max_signals_per_day INTEGER DEFAULT 5,
                    compact_mode INTEGER DEFAULT 0,
                    backtest_slippage_enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    pnl_pips REAL DEFAULT 0.0,
                    is_win INTEGER DEFAULT 0,
                    strategy TEXT DEFAULT '',
                    timeframe TEXT DEFAULT 'H1',
                    regime TEXT DEFAULT '',
                    confidence REAL DEFAULT 0.0,
                    indicators_snapshot TEXT DEFAULT '{}',
                    patterns_snapshot TEXT DEFAULT '[]',
                    causal_chain TEXT,
                    reasoning TEXT DEFAULT '',
                    closed_at TEXT,
                    status TEXT DEFAULT 'open'
                );

                CREATE TABLE IF NOT EXISTS pattern_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_name TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    predicted_direction TEXT NOT NULL,
                    actual_outcome TEXT,
                    is_success INTEGER,
                    price_at_detection REAL,
                    price_at_resolution REAL,
                    resolved_at TEXT,
                    causal_chain TEXT
                );

                CREATE TABLE IF NOT EXISTS learning_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT NOT NULL,
                    accuracy REAL NOT NULL,
                    factors TEXT DEFAULT '[]',
                    recommendations TEXT DEFAULT '[]',
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_threads (
                    chat_id INTEGER NOT NULL,
                    topic_key TEXT NOT NULL,
                    thread_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, topic_key)
                );
            """)
            self._ensure_columns_sync(conn)
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
        finally:
            conn.close()

    @staticmethod
    def _ensure_columns_sync(conn: sqlite3.Connection):
        """Ensure extra columns exist (migration support)."""
        for table, column, col_def in [
            ("user_preferences", "compact_mode", "INTEGER DEFAULT 0"),
            ("user_preferences", "backtest_slippage_enabled", "INTEGER DEFAULT 1"),
            ("pattern_stats", "causal_chain", "TEXT"),
            ("trade_journal", "causal_chain", "TEXT"),
        ]:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pattern_stats_name_time ON pattern_stats(pattern_name, detected_at)"
        )

    # ── Async Connection Management ──────────────────────────

    async def _get_db(self) -> aiosqlite.Connection:
        """Get or create the async database connection with WAL mode."""
        if self._db is None:
            self._db = await aiosqlite.connect(str(self.db_path), timeout=30.0)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.execute("PRAGMA busy_timeout=30000")
        return self._db

    async def close(self):
        """Close the async database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _query_rows(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a SELECT query and return results as a list of dicts."""
        db = await self._get_db()
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def _query_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Execute a SELECT query and return one result as dict or None."""
        db = await self._get_db()
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    # --- Predictions ---

    async def save_prediction(self, timeframe: str, direction: str, confidence: float,
                        reasoning: str = "", target_price: float = None) -> int:
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO predictions (timestamp, timeframe, direction, confidence, reasoning, target_price)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), timeframe, direction, confidence, reasoning, target_price)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def resolve_prediction(self, pred_id: int, outcome: str, accuracy: float):
        db = await self._get_db()
        await db.execute(
            """UPDATE predictions SET actual_outcome=?, accuracy_score=?, resolved_at=? WHERE id=?""",
            (outcome, accuracy, datetime.now(timezone.utc).isoformat(), pred_id)
        )
        await db.commit()

    async def get_accuracy_stats(self, days: int = 30) -> dict:
        rows = await self._query_rows(
            """SELECT direction, accuracy_score FROM predictions
                WHERE resolved_at IS NOT NULL
                AND timestamp > datetime('now', ?)""",
            (f"-{days} days",)
        )

        if not rows:
            return {"total": 0, "accuracy": 0.0, "message": "No resolved predictions yet"}

        correct = sum(1 for r in rows if r["accuracy_score"] and r["accuracy_score"] >= 0.5)
        return {
            "total": len(rows),
            "correct": correct,
            "accuracy": round(correct / len(rows) * 100, 1),
            "by_direction": self._accuracy_by_direction(rows),
        }

    @staticmethod
    def _accuracy_by_direction(rows) -> dict:
        from collections import defaultdict
        stats = defaultdict(lambda: {"total": 0, "correct": 0})
        for r in rows:
            direction = r["direction"]
            score = r["accuracy_score"]
            stats[direction]["total"] += 1
            if score and score >= 0.5:
                stats[direction]["correct"] += 1
        return {
            d: {**s, "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] else 0}
            for d, s in stats.items()
        }

    async def get_unresolved_predictions(self) -> list[dict]:
        return await self._query_rows(
            "SELECT * FROM predictions WHERE resolved_at IS NULL ORDER BY timestamp DESC"
        )

    # --- Alerts ---

    async def add_alert(self, condition: str, target_value: float, chat_id: int) -> int:
        db = await self._get_db()
        async with db.execute(
            "INSERT INTO alerts (created_at, condition, target_value, chat_id) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), condition, target_value, chat_id)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def get_active_alerts(self) -> list[dict]:
        return await self._query_rows("SELECT * FROM alerts WHERE triggered = 0")

    async def get_user_alerts(self, chat_id: int) -> list[dict]:
        """Get all active alerts for a specific user."""
        return await self._query_rows(
            "SELECT * FROM alerts WHERE chat_id = ? AND triggered = 0",
            (chat_id,)
        )

    async def trigger_alert(self, alert_id: int):
        db = await self._get_db()
        await db.execute(
            "UPDATE alerts SET triggered=1, triggered_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), alert_id)
        )
        await db.commit()

    async def delete_alert(self, alert_id: int):
        """Permanently delete an alert."""
        db = await self._get_db()
        await db.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
        await db.commit()

    # --- Memory (key-value for learning) ---

    async def set_memory(self, key: str, value: Any):
        data = json.dumps(value) if not isinstance(value, str) else value
        db = await self._get_db()
        await db.execute(
            "INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?, ?, ?)",
            (key, data, datetime.now(timezone.utc).isoformat())
        )
        await db.commit()

    async def get_memory(self, key: str) -> Optional[str]:
        db = await self._get_db()
        async with db.execute("SELECT value FROM memory WHERE key=?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def save_json(self, key: str, value: Any):
        """Save a JSON-serializable value to the memory table."""
        await self.set_memory(key, json.dumps(value))

    async def load_json(self, key: str) -> Optional[Any]:
        """Load a JSON value from the memory table."""
        raw = await self.get_memory(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    # --- Market Notes ---

    async def add_note(self, category: str, content: str, metadata: dict = None):
        db = await self._get_db()
        await db.execute(
            "INSERT INTO market_notes (timestamp, category, content, metadata) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), category, content,
             json.dumps(metadata) if metadata else None)
        )
        await db.commit()

    async def get_recent_notes(self, category: str = None, limit: int = 20) -> list[dict]:
        if category:
            return await self._query_rows(
                "SELECT * FROM market_notes WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                (category, limit)
            )
        else:
            return await self._query_rows(
                "SELECT * FROM market_notes ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )

    # --- Trading Signals ---

    async def save_signal(self, direction: str, entry_price: float, stop_loss: float,
                    take_profit: float, confidence: float, timeframe: str,
                    source: str = "system", reasoning: str = "",
                    risk_reward_ratio: float = 0.0) -> int:
        """Save a new trading signal."""
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO trading_signals
               (created_at, direction, entry_price, stop_loss, take_profit,
                confidence, timeframe, source, reasoning, risk_reward_ratio)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), direction, entry_price, stop_loss,
             take_profit, confidence, timeframe, source, reasoning, risk_reward_ratio)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def update_signal_status(self, signal_id: int, status: str, pnl_pips: float = 0.0):
        """Update a signal's status (active, closed, cancelled)."""
        closed_at = datetime.now(timezone.utc).isoformat() if status in ("closed", "cancelled") else None
        db = await self._get_db()
        await db.execute(
            "UPDATE trading_signals SET status=?, pnl_pips=?, closed_at=? WHERE id=?",
            (status, pnl_pips, closed_at, signal_id)
        )
        await db.commit()

    async def get_signals(self, status: str = None, limit: int = 20) -> list[dict]:
        """Get trading signals, optionally filtered by status."""
        if status:
            return await self._query_rows(
                "SELECT * FROM trading_signals WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            return await self._query_rows(
                "SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )

    # --- News Events ---

    async def save_news_event(self, title: str, source: str, url: str = "",
                        description: str = "", impact_score: float = 0.0,
                        sentiment: str = "neutral", sentiment_score: float = 0.0,
                        currency_impact: str = "", published_at: str = "") -> int:
        """Save a news event."""
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO news_events
               (title, source, url, description, impact_score, sentiment,
                sentiment_score, currency_impact, published_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, source, url, description, impact_score, sentiment,
             sentiment_score, currency_impact, published_at,
             datetime.now(timezone.utc).isoformat())
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def get_recent_news(self, limit: int = 20, min_impact: float = 0.0) -> list[dict]:
        """Get recent news events, optionally filtered by minimum impact."""
        return await self._query_rows(
            """SELECT * FROM news_events
                WHERE impact_score >= ?
                ORDER BY fetched_at DESC LIMIT ?""",
            (min_impact, limit)
        )

    # --- Performance Metrics ---

    async def save_performance_metric(self, period: str, total_signals: int = 0,
                                winning_signals: int = 0, losing_signals: int = 0,
                                win_rate: float = 0.0, total_pnl_pips: float = 0.0,
                                avg_pnl_pips: float = 0.0, max_drawdown_pips: float = 0.0,
                                profit_factor: float = 0.0, sharpe_ratio: float = 0.0,
                                avg_risk_reward: float = 0.0, best_trade_pips: float = 0.0,
                                worst_trade_pips: float = 0.0,
                                avg_trade_duration_hours: float = 0.0) -> int:
        """Save a performance metrics snapshot."""
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO performance_metrics
               (period, total_signals, winning_signals, losing_signals, win_rate,
                total_pnl_pips, avg_pnl_pips, max_drawdown_pips, profit_factor,
                sharpe_ratio, avg_risk_reward, best_trade_pips, worst_trade_pips,
                avg_trade_duration_hours, calculated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (period, total_signals, winning_signals, losing_signals, win_rate,
             total_pnl_pips, avg_pnl_pips, max_drawdown_pips, profit_factor,
             sharpe_ratio, avg_risk_reward, best_trade_pips, worst_trade_pips,
             avg_trade_duration_hours, datetime.now(timezone.utc).isoformat())
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def get_latest_metrics(self, period: str = "daily") -> Optional[dict]:
        """Get the most recent performance metrics for a period."""
        return await self._query_one(
            "SELECT * FROM performance_metrics WHERE period=? ORDER BY calculated_at DESC LIMIT 1",
            (period,)
        )

    # --- User Preferences ---

    async def save_user_preferences(self, chat_id: int, **kwargs) -> int:
        """Save or update user preferences (upsert)."""
        now = datetime.now(timezone.utc).isoformat()
        defaults = {
            "risk_tolerance": "medium",
            "preferred_timeframe": "H1",
            "alert_on_signals": 1,
            "alert_on_news": 1,
            "alert_min_confidence": 60.0,
            "daily_report_enabled": 1,
            "daily_report_hour": 8,
            "language": "en",
            "max_signals_per_day": 5,
            "compact_mode": 0,
            "backtest_slippage_enabled": 1,
        }
        defaults.update(kwargs)

        db = await self._get_db()
        async with db.execute(
            """INSERT INTO user_preferences
               (chat_id, risk_tolerance, preferred_timeframe, alert_on_signals,
                alert_on_news, alert_min_confidence, daily_report_enabled,
                daily_report_hour, language, max_signals_per_day, compact_mode,
                backtest_slippage_enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                risk_tolerance=excluded.risk_tolerance,
                preferred_timeframe=excluded.preferred_timeframe,
                alert_on_signals=excluded.alert_on_signals,
                alert_on_news=excluded.alert_on_news,
                alert_min_confidence=excluded.alert_min_confidence,
                daily_report_enabled=excluded.daily_report_enabled,
                daily_report_hour=excluded.daily_report_hour,
                language=excluded.language,
                max_signals_per_day=excluded.max_signals_per_day,
                compact_mode=excluded.compact_mode,
                backtest_slippage_enabled=excluded.backtest_slippage_enabled,
                updated_at=excluded.updated_at""",
            (chat_id, defaults["risk_tolerance"], defaults["preferred_timeframe"],
             defaults["alert_on_signals"], defaults["alert_on_news"],
             defaults["alert_min_confidence"], defaults["daily_report_enabled"],
             defaults["daily_report_hour"], defaults["language"],
             defaults["max_signals_per_day"], defaults["compact_mode"],
             defaults["backtest_slippage_enabled"], now, now)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def get_user_preferences(self, chat_id: int) -> Optional[dict]:
        """Get preferences for a specific user."""
        return await self._query_one(
            "SELECT * FROM user_preferences WHERE chat_id=?", (chat_id,)
        )

    # ── Trade Journal ─────────────────────────────────────────

    async def save_trade_journal(self, direction: str, entry_price: float,
                           stop_loss: float = 0.0, take_profit: float = 0.0,
                           strategy: str = "", timeframe: str = "H1",
                           regime: str = "", confidence: float = 0.0,
                           indicators: dict = None, patterns: list = None,
                           reasoning: str = "", causal_chain: Any = None,
                           status: str = "open") -> int:
        """Save a new trade journal entry."""
        now = datetime.now(timezone.utc).isoformat()
        if isinstance(causal_chain, (dict, list)):
            causal_payload = json.dumps(causal_chain)
        else:
            causal_payload = causal_chain
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO trade_journal
               (timestamp, direction, entry_price, stop_loss, take_profit,
                strategy, timeframe, regime, confidence,
                indicators_snapshot, patterns_snapshot, causal_chain, reasoning, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, direction, entry_price, stop_loss, take_profit,
             strategy, timeframe, regime, confidence,
             json.dumps(indicators or {}),
             json.dumps(patterns or []),
             causal_payload,
             reasoning,
             status)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def close_trade_journal(self, trade_id: int, exit_price: float,
                             pnl_pips: float, is_win: bool):
        """Close a trade journal entry with outcome."""
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        await db.execute(
            """UPDATE trade_journal SET exit_price=?, pnl_pips=?,
               is_win=?, closed_at=?, status='closed'
               WHERE id=?""",
            (exit_price, pnl_pips, 1 if is_win else 0, now, trade_id)
        )
        await db.commit()

    async def get_trade_journal(self, strategy: str = None, status: str = None,
                          limit: int = 50) -> list[dict]:
        """Get trade journal entries, optionally filtered."""
        query = "SELECT * FROM trade_journal WHERE 1=1"
        params = []
        if strategy:
            query += " AND strategy=?"
            params.append(strategy)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        trades = await self._query_rows(query, tuple(params))
        for t in trades:
            t["causal_chain"] = self._parse_json_payload(t.get("causal_chain"))
        return trades

    async def get_trade_journal_for_date(self, date: str, status: str = None) -> list[dict]:
        try:
            day = datetime.fromisoformat(date)
        except ValueError:
            day = datetime.strptime(date, "%Y-%m-%d")
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        query = "SELECT * FROM trade_journal WHERE timestamp >= ? AND timestamp < ?"
        params: list[Any] = [start.isoformat(), end.isoformat()]
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY timestamp DESC"

        trades = await self._query_rows(query, tuple(params))
        for t in trades:
            t["causal_chain"] = self._parse_json_payload(t.get("causal_chain"))
        return trades

    async def get_trade_with_causal(self, trade_id: int) -> Optional[dict]:
        trade = await self._query_one(
            "SELECT * FROM trade_journal WHERE id=?",
            (trade_id,),
        )
        if not trade:
            return None
        trade["causal_chain"] = self._parse_json_payload(trade.get("causal_chain"))
        return trade

    async def get_trade_journal_stats(self, strategy: str = None) -> dict:
        """Get aggregate stats from trade journal."""
        query = "SELECT * FROM trade_journal WHERE status='closed'"
        params = []
        if strategy:
            query += " AND strategy=?"
            params.append(strategy)

        trades = await self._query_rows(query, tuple(params))

        if not trades:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                    "total_pnl": 0.0, "avg_pnl": 0.0}

        wins = [t for t in trades if t["is_win"]]
        total_pnl = sum(t["pnl_pips"] for t in trades)

        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(trades) - len(wins),
            "win_rate": round(len(wins) / len(trades) * 100, 1),
            "total_pnl": round(total_pnl, 1),
            "avg_pnl": round(total_pnl / len(trades), 1),
            "by_strategy": self._journal_by_strategy(trades),
        }

    @staticmethod
    def _journal_by_strategy(trades: list[dict]) -> dict:
        """Group trade journal stats by strategy."""
        by_strat = {}
        for t in trades:
            s = t.get("strategy", "unknown")
            if s not in by_strat:
                by_strat[s] = {"total": 0, "wins": 0, "pnl": 0.0}
            by_strat[s]["total"] += 1
            if t["is_win"]:
                by_strat[s]["wins"] += 1
            by_strat[s]["pnl"] += t["pnl_pips"]

        for s, data in by_strat.items():
            data["win_rate"] = round(data["wins"] / data["total"] * 100, 1) if data["total"] else 0
            data["pnl"] = round(data["pnl"], 1)

        return by_strat

    @staticmethod
    def _parse_json_payload(raw: Any) -> Any:
        if raw is None:
            return None
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    # ── Pattern Stats ─────────────────────────────────────────

    async def save_pattern_detection(self, pattern_name: str, timeframe: str,
                                predicted_direction: str,
                                price_at_detection: float,
                                causal_chain: Optional[dict] = None) -> int:
        """Record a new pattern detection."""
        now = datetime.now(timezone.utc).isoformat()
        causal_payload = json.dumps(causal_chain) if causal_chain else None
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO pattern_stats
               (pattern_name, timeframe, detected_at, predicted_direction,
                price_at_detection, causal_chain)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pattern_name, timeframe, now, predicted_direction,
             price_at_detection, causal_payload)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def resolve_pattern(self, pattern_id: int, actual_outcome: str,
                        price_at_resolution: float, is_success: bool):
        """Resolve a pattern detection with actual outcome."""
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        await db.execute(
            """UPDATE pattern_stats SET actual_outcome=?,
               price_at_resolution=?, is_success=?, resolved_at=?
               WHERE id=?""",
            (actual_outcome, price_at_resolution,
             1 if is_success else 0, now, pattern_id)
        )
        await db.commit()

    async def get_pattern_success_rates(self) -> dict:
        """Get success rates grouped by pattern_name + timeframe."""
        rows = await self._query_rows(
            """SELECT pattern_name, timeframe,
                COUNT(*) as total,
                SUM(CASE WHEN is_success=1 THEN 1 ELSE 0 END) as successes
                FROM pattern_stats
                WHERE is_success IS NOT NULL
                GROUP BY pattern_name, timeframe"""
        )

        result = {}
        for r in rows:
            key = f"{r['pattern_name']}_{r['timeframe']}"
            total = r["total"]
            successes = r["successes"]
            result[key] = {
                "pattern": r["pattern_name"],
                "timeframe": r["timeframe"],
                "total": total,
                "successes": successes,
                "success_rate": round(successes / total * 100, 1) if total else 0,
            }
        return result

    async def get_unresolved_patterns(self, limit: int = 50) -> list[dict]:
        """Get pattern detections that haven't been resolved yet."""
        return await self._query_rows(
            """SELECT * FROM pattern_stats
                WHERE is_success IS NULL
                ORDER BY detected_at DESC LIMIT ?""",
            (limit,)
        )

    async def get_resolved_patterns(self, limit: int = 50) -> list[dict]:
        """Get recently resolved patterns for reporting."""
        return await self._query_rows(
            """SELECT * FROM pattern_stats
                WHERE is_success IS NOT NULL
                ORDER BY resolved_at DESC LIMIT ?""",
            (limit,)
        )

    async def get_similar_patterns(
        self,
        pattern_name: str,
        timeframe: Optional[str] = None,
        min_similarity: float = 0.7,
        limit: int = 5,
    ) -> list[dict]:
        if not pattern_name:
            return []
        query = """SELECT *,
                          1.0 as similarity
                   FROM pattern_stats
                   WHERE pattern_name=?
                   AND is_success IS NOT NULL"""
        params: list[Any] = [pattern_name]
        if timeframe:
            query += " AND timeframe=?"
            params.append(timeframe)
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)
        results = await self._query_rows(query, tuple(params))
        return [r for r in results if r.get("similarity", 0) >= min_similarity]

    # ── Learning Insights ─────────────────────────────────────

    async def save_learning_insight(self, trade_id: str, accuracy: float,
                              factors: list[str], recommendations: list[str]) -> int:
        """Save a new learning insight extract from a trade."""
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        async with db.execute(
            """INSERT INTO learning_insights (trade_id, accuracy, factors, recommendations, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (trade_id, accuracy, json.dumps(factors), json.dumps(recommendations), now)
        ) as cursor:
            await db.commit()
            return cursor.lastrowid

    async def get_recent_learning_insights(self, limit: int = 20) -> list[dict]:
        """Get the most recent learning insights."""
        rows = await self._query_rows(
            "SELECT * FROM learning_insights ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        for r in rows:
            r["factors"] = self._parse_json_payload(r.get("factors"))
            r["recommendations"] = self._parse_json_payload(r.get("recommendations"))
        return rows

    # ─── User Threads (Private Topics) ───────────────────────

    async def save_user_thread(self, chat_id: int, topic_key: str, thread_id: int):
        """Save or update a thread ID for a user's topic."""
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        await db.execute(
            """INSERT OR REPLACE INTO user_threads (chat_id, topic_key, thread_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (chat_id, topic_key, thread_id, now)
        )
        await db.commit()

    async def get_user_thread(self, chat_id: int, topic_key: str) -> Optional[int]:
        """Get the thread ID for a specific user topic."""
        db = await self._get_db()
        async with db.execute(
            "SELECT thread_id FROM user_threads WHERE chat_id=? AND topic_key=?",
            (chat_id, topic_key)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_all_user_threads(self, chat_id: int) -> dict[str, int]:
        """Get all thread IDs for a specific user."""
        db = await self._get_db()
        async with db.execute(
            "SELECT topic_key, thread_id FROM user_threads WHERE chat_id=?",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
            
    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Storage: Database connection closed.")
