from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import (
    ORMExecuteState,
    Session,
    UOWTransaction,
    with_loader_criteria,
)
from sqlalchemy.sql.selectable import Select
from erp.shared.infrastructure.database.audit import AuditLog
from erp.shared.infrastructure.database.base import (
    Entity,
    SoftDeleteMixin,
    TenantScoped,
    utcnow,
)
from erp.shared.infrastructure.database.context import AuditContext


class ApplicationSession(Session):
    """Dedicated event target; migration connections are deliberately separate."""

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Use repository SELECT; identity-map get bypasses filters")


def context(session: Session) -> AuditContext:
    value = session.info.get("audit_context")
    if not isinstance(value, AuditContext):
        raise RuntimeError("Session requires a trusted AuditContext")
    return value


@event.listens_for(ApplicationSession, "do_orm_execute")
def enforce_reads(state: ORMExecuteState) -> None:
    # Core/raw SQL and bulk DML do not participate in before_flush.
    if not state.is_select or not isinstance(state.statement, Select):
        raise RuntimeError("Only ORM SELECT is allowed; mutate loaded entities")
    if not state.is_orm_statement:
        raise RuntimeError("Core SQL is reserved for migrations")
    tenant = context(state.session).tenant_id
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped, lambda cls: cls.tenant_id == tenant, include_aliases=True
        ),
        with_loader_criteria(
            SoftDeleteMixin, lambda cls: cls.deleted_at.is_(None), include_aliases=True
        ),
    )


def json_value(value: Any) -> Any:
    """Lossless decimals and UTC ISO timestamps; never serialize ORM objects."""
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    raise TypeError(f"Unsupported audit type: {type(value).__name__}")


@event.listens_for(ApplicationSession, "before_flush")
def audit_changes(
    session: Session, flush_context: UOWTransaction, instances: Sequence[Any] | None
) -> None:
    ctx = context(session)
    # Reject attempts to rewrite evidence, even when using ORM instance methods.
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, AuditLog):
            raise RuntimeError("Audit is append-only")
    for obj in list(session.new):
        if isinstance(obj, AuditLog):
            raise RuntimeError("Audit rows may only be produced by this listener")
    deleted = list(session.deleted)
    for obj in deleted:
        if not isinstance(obj, Entity):
            raise RuntimeError("Physical deletion is not allowed")
        session.add(obj)
        obj.soft_delete()
    objects = list(session.new) + list(session.dirty)
    for obj in objects:
        if not isinstance(obj, Entity):
            raise RuntimeError("All application models must be audited Entity objects")
        if obj.tenant_id != ctx.tenant_id:
            raise RuntimeError("Cross-tenant write")
        state = inspect(obj)
        is_new = obj in session.new
        if not is_new and not session.is_modified(obj, include_collections=False):
            continue
        if not is_new:
            for field in ("id", "tenant_id", "created_at", "version"):
                if state.attrs[field].history.has_changes():
                    raise RuntimeError(f"Immutable field: {field}")
        operation = "INSERT" if is_new else "UPDATE"
        if not is_new:
            obj.updated_at = utcnow()
            if state.attrs.deleted_at.history.has_changes() and obj.deleted_at:
                operation = "DELETE"  # Semantic delete; the row remains stored.
        diff: dict[str, dict[str, Any]] = {}
        for prop in state.mapper.column_attrs:
            key = prop.key
            history = state.attrs[key].history
            if not is_new and not history.has_changes():
                continue
            new = getattr(obj, key)
            if not is_new and not history.deleted:
                raise RuntimeError(
                    f"Load {key} before mutation (active_history required)"
                )
            old = None if is_new else cast(Sequence[Any], history.deleted)[0]
            redact = prop.columns[0].info.get("audit_redact", False)
            diff[key] = {
                "valor_antigo": (
                    "[REDACTED]" if redact and old is not None else json_value(old)
                ),
                "valor_novo": (
                    "[REDACTED]" if redact and new is not None else json_value(new)
                ),
            }
        if not is_new:
            diff["version"] = {
                "valor_antigo": obj.version,
                "valor_novo": obj.version + 1,
            }
        session.add(
            AuditLog(
                id=uuid4(),
                tenant_id=ctx.tenant_id,
                actor_id=ctx.actor_id,
                actor_kind=ctx.actor_kind,
                request_id=ctx.request_id,
                table_name=cast(str, obj.__tablename__),
                entity_id=obj.id,
                operation=operation,
                diff=diff,
                occurred_at=utcnow(),
                ip=ctx.ip,
                user_agent=ctx.user_agent,
            )
        )


def session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url, pool_pre_ping=True)
    return async_sessionmaker(
        engine, expire_on_commit=False, sync_session_class=ApplicationSession
    )
