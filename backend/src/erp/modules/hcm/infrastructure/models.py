from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import (
    String,
    Numeric,
    Date,
    JSON,
    UniqueConstraint,
    CheckConstraint,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Employee(Entity):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "registration"),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("base_salary > 0", name="positive_salary"),
    )
    registration: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120), active_history=True)
    department: Mapped[str] = mapped_column(String(80), active_history=True)
    job_title: Mapped[str] = mapped_column(String(80), active_history=True)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(14, 2), active_history=True)
    hired_on: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(active_history=True)
    is_simulated: Mapped[bool]


class Payroll(Entity):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "month", "is_simulated"),)
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), active_history=True)
    gross: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    net: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    is_simulated: Mapped[bool]
    cash_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cash_entries.id"), active_history=True
    )
