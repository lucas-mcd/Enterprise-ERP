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
)
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Project(Entity):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        CheckConstraint("budget >= 0", name="budget_positive"),
        CheckConstraint(
            "status IN ('planejamento','em_execucao','concluido')",
            name="project_status",
        ),
    )
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160), active_history=True)
    customer: Mapped[str] = mapped_column(String(120), active_history=True)
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    status: Mapped[str] = mapped_column(String(20), active_history=True)
    is_simulated: Mapped[bool]


class Allocation(Entity):
    __tablename__ = "project_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]
        ),
        UniqueConstraint("tenant_id", "request_key"),
        CheckConstraint("hours > 0 AND hourly_cost >= 0", name="allocation_positive"),
    )
    project_id: Mapped[UUID]
    description: Mapped[str] = mapped_column(String(180))
    worked_on: Mapped[date] = mapped_column(Date)
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    hourly_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    request_key: Mapped[UUID]


class Delivery(Entity):
    __tablename__ = "project_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "cash_entry_id"],
            ["cash_entries.tenant_id", "cash_entries.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]
        ),
        UniqueConstraint("tenant_id", "request_key"),
        CheckConstraint("amount > 0", name="delivery_positive"),
    )
    project_id: Mapped[UUID]
    description: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[date] = mapped_column(Date)
    cash_entry_id: Mapped[UUID]
    request_key: Mapped[UUID]
