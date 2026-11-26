import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta
from pydantic import BaseModel
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response, FileResponse
from sqlalchemy import select, func
from erp.config import settings
from erp.presentation.dependencies import require_permissions, authenticated_uow
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.infrastructure.database.base import utcnow
from erp.modules.financeiro.domain.cash import EntryFilter
from erp.modules.financeiro.presentation.routers.cash import filters
from erp.modules.reports.infrastructure.models import ReportJob
from erp.modules.reports.infrastructure.render import csv_chunks, xlsx_file
from erp.modules.reports.infrastructure.service import report_data

router = APIRouter(prefix="/financeiro/exportacoes", tags=["relatórios"])
Reader = Annotated[
    Principal,
    Depends(
        require_permissions("financeiro:relatorio:ler", "financeiro:lancamento:ler")
    ),
]
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Selection = Annotated[EntryFilter, Depends(filters)]


@router.get("/planilha")
async def spreadsheet(
    principal: Reader,
    uow: Uow,
    selection: Selection,
    format: Literal["csv", "xlsx"] = "csv",
) -> Response:
    rows, _, _ = await report_data(uow.session, selection)
    headers = {
        "Content-Disposition": f'attachment; filename="fluxo-caixa.{format}"',
        "Cache-Control": "no-store",
    }
    if format == "csv":
        return StreamingResponse(
            csv_chunks(rows), media_type="text/csv; charset=utf-8", headers=headers
        )
    data = await asyncio.to_thread(xlsx_file, rows)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/pdf", status_code=202)
async def queue_pdf(
    principal: Reader, uow: Uow, selection: Selection
) -> dict[str, Any]:
    await uow.operations.actor_lock(principal.user_id)
    count = await uow.session.scalar(
        select(func.count())
        .select_from(ReportJob)
        .where(
            ReportJob.owner_id == principal.user_id,
            ReportJob.status == "queued",
            ReportJob.expires_at > utcnow(),
        )
    )
    if (count or 0) >= 3:
        raise HTTPException(429, "Aguarde seus relatórios pendentes.")
    data = asdict(selection)
    data["start"] = str(selection.start)
    data["end"] = str(selection.end)
    row = ReportJob(
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        status="queued",
        filters=data,
        include_audit="auditoria:registro:ler" in principal.permissions,
        file_name=None,
        error=None,
        expires_at=utcnow() + timedelta(hours=24),
    )
    uow.session.add(row)
    await uow.commit()
    # Durable DB queue: Beat publishes outstanding jobs. Redis outage loses no request.
    return {"id": row.id, "status": row.status, "expires_at": row.expires_at}


async def owned(uow: SqlUnitOfWork, principal: Principal, job_id: UUID) -> ReportJob:
    row = await uow.session.scalar(
        select(ReportJob).where(
            ReportJob.id == job_id, ReportJob.owner_id == principal.user_id
        )
    )
    if row is None:
        raise HTTPException(404, "Relatório não encontrado.")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=utcnow().tzinfo)
    if expires <= utcnow():
        raise HTTPException(410, "Relatório expirado.")
    if row.include_audit and "auditoria:registro:ler" not in principal.permissions:
        raise HTTPException(403, "Permissão de auditoria revogada.")
    return row


class ReportPeriod(BaseModel):
    start: str
    end: str
    source: str


class ReportSummary(BaseModel):
    id: UUID
    status: Literal["queued", "ready", "failed"]
    created_at: datetime
    expires_at: datetime
    filters: ReportPeriod
    error: str | None


@router.get("", response_model=list[ReportSummary])
async def history(principal: Reader, uow: Uow) -> list[dict[str, Any]]:
    query = select(ReportJob).where(
        ReportJob.owner_id == principal.user_id, ReportJob.expires_at > utcnow()
    )
    if "auditoria:registro:ler" not in principal.permissions:
        query = query.where(ReportJob.include_audit.is_(False))
    rows = await uow.session.scalars(
        query.order_by(ReportJob.created_at.desc()).limit(30)
    )
    return [
        {
            "id": row.id,
            "status": row.status,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "filters": row.filters,
            "error": row.error,
        }
        for row in rows
    ]


@router.get("/{job_id}")
async def job(job_id: UUID, principal: Reader, uow: Uow) -> dict[str, Any]:
    row = await owned(uow, principal, job_id)
    return {
        "id": row.id,
        "status": row.status,
        "error": row.error,
        "expires_at": row.expires_at,
    }


@router.get("/{job_id}/download")
async def download(job_id: UUID, principal: Reader, uow: Uow) -> FileResponse:
    row = await owned(uow, principal, job_id)
    if row.status != "ready":
        raise HTTPException(409, "Relatório ainda não está pronto.")
    path = Path(settings().report_directory) / f"{row.id}.pdf"
    if not path.is_file():
        raise HTTPException(410, "Arquivo indisponível. Gere novamente.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="relatorio-financeiro.pdf",
        headers={"Cache-Control": "no-store"},
    )
