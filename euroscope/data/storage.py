"""
SQLite Storage Layer

Stores predictions, accuracy tracking, alerts, and cached data.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("euroscope.data.storage")


class Storage:
    """SQLite-based storage for EuroScope."""

    def __init__(self, db_path: str = "data/euroscope.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
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
            """)
        logger.info(f"Database initialized at {self.db_path}")

    # --- Predictions ---

    def save_prediction(self, timeframe: str, direction: str, confidence: float,
                        reasoning: str = "", target_price: float = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO predictions (timestamp, timeframe, direction, confidence, reasoning, target_price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.utcnow().isoformat(), timeframe, direction, confidence, reasoning, target_price)
            )
            return cursor.lastrowid

    def resolve_prediction(self, pred_id: int, outcome: str, accuracy: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE predictions SET actual_outcome=?, accuracy_score=?, resolved_at=? WHERE id=?""",
                (outcome, accuracy, datetime.utcnow().isoformat(), pred_id)
            )

    def get_accuracy_stats(self, days: int = 30) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
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
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM predictions WHERE resolved_at IS NULL ORDER BY timestamp DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Alerts ---

    def add_alert(self, condition: str, target_value: float, chat_id: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO alerts (created_at, condition, target_value, chat_id) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), condition, target_value, chat_id)
            )
            return cursor.lastrowid

    def get_active_alerts(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM alerts WHERE triggered = 0"
            ).fetchall()
            return [dict(r) for r in rows]

    def trigger_alert(self, alert_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE alerts SET triggered=1, triggered_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), alert_id)
            )

    # --- Memory (key-value for learning) ---

    def set_memory(self, key: str, value: Any):
        data = json.dumps(value) if not isinstance(value, str) else value
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?, ?, ?)",
                (key, data, datetime.utcnow().isoformat())
            )

    def get_memory(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    # --- Market Notes ---

    def add_note(self, category: str, content: str, metadata: dict = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO market_notes (timestamp, category, content, metadata) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), category, content,
                 json.dumps(metadata) if metadata else None)
            )

    def get_recent_notes(self, category: str = None, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if category:
                rows = conn.execute(
                    "SELECT * FROM market_notes WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                    (category, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM market_notes ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
