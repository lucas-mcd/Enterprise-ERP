from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from erp.config import settings
from erp.modules.organization.infrastructure.models import Tenant
from erp.main import app
from erp.modules.identity.infrastructure.models import (
    User,
    Role,
    Permission,
    UserRole,
    RolePermission,
)


@pytest.fixture
async def client(factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-32-characters-minimum-only")
    settings.cache_clear()
    app.state.sessions = factory
    app.state.redis = AsyncMock()
    app.state.redis.get.return_value = None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    settings.cache_clear()


def token(ctx, **overrides):
    now = datetime.now(timezone.utc)
    cfg = settings()
    claims = dict(
        sub=str(ctx.actor_id),
        tid=str(ctx.tenant_id),
        sid=str(uuid4()),
        jti=str(uuid4()),
        iss=cfg.jwt_issuer,
        aud=cfg.jwt_audience,
        iat=now,
        nbf=now,
        exp=now + timedelta(minutes=5),
        typ="access",
    )
    claims.update(overrides)
    return jwt.encode(claims, cfg.jwt_secret.get_secret_value(), algorithm="HS256")


async def test_anonymous_and_revoked(client, ctx):
    assert (await client.get("/api/v1/identity/me")).status_code == 401
    response = await client.get(
        "/api/v1/identity/me", headers={"Authorization": f"Bearer {token(ctx)}"}
    )
    assert response.status_code == 401


async def test_invalid_signature(client, ctx):
    bad = token(ctx)[:-8] + "tampered"
    assert (
        await client.get(
            "/api/v1/identity/me", headers={"Authorization": f"Bearer {bad}"}
        )
    ).status_code == 401


async def test_authenticated_permission_and_revocation(client, factory, ctx):
    async with factory(info={"audit_context": ctx}) as s:
        u = User(
            id=ctx.actor_id,
            tenant_id=ctx.tenant_id,
            email="lucas@example.com",
            display_name="Lucas",
            password_hash="not-a-real-login",
            is_active=True,
            approval_limit=Decimal("0"),
        )
        role = Role(tenant_id=ctx.tenant_id, name="viewer")
        permission = Permission(tenant_id=ctx.tenant_id, code="identidade:perfil:ler")
        s.add_all(
            [
                Tenant(
                    id=ctx.tenant_id,
                    tenant_id=ctx.tenant_id,
                    name="Test",
                    is_active=True,
                ),
                u,
                role,
                permission,
            ]
        )
        await s.flush()
        grant = RolePermission(
            tenant_id=ctx.tenant_id, role_id=role.id, permission_id=permission.id
        )
        s.add_all(
            [grant, UserRole(tenant_id=ctx.tenant_id, user_id=u.id, role_id=role.id)]
        )
        await s.commit()
        app.state.redis.get.return_value = str(ctx.actor_id)
        headers = {"Authorization": f"Bearer {token(ctx)}", "X-Tenant-ID": str(uuid4())}
        response = await client.get("/api/v1/identity/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["tenant_id"] == str(ctx.tenant_id)
        await s.delete(grant)
        await s.commit()
        assert (
            await client.get("/api/v1/identity/me", headers=headers)
        ).status_code == 403


async def test_wrong_tenant_claim_cannot_find_user(client, factory, ctx):
    app.state.redis.get.return_value = str(ctx.actor_id)
    headers = {"Authorization": f"Bearer {token(ctx, tid=str(uuid4()))}"}
    assert (await client.get("/api/v1/identity/me", headers=headers)).status_code == 401
