from erp.modules.governance.infrastructure.models import Budget
from datetime import date, timedelta
from decimal import Decimal
from math import sin, pi
from uuid import UUID, uuid5
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.projects.infrastructure.models import Project, Allocation, Delivery
from erp.modules.assets.infrastructure.models import Asset, Maintenance
from erp.modules.hcm.infrastructure.models import Employee
from erp.modules.operations.infrastructure.models import Product


async def seed_enterprise(session: AsyncSession, tenant: UUID) -> int:
    """Additive deterministic demo fixtures. Never rewrite real/legacy cash data."""
    created = 0
    actor = uuid5(tenant, "seed:organic")
    existing = list(
        await session.scalars(
            select(CashEntry).where(
                CashEntry.is_simulated.is_(True), CashEntry.created_by != actor
            )
        )
    )
    anchor = business_today()
    originals: dict[tuple[date, str, str], Decimal] = {}
    for r in existing:
        key = (r.effective_on, r.kind, r.status)
        originals[key] = originals.get(key, Decimal("0")) + r.amount
    baseline = max(originals.values(), default=Decimal("0")) + Decimal("5000")
    for i in range(90):
        day = anchor - timedelta(days=89 - i)
        # Slow growth, a smooth 30-day cycle and bounded weekly seasonality.
        shape = Decimal(
            str(
                1
                + i * 0.004
                + 0.065 * sin(2 * pi * i / 30)
                + 0.025 * sin(2 * pi * i / 7)
            )
        )
        for kind, status, factor in [
            ("receita", "concluido", Decimal("2.1")),
            ("despesa", "concluido", Decimal("1.4")),
            ("receita", "pendente", Decimal("1")),
            ("despesa", "pendente", Decimal(".8")),
        ]:
            identity = uuid5(tenant, f"organic:{day}:{kind}:{status}")
            if await session.scalar(
                select(CashEntry.id).where(CashEntry.id == identity)
            ):
                continue
            target = (baseline * shape * factor).quantize(Decimal(".01"))
            value = target - originals.get((day, kind, status), Decimal("0"))
            if value <= 0:
                continue
            session.add(
                CashEntry(
                    id=identity,
                    tenant_id=tenant,
                    description=f"Operação diária demonstrativa {day}",
                    counterparty="Serviços recorrentes / operação",
                    category="Serviços" if kind == "receita" else "Infraestrutura",
                    kind=kind,
                    status=status,
                    amount=value,
                    currency="BRL",
                    due_date=day,
                    settled_on=day if status == "concluido" else None,
                    effective_on=day,
                    is_simulated=True,
                    created_by=actor,
                    request_key=identity,
                    payload_hash="organic-v1",
                )
            )
            created += 1
    employees = list(
        await session.scalars(
            select(Employee)
            .where(Employee.is_simulated.is_(True))
            .order_by(Employee.id)
        )
    )
    for i, name in enumerate(
        [
            "Implantação Aurora",
            "Portal do cliente",
            "Modernização do WMS",
            "Programa de eficiência",
        ]
    ):
        identity = uuid5(tenant, f"project-demo:{i}")
        if await session.scalar(select(Project.id).where(Project.id == identity)):
            continue
        row = Project(
            id=identity,
            tenant_id=tenant,
            code=f"PRJ-DEMO-{i+1:03}",
            name=name,
            customer=[
                "Aurora Studio",
                "Norte Digital",
                "Operação interna",
                "Operação interna",
            ][i],
            budget=Decimal(24000 + i * 18000),
            status=["em_execucao", "concluido", "em_execucao", "planejamento"][i],
            is_simulated=True,
        )
        session.add(row)
        await session.flush()
        created += 1
        if i < 3:
            for j in range(8):
                session.add(
                    Allocation(
                        id=uuid5(identity, f"hours:{j}"),
                        tenant_id=tenant,
                        project_id=identity,
                        description=f"Entrega técnica / sprint {j+1}",
                        worked_on=anchor - timedelta(days=(7 - j) * 4),
                        hours=Decimal(6 + i),
                        hourly_cost=Decimal(120 + i * 30),
                        request_key=uuid5(identity, f"hours:{j}"),
                    )
                )
                created += 1
            # Reuse a real demonstration receivable; no duplicate financial title.
            candidates = [r for r in existing if r.kind == "receita"]
            if len(candidates) > i:
                cash = candidates[i]
                session.add(
                    Delivery(
                        id=uuid5(identity, "delivery"),
                        tenant_id=tenant,
                        project_id=identity,
                        description="Marco demonstrativo vinculado",
                        amount=cash.amount,
                        due_date=cash.due_date,
                        cash_entry_id=cash.id,
                        request_key=uuid5(identity, "delivery"),
                    )
                )
                created += 1
    for i, name in enumerate(
        [
            "Notebook Engenharia",
            "Notebook Comercial",
            "Veículo de serviço",
            "Servidor local",
            "Impressora industrial",
            "Estação de design",
        ]
    ):
        identity = uuid5(tenant, f"asset-demo:{i}")
        if await session.scalar(select(Asset.id).where(Asset.id == identity)):
            continue
        cost = Decimal([8500, 6200, 98000, 24500, 42000, 16800][i])
        asset = Asset(
            id=identity,
            tenant_id=tenant,
            tag=f"PAT-DEMO-{i+1:03}",
            name=name,
            category="Veículos" if i == 2 else "Equipamentos",
            cost=cost,
            residual=cost * Decimal(".10"),
            life_months=60 if i == 2 else 36,
            service_on=anchor - timedelta(days=180 + i * 70),
            employee_id=employees[i % len(employees)].id if employees else None,
            is_simulated=True,
        )
        session.add(asset)
        await session.flush()
        created += 1
        session.add(
            Maintenance(
                id=uuid5(identity, "maintenance"),
                tenant_id=tenant,
                asset_id=identity,
                performed_on=anchor - timedelta(days=10 + i),
                description="Inspeção preventiva e revisão",
                cost=Decimal(150 + i * 60),
                request_key=uuid5(identity, "maintenance"),
            )
        )
        created += 1
    # Add critical fixtures without changing the six existing product balances.
    for i in range(2):
        identity = uuid5(tenant, f"critical-demo:{i}")
        if await session.scalar(select(Product.id).where(Product.id == identity)):
            continue
        product = Product(
            id=identity,
            tenant_id=tenant,
            sku=f"CRIT-DEMO-{i}",
            name=["Adaptador USB-C", "Kit de cabeamento"][i],
            category="Suprimentos",
            balance=0,
            minimum=5 + i * 5,
            is_simulated=True,
            average_cost=None,
        )
        session.add(product)
        created += 1
    await session.flush()
    daily = list(
        await session.scalars(select(CashEntry).where(CashEntry.is_simulated.is_(True)))
    )
    grouped: dict[tuple[date, str, str], Decimal] = {}
    for entry in daily:
        key = (entry.effective_on.replace(day=1), entry.category, entry.kind)
        grouped[key] = grouped.get(key, Decimal("0")) + entry.amount
    for (month, category, kind), value in grouped.items():
        budget = await session.scalar(
            select(Budget).where(
                Budget.month == month,
                Budget.category == category,
                Budget.kind == kind,
                Budget.is_simulated.is_(True),
            )
        )
        target = (value * Decimal("1.06")).quantize(Decimal(".01"))
        if budget:
            if budget.amount != target:
                budget.amount = target
        else:
            session.add(
                Budget(
                    id=uuid5(tenant, f"organic-budget:{month}:{category}:{kind}"),
                    tenant_id=tenant,
                    month=month,
                    category=category,
                    kind=kind,
                    amount=target,
                    is_simulated=True,
                )
            )
            created += 1
    await session.flush()
    return created
