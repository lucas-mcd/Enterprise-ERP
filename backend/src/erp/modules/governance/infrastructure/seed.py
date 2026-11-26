from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.fiscal.infrastructure.models import Invoice
from erp.modules.fiscal.domain.taxes import calculate, RULE_VERSION
from erp.modules.hcm.infrastructure.models import Employee, Payroll
from erp.modules.governance.infrastructure.models import Budget
from erp.modules.operations.infrastructure.models import Order, OrderLine, Product
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today


async def seed_ecosystem(session: AsyncSession, tenant: UUID) -> int:
    created = 0
    today = business_today()
    actor = uuid5(tenant, "seed:service")
    orders = list(
        await session.scalars(
            select(Order)
            .where(Order.is_simulated.is_(True), Order.status == "completed")
            .order_by(Order.id)
        )
    )
    for order in orders:
        lines = await session.scalars(
            select(OrderLine).where(OrderLine.order_id == order.id)
        )
        for line in lines:
            if line.unit_cost is None:
                line.unit_cost = (line.unit_price * Decimal(".6")).quantize(
                    Decimal(".01")
                )
        if order.variable_cost == 0:
            order.variable_cost = (order.total * Decimal(".03")).quantize(
                Decimal(".01")
            )
    for index, order in enumerate(orders[:12]):
        identity = uuid5(order.id, "fiscal-demo")
        if await session.scalar(select(Invoice).where(Invoice.id == identity)):
            continue
        number = (await session.scalar(select(func.max(Invoice.number))) or 0) + 1
        kind = "nfse" if index % 3 == 0 else "nfe"
        regime = ["simples", "real", "presumido"][index % 3]
        session.add(
            Invoice(
                id=identity,
                tenant_id=tenant,
                order_id=order.id,
                number=number,
                kind=kind,
                regime=regime,
                status="cancelada" if index % 5 == 0 else "autorizada",
                base=order.total,
                taxes=calculate(order.total, regime, kind),
                rule_version=RULE_VERSION,
                is_simulated=True,
                requested_by=actor,
                cancellation_reason=(
                    "Cancelamento demonstrativo." if index % 5 == 0 else None
                ),
            )
        )
        await session.flush()
        created += 1
    people = []
    for i, name in enumerate(
        [
            "Ana Martins",
            "Bruno Costa",
            "Carla Ribeiro",
            "Diego Almeida",
            "Eva Santos",
            "Felipe Lima",
            "Giovana Rocha",
            "Henrique Souza",
        ]
    ):
        identity = uuid5(tenant, f"demo-employee:{i}")
        row = await session.scalar(select(Employee).where(Employee.id == identity))
        if row is None:
            row = Employee(
                id=identity,
                tenant_id=tenant,
                registration=f"DEMO-RH-{i+1:03}",
                name=name,
                department=["Tecnologia", "Comercial", "Operações"][i % 3],
                job_title=["Analista", "Consultor", "Coordenador"][i % 3],
                base_salary=Decimal(2800 + i * 550),
                hired_on=date(2024, 1, 1),
                is_active=True,
                is_simulated=True,
            )
            session.add(row)
            created += 1
        people.append(row)
    for offset in range(3):
        ordinal = today.year * 12 + today.month - 1 - offset
        month = date(ordinal // 12, ordinal % 12 + 1, 1)
        identity = uuid5(tenant, f"demo-payroll:{month}")
        if await session.scalar(select(Payroll).where(Payroll.id == identity)):
            continue
        gross = sum((p.base_salary for p in people), Decimal("0"))
        session.add(
            Payroll(
                id=identity,
                tenant_id=tenant,
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
                is_simulated=True,
                cash_entry_id=None,
            )
        )
        created += 1
    product = await session.scalar(
        select(Product).where(Product.is_simulated.is_(True)).order_by(Product.id)
    )
    if product:
        for i in range(3):
            identity = uuid5(tenant, f"purchase-waiting:{i}")
            if await session.scalar(select(Order).where(Order.id == identity)):
                continue
            value = Decimal(7500 + i * 6000)
            purchase = Order(
                id=identity,
                tenant_id=tenant,
                kind="purchase",
                status="aguardando_aprovacao",
                counterparty=f"Fornecedor demonstração {i+1}",
                ordered_on=today,
                due_date=today,
                total=value,
                is_simulated=True,
                cash_entry_id=None,
                created_by=actor,
                request_key=identity,
                payload_hash="demo-approval",
                variable_cost=Decimal("0"),
            )
            session.add(purchase)
            await session.flush()
            session.add(
                OrderLine(
                    tenant_id=tenant,
                    order_id=purchase.id,
                    product_id=product.id,
                    quantity=1,
                    unit_price=value,
                    unit_cost=None,
                )
            )
            created += 1
    rows = await session.scalars(
        select(CashEntry).where(
            CashEntry.is_simulated.is_(True),
            CashEntry.created_by != uuid5(tenant, "seed:organic"),
        )
    )
    grouped: dict[tuple[date, str, str], Decimal] = {}
    for cash in rows:
        key = (cash.effective_on.replace(day=1), cash.category, cash.kind)
        grouped[key] = grouped.get(key, Decimal("0")) + cash.amount
    for (month, category, kind), value in grouped.items():
        identity = uuid5(tenant, f"budget-demo:{month}:{category}:{kind}")
        if await session.scalar(select(Budget).where(Budget.id == identity)):
            continue
        session.add(
            Budget(
                id=identity,
                tenant_id=tenant,
                month=month,
                category=category,
                kind=kind,
                amount=(value * Decimal("1.10")).quantize(Decimal(".01")),
                is_simulated=True,
            )
        )
        created += 1
    await session.flush()
    return created
