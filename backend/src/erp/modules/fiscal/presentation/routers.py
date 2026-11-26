from typing import Annotated, Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, func
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.modules.governance.presentation.routers import Strict
from erp.modules.fiscal.infrastructure.models import Invoice
from erp.modules.fiscal.domain.taxes import calculate, RULE_VERSION
from erp.modules.operations.infrastructure.models import Order
from erp.modules.organization.infrastructure.models import Tenant
from erp.modules.operations.domain.orders import BusinessError

router = APIRouter(prefix="/fiscal", tags=["fiscal simulado"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Reader = Annotated[Principal, Depends(require_permissions("fiscal:documento:ler"))]
Writer = Annotated[Principal, Depends(require_permissions("fiscal:documento:emitir"))]


class Issue(Strict):
    order_id: str
    kind: Literal["nfe", "nfse"]
    regime: Literal["simples", "presumido", "real"]


class Cancel(Strict):
    reason: str = Field(min_length=15, max_length=250)


def invoice_view(r: Invoice) -> dict[str, Any]:
    return {
        "id": r.id,
        "order_id": r.order_id,
        "number": r.number,
        "kind": r.kind,
        "regime": r.regime,
        "status": r.status,
        "base": str(r.base),
        "taxes": r.taxes,
        "rule_version": r.rule_version,
        "is_simulated": r.is_simulated,
        "cancellation_reason": r.cancellation_reason,
        "fiscal_simulation": True,
    }


@router.get("/notas")
async def invoices(
    principal: Reader,
    uow: Uow,
    source: Literal["real", "demo"] = "real",
    status: Literal["processando", "autorizada", "cancelada"] | None = None,
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    where: list[Any] = [Invoice.is_simulated.is_(source == "demo")]
    if status:
        where.append(Invoice.status == status)
    total = await uow.session.scalar(
        select(func.count()).select_from(Invoice).where(*where)
    )
    rows = await uow.session.scalars(
        select(Invoice)
        .where(*where)
        .order_by(Invoice.number.desc())
        .offset((page - 1) * 10)
        .limit(10)
    )
    return {"items": [invoice_view(r) for r in rows], "total": total or 0}


@router.post("/notas", status_code=202)
async def issue(body: Issue, principal: Writer, uow: Uow) -> dict[str, Any]:
    try:
        identity = UUID(body.order_id)
    except ValueError:
        raise HTTPException(422, "Pedido inválido.") from None
    await uow.session.scalar(select(Tenant).with_for_update())
    order = await uow.session.scalar(select(Order).where(Order.id == identity))
    if order is None or order.is_simulated or order.status != "completed":
        raise BusinessError("Vincule uma venda concluída ou compra recebida real.")
    prior = await uow.session.scalar(
        select(Invoice).where(Invoice.order_id == identity, Invoice.kind == body.kind)
    )
    if prior:
        if prior.regime != body.regime:
            raise BusinessError("Nota já existe com outro regime.")
        return invoice_view(prior)
    number = (await uow.session.scalar(select(func.max(Invoice.number))) or 0) + 1
    row = Invoice(
        tenant_id=principal.tenant_id,
        order_id=order.id,
        number=number,
        kind=body.kind,
        regime=body.regime,
        status="processando",
        base=order.total,
        taxes=calculate(order.total, body.regime, body.kind),
        rule_version=RULE_VERSION,
        is_simulated=False,
        requested_by=principal.user_id,
        cancellation_reason=None,
    )
    uow.session.add(row)
    await uow.commit()
    return invoice_view(row)


@router.post("/notas/{identity}/cancelar")
async def cancel(
    identity: UUID, body: Cancel, principal: Writer, uow: Uow
) -> dict[str, Any]:
    row = await uow.session.scalar(
        select(Invoice).where(Invoice.id == identity).with_for_update()
    )
    if row is None or row.is_simulated:
        raise HTTPException(404, "Nota real não encontrada.")
    if row.status == "processando":
        raise BusinessError("Aguarde a simulação de autorização.")
    if row.status != "cancelada":
        row.status = "cancelada"
        row.cancellation_reason = body.reason
    await uow.commit()
    return invoice_view(row)


@router.get("/origens")
async def origins(uow: Uow, principal: Reader) -> list[dict[str, Any]]:
    rows = await uow.session.scalars(
        select(Order)
        .where(Order.status == "completed", Order.is_simulated.is_(False))
        .order_by(Order.ordered_on.desc(), Order.id)
        .limit(100)
    )
    return [
        {
            "id": str(r.id),
            "counterparty": r.counterparty,
            "kind": r.kind,
            "total": str(r.total),
        }
        for r in rows
    ]
