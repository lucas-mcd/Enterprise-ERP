from uuid import UUID, uuid5
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.operations.infrastructure.models import (
    Product,
    Order,
    OrderLine,
)
from erp.modules.operations.infrastructure.repository import OperationsRepository
from erp.modules.financeiro.infrastructure.models import CashEntry


async def seed_operations(session: AsyncSession, tenant: UUID) -> tuple[int, int]:
    created = existing = 0
    products = []
    repo = OperationsRepository(session)
    for index, name in enumerate(
        [
            "Notebook corporativo",
            "Monitor 27 polegadas",
            "Teclado mecânico",
            "Mouse sem fio",
            "Dock USB-C",
            "Headset profissional",
        ]
    ):
        identity = uuid5(tenant, f"demo-product:{index}")
        row = await session.scalar(select(Product).where(Product.id == identity))
        if row is None:
            row = Product(
                id=identity,
                tenant_id=tenant,
                sku=f"DEMO-{index+1:03}",
                name=name,
                category="Tecnologia",
                balance=0,
                minimum=10,
                is_simulated=True,
            )
            session.add(row)
            await session.flush()
            await repo.move(
                row, 100, "Saldo inicial demonstrativo", uuid5(identity, "opening")
            )
            created += 1
        else:
            existing += 1
        products.append(row)
    cash = list(
        await session.scalars(
            select(CashEntry)
            .where(
                CashEntry.is_simulated.is_(True),
                CashEntry.created_by != uuid5(tenant, "seed:organic"),
            )
            .order_by(CashEntry.effective_on, CashEntry.id)
        )
    )
    for index, entry in enumerate(cash):
        identity = uuid5(entry.id, "demo-order")
        if await session.scalar(select(Order).where(Order.id == identity)):
            existing += 1
            continue
        product = products[index % len(products)]
        sale = entry.kind == "receita"
        order = Order(
            id=identity,
            tenant_id=tenant,
            kind="sale" if sale else "purchase",
            status="completed",
            counterparty=entry.counterparty,
            ordered_on=entry.due_date,
            due_date=entry.due_date,
            total=entry.amount,
            is_simulated=True,
            cash_entry_id=entry.id,
            created_by=uuid5(tenant, "seed:service"),
            request_key=identity,
            payload_hash=entry.payload_hash,
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderLine(
                tenant_id=tenant,
                order_id=order.id,
                product_id=product.id,
                quantity=1,
                unit_price=entry.amount,
            )
        )
        await repo.move(
            product,
            -1 if sale else 1,
            "Venda demonstrativa" if sale else "Compra demonstrativa",
            order.id,
            order.id,
        )
        created += 1
    await session.flush()
    return created, existing
