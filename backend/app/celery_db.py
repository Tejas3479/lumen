"""
Lumen Celery Database Utilities
Provides a synchronous-compatible async DB session for Celery tasks.
Celery tasks run in sync context via asyncio.run().
This module creates ONE shared engine per worker process, not per task call.
"""
import asyncio
from functools import lru_cache
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings


@lru_cache(maxsize=1)
def _get_engine():
    """Returns a cached async engine. Created once per worker process."""
    return create_async_engine(
        settings.database_url,
        pool_size=3,          # Celery workers need smaller pools
        max_overflow=5,
        echo=False,
        future=True,
    )


def get_celery_session() -> AsyncSession:
    """Returns a new async session using the shared engine."""
    engine = _get_engine()
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal()


async def run_with_db(coro_factory):
    """
    Helper: runs an async coroutine that needs a DB session.
    Usage in Celery tasks:
        from app.utils.async_utils import run_async_task
        result = run_async_task(run_with_db(lambda db: my_async_function(db)))
    """
    async with get_celery_session() as db:
        try:
            result = await coro_factory(db)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise
