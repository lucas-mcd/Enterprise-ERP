from dataclasses import replace
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError
from erp.modules.identity.infrastructure.models import (
    User,
    Role,
    Permission,
    UserRole,
    RolePermission,
)
from erp.modules.identity.infrastructure.repositories.identity import SqlIdentityReader
from erp.shared.infrastructure.database.audit import AuditLog
from erp.shared.infrastructure.database.uow import SqlUnitOfWork
from erp.shared.domain.security import (
    Principal,
    ResourceAttributes,
    authorize,
    Forbidden,
)


def user(ctx, email="test@example.com") -> User:
    return User(
        tenant_id=ctx.tenant_id,
        email=email,
        display_name="Lucas",
        password_hash="secret-hash",
        is_active=True,
        approval_limit=Decimal("100"),
    )


async def test_insert_update_delete_audit_and_metadata(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u = user(ctx)
        s.add(u)
        await s.commit()
        log = await s.scalar(select(AuditLog))
        assert log.operation == "INSERT"
        assert log.actor_id == ctx.actor_id and log.ip == "127.0.0.1"
        assert log.diff["id"]["valor_novo"] == str(u.id)
        assert log.diff["password_hash"]["valor_novo"] == "[REDACTED]"
        u.display_name = "Lucas Macedo"
        await s.commit()
        logs = list(await s.scalars(select(AuditLog).order_by(AuditLog.occurred_at)))
        assert logs[-1].diff["display_name"] == {
            "valor_antigo": "Lucas",
            "valor_novo": "Lucas Macedo",
        }
        assert u.version == 2
        u.display_name = "Lucas Macedo"
        await s.commit()
        assert len(list(await s.scalars(select(AuditLog)))) == 2
        await s.delete(u)
        await s.commit()
        assert await s.scalar(select(User)) is None
        latest = list(await s.scalars(select(AuditLog).order_by(AuditLog.occurred_at)))[
            -1
        ]
        assert latest.operation == "DELETE"
        assert latest.diff["deleted_at"]["valor_novo"] is not None


async def test_rollback_includes_audit(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        s.add(user(ctx))
        await s.flush()
        await s.rollback()
        assert await s.scalar(select(User)) is None
        assert await s.scalar(select(AuditLog)) is None


async def test_uow_requires_explicit_commit(factory, ctx):
    async with SqlUnitOfWork(factory, ctx) as uow:
        uow.session.add(user(ctx))
        await uow.session.flush()
    async with factory(info={"audit_context": ctx}) as s:
        assert await s.scalar(select(User)) is None


async def test_tenant_filter_alias_and_cross_write(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        s.add(user(ctx))
        await s.commit()
    other = replace(ctx, tenant_id=uuid4())
    async with factory(info={"audit_context": other}) as s:
        assert await s.scalar(select(aliased(User))) is None
        s.add(user(ctx, "other@example.com"))
        with pytest.raises(RuntimeError, match="Cross-tenant"):
            await s.flush()


async def test_concurrent_versions(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        s.add(user(ctx))
        await s.commit()
    async with (
        factory(info={"audit_context": ctx}) as a,
        factory(info={"audit_context": ctx}) as b,
    ):
        ua = await a.scalar(select(User))
        ub = await b.scalar(select(User))
        ua.display_name = "First"
        await a.commit()
        ub.display_name = "Second"
        with pytest.raises(StaleDataError):
            await b.commit()
        await b.rollback()
        assert len(list(await a.scalars(select(AuditLog)))) == 2


async def test_bulk_and_raw_sql_blocked(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        for statement in [
            update(User).values(display_name="Bypass"),
            text("DELETE FROM users"),
        ]:
            with pytest.raises(RuntimeError, match="Only ORM SELECT"):
                await s.execute(statement)


async def test_audit_append_only(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        s.add(user(ctx))
        await s.commit()
        log = await s.scalar(select(AuditLog))
        log.operation = "FAKE"
        with pytest.raises(RuntimeError, match="append-only"):
            await s.flush()


async def test_missing_context(factory, ctx):
    async with factory() as s:
        s.add(user(ctx))
        with pytest.raises(RuntimeError, match="AuditContext"):
            await s.flush()


async def test_cross_tenant_foreign_key(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u = user(ctx)
        s.add(u)
        await s.commit()
        uid = u.id
    other = replace(ctx, tenant_id=uuid4())
    async with factory(info={"audit_context": other}) as s:
        r = Role(tenant_id=other.tenant_id, name="admin")
        s.add(r)
        await s.flush()
        s.add(UserRole(tenant_id=other.tenant_id, user_id=uid, role_id=r.id))
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_role_revocation_removes_permission(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u, r, p = (
            user(ctx),
            Role(tenant_id=ctx.tenant_id, name="reader"),
            Permission(tenant_id=ctx.tenant_id, code="identidade:perfil:ler"),
        )
        s.add_all([u, r, p])
        await s.flush()
        grant = RolePermission(
            tenant_id=ctx.tenant_id, role_id=r.id, permission_id=p.id
        )
        s.add_all(
            [grant, UserRole(tenant_id=ctx.tenant_id, user_id=u.id, role_id=r.id)]
        )
        await s.commit()
        principal = await SqlIdentityReader(s).principal(u.id)
        assert "identidade:perfil:ler" in principal.permissions
        await s.delete(grant)
        await s.commit()
        assert not (await SqlIdentityReader(s).principal(u.id)).permissions


async def test_null_old_value_and_two_flushes(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u = user(ctx)
        s.add(u)
        await s.flush()
        u.soft_delete()
        await s.flush()
        await s.commit()
        logs = list(await s.scalars(select(AuditLog).order_by(AuditLog.occurred_at)))
        assert len(logs) == 2
        assert logs[-1].diff["deleted_at"]["valor_antigo"] is None


def test_abac_and_exact_permission():
    tenant, company, requester, approver = (uuid4() for _ in range(4))
    p = Principal(
        approver,
        tenant,
        frozenset({"compras:aprovacao:senior"}),
        frozenset({company}),
        Decimal("100"),
    )
    resource = ResourceAttributes(tenant, company, Decimal("50"), requester)
    authorize(p, "compras:aprovacao:senior", resource)
    for bad in [
        replace(resource, amount=Decimal("101")),
        replace(resource, requester_id=approver),
        replace(resource, tenant_id=uuid4()),
        replace(resource, company_id=uuid4()),
    ]:
        with pytest.raises(Forbidden):
            authorize(p, "compras:aprovacao:senior", bad)
    with pytest.raises(Forbidden):
        authorize(p, "compras:*")


async def test_identity_map_get_disabled(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u = user(ctx)
        s.add(u)
        await s.commit()
        with pytest.raises(RuntimeError, match="identity-map"):
            await s.get(User, u.id)


async def test_immutable_tenant_and_version(factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u = user(ctx)
        s.add(u)
        await s.commit()
        u.version = 77
        with pytest.raises(RuntimeError, match="Immutable field: version"):
            await s.flush()
