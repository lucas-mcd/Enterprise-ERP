import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID
from sqlalchemy import select, func, or_
from erp.modules.integration.infrastructure.models import Customer
from erp.modules.financeiro.infrastructure.models import CashEntry
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.operations.domain.orders import BusinessError, Line, total
from erp.modules.operations.infrastructure.models import (
    Supplier,
    Product,
    Order,
    OrderLine,
    StockMovement,
)
from erp.modules.financeiro.domain.cash import NewEntry
from erp.modules.financeiro.infrastructure.repositories.cash import SqlCashRepository
from erp.modules.identity.infrastructure.models import User
from erp.shared.infrastructure.database.session import context


class OperationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def tenant(self) -> UUID:
        return context(self.session.sync_session).tenant_id

    async def actor_lock(self, actor: UUID) -> None:
        # Serializes idempotent creation for one actor, including requests in flight.
        await self.session.scalar(
            select(User).where(User.id == actor).with_for_update()
        )

    async def create_order(
        self,
        actor: UUID,
        key: UUID,
        kind: str,
        counterparty: str,
        ordered_on: date,
        due_date: date,
        lines: list[Line],
        variable_cost: Decimal = Decimal("0"),
        customer_id: UUID | None = None,
    ) -> Order:
        value = total(lines)
        signature: list[object] = [
            kind,
            counterparty,
            str(ordered_on),
            str(due_date),
            [(str(x.product_id), x.quantity, str(x.unit_price)) for x in lines],
        ]
        if customer_id is not None:
            if kind != "sale":
                raise BusinessError("Cliente permitido apenas em venda.")
            signature.append(str(customer_id))
        if variable_cost:
            signature.append(format(variable_cost, ".2f"))
        fingerprint = hashlib.sha256(
            json.dumps(signature, sort_keys=True).encode()
        ).hexdigest()
        await self.actor_lock(actor)
        existing = await self.session.scalar(
            select(Order).where(Order.created_by == actor, Order.request_key == key)
        )
        if existing:
            if existing.payload_hash != fingerprint:
                raise BusinessError("Chave já usada com outros dados.")
            return existing
        if kind == "sale":
            lookup = (
                Customer.id == customer_id
                if customer_id is not None
                else func.lower(Customer.name) == counterparty.strip().lower()
            )
            customers = list(
                await self.session.scalars(
                    select(Customer)
                    .where(lookup, Customer.is_simulated.is_(False))
                    .order_by(Customer.id)
                    .limit(2)
                    .with_for_update()
                )
            )
            if len(customers) > 1 or (customer_id is not None and not customers):
                raise BusinessError("Selecione um cliente cadastrado válido.")
            if customers:
                customer = customers[0]
                exposure = await self.session.scalar(
                    select(func.coalesce(func.sum(Order.total), 0))
                    .outerjoin(CashEntry, CashEntry.id == Order.cash_entry_id)
                    .where(
                        Order.customer_id == customer.id,
                        Order.status != "cancelled",
                        or_(
                            Order.cash_entry_id.is_(None),
                            CashEntry.status != "concluido",
                        ),
                    )
                )
                if Decimal(exposure or 0) + value > customer.credit_limit:
                    raise BusinessError("Limite de crédito insuficiente.")
                customer_id, counterparty = customer.id, customer.name
        products = list(
            await self.session.scalars(
                select(Product).where(Product.id.in_([x.product_id for x in lines]))
            )
        )
        if len(products) != len(lines) or any(p.is_simulated for p in products):
            raise BusinessError("Selecione produtos reais da sua empresa.")
        supplier_id = None
        if kind == "purchase":
            normalized = " ".join(counterparty.split()).casefold()
            supplier = await self.session.scalar(
                select(Supplier).where(Supplier.normalized_name == normalized)
            )
            if supplier is None:
                supplier = Supplier(
                    tenant_id=self.tenant,
                    name=counterparty.strip(),
                    normalized_name=normalized,
                )
                self.session.add(supplier)
                await self.session.flush()
            supplier_id, counterparty = supplier.id, supplier.name
        order = Order(
            supplier_id=supplier_id,
            customer_id=customer_id,
            tenant_id=self.tenant,
            kind=kind,
            status=(
                "aguardando_aprovacao"
                if kind == "purchase" and value > Decimal("5000")
                else "draft"
            ),
            counterparty=counterparty,
            ordered_on=ordered_on,
            due_date=due_date,
            total=value,
            is_simulated=False,
            cash_entry_id=None,
            created_by=actor,
            request_key=key,
            payload_hash=fingerprint,
            variable_cost=variable_cost,
        )
        self.session.add(order)
        await self.session.flush()
        for x in lines:
            self.session.add(
                OrderLine(
                    tenant_id=self.tenant,
                    order_id=order.id,
                    product_id=x.product_id,
                    quantity=x.quantity,
                    unit_price=x.unit_price,
                )
            )
        await self.session.flush()
        return order

    async def complete(self, order_id: UUID, kind: str, actor: UUID) -> Order:
        order = await self.session.scalar(
            select(Order)
            .where(Order.id == order_id, Order.kind == kind)
            .with_for_update()
        )
        if order is None or order.is_simulated:
            raise BusinessError("Pedido real não encontrado.")
        if order.status == "cancelled":
            raise BusinessError("Pedido cancelado.")
        if order.status == "aguardando_aprovacao":
            raise BusinessError("Aprovação por alçada necessária antes do recebimento.")
        if order.status == "completed":
            return order
        lines = list(
            await self.session.scalars(
                select(OrderLine).where(OrderLine.order_id == order.id)
            )
        )
        # Global ordering avoids deadlocks between different orders sharing products.
        products = list(
            await self.session.scalars(
                select(Product)
                .where(Product.id.in_([x.product_id for x in lines]))
                .order_by(Product.id)
                .with_for_update()
            )
        )
        if len(products) != len(lines):
            raise BusinessError("Produto indisponível.")
        quantities = {x.product_id: x.quantity for x in lines}
        line_map = {x.product_id: x for x in lines}
        for p in products:
            line = line_map[p.id]
            if kind == "sale":
                line.unit_cost = p.average_cost
            elif p.balance == 0:
                p.average_cost = line.unit_price
            elif p.average_cost is not None:
                p.average_cost = (
                    (p.average_cost * p.balance + line.unit_price * line.quantity)
                    / (p.balance + line.quantity)
                ).quantize(Decimal(".01"))
            delta = quantities[p.id] * (-1 if kind == "sale" else 1)
            await self.move(
                p,
                delta,
                "Venda concluída" if kind == "sale" else "Compra recebida",
                order.id,
                order.id,
            )
        cash, _ = await SqlCashRepository(self.session).create(
            NewEntry(
                f"{'Venda' if kind == 'sale' else 'Compra'} {str(order.id)[:8]}",
                order.counterparty,
                "Vendas" if kind == "sale" else "Fornecedores",
                "receita" if kind == "sale" else "despesa",
                "pendente",
                order.total,
                order.due_date,
                None,
            ),
            actor,
            order.id,
        )
        order.cash_entry_id = cash.id
        order.status = "completed"
        await self.session.flush()
        return order

    async def move(
        self,
        product: Product,
        delta: int,
        reason: str,
        key: UUID,
        order: UUID | None = None,
    ) -> StockMovement:
        existing = await self.session.scalar(
            select(StockMovement).where(
                StockMovement.product_id == product.id, StockMovement.request_key == key
            )
        )
        if existing:
            if existing.quantity != delta or existing.reason != reason:
                raise BusinessError("Chave de movimentação já utilizada.")
            return existing
        if product.balance + delta < 0 or product.balance + delta > 1000000000:
            raise BusinessError(
                f"Saldo insuficiente ou limite excedido: {product.name}."
            )
        product.balance += delta
        row = StockMovement(
            tenant_id=self.tenant,
            product_id=product.id,
            order_id=order,
            quantity=delta,
            balance_after=product.balance,
            reason=reason,
            request_key=key,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def page(
        self,
        model: type[Product] | type[Order] | type[StockMovement],
        conditions: list[Any],
        page: int,
        size: int,
        sort: str,
        desc: bool,
    ) -> dict[str, Any]:
        allowed = (
            {"name", "sku", "balance", "minimum", "category"}
            if model is Product
            else (
                {"ordered_on", "total", "counterparty", "status"}
                if model is Order
                else {"created_at", "quantity"}
            )
        )
        if sort not in allowed:
            raise BusinessError("Ordenação inválida.")
        col = getattr(model, sort)
        count = await self.session.scalar(
            select(func.count()).select_from(model).where(*conditions)
        )
        rows = await self.session.scalars(
            select(model)
            .where(*conditions)
            .order_by(col.desc() if desc else col.asc(), model.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return {
            "items": [
                self.view(cast(Product | Order | StockMovement, row)) for row in rows
            ],
            "total": count or 0,
            "page": page,
            "page_size": size,
        }

    @staticmethod
    def view(row: Product | Order | StockMovement) -> dict[str, Any]:
        fields = (
            ("sku", "name", "category", "balance", "minimum", "is_simulated")
            if isinstance(row, Product)
            else (
                (
                    "kind",
                    "status",
                    "counterparty",
                    "ordered_on",
                    "due_date",
                    "total",
                    "is_simulated",
                    "cash_entry_id",
                    "supplier_id",
                )
                if isinstance(row, Order)
                else (
                    "product_id",
                    "quantity",
                    "reason",
                    "balance_after",
                    "created_at",
                    "order_id",
                )
            )
        )
        return {
            "id": row.id,
            "version": row.version,
            **{
                k: str(getattr(row, k)) if k == "total" else getattr(row, k)
                for k in fields
            },
        }
