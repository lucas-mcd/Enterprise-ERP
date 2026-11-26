from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from erp.config import settings
from erp.main import app
from erp.modules.identity.infrastructure.models import User, UserRole
from erp.modules.organization.infrastructure.models import Tenant, DemoActivity
from erp.shared.infrastructure.database.audit import AuditLog
from erp.shared.infrastructure.database.seed import SeedOptions, populate
from erp.modules.identity.infrastructure.passwords import password_service

PASSWORD = "Test-only-Password-2026!"


def options(ctx, demo=True):
    return SeedOptions(
        tenant_id=ctx.tenant_id,
        demo=demo,
        passwords={
            "SEED_ADMIN_PASSWORD": PASSWORD,
            "SEED_FINANCE_PASSWORD": PASSWORD,
            "SEED_SALES_PASSWORD": PASSWORD,
        },
    )


@pytest.fixture
async def seeded(factory, ctx):
    await populate(factory, options(ctx))
    return options(ctx)


@pytest.fixture
async def auth_client(factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "testing-secret-at-least-32-characters-long")
    settings.cache_clear()
    app.state.sessions = factory
    app.state.redis = FakeRedis(decode_responses=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await app.state.redis.aclose()
    settings.cache_clear()


async def login(client, ctx, email="admin@enterprise.com", password=PASSWORD):
    return await client.post(
        "/api/v1/identity/auth/login",
        json={"tenant_id": str(ctx.tenant_id), "email": email, "password": password},
    )


def headers(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_seed_idempotent_no_password_overwrite(factory, ctx, seeded):
    async with factory(info={"audit_context": ctx}) as session:
        users = list(await session.scalars(select(User)))
        assert len(users) == 3
        hashes = {u.id: u.password_hash for u in users}
        assert all(h.startswith("$argon2id$") for h in hashes.values())
        logs_before = len(list(await session.scalars(select(AuditLog))))
        assert len(list(await session.scalars(select(DemoActivity)))) == 36
    report = await populate(factory, replace(seeded, passwords={}))
    assert report.created == 0
    async with factory(info={"audit_context": ctx}) as session:
        assert {
            u.id: u.password_hash for u in await session.scalars(select(User))
        } == hashes
        logs = list(await session.scalars(select(AuditLog)))
        assert len(logs) == logs_before
        assert any(
            log.operation == "UPDATE" and log.table_name == "demo_activities"
            for log in logs
        )
        assert PASSWORD not in str([log.diff for log in logs])
        for log in logs:
            assert all(
                set(diff) == {"valor_antigo", "valor_novo"}
                for diff in log.diff.values()
            )


async def test_seed_rolls_back_everything_on_bad_password(factory, ctx):
    with pytest.raises(ValueError):
        await populate(factory, replace(options(ctx), passwords={}))
    async with factory(info={"audit_context": ctx}) as session:
        assert await session.scalar(select(Tenant)) is None
        assert await session.scalar(select(AuditLog)) is None


async def test_seed_does_not_restore_revoked_membership(factory, ctx, seeded):
    async with factory(info={"audit_context": ctx}) as session:
        grant = await session.scalar(select(UserRole))
        await session.delete(grant)
        await session.commit()
        count = len(list(await session.scalars(select(AuditLog))))
    with pytest.raises(IntegrityError):
        await populate(factory, seeded)
    async with factory(info={"audit_context": ctx}) as session:
        assert len(list(await session.scalars(select(UserRole)))) == 2
        assert len(list(await session.scalars(select(AuditLog)))) == count


async def test_login_claims_session_ttl_and_logout(auth_client, ctx, seeded):
    response = await login(auth_client, ctx)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cfg = settings()
    body = response.json()
    claims = jwt.decode(
        body["access_token"],
        cfg.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=cfg.jwt_audience,
        issuer=cfg.jwt_issuer,
    )
    assert claims["tenant_id"] == str(ctx.tenant_id)
    assert claims["user_id"] == body["user"]["user_id"]
    assert "compras:aprovacao:senior" in claims["permissions"]
    key = f"session:{ctx.tenant_id}:{claims['sid']}"
    assert 0 < await app.state.redis.ttl(key) <= 900
    assert (
        await auth_client.get("/api/v1/identity/me", headers=headers(response))
    ).status_code == 200
    assert (
        await auth_client.post(
            "/api/v1/identity/auth/logout", headers=headers(response)
        )
    ).status_code == 204
    assert await app.state.redis.get(key) is None
    assert (
        await auth_client.get("/api/v1/identity/me", headers=headers(response))
    ).status_code == 401


@pytest.mark.parametrize(
    "email,category",
    [
        ("financeiro@enterprise.com", "financeiro"),
        ("vendedor@enterprise.com", "vendas"),
    ],
)
async def test_role_scoped_dashboard(auth_client, ctx, seeded, email, category):
    response = await login(auth_client, ctx, email)
    assert response.status_code == 200
    assert "compras:aprovacao:senior" not in response.json()["user"]["permissions"]
    dashboard = await auth_client.get(
        "/api/v1/identity/dashboard", headers=headers(response)
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["total_records"] == 18
    assert {a["category"] for a in dashboard.json()["activities"]} == {category}
    assert dashboard.json()["audit"] == []


async def test_wrong_password_unknown_user_same_error(auth_client, ctx, seeded):
    one = await login(auth_client, ctx, password="wrong")
    two = await login(auth_client, ctx, email="unknown@enterprise.com")
    assert one.status_code == two.status_code == 401
    assert one.json() == two.json()
    assert not await app.state.redis.keys("session:*")


async def test_inactive_user_and_tenant(auth_client, factory, ctx, seeded):
    async with factory(info={"audit_context": ctx}) as session:
        user = await session.scalar(
            select(User).where(User.email == "admin@enterprise.com")
        )
        user.is_active = False
        await session.commit()
        assert (await login(auth_client, ctx)).status_code == 401
        user.is_active = True
        tenant = await session.scalar(select(Tenant))
        tenant.is_active = False
        await session.commit()
        assert (await login(auth_client, ctx)).status_code == 401


async def test_permissions_reloaded_after_login(auth_client, factory, ctx, seeded):
    response = await login(auth_client, ctx)
    async with factory(info={"audit_context": ctx}) as session:
        user = await session.scalar(
            select(User).where(User.email == "admin@enterprise.com")
        )
        grant = await session.scalar(
            select(UserRole).where(UserRole.user_id == user.id)
        )
        await session.delete(grant)
        await session.commit()
    assert (
        await auth_client.get("/api/v1/identity/dashboard", headers=headers(response))
    ).status_code == 403


async def test_redis_unavailable_fails_closed(auth_client, ctx, seeded, monkeypatch):
    async def failed(*args, **kwargs):
        raise RedisConnectionError("test")

    monkeypatch.setattr(app.state.redis, "eval", failed)
    response = await login(auth_client, ctx)
    assert response.status_code == 503
    assert "access_token" not in response.text


async def test_session_creation_failure_returns_no_token(
    auth_client, ctx, seeded, monkeypatch
):
    async def failed(*args, **kwargs):
        raise RedisConnectionError("test")

    monkeypatch.setattr("redis.asyncio.client.Pipeline.execute", failed)
    response = await login(auth_client, ctx)
    assert response.status_code == 503
    assert "access_token" not in response.text


async def test_rate_limit_atomic_ttl(auth_client, ctx):
    for _ in range(10):
        assert (await login(auth_client, ctx)).status_code == 401
    response = await login(auth_client, ctx)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    for key in await app.state.redis.keys("login-rate:*"):
        assert await app.state.redis.ttl(key) > 0
        assert "admin@" not in key


async def test_validation_never_echoes_password(auth_client, ctx):
    response = await auth_client.post(
        "/api/v1/identity/auth/login",
        json={
            "tenant_id": str(ctx.tenant_id),
            "email": "bad",
            "password": {"value": PASSWORD},
        },
    )
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert "input" not in response.text


async def test_expired_token_and_wrong_tenant(auth_client, ctx, seeded):
    response = await login(auth_client, ctx)
    cfg = settings()
    claims = jwt.decode(
        response.json()["access_token"],
        cfg.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=cfg.jwt_audience,
        issuer=cfg.jwt_issuer,
    )
    claims["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = jwt.encode(claims, cfg.jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        await auth_client.get(
            "/api/v1/identity/me", headers={"Authorization": f"Bearer {expired}"}
        )
    ).status_code == 401
    other = replace(ctx, tenant_id=uuid4())
    assert (await login(auth_client, other)).status_code == 401


async def test_hash_verify_and_needs_rehash():
    service = password_service()
    encoded = await service.hash(PASSWORD)
    assert await service.verify(PASSWORD, encoded)
    assert not await service.verify("wrong", encoded)
    assert not await service.verify(PASSWORD, None)
    assert not service.needs_rehash(encoded)
