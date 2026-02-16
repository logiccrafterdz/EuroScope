"""
SQLite Storage Layer

Stores predictions, accuracy tracking, alerts, trading signals,
news events, performance metrics, user preferences, and cached data.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("euroscope.data.storage")


class Storage:
    """SQLite-based storage for EuroScope."""

    def __init__(self, db_path: str = "data/euroscope.db"):
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._conn:
            self._conn.executescript("""
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

                CREATE TABLE IF NOT EXISTS user_threads (
                    chat_id INTEGER NOT NULL,
                    topic_key TEXT NOT NULL,
                    thread_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, topic_key)
                );
            """)
            self._ensure_user_preferences_columns()
            self._ensure_pattern_stats_columns()
            self._ensure_trade_journal_columns()
            logger.info(f"Database initialized at {self.db_path}")

    def _ensure_user_preferences_columns(self):
        cols = {
            row[1] for row in self._conn.execute("PRAGMA table_info(user_preferences)")
        }
        if "compact_mode" not in cols:
            self._conn.execute(
                "ALTER TABLE user_preferences ADD COLUMN compact_mode INTEGER DEFAULT 0"
            )
        if "backtest_slippage_enabled" not in cols:
            self._conn.execute(
                "ALTER TABLE user_preferences ADD COLUMN backtest_slippage_enabled INTEGER DEFAULT 1"
            )

    def _ensure_pattern_stats_columns(self):
        cols = {
            row[1] for row in self._conn.execute("PRAGMA table_info(pattern_stats)")
        }
        if "causal_chain" not in cols:
            self._conn.execute(
                "ALTER TABLE pattern_stats ADD COLUMN causal_chain TEXT"
            )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pattern_stats_name_time ON pattern_stats(pattern_name, detected_at)"
        )

    def _ensure_trade_journal_columns(self):
        cols = {
            row[1] for row in self._conn.execute("PRAGMA table_info(trade_journal)")
        }
        if "causal_chain" not in cols:
            self._conn.execute(
                "ALTER TABLE trade_journal ADD COLUMN causal_chain TEXT"
            )

    # --- Predictions ---

    def save_prediction(self, timeframe: str, direction: str, confidence: float,
                        reasoning: str = "", target_price: float = None) -> int:
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO predictions (timestamp, timeframe, direction, confidence, reasoning, target_price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.utcnow().isoformat(), timeframe, direction, confidence, reasoning, target_price)
            )
            return cursor.lastrowid

    def resolve_prediction(self, pred_id: int, outcome: str, accuracy: float):
        with self._conn:
            self._conn.execute(
                """UPDATE predictions SET actual_outcome=?, accuracy_score=?, resolved_at=? WHERE id=?""",
                (outcome, accuracy, datetime.utcnow().isoformat(), pred_id)
            )

    def get_accuracy_stats(self, days: int = 30) -> dict:
        rows = self._conn.execute(
            """SELECT direction, accuracy_score FROM predictions
                WHERE resolved_at IS NOT NULL
                AND timestamp > datetime('now', ?)""",
            (f"-{days} days",)
        ).fetchall()

        if not rows:
            return {"total": 0, "accuracy": 0.0, "message": "No resolved predictions yet"}

        correct = sum(1 for _, score in rows if score and score >= 0.5)
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
        for direction, score in rows:
            stats[direction]["total"] += 1
            if score and score >= 0.5:
                stats[direction]["correct"] += 1
        return {
            d: {**s, "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] else 0}
            for d, s in stats.items()
        }

    def get_unresolved_predictions(self) -> list[dict]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT * FROM predictions WHERE resolved_at IS NULL ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Alerts ---

    def add_alert(self, condition: str, target_value: float, chat_id: int) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO alerts (created_at, condition, target_value, chat_id) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), condition, target_value, chat_id)
            )
            return cursor.lastrowid

    def get_active_alerts(self) -> list[dict]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE triggered = 0"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_user_alerts(self, chat_id: int) -> list[dict]:
        """Get all active alerts for a specific user."""
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE chat_id = ? AND triggered = 0",
            (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def trigger_alert(self, alert_id: int):
        with self._conn:
            self._conn.execute(
                "UPDATE alerts SET triggered=1, triggered_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), alert_id)
            )

    def delete_alert(self, alert_id: int):
        """Permanently delete an alert."""
        with self._conn:
            self._conn.execute("DELETE FROM alerts WHERE id=?", (alert_id,))

    # --- Memory (key-value for learning) ---

    def set_memory(self, key: str, value: Any):
        data = json.dumps(value) if not isinstance(value, str) else value
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?, ?, ?)",
                (key, data, datetime.utcnow().isoformat())
            )

    def get_memory(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    # --- Market Notes ---

    def add_note(self, category: str, content: str, metadata: dict = None):
        with self._conn:
            self._conn.execute(
                "INSERT INTO market_notes (timestamp, category, content, metadata) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), category, content,
                 json.dumps(metadata) if metadata else None)
            )

    def get_recent_notes(self, category: str = None, limit: int = 20) -> list[dict]:
        self._conn.row_factory = sqlite3.Row
        if category:
            rows = self._conn.execute(
                "SELECT * FROM market_notes WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM market_notes ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Trading Signals ---

    def save_signal(self, direction: str, entry_price: float, stop_loss: float,
                    take_profit: float, confidence: float, timeframe: str,
                    source: str = "system", reasoning: str = "",
                    risk_reward_ratio: float = 0.0) -> int:
        """Save a new trading signal."""
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO trading_signals
                   (created_at, direction, entry_price, stop_loss, take_profit,
                    confidence, timeframe, source, reasoning, risk_reward_ratio)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.utcnow().isoformat(), direction, entry_price, stop_loss,
                 take_profit, confidence, timeframe, source, reasoning, risk_reward_ratio)
            )
            return cursor.lastrowid

    def update_signal_status(self, signal_id: int, status: str, pnl_pips: float = 0.0):
        """Update a signal's status (active, closed, cancelled)."""
        closed_at = datetime.utcnow().isoformat() if status in ("closed", "cancelled") else None
        with self._conn:
            self._conn.execute(
                "UPDATE trading_signals SET status=?, pnl_pips=?, closed_at=? WHERE id=?",
                (status, pnl_pips, closed_at, signal_id)
            )

    def get_signals(self, status: str = None, limit: int = 20) -> list[dict]:
        """Get trading signals, optionally filtered by status."""
        self._conn.row_factory = sqlite3.Row
        if status:
            rows = self._conn.execute(
                "SELECT * FROM trading_signals WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- News Events ---

    def save_news_event(self, title: str, source: str, url: str = "",
                        description: str = "", impact_score: float = 0.0,
                        sentiment: str = "neutral", sentiment_score: float = 0.0,
                        currency_impact: str = "", published_at: str = "") -> int:
        """Save a news event."""
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO news_events
                   (title, source, url, description, impact_score, sentiment,
                    sentiment_score, currency_impact, published_at, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, source, url, description, impact_score, sentiment,
                 sentiment_score, currency_impact, published_at,
                 datetime.utcnow().isoformat())
            )
            return cursor.lastrowid

    def get_recent_news(self, limit: int = 20, min_impact: float = 0.0) -> list[dict]:
        """Get recent news events, optionally filtered by minimum impact."""
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            """SELECT * FROM news_events
                WHERE impact_score >= ?
                ORDER BY fetched_at DESC LIMIT ?""",
            (min_impact, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Performance Metrics ---

    def save_performance_metric(self, period: str, total_signals: int = 0,
                                winning_signals: int = 0, losing_signals: int = 0,
                                win_rate: float = 0.0, total_pnl_pips: float = 0.0,
                                avg_pnl_pips: float = 0.0, max_drawdown_pips: float = 0.0,
                                profit_factor: float = 0.0, sharpe_ratio: float = 0.0,
                                avg_risk_reward: float = 0.0, best_trade_pips: float = 0.0,
                                worst_trade_pips: float = 0.0,
                                avg_trade_duration_hours: float = 0.0) -> int:
        """Save a performance metrics snapshot."""
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO performance_metrics
                   (period, total_signals, winning_signals, losing_signals, win_rate,
                    total_pnl_pips, avg_pnl_pips, max_drawdown_pips, profit_factor,
                    sharpe_ratio, avg_risk_reward, best_trade_pips, worst_trade_pips,
                    avg_trade_duration_hours, calculated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (period, total_signals, winning_signals, losing_signals, win_rate,
                 total_pnl_pips, avg_pnl_pips, max_drawdown_pips, profit_factor,
                 sharpe_ratio, avg_risk_reward, best_trade_pips, worst_trade_pips,
                 avg_trade_duration_hours, datetime.utcnow().isoformat())
            )
            return cursor.lastrowid

    def get_latest_metrics(self, period: str = "daily") -> Optional[dict]:
        """Get the most recent performance metrics for a period."""
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT * FROM performance_metrics WHERE period=? ORDER BY calculated_at DESC LIMIT 1",
            (period,)
        ).fetchone()
        return dict(row) if row else None

    # --- User Preferences ---

    def save_user_preferences(self, chat_id: int, **kwargs) -> int:
        """Save or update user preferences (upsert)."""
        now = datetime.utcnow().isoformat()
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

        with self._conn:
            cursor = self._conn.execute(
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
            )
            return cursor.lastrowid

    def get_user_preferences(self, chat_id: int) -> Optional[dict]:
        """Get preferences for a specific user."""
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT * FROM user_preferences WHERE chat_id=?", (chat_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Trade Journal ─────────────────────────────────────────

    def save_trade_journal(self, direction: str, entry_price: float,
                           stop_loss: float = 0.0, take_profit: float = 0.0,
                           strategy: str = "", timeframe: str = "H1",
                           regime: str = "", confidence: float = 0.0,
                           indicators: dict = None, patterns: list = None,
                           reasoning: str = "", causal_chain: Any = None,
                           status: str = "open") -> int:
        """Save a new trade journal entry."""
        now = datetime.utcnow().isoformat()
        if isinstance(causal_chain, (dict, list)):
            causal_payload = json.dumps(causal_chain)
        else:
            causal_payload = causal_chain
        with self._conn:
            cursor = self._conn.execute(
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
            )
            return cursor.lastrowid

    def close_trade_journal(self, trade_id: int, exit_price: float,
                             pnl_pips: float, is_win: bool):
        """Close a trade journal entry with outcome."""
        now = datetime.utcnow().isoformat()
        with self._conn:
            self._conn.execute(
                """UPDATE trade_journal SET exit_price=?, pnl_pips=?,
                   is_win=?, closed_at=?, status='closed'
                   WHERE id=?""",
                (exit_price, pnl_pips, 1 if is_win else 0, now, trade_id)
            )

    def get_trade_journal(self, strategy: str = None, status: str = None,
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

        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(query, params).fetchall()
        trades = [dict(r) for r in rows]
        for t in trades:
            t["causal_chain"] = self._parse_json_payload(t.get("causal_chain"))
        return trades

    def get_trade_journal_for_date(self, date: str, status: str = None) -> list[dict]:
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

        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(query, params).fetchall()
        trades = [dict(r) for r in rows]
        for t in trades:
            t["causal_chain"] = self._parse_json_payload(t.get("causal_chain"))
        return trades

    def get_trade_with_causal(self, trade_id: int) -> Optional[dict]:
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT * FROM trade_journal WHERE id=?",
            (trade_id,),
        ).fetchone()
        if not row:
            return None
        trade = dict(row)
        trade["causal_chain"] = self._parse_json_payload(trade.get("causal_chain"))
        return trade

    def get_trade_journal_stats(self, strategy: str = None) -> dict:
        """Get aggregate stats from trade journal."""
        query = "SELECT * FROM trade_journal WHERE status='closed'"
        params = []
        if strategy:
            query += " AND strategy=?"
            params.append(strategy)

        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(query, params).fetchall()

        if not rows:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                    "total_pnl": 0.0, "avg_pnl": 0.0}

        trades = [dict(r) for r in rows]
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

    def save_pattern_detection(self, pattern_name: str, timeframe: str,
                                predicted_direction: str,
                                price_at_detection: float,
                                causal_chain: Optional[dict] = None) -> int:
        """Record a new pattern detection."""
        now = datetime.utcnow().isoformat()
        causal_payload = json.dumps(causal_chain) if causal_chain else None
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO pattern_stats
                   (pattern_name, timeframe, detected_at, predicted_direction,
                    price_at_detection, causal_chain)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pattern_name, timeframe, now, predicted_direction,
                 price_at_detection, causal_payload)
            )
            return cursor.lastrowid

    def resolve_pattern(self, pattern_id: int, actual_outcome: str,
                        price_at_resolution: float, is_success: bool):
        """Resolve a pattern detection with actual outcome."""
        now = datetime.utcnow().isoformat()
        with self._conn:
            self._conn.execute(
                """UPDATE pattern_stats SET actual_outcome=?,
                   price_at_resolution=?, is_success=?, resolved_at=?
                   WHERE id=?""",
                (actual_outcome, price_at_resolution,
                 1 if is_success else 0, now, pattern_id)
            )

    def get_pattern_success_rates(self) -> dict:
        """Get success rates grouped by pattern_name + timeframe."""
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            """SELECT pattern_name, timeframe,
                COUNT(*) as total,
                SUM(CASE WHEN is_success=1 THEN 1 ELSE 0 END) as successes
                FROM pattern_stats
                WHERE is_success IS NOT NULL
                GROUP BY pattern_name, timeframe"""
        ).fetchall()

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

    def get_unresolved_patterns(self, limit: int = 50) -> list[dict]:
        """Get pattern detections that haven't been resolved yet."""
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            """SELECT * FROM pattern_stats
                WHERE is_success IS NULL
                ORDER BY detected_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_similar_patterns(
        self,
        pattern_name: str,
        timeframe: Optional[str] = None,
        min_similarity: float = 0.7,
        limit: int = 5,
    ) -> list[dict]:
        self._conn.row_factory = sqlite3.Row
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
        rows = self._conn.execute(query, params).fetchall()
        results = [dict(r) for r in rows]
        return [r for r in results if r.get("similarity", 0) >= min_similarity]

    # ─── User Threads (Private Topics) ───────────────────────

    def save_user_thread(self, chat_id: int, topic_key: str, thread_id: int):
        """Save or update a thread ID for a user's topic."""
        now = datetime.utcnow().isoformat()
        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO user_threads (chat_id, topic_key, thread_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (chat_id, topic_key, thread_id, now)
            )

    def get_user_thread(self, chat_id: int, topic_key: str) -> Optional[int]:
        """Get the thread ID for a specific user topic."""
        row = self._conn.execute(
            "SELECT thread_id FROM user_threads WHERE chat_id=? AND topic_key=?",
            (chat_id, topic_key)
        ).fetchone()
        return row[0] if row else None

    def get_all_user_threads(self, chat_id: int) -> dict[str, int]:
        """Get all thread IDs for a specific user."""
        rows = self._conn.execute(
            "SELECT topic_key, thread_id FROM user_threads WHERE chat_id=?",
            (chat_id,)
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def __del__(self):
        """Close connection on deletion."""
        if hasattr(self, "_conn"):
            self._conn.close()

