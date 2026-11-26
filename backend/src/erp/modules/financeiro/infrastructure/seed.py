"""Explicit projection of the 36 legacy examples, never real accounting data."""

import hashlib
from datetime import timedelta
from uuid import UUID, uuid5
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.organization.infrastructure.models import DemoActivity


async def seed_cash_demo(session: AsyncSession, tenant: UUID) -> tuple[int, int]:
    records = list(
        await session.scalars(select(DemoActivity).order_by(DemoActivity.code))
    )
    # Preserve existing dates; anchor the synthetic timeline once.
    anchor = business_today()
    created, existing = 0, 0
    names = [
        "Aurora Studio",
        "Norte Digital",
        "Atlas Serviços",
        "Vértice Design",
        "Cloud Systems",
        "Horizonte Labs",
    ]
    for index, record in enumerate(records):
        identity = uuid5(tenant, f"cash-demo:{record.code}")
        if (
            await session.scalar(select(CashEntry).where(CashEntry.id == identity))
            is not None
        ):
            existing += 1
            continue
        due = anchor - timedelta(days=(len(records) - index - 1) * 2)
        income = record.category == "vendas"
        category = (
            ["Vendas", "Serviços", "Assinaturas"][index % 3]
            if income
            else ["Fornecedores", "Marketing", "Infraestrutura"][index % 3]
        )
        session.add(
            CashEntry(
                id=identity,
                tenant_id=tenant,
                description=f"{category} — {record.code}",
                counterparty=names[index % len(names)],
                category=category,
                kind="receita" if income else "despesa",
                status=record.status,
                amount=record.amount,
                currency="BRL",
                due_date=due,
                settled_on=due if record.status == "concluido" else None,
                effective_on=due,
                is_simulated=True,
                created_by=uuid5(tenant, "seed:service"),
                request_key=uuid5(tenant, f"cash-demo-request:{record.code}"),
                payload_hash=hashlib.sha256(record.code.encode()).hexdigest(),
            )
        )
        created += 1
    await session.flush()
    return created, existing
