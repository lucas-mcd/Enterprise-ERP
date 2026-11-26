from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import DateTime, Index, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Base, TenantScoped


class AuditLog(TenantScoped, Base):
    """Append-only evidence, without FK to an actor that may be deactivated."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index(
            "ix_audit_tenant_entity_time",
            "tenant_id",
            "table_name",
            "entity_id",
            "occurred_at",
        ),
        Index("ix_audit_tenant_time", "tenant_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID | None]
    actor_kind: Mapped[str] = mapped_column(String(20))
    request_id: Mapped[UUID]
    table_name: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[UUID]
    operation: Mapped[str] = mapped_column(String(10))
    diff: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
