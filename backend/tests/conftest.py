"""
Lumen Test Configuration
Provides async test client and isolated test database.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import socket_app
from app.database import Base, get_db
from app.config import settings
settings.environment = "testing"

from app.celery_app import celery_app
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
)

from unittest.mock import MagicMock
from app.services.ai_categorizer import categorize_issue_task
categorize_issue_task.delay = MagicMock()


if settings.database_url.endswith("/lumen"):
    TEST_DATABASE_URL = settings.database_url[:-6] + "/lumen_test"
else:
    parts = settings.database_url.rsplit("/", 1)
    TEST_DATABASE_URL = parts[0] + "/" + parts[1] + "_test"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        await conn.execute(
            text(
                "INSERT INTO issues (id, title, description, severity, status, is_anonymous, is_emergency, vote_count, verification_count, view_count, user_correction, latitude, longitude, escalation_count, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000000', 'Placeholder Issue', 'Placeholder description', 'medium', 'reported', false, false, 0, 0, 0, false, 12.9716, 77.5946, 0, NOW(), NOW()) "
                "ON CONFLICT DO NOTHING"
            )
        )
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    from app.main import app as fastapi_app
    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test"
    ) as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()
