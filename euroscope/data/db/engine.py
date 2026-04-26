import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from euroscope.data.db.models import Base

logger = logging.getLogger("euroscope.data.db.engine")

from contextlib import asynccontextmanager

class DatabaseManager:
    """Manages the SQLAlchemy async engine and session factory."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        if self.db_url.startswith("sqlite://"):
            if not self.db_url.startswith("sqlite+aiosqlite://"):
                self.db_url = self.db_url.replace("sqlite://", "sqlite+aiosqlite://")
        elif self.db_url.startswith("postgres://") or self.db_url.startswith("postgresql://"):
            if not "asyncpg" in self.db_url:
                self.db_url = self.db_url.replace("postgres://", "postgresql+asyncpg://").replace("postgresql://", "postgresql+asyncpg://")

        logger.info(f"Initializing database engine: {self.db_url.split('@')[-1] if '@' in self.db_url else self.db_url}")
        
        kwargs = {}
        if "sqlite" in self.db_url:
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            kwargs["pool_size"] = 10
            kwargs["max_overflow"] = 20
            kwargs["pool_pre_ping"] = True

        self.engine = create_async_engine(self.db_url, echo=False, **kwargs)
        self.async_session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    async def init_db(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            if "sqlite" in self.db_url:
                await conn.execute(org_sqlalchemy_text("PRAGMA journal_mode=WAL"))
                await conn.execute(org_sqlalchemy_text("PRAGMA synchronous=NORMAL"))
            await conn.run_sync(Base.metadata.create_all)
            
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for getting a database session with auto-commit."""
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """Close the database engine."""
        if self.engine:
            await self.engine.dispose()

from sqlalchemy import text as org_sqlalchemy_text
