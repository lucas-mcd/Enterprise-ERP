from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.modules.operations.infrastructure.models import (
    Order,
    OrderLine,
    Product,
    StockMovement,
)
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today, CATEGORIES
from erp.modules.identity.infrastructure.models import User
from erp.modules.organization.infrastructure.models import Tenant
from erp.modules.governance.infrastructure.models import Budget
from erp.modules.governance.presentation.routers import Strict
from pydantic import Field

router = APIRouter(prefix="/bi", tags=["analytics"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]


def amount(value: Any) -> str:
    return format(Decimal(value or 0).quantize(Decimal(".01")), ".2f")


def period(start: date, end: date) -> None:
    if (
        not date(2000, 1, 1) <= start <= end <= date(2100, 12, 31)
        or (end - start).days > 365
    ):
        raise HTTPException(422, "Período deve ter até 366 dias.")


async def sales_data(
    uow: SqlUnitOfWork, start: date, end: date, demo: bool
) -> dict[str, Any]:
    where = [
        Order.kind == "sale",
        Order.status == "completed",
        Order.is_simulated.is_(demo),
        Order.ordered_on >= start,
        Order.ordered_on <= end,
    ]
    totals = (
        await uow.session.execute(
            select(func.count(), func.sum(Order.total), func.sum(Order.variable_cost))
            .select_from(Order)
            .where(*where)
        )
    ).one()
    revenue = Decimal(totals[1] or 0)
    count = int(totals[0])
    categories = await uow.session.execute(
        select(Product.category, func.sum(OrderLine.quantity * OrderLine.unit_price))
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .join(Product, Product.id == OrderLine.product_id)
        .where(*where)
        .group_by(Product.category)
    )
    sellers = await uow.session.execute(
        select(User.display_name, Order.created_by, func.sum(Order.total))
        .select_from(Order)
        .outerjoin(User, User.id == Order.created_by)
        .where(*where)
        .group_by(User.display_name, Order.created_by)
    )
    costs = (
        await uow.session.execute(
            select(
                func.count(),
                func.sum(case((OrderLine.unit_cost.is_(None), 1), else_=0)),
                func.sum(OrderLine.unit_cost * OrderLine.quantity),
            )
            .select_from(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .where(*where)
        )
    ).one()
    margin = (
        None
        if not revenue or costs[1]
        else amount(
            (revenue - Decimal(costs[2] or 0) - Decimal(totals[2] or 0)) / revenue * 100
        )
    )
    return {
        "ticket": amount(revenue / count) if count else "0.00",
        "sales_count": count,
        "revenue": amount(revenue),
        "margin": margin,
        "cost_coverage": (
            amount(
                (Decimal(costs[0]) - Decimal(costs[1] or 0)) / Decimal(costs[0]) * 100
            )
            if costs[0]
            else "0.00"
        ),
        "categories": [{"name": x[0], "amount": amount(x[1])} for x in categories],
        "sellers": [
            {
                "name": x[0]
                or ("Equipe demonstração" if demo else "Usuário indisponível"),
                "amount": amount(x[2]),
            }
            for x in sellers
        ],
    }


@router.get("/vendas")
async def sales(
    uow: Uow,
    principal: Annotated[Principal, Depends(require_permissions("vendas:pedido:ler"))],
    start_date: date,
    end_date: date,
    source: Literal["demo", "real"] = "real",
) -> dict[str, Any]:
    period(start_date, end_date)
    return await sales_data(uow, start_date, end_date, source == "demo")


@router.get("/overview")
async def overview(
    uow: Uow,
    principal: Annotated[
        Principal, Depends(require_permissions("financeiro:lancamento:ler"))
    ],
    start_date: date,
    end_date: date,
    source: Literal["demo", "real"] = "real",
) -> dict[str, Any]:
    period(start_date, end_date)
    demo = source == "demo"
    sale = (
        await sales_data(uow, start_date, end_date, demo)
        if "vendas:pedido:ler" in principal.permissions
        else None
    )
    receivables = (
        await uow.session.execute(
            select(
                func.sum(CashEntry.amount),
                func.sum(
                    case(
                        (CashEntry.due_date < business_today(), CashEntry.amount),
                        else_=0,
                    )
                ),
            ).where(
                CashEntry.kind == "receita",
                CashEntry.status.in_(["pendente", "aguardando_aprovacao"]),
                CashEntry.is_simulated.is_(demo),
                CashEntry.due_date >= start_date,
                CashEntry.due_date <= end_date,
            )
        )
    ).one()
    delinquency = (
        amount(Decimal(receivables[1] or 0) / Decimal(receivables[0]) * 100)
        if receivables[0]
        else "0.00"
    )
    turnover = None
    if "estoque:saldo:ler" in principal.permissions:
        begin = datetime.combine(start_date, time.min, ZoneInfo("America/Sao_Paulo"))
        finish = datetime.combine(
            end_date + timedelta(days=1), time.min, ZoneInfo("America/Sao_Paulo")
        )
        balance = Decimal(
            await uow.session.scalar(
                select(func.sum(Product.balance)).where(Product.is_simulated.is_(demo))
            )
            or 0
        )
        movement = (
            await uow.session.execute(
                select(
                    func.sum(
                        case(
                            (StockMovement.created_at >= begin, StockMovement.quantity),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (
                                StockMovement.created_at >= finish,
                                StockMovement.quantity,
                            ),
                            else_=0,
                        )
                    ),
                )
                .select_from(StockMovement)
                .join(Product, Product.id == StockMovement.product_id)
                .where(Product.is_simulated.is_(demo))
            )
        ).one()
        opening = balance - Decimal(movement[0] or 0)
        closing = balance - Decimal(movement[1] or 0)
        average = (opening + closing) / 2
        out = await uow.session.scalar(
            select(func.sum(-StockMovement.quantity))
            .select_from(StockMovement)
            .join(Product, Product.id == StockMovement.product_id)
            .join(Order, Order.id == StockMovement.order_id)
            .where(
                Product.is_simulated.is_(demo),
                Order.kind == "sale",
                StockMovement.quantity < 0,
                StockMovement.created_at >= begin,
                StockMovement.created_at < finish,
            )
        )
        if average > 0:
            turnover = amount(Decimal(out or 0) / average)
    budgets = list(
        await uow.session.scalars(
            select(Budget).where(
                Budget.is_simulated.is_(demo),
                Budget.month >= start_date.replace(day=1),
                Budget.month <= end_date.replace(day=1),
            )
        )
    )
    actual = list(
        await uow.session.execute(
            select(CashEntry.effective_on, CashEntry.kind, func.sum(CashEntry.amount))
            .where(
                CashEntry.is_simulated.is_(demo),
                CashEntry.status == "concluido",
                CashEntry.effective_on >= start_date,
                CashEntry.effective_on <= end_date,
            )
            .group_by(CashEntry.effective_on, CashEntry.kind)
        )
    )
    months: dict[str, dict[str, Any]] = {}
    cursor = start_date.replace(day=1)
    while cursor <= end_date:
        stop = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        days = (min(stop, end_date) - max(cursor, start_date)).days + 1
        key = str(cursor)[:7]
        months[key] = {
            "month": key,
            "budget_income": Decimal("0"),
            "budget_expense": Decimal("0"),
            "actual_income": Decimal("0"),
            "actual_expense": Decimal("0"),
        }
        for b in budgets:
            if b.month == cursor:
                months[key][
                    "budget_income" if b.kind == "receita" else "budget_expense"
                ] += (b.amount * days / stop.day)
        for day, kind, value in actual:
            if str(day)[:7] == key:
                months[key][
                    "actual_income" if kind == "receita" else "actual_expense"
                ] += Decimal(value)
        cursor = (stop + timedelta(days=1)).replace(day=1)
    return {
        "sales": sale,
        "turnover": turnover,
        "delinquency": delinquency,
        "budgets": [
            {k: amount(v) if isinstance(v, Decimal) else v for k, v in row.items()}
            for row in months.values()
        ],
    }


class BudgetInput(Strict):
    month: str
    category: str
    kind: Literal["receita", "despesa"]
    amount: str = Field(pattern=r"^[0-9]{1,9}\.[0-9]{2}$")


@router.put("/orcamento")
async def budget(
    body: BudgetInput,
    uow: Uow,
    principal: Annotated[
        Principal, Depends(require_permissions("financeiro:lancamento:escrever"))
    ],
) -> dict[str, str]:
    try:
        month = date.fromisoformat(body.month + "-01")
    except ValueError:
        raise HTTPException(422, "Competência inválida.") from None
    if not 2000 <= month.year <= 2100:
        raise HTTPException(422, "Competência fora do intervalo suportado.")
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Categoria inválida.")
    await uow.session.scalar(select(Tenant).with_for_update())
    row = await uow.session.scalar(
        select(Budget).where(
            Budget.month == month,
            Budget.category == body.category,
            Budget.kind == body.kind,
            Budget.is_simulated.is_(False),
        )
    )
    if row:
        row.amount = Decimal(body.amount)
    else:
        uow.session.add(
            Budget(
                tenant_id=principal.tenant_id,
                month=month,
                category=body.category,
                kind=body.kind,
                amount=Decimal(body.amount),
                is_simulated=False,
            )
        )
    await uow.commit()
    return {"status": "saved"}
