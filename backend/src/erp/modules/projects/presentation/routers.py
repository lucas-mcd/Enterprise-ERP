from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from pydantic import Field
from sqlalchemy import select, func, or_
from erp.modules.governance.presentation.routers import Strict
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.domain.security import Principal
from erp.modules.projects.infrastructure.models import Project, Allocation, Delivery
from erp.modules.projects.infrastructure.repository import EnterpriseRepository
from erp.modules.operations.domain.orders import BusinessError
from erp.modules.financeiro.domain.cash import business_today

router = APIRouter(prefix="/projetos", tags=["projetos"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Read = Annotated[Principal, Depends(require_permissions("projetos:projeto:ler"))]
Write = Annotated[Principal, Depends(require_permissions("projetos:projeto:escrever"))]
Bill = Annotated[
    Principal,
    Depends(
        require_permissions(
            "projetos:entrega:faturar", "financeiro:lancamento:escrever"
        )
    ),
]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Money = Annotated[str, Field(pattern=r"^[0-9]{1,9}\.[0-9]{2}$")]


class ProjectInput(Strict):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=3, max_length=160)
    customer: str = Field(min_length=2, max_length=120)
    budget: Money


class StateInput(Strict):
    version: int = Field(ge=1)
    status: Literal["planejamento", "em_execucao", "concluido"]


class AllocationInput(Strict):
    description: str = Field(min_length=3, max_length=180)
    worked_on: str
    hours: str = Field(pattern=r"^[0-9]{1,3}\.[0-9]{2}$")
    hourly_cost: Money


class DeliveryInput(Strict):
    description: str = Field(min_length=3, max_length=160)
    amount: Money
    due_date: str


def day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "Data inválida.") from None
    if not date(2000, 1, 1) <= result <= date(2100, 12, 31):
        raise HTTPException(422, "Data fora do intervalo suportado.")
    return result


@router.get("")
async def listing(
    uow: Uow,
    principal: Read,
    source: Literal["demo", "real"] = "real",
    q: str = "",
    status: Literal["", "planejamento", "em_execucao", "concluido"] = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    where: list[Any] = [Project.is_simulated.is_(source == "demo")]
    if q:
        where.append(
            or_(
                Project.name.icontains(q[:100], autoescape=True),
                Project.code.icontains(q[:100], autoescape=True),
            )
        )
    if status:
        where.append(Project.status == status)
    count = await uow.session.scalar(
        select(func.count()).select_from(Project).where(*where)
    )
    rows = await uow.session.scalars(
        select(Project)
        .where(*where)
        .order_by(Project.created_at.desc(), Project.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    repo = EnterpriseRepository(uow.session)
    return {"items": await repo.project_views(list(rows)), "total": count or 0}


@router.post("", status_code=201)
async def create(body: ProjectInput, uow: Uow, principal: Write) -> dict[str, Any]:
    repo = EnterpriseRepository(uow.session)
    await repo.lock_tenant()
    if await uow.session.scalar(
        select(Project.id).where(Project.code == body.code.upper())
    ):
        raise BusinessError("Código já utilizado, inclusive no histórico.")
    row = Project(
        tenant_id=principal.tenant_id,
        code=body.code.upper(),
        name=body.name,
        customer=body.customer,
        budget=Decimal(body.budget),
        status="planejamento",
        is_simulated=False,
    )
    uow.session.add(row)
    await uow.commit()
    return await repo.project_view(row)


@router.patch("/{identity}/status")
async def change(
    identity: UUID, body: StateInput, uow: Uow, principal: Write
) -> dict[str, str]:
    row = await EnterpriseRepository(uow.session).project(identity, body.version)
    transitions = {
        "planejamento": {"em_execucao"},
        "em_execucao": {"concluido"},
        "concluido": set(),
    }
    if body.status != row.status and body.status not in transitions[row.status]:
        raise BusinessError("Transição de status inválida.")
    row.status = body.status
    await uow.commit()
    return {"status": row.status}


@router.post("/{identity}/horas", status_code=201)
async def allocate(
    identity: UUID, body: AllocationInput, key: Key, uow: Uow, principal: Write
) -> dict[str, UUID]:
    worked = day(body.worked_on)
    if worked > business_today() or Decimal(body.hours) <= 0:
        raise HTTPException(422, "Horas positivas e data não futura são obrigatórias.")
    row = await EnterpriseRepository(uow.session).allocate(
        identity,
        key,
        body.description,
        worked,
        Decimal(body.hours),
        Decimal(body.hourly_cost),
    )
    await uow.commit()
    return {"id": row.id}


@router.post("/{identity}/entregas", status_code=201)
async def bill(
    identity: UUID, body: DeliveryInput, key: Key, uow: Uow, principal: Bill
) -> dict[str, UUID]:
    if Decimal(body.amount) <= 0:
        raise HTTPException(422, "Valor deve ser positivo.")
    row = await EnterpriseRepository(uow.session).bill(
        identity,
        key,
        body.description,
        Decimal(body.amount),
        day(body.due_date),
        principal.user_id,
    )
    await uow.commit()
    return {"id": row.id, "cash_entry_id": row.cash_entry_id}


@router.get("/{identity}/historico")
async def history(
    identity: UUID, uow: Uow, principal: Read, page: int = Query(1, ge=1)
) -> dict[str, Any]:
    if (
        await uow.session.scalar(select(Project.id).where(Project.id == identity))
        is None
    ):
        raise HTTPException(404, "Projeto não encontrado.")
    allocations = await uow.session.scalars(
        select(Allocation)
        .where(Allocation.project_id == identity)
        .order_by(Allocation.worked_on.desc(), Allocation.id)
        .offset((page - 1) * 20)
        .limit(20)
    )
    deliveries = await uow.session.scalars(
        select(Delivery)
        .where(Delivery.project_id == identity)
        .order_by(Delivery.created_at.desc(), Delivery.id)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "hours": [
            {
                "id": r.id,
                "description": r.description,
                "date": r.worked_on,
                "hours": str(r.hours),
                "cost": str(r.hours * r.hourly_cost),
            }
            for r in allocations
        ],
        "deliveries": [
            {
                "id": r.id,
                "description": r.description,
                "amount": str(r.amount),
                "cash_entry_id": r.cash_entry_id,
            }
            for r in deliveries
        ],
    }


@router.delete("/{identity}", status_code=204)
async def archive(
    identity: UUID, uow: Uow, principal: Write, version: int = Query(ge=1)
) -> None:
    row = await EnterpriseRepository(uow.session).project(identity, version)
    if row.status != "planejamento":
        raise BusinessError("Somente planejamento sem execução pode ser arquivado.")
    row.soft_delete()
    await uow.commit()
