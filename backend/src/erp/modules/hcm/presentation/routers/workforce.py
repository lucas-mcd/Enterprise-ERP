from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, func
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.modules.governance.presentation.routers import Strict
from erp.modules.hcm.infrastructure.models import Employee, Payroll
from erp.modules.operations.domain.orders import BusinessError
from erp.modules.organization.infrastructure.models import Tenant
from erp.modules.financeiro.domain.cash import NewEntry

router = APIRouter(prefix="/rh", tags=["pessoas"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Reader = Annotated[Principal, Depends(require_permissions("rh:folha:ler"))]
Writer = Annotated[Principal, Depends(require_permissions("rh:folha:processar"))]


class EmployeeInput(Strict):
    registration: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=3, max_length=120)
    department: str = Field(min_length=2, max_length=80)
    job_title: str = Field(min_length=2, max_length=80)
    base_salary: str = Field(pattern=r"^[0-9]{1,7}\.[0-9]{2}$")
    hired_on: str
    is_active: bool = True


class MonthInput(Strict):
    month: str


class ProvisionInput(Strict):
    due_date: str


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "Data inválida.") from None


def employee_view(row: Employee) -> dict[str, Any]:
    return {
        "id": row.id,
        "registration": row.registration,
        "name": row.name,
        "department": row.department,
        "job_title": row.job_title,
        "base_salary": str(row.base_salary),
        "hired_on": row.hired_on,
        "is_active": row.is_active,
        "is_simulated": row.is_simulated,
    }


