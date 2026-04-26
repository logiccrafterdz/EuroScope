import asyncio
import sqlite3
import json
import logging
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, insert

from euroscope.data.db.models import Base
from euroscope.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("euroscope.migration")

async def migrate_data():
    config = Config()
    pg_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/euroscope" # Update with actual URL
    
    sqlite_path = Path("data/euroscope.db")
    if not sqlite_path.exists():
        logger.error(f"SQLite database not found at {sqlite_path}")
        return

    logger.info("Connecting to PostgreSQL...")
    engine = create_async_engine(pg_url, echo=False)
    
    # Create tables in Postgres
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL tables recreated.")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    tables = [
        "predictions", "transaction_logs", "alerts", "market_notes",
        "memory", "trading_signals", "news_events", "performance_metrics",
        "user_preferences", "trade_journal", "pattern_stats", 
        "learning_insights", "user_threads"
    ]

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for table in tables:
            logger.info(f"Migrating table: {table}")
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                if not rows:
                    logger.info(f"Table {table} is empty, skipping.")
                    continue

                # Prepare dictionaries for batch insert
                batch = []
                for row in rows:
                    row_dict = dict(row)
                    
                    # Handle specific JSON columns that are stored as text in SQLite
                    json_cols = ["indicators_snapshot", "patterns_snapshot", "factors", "recommendations"]
                    for col in json_cols:
                        if col in row_dict and row_dict[col]:
                            try:
                                row_dict[col] = json.loads(row_dict[col])
                            except Exception:
                                pass # Leave as string if not parseable

                    if table == "market_notes" and "metadata" in row_dict:
                        # Rename metadata to metadata_json for SQLAlchemy
                        val = row_dict.pop("metadata")
                        if val:
                            try:
                                row_dict["metadata_json"] = json.loads(val)
                            except Exception:
                                row_dict["metadata_json"] = {}
                        else:
                            row_dict["metadata_json"] = None

                    batch.append(row_dict)

                # Batch insert
                if batch:
                    # Dynamically get the model class
                    model_class = next((m for m in Base.registry.mappers if m.class_.__tablename__ == table), None)
                    if model_class:
                        await session.execute(insert(model_class.class_), batch)
                        logger.info(f"Inserted {len(batch)} rows into {table}.")
                    else:
                        logger.warning(f"No SQLAlchemy model found for table {table}")

            except sqlite3.OperationalError as e:
                logger.warning(f"Could not read from SQLite table {table}: {e}")
        
        await session.commit()
        logger.info("Migration commit successful.")

    sqlite_conn.close()
    await engine.dispose()
    logger.info("Migration fully complete!")

if __name__ == "__main__":
    asyncio.run(migrate_data())
