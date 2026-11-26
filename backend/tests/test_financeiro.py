import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.financeiro.infrastructure.repositories.cash import SqlCashRepository
from erp.modules.financeiro.presentation.schemas.cash import CreateEntry
from erp.shared.infrastructure.database.audit import AuditLog
from erp.shared.infrastructure.database.seed import populate
from test_auth_seed import login, headers, options

pytest_plugins = ["test_auth_seed"]


def payload(**updates):
    value = {
        "description": "Consultoria de software",
        "counterparty": "Cliente Atlas",
        "category": "Serviços",
        "kind": "receita",
        "status": "concluido",
        "amount": "1250.50",
        "due_date": str(business_today()),
        "settled_on": str(business_today()),
    }
    return value | updates


def parameters(source="real", **updates):
    return {
        "start_date": str(business_today() - timedelta(days=89)),
        "end_date": str(business_today()),
        "source": source,
    } | updates


async def submit(client, ctx, value=None, key=None, email="financeiro@enterprise.com"):
    response = await login(client, ctx, email)
    auth = headers(response) | {"Idempotency-Key": str(key or uuid4())}
    return await client.post(
        "/api/v1/financeiro/lancamentos", json=value or payload(), headers=auth
    )


async def test_create_audit_and_exact_summary(auth_client, factory, ctx, seeded):
    response = await submit(auth_client, ctx)
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["amount"] == "1250.50" and entry["is_simulated"] is False
    auth = headers(await login(auth_client, ctx))
    summary = await auth_client.get(
        "/api/v1/financeiro/fluxo-caixa", params=parameters(), headers=auth
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["income"] == "1250.50"
    assert summary.json()["net"] == "1250.50"
    assert summary.json()["total_records"] == 1
    async with factory(info={"audit_context": ctx}) as session:
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.table_name == "cash_entries",
                AuditLog.entity_id == UUID(entry["id"]),
            )
        )
        assert audit is not None
        assert audit.diff["amount"] == {"valor_antigo": None, "valor_novo": "1250.50"}


async def test_demo_real_separation_and_pagination(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx))
    first = await auth_client.get(
        "/api/v1/financeiro/lancamentos",
        params=parameters("demo", page=1, page_size=10),
        headers=auth,
    )
    second = await auth_client.get(
        "/api/v1/financeiro/lancamentos",
        params=parameters("demo", page=2, page_size=10),
        headers=auth,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == 396
    assert len(first.json()["items"]) == 10
    assert not (
        {r["id"] for r in first.json()["items"]}
        & {r["id"] for r in second.json()["items"]}
    )
    real = await auth_client.get(
        "/api/v1/financeiro/lancamentos", params=parameters(), headers=auth
    )
    assert real.json()["total"] == 0
    daily = await auth_client.get(
        "/api/v1/financeiro/fluxo-caixa", params=parameters("demo"), headers=auth
    )
    assert daily.json()["total_records"] == 396
    assert len(daily.json()["points"]) == 90


async def test_pending_does_not_change_realized_cash(auth_client, ctx, seeded):
    response = await submit(
        auth_client,
        ctx,
        payload(kind="despesa", status="pendente", settled_on=None, amount="10.10"),
    )
    assert response.status_code == 201
    auth = headers(await login(auth_client, ctx))
    result = (
        await auth_client.get(
            "/api/v1/financeiro/fluxo-caixa", params=parameters(), headers=auth
        )
    ).json()
    assert result["expense"] == "0.00" and result["net"] == "0.00"
    assert result["pending_expense"] == "10.10"


async def test_idempotent_retry_and_payload_conflict(auth_client, factory, ctx, seeded):
    key = uuid4()
    one = await submit(auth_client, ctx, key=key)
    two = await submit(auth_client, ctx, key=key)
    conflict = await submit(auth_client, ctx, payload(amount="10.00"), key=key)
    assert (
        one.status_code == 201
        and two.status_code == 200
        and conflict.status_code == 409
    )
    assert one.json()["id"] == two.json()["id"]
    async with factory(info={"audit_context": ctx}) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == UUID(one.json()["id"]))
        )
        assert count == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "0"},
        {"amount": "-10"},
        {"amount": "1.001"},
        {"amount": 1.5},
        {"amount": "NaN"},
        {"status": "pendente"},
        {"settled_on": None},
        {"settled_on": str(business_today() + timedelta(days=1))},
        {"category": "Inexistente"},
        {"description": "   "},
        {"tenant_id": str(uuid4())},
        {"is_simulated": True},
    ],
)
async def test_invalid_creation(auth_client, ctx, seeded, changes):
    assert (await submit(auth_client, ctx, payload(**changes))).status_code == 422


