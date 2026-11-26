from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid5
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.integration.infrastructure.models import (
    Customer,
    Opportunity,
    CostCenter,
    BankBatch,
    BankTransaction,
)
from erp.modules.operations.infrastructure.models import Product, Order, OrderLine
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.domain.cash import business_today


def demo_cpf(number: int) -> str:
    base = [int(x) for x in f"{number:09d}"]
    for size in (10, 11):
        remainder = sum(x * y for x, y in zip(base, range(size, 1, -1))) % 11
        base.append(0 if remainder < 2 else 11 - remainder)
    return "".join(str(x) for x in base)


async def seed_integration(session: AsyncSession, tenant: UUID, demo: bool) -> int:
    created = 0
    centers: list[CostCenter] = []
    for name in ("TI", "Comercial", "Operações", "Administrativo"):
        row = await session.scalar(select(CostCenter).where(CostCenter.name == name))
        if row is None:
            row = CostCenter(
                id=uuid5(tenant, f"center:{name}"), tenant_id=tenant, name=name
            )
            session.add(row)
            created += 1
        centers.append(row)
    await session.flush()
    if not demo:
        return created
    products = list(
        await session.scalars(
            select(Product).where(Product.is_simulated.is_(True)).order_by(Product.id)
        )
    )
    orders = list(
        await session.scalars(
            select(Order)
            .where(Order.is_simulated.is_(True), Order.kind == "sale")
            .order_by(Order.id)
        )
    )
    for i in range(12):
        cid = uuid5(tenant, f"crm-demo-customer:{i}")
        order = orders[i % len(orders)] if orders and i % 4 == 3 else None
        if await session.scalar(select(Customer).where(Customer.id == cid)) is None:
            session.add(
                Customer(
                    id=cid,
                    tenant_id=tenant,
                    name=order.counterparty if order else f"Demo — Cliente {i+1}",
                    document=demo_cpf(123000000 + i),
                    segment=("Tecnologia", "Varejo", "Serviços")[i % 3],
                    email=f"demo{i}@example.invalid",
                    phone="",
                    credit_limit=Decimal("100000"),
                    is_simulated=True,
                )
            )
            created += 1
        await session.flush()
        oid = uuid5(tenant, f"crm-demo-opportunity:{i}")
        if (
            products
            and await session.scalar(select(Opportunity).where(Opportunity.id == oid))
            is None
        ):
            items: list[dict[str, str | int]] = [
                {
                    "product_id": str(products[i % len(products)].id),
                    "quantity": 1,
                    "unit_price": str(600 + i * 140),
                }
            ]
            if order:
                order.customer_id = cid
                lines = await session.scalars(
                    select(OrderLine).where(OrderLine.order_id == order.id)
                )
                items = [
                    {
                        "product_id": str(x.product_id),
                        "quantity": x.quantity,
                        "unit_price": str(x.unit_price),
                    }
                    for x in lines
                ]
            stage = (
                "prospeccao",
                "proposta",
                "negociacao",
                "fechado" if order else "negociacao",
            )[i % 4]
            session.add(
                Opportunity(
                    id=oid,
                    tenant_id=tenant,
                    title=f"Projeto comercial {i+1}",
                    customer_id=cid,
                    stage=stage,
                    expected_on=(
                        order.due_date
                        if order
                        else business_today() + timedelta(days=15 + i)
                    ),
                    amount=order.total if order else Decimal(600 + i * 140),
                    items=items,
                    order_id=order.id if order else None,
                    request_key=oid,
                    payload_hash="demo",
                    is_simulated=True,
                )
            )
            created += 1
    await session.flush()
    bid = uuid5(tenant, "bank-demo-batch")
    if await session.scalar(select(BankBatch).where(BankBatch.id == bid)) is None:
        session.add(
            BankBatch(
                id=bid,
                tenant_id=tenant,
                account="DEMO",
                reference="DEMO-INICIAL",
                origin="seed-demo",
                payload_hash="demo",
                is_simulated=True,
            )
        )
        await session.flush()
        rows = await session.scalars(
            select(CashEntry)
            .where(
                CashEntry.is_simulated.is_(True),
                CashEntry.effective_on <= business_today(),
            )
            .order_by(CashEntry.effective_on.desc(), CashEntry.id)
            .limit(16)
        )
        for i, cash in enumerate(rows):
            if cash.cost_center_id is None:
                cash.cost_center_id = centers[i % len(centers)].id
            session.add(
                BankTransaction(
                    id=uuid5(tenant, f"bank-demo:{cash.id}"),
                    tenant_id=tenant,
                    batch_id=bid,
                    account="DEMO",
                    external_id=str(cash.id),
                    posted_on=cash.effective_on,
                    description=cash.description,
                    amount=cash.amount if cash.kind == "receita" else -cash.amount,
                    cash_entry_id=None,
                    matched_at=None,
                    is_simulated=True,
                )
            )
            created += 1
        created += 1
    await session.flush()
    return created
