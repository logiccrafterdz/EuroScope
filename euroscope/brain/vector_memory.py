"""
Vector Memory — Lightweight Long-term Context with SQLite FTS5

Replaced ChromaDB with SQLite FTS5 (built-in full-text search).
Stores past analyses, insights, and market events with keyword-based
search. Zero external dependencies.
"""

import logging
import sqlite3
import os
import re
from datetime import datetime, timedelta, UTC
from typing import Optional

logger = logging.getLogger("euroscope.brain.vector_memory")


class VectorMemory:
    """
    Long-term memory using SQLite FTS5 for full-text search.

    Previously used ChromaDB for vector embeddings; replaced with
    lightweight FTS5 which is built into SQLite — zero dependencies,
    works on all Python versions, and sufficient for keyword-based
    context retrieval in a single-pair trading bot.
    """

    def __init__(self, storage=None, persist_dir: str = "data"):
        self.storage = storage
        self.persist_dir = persist_dir
        self._cache = {}
        self._conn: Optional[sqlite3.Connection] = None
        self._available = False
        self._init_db()

    def _init_db(self):
        """Initialize SQLite FTS5 database."""
        try:
            os.makedirs(self.persist_dir, exist_ok=True)
            db_path = os.path.join(self.persist_dir, "memory.db")
            self._conn = sqlite3.connect(db_path, timeout=30.0)
            self._conn.row_factory = sqlite3.Row
            
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=30000")

            # Create FTS5 virtual tables for full-text search
            self._conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS analyses
                USING fts5(doc_id, text, stored_at, timestamp, metadata);

                CREATE VIRTUAL TABLE IF NOT EXISTS insights
                USING fts5(doc_id, text, stored_at, timestamp, tags);

                CREATE VIRTUAL TABLE IF NOT EXISTS market_events
                USING fts5(doc_id, text, stored_at, timestamp, impact, metadata);
            """)
            self._conn.commit()
            self._available = True
            logger.info(f"VectorMemory (SQLite FTS5) initialized at {db_path}")

        except Exception as e:
            logger.error(f"VectorMemory init failed: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def store_analysis(self, text: str, metadata: dict = None) -> Optional[str]:
        """
        Store a past analysis for future search.

        Args:
            text: The analysis text
            metadata: Optional metadata (timeframe, verdict, confidence, etc.)

        Returns:
            Document ID if stored, None if unavailable
        """
        if not self._available:
            return None

        doc_id = f"analysis_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        meta = metadata or {}
        now_iso = datetime.now(UTC).isoformat()
        meta_str = str(meta)

        try:
            self._conn.execute(
                "INSERT INTO analyses (doc_id, text, stored_at, timestamp, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, text, now_iso, meta.get("timestamp", now_iso), meta_str),
            )
            self._conn.commit()
            logger.debug(f"Stored analysis: {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store analysis: {e}")
            return None

    def search_similar(self, query: str, k: int = 5,
                       collection: str = "analyses") -> list[dict]:
        """
        Search for similar past entries using FTS5 full-text search.

        Args:
            query: Search text
            k: Number of results
            collection: Which collection to search ("analyses", "insights", "market_events")

        Returns:
            List of {"text": str, "metadata": dict, "distance": float}
        """
        if not self._available:
            return []

        if collection not in ("analyses", "insights", "market_events"):
            return []

        try:
            # Build FTS5 query: use each word as a match term
            # FTS5 uses implicit AND between terms
            cleaned = re.sub(r"[^\w\s]+", " ", query or "").strip()
            operators = {"and", "or", "not", "near"}
            terms = [
                word
                for word in cleaned.split()
                if len(word) > 2 and word.lower() not in operators
            ]
            search_terms = " OR ".join(terms)
            if not search_terms:
                if not cleaned:
                    return []
                search_terms = cleaned

            rows = self._conn.execute(
                f"SELECT doc_id, text, stored_at, timestamp, rank "
                f"FROM {collection} "
                f"WHERE {collection} MATCH ? "
                f"ORDER BY rank "
                f"LIMIT ?",
                (search_terms, k),
            ).fetchall()

            items = []
            for row in rows:
                items.append({
                    "text": row["text"],
                    "metadata": {
                        "stored_at": row["stored_at"],
                        "timestamp": row["timestamp"],
                    },
                    "distance": abs(row["rank"]),  # FTS5 rank (lower = better)
                })

            return items
        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            return []

    def store_insight(self, insight: str, tags: list[str] = None) -> Optional[str]:
        """Store a learning insight."""
        if not self._available:
            return None

        doc_id = f"insight_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        now_iso = datetime.now(UTC).isoformat()
        tags_str = ",".join(tags) if tags else ""

        try:
            self._conn.execute(
                "INSERT INTO insights (doc_id, text, stored_at, timestamp, tags) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, insight, now_iso, now_iso, tags_str),
            )
            self._conn.commit()
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store insight: {e}")
            return None

    def store_market_event(self, description: str, impact: str = "medium",
                           metadata: dict = None) -> Optional[str]:
        """Store a significant market event."""
        if not self._available:
            return None

        doc_id = f"event_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        meta = metadata or {}
        now_iso = datetime.now(UTC).isoformat()
        meta_str = str(meta)

        try:
            self._conn.execute(
                "INSERT INTO market_events (doc_id, text, stored_at, timestamp, impact, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, description, now_iso, now_iso, impact, meta_str),
            )
            self._conn.commit()
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store event: {e}")
            return None

    def get_relevant_context(self, current_situation: str, k: int = 3) -> str:
        """
        Get relevant past context for the AI prompt.

        Searches analyses and insights for similar situations.
        """
        if not self._available:
            return ""

        lines = []

        # Search past analyses
        similar = self.search_similar(current_situation, k=k, collection="analyses")
        if similar:
            lines.append("📚 *Relevant Past Analyses:*")
            for i, item in enumerate(similar, 1):
                snippet = item["text"][:200]
                date = item["metadata"].get("stored_at", "")[:10]
                lines.append(f"  {i}. [{date}] {snippet}...")

        # Search insights
        insights = self.search_similar(current_situation, k=2, collection="insights")
        if insights:
            lines.append("\n💡 *Related Insights:*")
            for item in insights:
                lines.append(f"  • {item['text'][:150]}")

        return "\n".join(lines) if lines else ""

    def get_collection_stats(self) -> dict:
        """Get stats about all collections."""
        if not self._available:
            return {"available": False}

        stats = {"available": True}
        for name in ("analyses", "insights", "market_events"):
            try:
                row = self._conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
                stats[name] = row[0]
            except Exception:
                stats[name] = 0
        return stats

    async def cleanup_old_documents(self, ttl_days: int = 30) -> int:
        if not self._available:
            return 0

        cutoff_date = datetime.now(UTC) - timedelta(days=ttl_days)
        cutoff_iso = cutoff_date.isoformat()
        total_deleted = 0

        for name in ("analyses", "insights", "market_events"):
            try:
                cursor = self._conn.execute(
                    f"DELETE FROM {name} WHERE timestamp < ?",
                    (cutoff_iso,),
                )
                deleted = cursor.rowcount
                total_deleted += deleted
                if deleted > 0:
                    logger.info(f"VectorMemory cleanup {name}: deleted {deleted} docs")
            except Exception as e:
                logger.error(f"VectorMemory cleanup failed for {name}: {e}")

        if total_deleted > 0:
            self._conn.commit()

        return total_deleted

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._available = False
