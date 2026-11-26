from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import String, Numeric, JSON, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class Invoice(Entity):
    __tablename__ = "simulated_invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_id", "kind"),
        UniqueConstraint("tenant_id", "number"),
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("business_orders.id"))
    number: Mapped[int]
    kind: Mapped[str] = mapped_column(String(8))
    regime: Mapped[str] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(16), active_history=True)
    base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    taxes: Mapped[dict[str, Any]] = mapped_column(JSON)
    rule_version: Mapped[str] = mapped_column(String(30))
    is_simulated: Mapped[bool]
    requested_by: Mapped[UUID]
    cancellation_reason: Mapped[str | None] = mapped_column(
        String(250), active_history=True
    )
