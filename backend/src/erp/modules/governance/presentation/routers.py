from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from erp.presentation.dependencies import (
    authenticated_uow,
    require_permissions,
    get_current_user,
)
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.infrastructure.database.audit import AuditLog
from erp.modules.identity.infrastructure.models import User, Role, UserRole
from erp.modules.operations.infrastructure.models import Order
from erp.modules.operations.domain.orders import BusinessError
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.governance.infrastructure.models import Approval
from erp.modules.reports.infrastructure.render import grid_file
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["governança"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Current = Annotated[Principal, Depends(get_current_user)]


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)


class LimitInput(Strict):
    amount: str = Field(pattern=r"^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$")


class RowInput(Strict):
    id: str
    version: int = Field(ge=1)


class BulkInput(Strict):
    rows: list[RowInput] = Field(min_length=1, max_length=100)
    settled_on: str | None = None
    format: Literal["csv", "xlsx"] = "csv"


async def admin(principal: Current, uow: Uow) -> Principal:
    role = await uow.session.scalar(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == principal.user_id, Role.name == "Administrador")
    )
    if role is None or "auditoria:registro:ler" not in principal.permissions:
        raise HTTPException(403, "Área exclusiva de administradores.")
    return principal


Admin = Annotated[Principal, Depends(admin)]


@router.get("/governanca/usuarios")
async def users(principal: Admin, uow: Uow) -> list[dict[str, Any]]:
    rows = await uow.session.scalars(
        select(User).order_by(User.display_name).limit(500)
    )
    return [
        {"id": r.id, "name": r.display_name, "approval_limit": str(r.approval_limit)}
        for r in rows
    ]


@router.put("/governanca/usuarios/{user_id}/alcada")
async def set_limit(
    user_id: UUID, body: LimitInput, principal: Admin, uow: Uow
) -> dict[str, str]:
    row = await uow.session.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Usuário não encontrado.")
    row.approval_limit = Decimal(body.amount)
    await uow.commit()
    return {"approval_limit": str(row.approval_limit)}


@router.get("/governanca/auditoria")
async def audit(
    principal: Admin,
    uow: Uow,
    user_id: UUID | None = None,
    table: str | None = None,
    operation: Literal["INSERT", "UPDATE", "DELETE"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    where = []
    if user_id:
        where.append(AuditLog.actor_id == user_id)
    if table:
        where.append(AuditLog.table_name == table)
    if operation:
        where.append(AuditLog.operation == operation)
    total = await uow.session.scalar(
        select(func.count()).select_from(AuditLog).where(*where)
    )
    rows = await uow.session.scalars(
        select(AuditLog)
        .where(*where)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                "id": r.id,
                "actor_id": r.actor_id,
                "table": r.table_name,
                "operation": r.operation,
                "occurred_at": r.occurred_at,
                "entity_id": r.entity_id,
                "diff": r.diff,
            }
            for r in rows
        ],
        "total": total or 0,
    }


@router.post("/governanca/aprovar/{resource}/{identity}")
async def approve(
    resource: Literal["cash", "purchase"], identity: UUID, principal: Current, uow: Uow
) -> dict[str, str]:
    permission = (
        "financeiro:lancamento:escrever"
        if resource == "cash"
        else "compras:aprovacao:senior"
    )
    if permission not in principal.permissions:
        raise HTTPException(403, "Permissão de aprovação necessária.")
    # Re-read the current limit under lock; never authorize using stale JWT data.
    actor = await uow.session.scalar(
        select(User)
        .where(User.id == principal.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource == "cash":
        row = await uow.session.scalar(
            select(CashEntry).where(CashEntry.id == identity).with_for_update()
        )
    else:
        row = await uow.session.scalar(
            select(Order)
            .where(Order.id == identity, Order.kind == "purchase")
            .with_for_update()
        )
    if row is None or row.is_simulated:
        raise HTTPException(404, "Registro real não encontrado.")
    amount = row.amount if isinstance(row, CashEntry) else row.total
    if actor is None or not actor.is_active or actor.approval_limit < amount:
        raise HTTPException(403, "Alçada insuficiente para este valor.")
    if row.status != "aguardando_aprovacao":
        prior = await uow.session.scalar(
            select(Approval).where(
                Approval.resource_type == resource, Approval.resource_id == identity
            )
        )
        if prior:
            return {"status": row.status}
        raise BusinessError("Registro não está aguardando aprovação.")
    row.status = "pendente" if resource == "cash" else "draft"
    uow.session.add(
        Approval(
            tenant_id=principal.tenant_id,
            resource_type=resource,
            resource_id=identity,
            reviewer_id=principal.user_id,
            amount=amount,
            limit_snapshot=actor.approval_limit,
        )
    )
    await uow.commit()
    return {"status": row.status}


async def selected(body: BulkInput, uow: SqlUnitOfWork) -> list[CashEntry]:
    try:
        ids = [UUID(r.id) for r in body.rows]
    except ValueError:
        raise HTTPException(422, "Identificador inválido.") from None
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Seleção repetida.")
    rows = list(
        await uow.session.scalars(
            select(CashEntry)
            .where(CashEntry.id.in_(ids))
            .order_by(CashEntry.id)
            .with_for_update()
        )
    )
    if len(rows) != len(ids):
        raise HTTPException(404, "Seleção inválida ou indisponível.")
    return rows


@router.post("/financeiro/lotes/baixar")
async def settle(
    body: BulkInput,
    uow: Uow,
    principal: Annotated[
        Principal, Depends(require_permissions("financeiro:lancamento:escrever"))
    ],
) -> dict[str, int]:
    try:
        day = date.fromisoformat(body.settled_on or "")
    except ValueError:
        raise HTTPException(422, "Data de baixa inválida.") from None
    if not date(2000, 1, 1) <= day <= business_today():
        raise HTTPException(422, "Data de baixa futura ou inválida.")
    rows = await selected(body, uow)
    versions = {r.id: r.version for r in body.rows}
    for row in rows:
        if row.is_simulated or row.status == "aguardando_aprovacao":
            raise BusinessError("Lote contém demonstração ou registro não aprovado.")
        if row.status == "concluido" and row.settled_on == day:
            continue
        if row.status != "pendente" or row.version != versions[str(row.id)]:
            raise BusinessError("Dados alterados. Atualize a seleção.")
        row.status = "concluido"
        row.settled_on = day
        row.effective_on = day
    await uow.commit()
    return {"processed": len(rows)}


@router.post("/financeiro/lotes/exportar")
async def export_selected(
    body: BulkInput,
    uow: Uow,
    principal: Annotated[
        Principal,
        Depends(
            require_permissions("financeiro:lancamento:ler", "financeiro:relatorio:ler")
        ),
    ],
) -> StreamingResponse:
    rows = await selected(body, uow)
    import asyncio

    content = await asyncio.to_thread(
        grid_file,
        ["Descrição", "Tipo", "Status", "Valor BRL"],
        [[r.description, r.kind, r.status, str(r.amount)] for r in rows],
        body.format,
        {3},
    )
    return StreamingResponse(
        iter([content]),
        media_type=(
            "text/csv"
            if body.format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="selecionados.{body.format}"',
            "Cache-Control": "no-store",
        },
    )
