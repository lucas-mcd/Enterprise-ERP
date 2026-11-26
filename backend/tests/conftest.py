import os
from collections.abc import AsyncIterator
from uuid import uuid4
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from erp.shared.infrastructure.database.base import Base
from erp.shared.infrastructure.database.context import AuditContext
from erp.shared.infrastructure.database.session import session_factory


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    factory = session_factory(url)
    engine: AsyncEngine = factory.kw["bind"]
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def enable_fk(connection, record):  # type: ignore[no-untyped-def]
            connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest.fixture
def ctx() -> AuditContext:
    return AuditContext(uuid4(), uuid4(), "user", uuid4(), "127.0.0.1", "pytest")