async def test_seller_cannot_read_or_write_finance(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx, "vendedor@enterprise.com"))
    for endpoint in ("/lancamentos", "/fluxo-caixa"):
        assert (
            await auth_client.get(
                "/api/v1/financeiro" + endpoint, params=parameters("demo"), headers=auth
            )
        ).status_code == 403
    result = await auth_client.post(
        "/api/v1/financeiro/lancamentos",
        json=payload(),
        headers=auth | {"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 403


async def test_tenant_isolation_aggregates_and_rows(auth_client, factory, ctx, seeded):
    other = replace(ctx, tenant_id=uuid4())
    await populate(factory, options(other, demo=False))
    assert (await submit(auth_client, ctx)).status_code == 201
    auth = headers(await login(auth_client, other))
    result = await auth_client.get(
        "/api/v1/financeiro/fluxo-caixa", params=parameters(), headers=auth
    )
    assert result.json()["total_records"] == 0
    rows = await auth_client.get(
        "/api/v1/financeiro/lancamentos", params=parameters(), headers=auth
    )
    assert rows.json()["total"] == 0


async def test_filter_search_is_literal_and_validated(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx))
    result = await auth_client.get(
        "/api/v1/financeiro/lancamentos", params=parameters("demo", q="%"), headers=auth
    )
    assert result.json()["total"] == 0
    result = await auth_client.get(
        "/api/v1/financeiro/lancamentos",
        params=parameters("demo", kind="receita", status="concluido"),
        headers=auth,
    )
    assert result.json()["total"] == 96
    for extra in [
        {"page": 0},
        {"start_date": "9999-12-31", "end_date": "9999-12-31"},
        {"page_size": 101},
        {"start_date": "2000-01-01"},
        {"end_date": "2000-01-01"},
    ]:
        assert (
            await auth_client.get(
                "/api/v1/financeiro/lancamentos",
                params=parameters(**extra),
                headers=auth,
            )
        ).status_code == 422


async def test_soft_deleted_entry_hidden_from_totals(auth_client, factory, ctx, seeded):
    response = await submit(auth_client, ctx)
    async with factory(info={"audit_context": ctx}) as session:
        row = await session.scalar(
            select(CashEntry).where(CashEntry.id == UUID(response.json()["id"]))
        )
        await session.delete(row)
        await session.commit()
    auth = headers(await login(auth_client, ctx))
    result = await auth_client.get(
        "/api/v1/financeiro/fluxo-caixa", params=parameters(), headers=auth
    )
    assert result.json()["total_records"] == 0


async def test_parallel_idempotency_postgres(factory, ctx, seeded):
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Concurrent writers require PostgreSQL")
    key = uuid4()

    async def write():
        async with factory(info={"audit_context": ctx}) as session:
            async with session.begin():
                return await SqlCashRepository(session).create(
                    CreateEntry(**payload()).command(), ctx.actor_id, key
                )

    a, b = await asyncio.gather(write(), write())
    assert a[0].id == b[0].id
    assert sorted([a[1], b[1]]) == [False, True]
    async with factory(info={"audit_context": ctx}) as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.entity_id == a[0].id)
            )
            == 1
        )
