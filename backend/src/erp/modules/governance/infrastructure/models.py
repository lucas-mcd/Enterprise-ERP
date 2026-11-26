from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import (
    String,
    Numeric,
    Date,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Approval(Entity):
    __tablename__ = "approval_decisions"
    __table_args__ = (UniqueConstraint("tenant_id", "resource_type", "resource_id"),)
    resource_type: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[UUID]
    reviewer_id: Mapped[UUID]
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    limit_snapshot: Mapped[Decimal] = mapped_column(Numeric(19, 4))


class Budget(Entity):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "month", "category", "kind", "is_simulated"),
        CheckConstraint("amount >= 0", name="budget_nonnegative"),
    )
    month: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    is_simulated: Mapped[bool]
