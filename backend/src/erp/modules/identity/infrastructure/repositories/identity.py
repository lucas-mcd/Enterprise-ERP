from uuid import UUID
from erp.modules.identity.domain.auth import Account
from erp.modules.organization.infrastructure.models import Tenant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from erp.modules.identity.infrastructure.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserCompany,
    UserRole,
)
from erp.shared.domain.security import Principal


class SqlIdentityReader:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def principal(self, user_id: UUID) -> Principal | None:
        user = await self.session.scalar(select(User).where(User.id == user_id))
        if user is None or not user.is_active:
            return None
        statement = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        permissions = await self.session.scalars(statement)
        companies = await self.session.scalars(
            select(UserCompany).where(UserCompany.user_id == user_id)
        )
        return Principal(
            user.id,
            user.tenant_id,
            frozenset(p.code for p in permissions),
            frozenset(c.company_id for c in companies),
            user.approval_limit,
        )

    async def account(self, email: str) -> Account | None:
        user = await self.session.scalar(select(User).where(User.email == email))
        if user is None:
            return None
        return Account(
            user.id, user.email, user.display_name, user.password_hash, user.is_active
        )

    async def tenant_active(self) -> bool:
        tenant = await self.session.scalar(select(Tenant))
        return tenant is not None and tenant.is_active

    async def replace_hash(self, user_id: UUID, value: str) -> None:
        user = await self.session.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise RuntimeError("Account disappeared during authentication")
        user.password_hash = value
