from decimal import Decimal
from typing import Any, Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import Field
from sqlalchemy import select, func, or_
from erp.modules.projects.presentation.routers import Uow, Key, Money, day
from erp.modules.governance.presentation.routers import Strict
from erp.presentation.dependencies import require_permissions
from erp.shared.domain.security import Principal
from erp.modules.assets.infrastructure.models import Asset, Maintenance
from erp.modules.projects.infrastructure.repository import EnterpriseRepository
from erp.modules.operations.domain.orders import BusinessError
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.hcm.infrastructure.models import Employee

router = APIRouter(prefix="/ativos", tags=["patrimonio"])
Read = Annotated[Principal, Depends(require_permissions("ativos:patrimonio:ler"))]
Write = Annotated[Principal, Depends(require_permissions("ativos:patrimonio:escrever"))]


class AssetInput(Strict):
    tag: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=3, max_length=160)
    category: str = Field(min_length=2, max_length=60)
    cost: Money
    residual: Money
    life_months: int = Field(ge=1, le=1200)
    service_on: str


class AssignInput(Strict):
    employee_id: str | None = None
    version: int = Field(ge=1)


class MaintenanceInput(Strict):
    description: str = Field(min_length=5, max_length=240)
    performed_on: str
    cost: Money


@router.get("")
async def listing(
    uow: Uow,
    principal: Read,
    source: Literal["demo", "real"] = "real",
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    as_of: str | None = None,
) -> dict[str, Any]:
    when = day(as_of) if as_of else business_today()
    where: list[Any] = [Asset.is_simulated.is_(source == "demo")]
    if q:
        where.append(
            or_(
                Asset.name.icontains(q[:100], autoescape=True),
                Asset.tag.icontains(q[:100], autoescape=True),
            )
        )
    count = await uow.session.scalar(
        select(func.count()).select_from(Asset).where(*where)
    )
    rows = await uow.session.scalars(
        select(Asset)
        .where(*where)
        .order_by(Asset.tag, Asset.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    repo = EnterpriseRepository(uow.session)
    return {
        "items": [await repo.asset_view(r, when) for r in rows],
        "total": count or 0,
    }


@router.get("/responsaveis")
async def employees(uow: Uow, principal: Write, q: str = "") -> list[dict[str, Any]]:
    rows = await uow.session.scalars(
        select(Employee)
        .where(
            Employee.is_active.is_(True),
            Employee.is_simulated.is_(False),
            Employee.name.icontains(q[:100], autoescape=True),
        )
        .order_by(Employee.name, Employee.id)
        .limit(100)
    )
    return [{"id": r.id, "name": r.name, "department": r.department} for r in rows]


@router.post("", status_code=201)
async def create(body: AssetInput, uow: Uow, principal: Write) -> dict[str, Any]:
    repo = EnterpriseRepository(uow.session)
    await repo.lock_tenant()
    if await uow.session.scalar(select(Asset.id).where(Asset.tag == body.tag.upper())):
        raise BusinessError("Plaqueta já utilizada, inclusive no histórico.")
    if Decimal(body.cost) <= 0 or Decimal(body.residual) > Decimal(body.cost):
        raise HTTPException(422, "Custo/residual inválido.")
    row = Asset(
        tenant_id=principal.tenant_id,
        tag=body.tag.upper(),
        name=body.name,
        category=body.category,
        cost=Decimal(body.cost),
        residual=Decimal(body.residual),
        life_months=body.life_months,
        service_on=day(body.service_on),
        employee_id=None,
        is_simulated=False,
    )
    uow.session.add(row)
    await uow.commit()
    return await repo.asset_view(row, business_today())


@router.put("/{identity}/posse")
async def assign(
    identity: UUID, body: AssignInput, uow: Uow, principal: Write
) -> dict[str, Any]:
    repo = EnterpriseRepository(uow.session)
    row = await repo.asset(identity)
    if row.version != body.version:
        raise BusinessError("Ativo alterado. Atualize a tela.")
    try:
        employee = UUID(body.employee_id) if body.employee_id else None
    except ValueError:
        raise HTTPException(422, "Colaborador inválido.") from None
    await repo.assign(row, employee)
    await uow.commit()
    return await repo.asset_view(row, business_today())


@router.post("/{identity}/manutencoes", status_code=201)
async def maintain(
    identity: UUID, body: MaintenanceInput, key: Key, uow: Uow, principal: Write
) -> dict[str, UUID]:
    repo = EnterpriseRepository(uow.session)
    await repo.lock_tenant()
    await repo.asset(identity)
    when = day(body.performed_on)
    if when > business_today():
        raise HTTPException(422, "Manutenção realizada não pode ter data futura.")
    old = await uow.session.scalar(
        select(Maintenance).where(Maintenance.request_key == key)
    )
    if old:
        if (old.asset_id, old.description, old.performed_on, old.cost) != (
            identity,
            body.description,
            when,
            Decimal(body.cost),
        ):
            raise BusinessError("Chave reutilizada com outros dados.")
        return {"id": old.id}
    row = Maintenance(
        tenant_id=principal.tenant_id,
        asset_id=identity,
        description=body.description,
        performed_on=when,
        cost=Decimal(body.cost),
        request_key=key,
    )
    uow.session.add(row)
    await uow.commit()
    return {"id": row.id}


@router.get("/{identity}/manutencoes")
async def history(
    identity: UUID, uow: Uow, principal: Read, page: int = Query(1, ge=1)
) -> dict[str, Any]:
    if await uow.session.scalar(select(Asset.id).where(Asset.id == identity)) is None:
        raise HTTPException(404, "Ativo não encontrado.")
    rows = await uow.session.scalars(
        select(Maintenance)
        .where(Maintenance.asset_id == identity)
        .order_by(Maintenance.performed_on.desc(), Maintenance.id)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "items": [
            {
                "id": r.id,
                "date": r.performed_on,
                "description": r.description,
                "cost": str(r.cost),
            }
            for r in rows
        ]
    }


@router.delete("/{identity}", status_code=204)
async def archive(
    identity: UUID, uow: Uow, principal: Write, version: int = Query(ge=1)
) -> None:
    row = await EnterpriseRepository(uow.session).asset(identity)
    if row.version != version:
        raise BusinessError("Ativo alterado. Atualize a tela.")
    if row.employee_id:
        raise BusinessError("Devolva a posse antes de arquivar.")
    row.soft_delete()
    await uow.commit()
