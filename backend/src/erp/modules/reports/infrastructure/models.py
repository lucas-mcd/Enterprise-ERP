from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import JSON, DateTime, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class ReportJob(Entity):
    __tablename__ = "report_jobs"
    __table_args__ = (Index("ix_reports_status_created", "status", "created_at"),)
    owner_id: Mapped[UUID] = mapped_column(active_history=True)
    status: Mapped[str] = mapped_column(String(12), active_history=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, active_history=True)
    include_audit: Mapped[bool] = mapped_column(active_history=True)
    file_name: Mapped[str | None] = mapped_column(String(80), active_history=True)
    error: Mapped[str | None] = mapped_column(String(180), active_history=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), active_history=True
    )
