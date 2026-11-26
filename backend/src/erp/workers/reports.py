import asyncio
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from erp.config import settings
from erp.modules.operations.domain.orders import BusinessError
from erp.workers.celery_app import app
from erp.modules.reports.infrastructure.models import ReportJob
from erp.modules.reports.infrastructure.render import pdf_file
from erp.modules.reports.infrastructure.service import selection, report_data
from erp.shared.infrastructure.database.session import session_factory
from erp.shared.infrastructure.database.context import AuditContext
from erp.shared.infrastructure.database.base import utcnow
from erp.modules.identity.infrastructure.repositories.identity import SqlIdentityReader


async def pending() -> list[tuple[str, str]]:
    # Infrastructure-only queue discovery across tenants. No business payload
    # leaves here.
    engine = create_async_engine(settings().database_url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                select(ReportJob.id, ReportJob.tenant_id)
                .where(ReportJob.status == "queued")
                .order_by(ReportJob.created_at)
                .limit(100)
            )
            return [(str(r.id), str(r.tenant_id)) for r in rows]
    finally:
        await engine.dispose()


async def generate(job_id: UUID, tenant_id: UUID) -> None:
    cfg = settings()
    factory = session_factory(cfg.database_url)
    ctx = AuditContext(tenant_id, None, "worker", uuid4(), user_agent="celery/pdf")
    try:
        async with factory(info={"audit_context": ctx}) as session:
            async with session.begin():
                # The lock spans snapshot capture and publishing;
                # duplicate delivery is safe.
                row = await session.scalar(
                    select(ReportJob)
                    .where(ReportJob.id == job_id)
                    .with_for_update(skip_locked=True)
                )
                if row is None or row.status != "queued":
                    return
                expires = row.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=utcnow().tzinfo)
                reader = SqlIdentityReader(session)
                principal = await reader.principal(row.owner_id)
                required = {"financeiro:relatorio:ler", "financeiro:lancamento:ler"}
                if row.include_audit:
                    required.add("auditoria:registro:ler")
                if (
                    expires <= utcnow()
                    or principal is None
                    or not await reader.tenant_active()
                    or not required.issubset(principal.permissions)
                ):
                    row.status = "failed"
                    row.error = "Solicitação expirada ou acesso revogado."
                    return
                data = selection(row.filters)
                try:
                    rows, summary, logs = await report_data(
                        session, data, row.include_audit
                    )
                    document = await asyncio.to_thread(
                        pdf_file,
                        rows,
                        summary,
                        logs,
                        f"Empresa {tenant_id} | {data.start} a {data.end} | Origem: "
                        f"{data.source} | Gerado: {utcnow().isoformat()}",
                    )
                    directory = Path(cfg.report_directory)
                    directory.mkdir(parents=True, exist_ok=True)
                    target = directory / f"{row.id}.pdf"
                    temporary = directory / f"{row.id}.tmp"
                    temporary.write_bytes(document)
                    temporary.replace(target)
                    row.file_name = target.name
                    row.status = "ready"
                    row.error = None
                except (ValueError, OSError, BusinessError):
                    row.status = "failed"
                    row.error = (
                        "Não foi possível gerar o arquivo. "
                        "Reduza os filtros e tente novamente."
                    )
    finally:
        await cast(AsyncEngine, factory.kw["bind"]).dispose()


@app.task(name="erp.reports.dispatch")  # type: ignore[untyped-decorator]
def dispatch() -> None:
    for job_id, tenant_id in asyncio.run(pending()):
        build.delay(job_id, tenant_id)
    # Files are private, shared only by API and worker. DB rows remain audit evidence.
    import time

    for path in Path(settings().report_directory).glob("*.pdf"):
        if path.stat().st_mtime < time.time() - 86400:
            path.unlink(missing_ok=True)


@app.task(  # type: ignore[untyped-decorator]
    name="erp.reports.build",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def build(job_id: str, tenant_id: str) -> None:
    asyncio.run(generate(UUID(job_id), UUID(tenant_id)))
