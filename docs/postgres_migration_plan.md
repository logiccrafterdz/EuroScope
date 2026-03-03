# PostgreSQL Migration Path: EuroScope

## Overview
EuroScope currently uses **`aiosqlite`** with WAL (Write-Ahead Logging) mode. As the bot scales to support more concurrent users, heavier high-frequency ticker data (via Capital.com WebSockets), and deeper LLM vector analytics, migrating to a robust RDBMS like **PostgreSQL** is necessary to avoid single-file database locks and enable distributed deployments.

## 1. Schema Mapping & Equivalencies
SQLite tables defined in `euroscope.data.storage.Storage._sync_init` will need to be translated to PostgreSQL syntax. 

### Key Type Conversions:
- `INTEGER PRIMARY KEY AUTOINCREMENT` ➡️ `SERIAL PRIMARY KEY` or `BIGSERIAL PRIMARY KEY`
- `TEXT` ➡️ `VARCHAR` or `TEXT`
- `REAL` ➡️ `DOUBLE PRECISION` or `NUMERIC`
- SQLite native booleans (`INTEGER DEFAULT 0/1`) ➡️ `BOOLEAN DEFAULT FALSE/TRUE`
- JSON fields (stored as `TEXT` in SQLite) ➡️ Native `JSONB` for optimized querying (e.g. `metadata`, `indicators_snapshot`, `factors`).

### Table Inventory Context:
- `predictions`: Forecasts and accuracy.
- `alerts`: Smart user notifications.
- `market_notes` / `news_events`: Fundamental & macro analysis points.
- `trading_signals` / `trade_journal`: Trade execution states.
- `performance_metrics` / `pattern_stats`: Engine learning metrics.
- `memory` / `user_preferences` / `user_threads`: Bot states.

## 2. Recommended Migration Tooling

### ORM or Async Driver?
To keep the codebase lightweight and highly performant (fitting the AI HFT narrative), transitioning from `aiosqlite` to `asyncpg` (raw async queries) or `SQLAlchemy 2.0` (with `asyncpg` driver) is recommended.

**Recommendation: `SQLAlchemy 2.0 (Async)` + `Alembic`**
- **Alembic** provides version-controlled migrations (crucial for staging schema changes).
- **SQLAlchemy 2.0** allows swapping the SQLite backend to PostgreSQL trivially via connection strings (`sqlite+aiosqlite:///` vs `postgresql+asyncpg://`).

## 3. Step-by-Step Migration Plan

### Phase 1: Database Abstraction & SQLAlchemy Integration
1. Introduce SQLAlchemy models mapped to the existing SQLite tables.
2. Refactor `euroscope.data.storage.Storage` methods to use SQLAlchemy `async_session` instead of raw `aiosqlite` string queries.
3. Validate parity by running the bot with the new SQLAlchemy-SQLite backend to ensure no regressions in reads/writes.

### Phase 2: Schema Versioning initialization
1. Initialize `Alembic` in the project root (`alembic init alembic`).
2. Auto-generate the initial migration script based on the SQLAlchemy models to represent the *current* state.

### Phase 3: PostgreSQL Infrastructure Setup
1. Provision a PostgreSQL 15+ database (e.g., via Northflank, Supabase, or AWS RDS).
2. Add PostgreSQL connection URI parsing to `euroscope.config.Config` (e.g., `EUROSCOPE_DATABASE_URL`).

### Phase 4: Data Migration Pipeline (ETL)
1. Write a standalone, one-off ETL script (`scripts/migrate_sqlite_to_pg.py`) that:
   - Connects to the legacy `data/euroscope.db`.
   - Connects to the new PostgreSQL database.
   - Iterates through all tables, transferring rows in bulk chunks (batch inserts).
   - Handles data type casting (e.g., converting SQLite `INTEGER` booleans to PostgreSQL `BOOLEAN`, parsing `TEXT` JSON to `JSONB`).

### Phase 5: Production Cut-over
1. Halt the EuroScope bot service to prevent new SQLite writes.
2. Run the final, differential ETL script sync.
3. Update `.env` to point `EUROSCOPE_DATABASE_URL` to the live Postgres instance.
4. Restart the bot.

## 4. Specific Code Adaptations

### `storage.py` Updates:
Instead of raw strings, transition to:
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

class Storage:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def get_active_alerts(self):
        async with self.async_session() as session:
            result = await session.execute(select(Alert).where(Alert.triggered == False))
            return result.scalars().all()
```

### JSON Optimizations in Postgres:
Leverage Postgres' native `JSONB`. 
```sql
-- Before (SQLite)
SELECT * FROM trade_journal WHERE indicators_snapshot LIKE '%"RSI": {"value": >70}%';

-- After (Postgres JSONB)
SELECT * FROM trade_journal WHERE indicators_snapshot->'RSI'->>'value' > '70';
``` 

## 5. Security & Backups
- Utilize Postgres Point-In-Time-Recovery (PITR) for financial data safety.
- Encrypt connection strings via SSL/TLS (required by most managed providers like Supabase/Neon).
