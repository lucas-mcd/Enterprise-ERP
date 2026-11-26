from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import (
    String,
    Numeric,
    Date,
    DateTime,
    JSON,
    UniqueConstraint,
    ForeignKeyConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Customer(Entity):
    __tablename__ = "crm_customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document"),
        CheckConstraint("credit_limit >= 0", name="credit_nonnegative"),
    )
    name: Mapped[str] = mapped_column(String(120), active_history=True)
    document: Mapped[str] = mapped_column(String(14), active_history=True)
    segment: Mapped[str] = mapped_column(String(80), active_history=True)
    email: Mapped[str] = mapped_column(String(254), active_history=True)
    phone: Mapped[str] = mapped_column(String(30), active_history=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)


class Opportunity(Entity):
    __tablename__ = "crm_opportunities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_key"),
        UniqueConstraint("tenant_id", "order_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["crm_customers.tenant_id", "crm_customers.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["business_orders.tenant_id", "business_orders.id"],
        ),
        CheckConstraint(
            "stage IN ('prospeccao','proposta','negociacao','fechado','perdido')",
            name="valid_stage",
        ),
        CheckConstraint("amount > 0", name="positive_amount"),
    )
    loss_reason: Mapped[str | None] = mapped_column(String(180), active_history=True)
    title: Mapped[str] = mapped_column(String(140), active_history=True)
    customer_id: Mapped[UUID] = mapped_column(active_history=True)
    stage: Mapped[str] = mapped_column(String(20), active_history=True)
    expected_on: Mapped[date] = mapped_column(Date, active_history=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    items: Mapped[list[dict[str, str | int]]] = mapped_column(JSON, active_history=True)
    order_id: Mapped[UUID | None] = mapped_column(active_history=True)
    request_key: Mapped[UUID] = mapped_column(active_history=True)
    payload_hash: Mapped[str] = mapped_column(String(64), active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)


class CostCenter(Entity):
    __tablename__ = "cost_centers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
    )
    name: Mapped[str] = mapped_column(String(80), active_history=True)


class BankBatch(Entity):
    __tablename__ = "bank_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "account", "reference"),
    )
    account: Mapped[str] = mapped_column(String(80), active_history=True)
    reference: Mapped[str] = mapped_column(String(80), active_history=True)
    payload_hash: Mapped[str] = mapped_column(String(64), active_history=True)
    origin: Mapped[str] = mapped_column(String(30), active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)


class BankTransaction(Entity):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account", "external_id"),
        UniqueConstraint("tenant_id", "cash_entry_id"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"], ["bank_batches.tenant_id", "bank_batches.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cash_entry_id"],
            ["cash_entries.tenant_id", "cash_entries.id"],
        ),
        CheckConstraint("amount <> 0", name="nonzero_amount"),
    )
    batch_id: Mapped[UUID] = mapped_column(active_history=True)
    account: Mapped[str] = mapped_column(String(80), active_history=True)
    external_id: Mapped[str] = mapped_column(String(120), active_history=True)
    posted_on: Mapped[date] = mapped_column(Date, active_history=True)
    description: Mapped[str] = mapped_column(String(180), active_history=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    cash_entry_id: Mapped[UUID | None] = mapped_column(active_history=True)
    matched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), active_history=True
    )
    is_simulated: Mapped[bool] = mapped_column(active_history=True)
