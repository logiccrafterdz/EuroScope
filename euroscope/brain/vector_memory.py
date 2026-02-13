"""
Vector Memory — Long-term Context with ChromaDB

Stores past analyses, insights, and market events as vector embeddings
for semantic search and context retrieval.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("euroscope.brain.vector_memory")


class VectorMemory:
    """
    Long-term memory using ChromaDB for semantic search.

    Falls back gracefully if ChromaDB is not installed.
    """

    def __init__(self, persist_dir: str = "data/vector_db"):
        self.persist_dir = persist_dir
        self._client = None
        self._collections: dict = {}
        self._available = False
        self._init_db()

    def _init_db(self):
        """Initialize ChromaDB client and collections."""
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )

            # Create collections
            self._collections["analyses"] = self._client.get_or_create_collection(
                name="analyses",
                metadata={"description": "Past EUR/USD analyses"},
            )
            self._collections["insights"] = self._client.get_or_create_collection(
                name="insights",
                metadata={"description": "Learning insights and lessons"},
            )
            self._collections["market_events"] = self._client.get_or_create_collection(
                name="market_events",
                metadata={"description": "Significant market events"},
            )

            self._available = True
            logger.info(f"VectorMemory initialized at {self.persist_dir}")

        except ImportError:
            logger.warning("chromadb not installed — vector memory disabled. "
                           "Install with: pip install chromadb")
            self._available = False
        except Exception as e:
            logger.error(f"VectorMemory init failed: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def store_analysis(self, text: str, metadata: dict = None) -> Optional[str]:
        """
        Store a past analysis for future semantic search.

        Args:
            text: The analysis text
            metadata: Optional metadata (timeframe, verdict, confidence, etc.)

        Returns:
            Document ID if stored, None if unavailable
        """
        if not self._available:
            return None

        doc_id = f"analysis_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        meta = metadata or {}
        meta["stored_at"] = datetime.utcnow().isoformat()
        meta["type"] = "analysis"

        # ChromaDB metadata values must be str, int, float, or bool
        clean_meta = {k: str(v) if not isinstance(v, (int, float, bool)) else v
                      for k, v in meta.items()}

        try:
            self._collections["analyses"].add(
                documents=[text],
                metadatas=[clean_meta],
                ids=[doc_id],
            )
            logger.debug(f"Stored analysis: {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store analysis: {e}")
            return None

    def search_similar(self, query: str, k: int = 5,
                       collection: str = "analyses") -> list[dict]:
        """
        Search for similar past entries.

        Args:
            query: Search text
            k: Number of results
            collection: Which collection to search

        Returns:
            List of {"text": str, "metadata": dict, "distance": float}
        """
        if not self._available:
            return []

        coll = self._collections.get(collection)
        if not coll:
            return []

        try:
            results = coll.query(query_texts=[query], n_results=k)

            items = []
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, meta, dist in zip(documents, metadatas, distances):
                items.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": round(dist, 4),
                })

            return items
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def store_insight(self, insight: str, tags: list[str] = None) -> Optional[str]:
        """Store a learning insight."""
        if not self._available:
            return None

        doc_id = f"insight_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        meta = {
            "stored_at": datetime.utcnow().isoformat(),
            "type": "insight",
            "tags": ",".join(tags) if tags else "",
        }

        try:
            self._collections["insights"].add(
                documents=[insight],
                metadatas=[meta],
                ids=[doc_id],
            )
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store insight: {e}")
            return None

    def store_market_event(self, description: str, impact: str = "medium",
                           metadata: dict = None) -> Optional[str]:
        """Store a significant market event."""
        if not self._available:
            return None

        doc_id = f"event_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        meta = metadata or {}
        meta.update({
            "stored_at": datetime.utcnow().isoformat(),
            "type": "market_event",
            "impact": impact,
        })
        clean_meta = {k: str(v) if not isinstance(v, (int, float, bool)) else v
                      for k, v in meta.items()}

        try:
            self._collections["market_events"].add(
                documents=[description],
                metadatas=[clean_meta],
                ids=[doc_id],
            )
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
        for name, coll in self._collections.items():
            try:
                stats[name] = coll.count()
            except Exception:
                stats[name] = 0
        return stats
