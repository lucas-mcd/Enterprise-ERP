from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import (
    String,
    Numeric,
    Date,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Supplier(Entity):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "normalized_name"),
    )
    name: Mapped[str] = mapped_column(String(120), active_history=True)
    normalized_name: Mapped[str] = mapped_column(String(360), active_history=True)


class Product(Entity):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku"),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("balance >= 0 AND minimum >= 0", name="nonnegative_stock"),
    )
    average_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True, active_history=True
    )
    sku: Mapped[str] = mapped_column(String(40), active_history=True)
    name: Mapped[str] = mapped_column(String(160), active_history=True)
    category: Mapped[str] = mapped_column(String(40), active_history=True)
    balance: Mapped[int] = mapped_column(active_history=True)
    minimum: Mapped[int] = mapped_column(active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)


class Order(Entity):
    __tablename__ = "business_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"], ["suppliers.tenant_id", "suppliers.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["crm_customers.tenant_id", "crm_customers.id"],
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "created_by", "request_key"),
        CheckConstraint("kind IN ('sale','purchase')", name="order_kind"),
        CheckConstraint(
            "status IN ('draft','completed','aguardando_aprovacao','cancelled')",
            name="order_status",
        ),
        CheckConstraint("total > 0 AND total <= 999999999.99", name="order_total"),
        Index("ix_orders_tenant_kind_date", "tenant_id", "kind", "ordered_on"),
    )
    supplier_id: Mapped[UUID | None] = mapped_column(active_history=True)
    customer_id: Mapped[UUID | None] = mapped_column(active_history=True)
    variable_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0", active_history=True
    )
    kind: Mapped[str] = mapped_column(String(10), active_history=True)
    status: Mapped[str] = mapped_column(String(24), active_history=True)
    counterparty: Mapped[str] = mapped_column(String(120), active_history=True)
    ordered_on: Mapped[date] = mapped_column(Date, active_history=True)
    due_date: Mapped[date] = mapped_column(Date, active_history=True)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)
    cash_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cash_entries.id"), active_history=True
    )
    created_by: Mapped[UUID] = mapped_column(active_history=True)
    request_key: Mapped[UUID] = mapped_column(active_history=True)
    payload_hash: Mapped[str] = mapped_column(String(64), active_history=True)


class OrderLine(Entity):
    __tablename__ = "order_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["business_orders.tenant_id", "business_orders.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"]
        ),
        UniqueConstraint("tenant_id", "order_id", "product_id"),
        CheckConstraint("quantity > 0 AND unit_price > 0", name="positive_line"),
    )
    unit_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True, active_history=True
    )
    order_id: Mapped[UUID] = mapped_column(active_history=True)
    product_id: Mapped[UUID] = mapped_column(active_history=True)
    quantity: Mapped[int] = mapped_column(active_history=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)


class StockMovement(Entity):
    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["business_orders.tenant_id", "business_orders.id"],
        ),
        UniqueConstraint("tenant_id", "product_id", "request_key"),
        CheckConstraint(
            "quantity <> 0 AND balance_after >= 0", name="movement_quantity"
        ),
    )
    product_id: Mapped[UUID] = mapped_column(active_history=True)
    order_id: Mapped[UUID | None] = mapped_column(active_history=True)
    quantity: Mapped[int] = mapped_column(active_history=True)
    balance_after: Mapped[int] = mapped_column(active_history=True)
    reason: Mapped[str] = mapped_column(String(180), active_history=True)
    request_key: Mapped[UUID] = mapped_column(active_history=True)
