from decimal import Decimal
from uuid import UUID
from sqlalchemy import ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from erp.shared.infrastructure.database.base import Entity


class User(Entity):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "email"),
    )
    email: Mapped[str] = mapped_column(String(254), active_history=True)
    display_name: Mapped[str] = mapped_column(String(120), active_history=True)
    password_hash: Mapped[str] = mapped_column(
        String(512), info={"audit_redact": True}, active_history=True
    )
    is_active: Mapped[bool] = mapped_column(active_history=True)
    approval_limit: Mapped[Decimal] = mapped_column(Numeric(19, 4), active_history=True)


class Role(Entity):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
    )
    name: Mapped[str] = mapped_column(String(100), active_history=True)


class Permission(Entity):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
    )
    code: Mapped[str] = mapped_column(String(150), active_history=True)


class UserRole(Entity):
    """Association entity: grants and revocations are versioned and audited."""

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "role_id"),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
    )
    user_id: Mapped[UUID] = mapped_column(active_history=True)
    role_id: Mapped[UUID] = mapped_column(active_history=True)


class RolePermission(Entity):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "role_id", "permission_id"),
        ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "permission_id"], ["permissions.tenant_id", "permissions.id"]
        ),
    )
    role_id: Mapped[UUID] = mapped_column(active_history=True)
    permission_id: Mapped[UUID] = mapped_column(active_history=True)


class UserCompany(Entity):
    __tablename__ = "user_companies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "company_id"),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
    )
    user_id: Mapped[UUID] = mapped_column(active_history=True)
    company_id: Mapped[UUID] = mapped_column(active_history=True)