@router.get("/colaboradores")
async def employees(
    principal: Reader,
    uow: Uow,
    source: Literal["real", "demo"] = "real",
    q: str = "",
    department: str = "",
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    where: list[Any] = [Employee.is_simulated.is_(source == "demo")]
    if q:
        where.append(Employee.name.icontains(q[:100], autoescape=True))
    if department:
        where.append(Employee.department == department)
    total = await uow.session.scalar(
        select(func.count()).select_from(Employee).where(*where)
    )
    rows = await uow.session.scalars(
        select(Employee)
        .where(*where)
        .order_by(Employee.name, Employee.id)
        .offset((page - 1) * 10)
        .limit(10)
    )
    return {"items": [employee_view(r) for r in rows], "total": total or 0}


async def employee_save(
    body: EmployeeInput,
    principal: Principal,
    uow: SqlUnitOfWork,
    identity: UUID | None = None,
) -> dict[str, Any]:
    amount = Decimal(body.base_salary)
    hired = parse_date(body.hired_on)
    if amount <= 0 or not date(1950, 1, 1) <= hired <= date(2100, 12, 31):
        raise HTTPException(422, "Salário ou admissão inválidos.")
    if identity:
        row = await uow.session.scalar(
            select(Employee).where(Employee.id == identity).with_for_update()
        )
        if row is None or row.is_simulated:
            raise HTTPException(404, "Colaborador real não encontrado.")
        if row.registration != body.registration:
            raise BusinessError("Matrícula é imutável.")
        row.name = body.name
        row.department = body.department
        row.job_title = body.job_title
        row.hired_on = hired
        row.base_salary = amount
        row.is_active = body.is_active
    else:
        await uow.session.scalar(select(Tenant).with_for_update())
        duplicate = await uow.session.scalar(
            select(Employee.id).where(Employee.registration == body.registration)
        )
        if duplicate:
            raise BusinessError("Matrícula já cadastrada nesta empresa.")
        row = Employee(
            tenant_id=principal.tenant_id,
            registration=body.registration,
            name=body.name,
            department=body.department,
            job_title=body.job_title,
            base_salary=amount,
            hired_on=hired,
            is_active=body.is_active,
            is_simulated=False,
        )
        uow.session.add(row)
    await uow.commit()
    return employee_view(row)


@router.post("/colaboradores", status_code=201)
async def create_employee(
    body: EmployeeInput, principal: Writer, uow: Uow
) -> dict[str, Any]:
    return await employee_save(body, principal, uow)


@router.put("/colaboradores/{identity}")
async def update_employee(
    identity: UUID, body: EmployeeInput, principal: Writer, uow: Uow
) -> dict[str, Any]:
    return await employee_save(body, principal, uow, identity)


def payroll_view(row: Payroll) -> dict[str, Any]:
    return {
        "id": row.id,
        "month": row.month,
        "status": row.status,
        "gross": str(row.gross),
        "deductions": str(row.deductions),
        "net": str(row.net),
        "lines": row.lines,
        "cash_entry_id": row.cash_entry_id,
        "is_simulated": row.is_simulated,
    }


@router.get("/folhas")
async def payrolls(
    principal: Reader,
    uow: Uow,
    source: Literal["real", "demo"] = "real",
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    where: list[Any] = [Payroll.is_simulated.is_(source == "demo")]
    total = await uow.session.scalar(
        select(func.count()).select_from(Payroll).where(*where)
    )
    rows = await uow.session.scalars(
        select(Payroll)
        .where(*where)
        .order_by(Payroll.month.desc())
        .offset((page - 1) * 10)
        .limit(10)
    )
    return {"items": [payroll_view(r) for r in rows], "total": total or 0}


@router.post("/folhas", status_code=201)
async def calculate_payroll(
    body: MonthInput, principal: Writer, uow: Uow
) -> dict[str, Any]:
    month = parse_date(body.month + "-01")
    if not date(2000, 1, 1) <= month <= date(2100, 12, 1):
        raise HTTPException(422, "Competência inválida.")
    await uow.session.scalar(select(Tenant).with_for_update())
    prior = await uow.session.scalar(
        select(Payroll).where(Payroll.month == month, Payroll.is_simulated.is_(False))
    )
    if prior:
        return payroll_view(prior)
    people = list(
        await uow.session.scalars(
            select(Employee)
            .where(
                Employee.is_simulated.is_(False),
                Employee.is_active.is_(True),
                Employee.hired_on
                <= month.replace(day=monthrange(month.year, month.month)[1]),
            )
            .order_by(Employee.id)
            .limit(1001)
        )
    )
    if not people or len(people) > 1000:
        raise BusinessError(
            "Selecione uma competência com 1 a 1.000 colaboradores ativos."
        )
    gross = sum((p.base_salary for p in people), Decimal("0"))
    if gross > Decimal("999999999.99"):
        raise BusinessError("Folha acima do limite financeiro.")
    row = Payroll(
        tenant_id=principal.tenant_id,
        month=month,
        status="calculada",
        gross=gross,
        deductions=Decimal("0"),
        net=gross,
        lines=[
            {
                "employee_id": str(p.id),
                "name": p.name,
                "department": p.department,
                "job_title": p.job_title,
                "base_salary": str(p.base_salary),
                "net": str(p.base_salary),
            }
            for p in people
        ],
        is_simulated=False,
        cash_entry_id=None,
    )
    uow.session.add(row)
    await uow.commit()
    return payroll_view(row)


@router.post("/folhas/{identity}/provisionar")
async def provision(
    identity: UUID, body: ProvisionInput, principal: Writer, uow: Uow
) -> dict[str, Any]:
    day = parse_date(body.due_date)
    if not date(2000, 1, 1) <= day <= date(2100, 12, 31):
        raise HTTPException(422, "Vencimento inválido.")
    row = await uow.session.scalar(
        select(Payroll).where(Payroll.id == identity).with_for_update()
    )
    if row is None or row.is_simulated:
        raise HTTPException(404, "Folha real não encontrada.")
    if row.cash_entry_id:
        return payroll_view(row)
    result, _ = await uow.cash.create(
        NewEntry(
            f"Folha salarial {row.month:%Y-%m}",
            "Colaboradores",
            "Pessoal",
            "despesa",
            "pendente",
            row.net,
            day,
            None,
        ),
        principal.user_id,
        row.id,
    )
    row.cash_entry_id = result.id
    row.status = "provisionada"
    await uow.commit()
    return payroll_view(row)
