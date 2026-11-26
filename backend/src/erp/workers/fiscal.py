from erp.modules.hcm.infrastructure import models as hcm_models  # noqa: F401
from erp.modules.operations.infrastructure import (  # noqa: F401
    models as operations_models,
)  # noqa: F401
from erp.modules.financeiro.infrastructure import models as cash_models  # noqa: F401
import asyncio
from typing import cast
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from erp.config import settings
from erp.workers.celery_app import app
from erp.modules.fiscal.infrastructure.models import Invoice
from erp.shared.infrastructure.database.session import session_factory
from erp.shared.infrastructure.database.context import AuditContext
from erp.modules.identity.infrastructure.repositories.identity import SqlIdentityReader


async def pending() -> list[tuple[str, str]]:
    engine = create_async_engine(settings().database_url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                select(Invoice.id, Invoice.tenant_id)
                .where(Invoice.status == "processando")
                .limit(100)
            )
            return [(str(r.id), str(r.tenant_id)) for r in rows]
    finally:
        await engine.dispose()


async def authorize(identity: UUID, tenant: UUID) -> None:
    factory = session_factory(settings().database_url)
    try:
        async with factory(
            info={
                "audit_context": AuditContext(
                    tenant, None, "worker", uuid4(), user_agent="fiscal-simulator"
                )
            }
        ) as session:
            async with session.begin():
                row = await session.scalar(
                    select(Invoice)
                    .where(Invoice.id == identity)
                    .with_for_update(skip_locked=True)
                )
                if row is None or row.status != "processando":
                    return
                reader = SqlIdentityReader(session)
                principal = await reader.principal(row.requested_by)
                if not row.is_simulated and (
                    principal is None
                    or "fiscal:documento:emitir" not in principal.permissions
                    or not await reader.tenant_active()
                ):
                    row.status = "cancelada"
                    row.cancellation_reason = "Simulação interrompida: acesso revogado."
                else:
                    row.status = "autorizada"
    finally:
        await cast(AsyncEngine, factory.kw["bind"]).dispose()


def dispatch() -> None:
    for identity, tenant in asyncio.run(pending()):
        app.send_task("erp.fiscal.authorize", args=[identity, tenant])


def process(identity: str, tenant: str) -> None:
    asyncio.run(authorize(UUID(identity), UUID(tenant)))


app.task(name="erp.fiscal.dispatch")(dispatch)
app.task(
    name="erp.fiscal.authorize",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)(process)
