import erp.modules.integration.infrastructure.models  # noqa: F401
from erp.modules.projects.infrastructure import models as projects_models  # noqa: F401
from erp.modules.assets.infrastructure import models as assets_models  # noqa: F401
from erp.modules.fiscal.infrastructure import models as fiscal_models  # noqa: F401
from erp.modules.hcm.infrastructure import models as hcm_models  # noqa: F401
from erp.modules.governance.infrastructure import (  # noqa: F401
    models as governance_models,  # noqa: F401
)  # noqa: F401
from erp.modules.reports.infrastructure import models as report_models  # noqa: F401
from erp.modules.operations.infrastructure import (  # noqa: F401
    models as operations_models,
)  # noqa: F401
import asyncio
from erp.modules.financeiro.infrastructure import models as cash_models  # noqa: F401
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import Connection, pool
from erp.config import settings
from erp.modules.organization.infrastructure import (  # noqa: F401
    models as organization_models,
)  # noqa: F401
from erp.shared.infrastructure.database.base import Base
from erp.shared.infrastructure.database import audit  # noqa: F401
from erp.modules.identity.infrastructure import models  # noqa: F401


def run(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_async_engine(settings().database_url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
