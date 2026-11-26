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


class Asset(Entity):
    __tablename__ = "fixed_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "tag"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"], ["employees.tenant_id", "employees.id"]
        ),
        CheckConstraint(
            "cost > 0 AND residual >= 0 AND residual <= cost "
            "AND life_months BETWEEN 1 AND 1200",
            name="valuation_valid",
        ),
    )
    tag: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    residual: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    life_months: Mapped[int]
    service_on: Mapped[date] = mapped_column(Date)
    employee_id: Mapped[UUID | None] = mapped_column(nullable=True, active_history=True)
    is_simulated: Mapped[bool]


class Maintenance(Entity):
    __tablename__ = "asset_maintenances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "asset_id"], ["fixed_assets.tenant_id", "fixed_assets.id"]
        ),
        UniqueConstraint("tenant_id", "request_key"),
        CheckConstraint("cost >= 0", name="maintenance_cost"),
    )
    asset_id: Mapped[UUID]
    performed_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(240))
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    request_key: Mapped[UUID]
