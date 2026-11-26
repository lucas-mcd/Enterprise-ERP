from decimal import Decimal
from sqlalchemy import CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Tenant(Entity):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("id = tenant_id", name="tenant_self_scope"),)
    name: Mapped[str] = mapped_column(String(160), active_history=True)
    is_active: Mapped[bool] = mapped_column(active_history=True)


class DemoActivity(Entity):
    """Clearly simulated data; never a posted accounting/operational document."""

    __tablename__ = "demo_activities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        CheckConstraint("amount >= 0", name="nonnegative_amount"),
        CheckConstraint("is_simulated = true", name="simulation_only"),
    )
    code: Mapped[str] = mapped_column(String(40), active_history=True)
    category: Mapped[str] = mapped_column(String(30), active_history=True)
    description: Mapped[str] = mapped_column(String(160), active_history=True)
    status: Mapped[str] = mapped_column(String(30), active_history=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), active_history=True)
    is_simulated: Mapped[bool] = mapped_column(active_history=True)
