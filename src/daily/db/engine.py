"""Async SQLAlchemy engine and session factory."""
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from daily.config import Settings


def make_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


def _default_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a session factory from the default Settings database_url.

    Used by scheduler.py and other module-level consumers that need a session
    factory without wiring through FastAPI dependency injection.
    """
    settings = Settings()
    engine = make_engine(settings.database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


# Module-level session factory for use by scheduler and CLI async helpers.
# Lazy-initialized on first use via _default_session_factory().
# This avoids importing Settings at module load time in test contexts.
async_session: async_sessionmaker[AsyncSession] = _default_session_factory()
