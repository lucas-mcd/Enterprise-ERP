from dataclasses import asdict
from datetime import datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Numeric
from erp.presentation.dependencies import authenticated_uow, require_permissions
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.domain.security import Principal
from erp.shared.infrastructure.database.audit import AuditLog
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import EntryFilter, business_today
from erp.modules.operations.infrastructure.models import Order, OrderLine, Product
from erp.modules.fiscal.infrastructure.models import Invoice
from erp.modules.hcm.infrastructure.models import Employee
from erp.modules.identity.infrastructure.models import Role, UserRole
from erp.modules.projects.infrastructure.models import Project
from erp.modules.assets.infrastructure.models import Asset

router = APIRouter(prefix="/cockpit", tags=["cockpit"])
Uow = Annotated[SqlUnitOfWork, Depends(authenticated_uow)]
Reader = Annotated[Principal, Depends(require_permissions("identidade:dashboard:ler"))]


def money(value: Any) -> str:
    return format(Decimal(value or 0), ".2f")


@router.get("")
async def cockpit(
    uow: Uow, principal: Reader, source: Literal["demo", "real"] = "real"
) -> dict[str, Any]:
    demo = source == "demo"
    today = business_today()
    start = today.replace(day=1)
    begin = datetime.combine(start, time.min, ZoneInfo("America/Sao_Paulo"))
    finish = datetime.combine(
        today + timedelta(days=1), time.min, ZoneInfo("America/Sao_Paulo")
    )
    result: dict[str, Any] = {
        "source": source,
        "start": start,
        "end": today,
        "updated_at": datetime.now(ZoneInfo("UTC")),
        "sales": None,
        "cash": None,
        "stock": None,
        "purchases": None,
        "fiscal": None,
        "people": None,
        "audit": None,
        "projects": None,
        "assets": None,
        "approvals": None,
    }
    permissions = principal.permissions
    approval_count = 0
    approval_scopes = []
    if "vendas:pedido:ler" in permissions:
        base = [
            Order.kind == "sale",
            Order.status == "completed",
            Order.is_simulated.is_(demo),
            Order.ordered_on >= start,
            Order.ordered_on <= today,
        ]
        revenue = await uow.session.scalar(select(func.sum(Order.total)).where(*base))
        top = await uow.session.execute(
            select(
                Product.name,
                func.sum(OrderLine.quantity),
                func.sum(OrderLine.quantity * OrderLine.unit_price),
            )
            .select_from(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .join(Product, Product.id == OrderLine.product_id)
            .where(*base)
            .group_by(Product.id, Product.name)
            .order_by(
                func.sum(OrderLine.quantity * OrderLine.unit_price).desc(), Product.id
            )
            .limit(5)
        )
        result["sales"] = {
            "revenue": money(revenue),
            "top_products": [
                {"name": r[0], "quantity": r[1], "amount": money(r[2])} for r in top
            ],
        }
    if "financeiro:lancamento:ler" in permissions:
        summary = await uow.cash.summary(EntryFilter(start, today, source))
        count = await uow.session.scalar(
            select(func.count())
            .select_from(CashEntry)
            .where(
                CashEntry.is_simulated.is_(demo),
                CashEntry.status == "aguardando_aprovacao",
            )
        )
        approval_count += count or 0
        approval_scopes.append("Financeiro")
        result["cash"] = asdict(summary)
    if "estoque:saldo:ler" in permissions:
        base_stock = [
            Product.is_simulated.is_(demo),
            Product.balance <= Product.minimum,
        ]
        count = await uow.session.scalar(
            select(func.count()).select_from(Product).where(*base_stock)
        )
        stock = await uow.session.scalars(
            select(Product)
            .where(*base_stock)
            .order_by(Product.balance - Product.minimum, Product.id)
            .limit(5)
        )
        result["stock"] = {
            "critical": count or 0,
            "items": [
                {"name": r.name, "balance": r.balance, "minimum": r.minimum}
                for r in stock
            ],
        }
    if "compras:pedido:ler" in permissions:
        base_orders = [
            Order.kind == "purchase",
            Order.is_simulated.is_(demo),
            Order.status == "aguardando_aprovacao",
        ]
        count = await uow.session.scalar(
            select(func.count()).select_from(Order).where(*base_orders)
        )
        rows = await uow.session.scalars(
            select(Order)
            .where(*base_orders)
            .order_by(Order.ordered_on, Order.id)
            .limit(5)
        )
        approval_count += count or 0
        approval_scopes.append("Compras")
        result["purchases"] = {
            "waiting": count or 0,
            "items": [{"name": r.counterparty, "amount": money(r.total)} for r in rows],
        }
    if approval_scopes:
        result["approvals"] = {"count": approval_count, "scopes": approval_scopes}
    if "fiscal:documento:ler" in permissions:
        names = ["ICMS", "PIS", "COFINS", "ISS"]
        taxes = (
            await uow.session.execute(
                select(
                    *[
                        func.sum(
                            cast(Invoice.taxes[k]["amount"].as_string(), Numeric(18, 2))
                        )
                        for k in names
                    ]
                ).where(
                    Invoice.is_simulated.is_(demo),
                    Invoice.status == "autorizada",
                    Invoice.created_at >= begin,
                    Invoice.created_at < finish,
                )
            )
        ).one()
        result["fiscal"] = {k: money(taxes[i]) for i, k in enumerate(names)}
    if "rh:folha:ler" in permissions:
        people_rows = await uow.session.execute(
            select(Employee.department, func.count())
            .where(
                Employee.is_simulated.is_(demo),
                Employee.is_active.is_(True),
                Employee.hired_on <= today,
            )
            .group_by(Employee.department)
            .order_by(Employee.department)
        )
        result["people"] = [{"department": r[0], "count": r[1]} for r in people_rows]
    if "auditoria:registro:ler" in permissions:
        admin = await uow.session.scalar(
            select(Role.id)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == principal.user_id, Role.name == "Administrador")
        )
        if admin:
            audit_rows = await uow.session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.table_name.in_(
                        [
                            "cash_entries",
                            "business_orders",
                            "approval_decisions",
                            "users",
                            "simulated_invoices",
                            "payrolls",
                            "projects",
                            "project_deliveries",
                            "fixed_assets",
                        ]
                    )
                )
                .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
                .limit(5)
            )
            result["audit"] = [
                {
                    "id": r.id,
                    "table": r.table_name,
                    "operation": r.operation,
                    "date": r.occurred_at,
                    "actor_id": r.actor_id,
                }
                for r in audit_rows
            ]
    if "projetos:projeto:ler" in permissions:
        project_rows = await uow.session.execute(
            select(Project.status, func.count())
            .where(Project.is_simulated.is_(demo))
            .group_by(Project.status)
        )
        result["projects"] = {r[0]: r[1] for r in project_rows}
    if "ativos:patrimonio:ler" in permissions:
        values = (
            await uow.session.execute(
                select(func.count(), func.sum(Asset.cost)).where(
                    Asset.is_simulated.is_(demo)
                )
            )
        ).one()
        result["assets"] = {"count": values[0], "cost": money(values[1])}
    return result
