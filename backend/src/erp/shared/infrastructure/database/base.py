from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import DateTime, MetaData, Uuid, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TenantScoped:
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, active_history=True
    )

    def soft_delete(self) -> None:
        self.deleted_at = utcnow()


class Entity(TenantScoped, SoftDeleteMixin, Base):
    __abstract__ = True
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), active_history=True
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


@event.listens_for(Entity, "init", propagate=True)
def initialize(target: Entity, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Materialize defaults before flush, so INSERT audit has actual values."""
    now = utcnow()
    for key, value in {
        "id": uuid4(),
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "version": 1,
    }.items():
        kwargs.setdefault(key, value)
