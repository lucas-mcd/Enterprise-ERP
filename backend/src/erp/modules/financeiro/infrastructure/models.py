from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class CashEntry(Entity):
    __tablename__ = "cash_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "cost_center_id"],
            ["cost_centers.tenant_id", "cost_centers.id"],
        ),
        UniqueConstraint("tenant_id", "created_by", "request_key"),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            "amount > 0 AND amount <= 999999999.99", name="positive_amount"
        ),
        CheckConstraint("kind IN ('receita', 'despesa')", name="valid_kind"),
        CheckConstraint(
            "status IN ('pendente', 'concluido', 'aguardando_aprovacao')",
            name="valid_status",
        ),
        CheckConstraint("currency = 'BRL'", name="brl_only"),
        CheckConstraint(
            "(status IN ('pendente','aguardando_aprovacao') AND settled_on IS NULL "
            "AND effective_on = due_date) OR (status = 'concluido' "
            "AND settled_on IS NOT NULL AND effective_on = settled_on)",
            name="settlement_consistency",
        ),
        Index(
            "ix_cash_tenant_source_date",
            "tenant_id",
            "is_simulated",
            "effective_on",
            "id",
        ),
        Index("ix_cash_tenant_status_date", "tenant_id", "status", "effective_on"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), index=True, nullable=False
    )
    cost_center_id: Mapped[UUID | None] = mapped_column(active_history=True)
    description: Mapped[str] = mapped_column(String(180), active_history=True)
    counterparty: Mapped[str] = mapped_column(String(120), active_history=True)
    category: Mapped[str] = mapped_column(String(40), active_history=True)
    kind: Mapped[str] = mapped_column(String(10), active_history=True)
    status: Mapped[str] = mapped_column(String(24), active_history=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    currency: Mapped[str] = mapped_column(String(3), active_history=True)
    due_date: Mapped[date] = mapped_column(Date, active_history=True)
    settled_on: Mapped[date | None] = mapped_column(Date, active_history=True)
    effective_on: Mapped[date] = mapped_column(Date, active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)
    created_by: Mapped[UUID] = mapped_column(active_history=True)
    request_key: Mapped[UUID] = mapped_column(active_history=True)
    payload_hash: Mapped[str] = mapped_column(String(64), active_history=True)
