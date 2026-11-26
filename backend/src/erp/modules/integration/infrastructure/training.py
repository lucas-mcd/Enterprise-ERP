"""Editable fixtures for a fresh, isolated rehearsal tenant."""

from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.integration.infrastructure.models import Customer, Opportunity
from erp.modules.operations.infrastructure.models import Product
from erp.modules.operations.infrastructure.repository import OperationsRepository


async def create_training(session: AsyncSession, tenant: UUID) -> None:
    product = Product(
        tenant_id=tenant,
        sku="AUR-KIT",
        name="Kit de reposição industrial",
        category="Manutenção",
        minimum=2,
        balance=0,
        average_cost=Decimal("120"),
        is_simulated=False,
    )
    customer = Customer(
        tenant_id=tenant,
        name="Aurora Distribuição",
        document="11222333000181",
        segment="Distribuição",
        email="compras@example.com",
        phone="",
        credit_limit=Decimal("1000"),
        is_simulated=False,
    )
    session.add_all([product, customer])
    await session.flush()
    await OperationsRepository(session).move(
        product, 10, "Estoque inicial de treinamento", uuid4()
    )
    for quantity, title in (
        (3, "Reposição Aurora"),
        (6, "Pedido acima do limite"),
    ):
        session.add(
            Opportunity(
                tenant_id=tenant,
                customer_id=customer.id,
                title=title,
                stage="negociacao",
                expected_on=business_today(),
                amount=Decimal(200 * quantity),
                items=[
                    {
                        "product_id": str(product.id),
                        "quantity": quantity,
                        "unit_price": "200.00",
                    }
                ],
                request_key=uuid4(),
                payload_hash="training",
                order_id=None,
                is_simulated=False,
            )
        )
