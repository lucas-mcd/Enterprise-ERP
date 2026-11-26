import asyncio
import io
from datetime import timedelta
from dataclasses import replace
from uuid import uuid4, UUID
import pytest
from openpyxl import load_workbook
from sqlalchemy import select, func
from erp.config import settings
from erp.modules.operations.infrastructure.models import Product, Order, StockMovement
from erp.modules.operations.infrastructure.repository import OperationsRepository
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.operations.domain.orders import BusinessError
from erp.modules.reports.infrastructure.render import pdf_file
from erp.modules.reports.infrastructure.service import report_data
from erp.modules.reports.infrastructure.models import ReportJob
from erp.modules.financeiro.domain.cash import EntryFilter, business_today
from erp.shared.infrastructure.database.seed import populate
from test_auth_seed import login, headers, options
from decimal import Decimal

pytest_plugins = ["test_auth_seed"]


async def product(client, auth, sku="REAL-01"):
    result = await client.post(
        "/api/v1/estoque/produtos",
        headers=auth,
        json={
            "sku": sku,
            "name": "Monitor profissional",
            "category": "Tecnologia",
            "minimum": 5,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


async def order(client, auth, pid, kind="vendas", quantity=2):
    result = await client.post(
        f"/api/v1/{kind}/pedidos",
        headers=auth | {"Idempotency-Key": str(uuid4())},
        json={
            "counterparty": "Atlas Software",
            "ordered_on": str(business_today()),
            "due_date": str(business_today()),
            "lines": [
                {"product_id": pid, "quantity": quantity, "unit_price": "125.50"}
            ],
        },
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


async def test_purchase_sale_atomic_and_replay(auth_client, ctx, seeded, factory):
    auth = headers(await login(auth_client, ctx))
    pid = await product(auth_client, auth)
    purchase = await order(auth_client, auth, pid, "compras", 10)
    for _ in range(2):
        result = await auth_client.post(
            f"/api/v1/compras/pedidos/{purchase}/concluir", headers=auth
        )
        assert result.status_code == 200, result.text
    sale = await order(auth_client, auth, pid, quantity=3)
    for _ in range(2):
        result = await auth_client.post(
            f"/api/v1/vendas/pedidos/{sale}/concluir", headers=auth
        )
        assert result.status_code == 200, result.text
    async with factory(info={"audit_context": ctx}) as session:
        p = await session.scalar(select(Product).where(Product.id == UUID(pid)))
        assert p.balance == 7
        assert (
            await session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.product_id == p.id)
            )
            == 2
        )
        cash = list(
            await session.scalars(
                select(CashEntry).where(CashEntry.is_simulated.is_(False))
            )
        )
        assert len(cash) == 2
        assert {x.kind: x.amount for x in cash} == {
            "despesa": Decimal("1255.00"),
            "receita": Decimal("376.50"),
        }
        assert all(x.status == "pendente" for x in cash)


async def test_insufficient_stock_rollback(auth_client, ctx, seeded, factory):
    auth = headers(await login(auth_client, ctx))
    pid = await product(auth_client, auth)
    sale = await order(auth_client, auth, pid)
    result = await auth_client.post(
        f"/api/v1/vendas/pedidos/{sale}/concluir", headers=auth
    )
    assert result.status_code == 409
    async with factory(info={"audit_context": ctx}) as session:
        row = await session.scalar(select(Order).where(Order.id == UUID(sale)))
        assert row.status == "draft" and row.cash_entry_id is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.product_id == UUID(pid))
            )
            == 0
        )


async def test_tenant_and_permissions(auth_client, ctx, seeded, factory):
    auth = headers(await login(auth_client, ctx))
    pid = await product(auth_client, auth)
    other = replace(ctx, tenant_id=uuid4())
    await populate(factory, options(other, False))
    other_auth = headers(await login(auth_client, other))
    res = await auth_client.post(
        f"/api/v1/estoque/produtos/{pid}/movimentos",
        headers=other_auth | {"Idempotency-Key": str(uuid4())},
        json={"quantity": 10, "reason": "Entrada inicial"},
    )
    assert res.status_code == 409
    seller = headers(await login(auth_client, ctx, "vendedor@enterprise.com"))
    assert (
        await auth_client.get("/api/v1/compras/pedidos", headers=seller)
    ).status_code == 403
    assert (
        await auth_client.get("/api/v1/estoque/produtos", headers=seller)
    ).status_code == 200
    assert (
        await auth_client.post(
            "/api/v1/estoque/produtos",
            headers=seller,
            json={"sku": "TEST", "name": "Produto", "category": "Teste", "minimum": 0},
        )
    ).status_code == 403


async def test_movement_idempotence_and_sort(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx))
    pid = await product(auth_client, auth)
    key = str(uuid4())
    for _ in range(2):
        result = await auth_client.post(
            f"/api/v1/estoque/produtos/{pid}/movimentos",
            headers=auth | {"Idempotency-Key": key},
            json={"quantity": 10, "reason": "Entrada inicial"},
        )
        assert result.status_code == 201
        assert result.json()["balance_after"] == 10
    result = await auth_client.get(
        "/api/v1/estoque/produtos?source=demo&sort=name", headers=auth
    )
    assert result.json()["total"] == 8
    names = [r["name"] for r in result.json()["items"]]
    assert names == sorted(names)


async def test_export_formats_filters_and_access(auth_client, ctx, seeded, factory):
    auth = headers(await login(auth_client, ctx))
    params = {"source": "demo", "start_date": "2000-01-01", "end_date": "2000-12-31"}
    csv = await auth_client.get(
        "/api/v1/financeiro/exportacoes/planilha", params=params, headers=auth
    )
    assert csv.status_code == 200 and csv.content.startswith(b"\xef\xbb\xbf")
    assert len(csv.text.splitlines()) == 1
    today = business_today()
    params |= {
        "start_date": str((today - timedelta(days=89))),
        "end_date": str(today),
        "format": "xlsx",
    }
    xlsx = await auth_client.get(
        "/api/v1/financeiro/exportacoes/planilha", params=params, headers=auth
    )
    assert xlsx.status_code == 200, xlsx.text[:100]
    workbook = load_workbook(io.BytesIO(xlsx.content))
    assert workbook.active.max_row == 397
    assert workbook.active["G2"].data_type == "n"
    seller = headers(await login(auth_client, ctx, "vendedor@enterprise.com"))
    assert (
        await auth_client.get(
            "/api/v1/financeiro/exportacoes/planilha", params=params, headers=seller
        )
    ).status_code == 403
    async with factory(info={"audit_context": ctx}) as session:
        rows, summary, logs = await report_data(
            session, EntryFilter((today - timedelta(days=89)), today, "demo"), True
        )
        assert len(rows) == 396 and logs
        pdf = pdf_file(rows, summary, logs, "Relatório de teste")
        assert pdf.startswith(b"%PDF") and len(pdf) > 1000


async def test_pdf_queue_owner_and_quota(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx))
    today = business_today()
    params = {"start_date": str(today), "end_date": str(today), "source": "demo"}
    first = await auth_client.post(
        "/api/v1/financeiro/exportacoes/pdf", params=params, headers=auth
    )
    assert first.status_code == 202, first.text
    job_id = first.json()["id"]
    limited = headers(await login(auth_client, ctx, "financeiro@enterprise.com"))
    assert (
        await auth_client.get(
            f"/api/v1/financeiro/exportacoes/{job_id}", headers=limited
        )
    ).status_code == 404
    for _ in range(2):
        assert (
            await auth_client.post(
                "/api/v1/financeiro/exportacoes/pdf", params=params, headers=auth
            )
        ).status_code == 202
    assert (
        await auth_client.post(
            "/api/v1/financeiro/exportacoes/pdf", params=params, headers=auth
        )
    ).status_code == 429


async def test_worker_pdf_postgres(
    auth_client, ctx, seeded, factory, monkeypatch, tmp_path
):
    from erp.workers.reports import generate

    engine = factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Worker uses independent PostgreSQL connections")
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("REPORT_DIRECTORY", str(tmp_path))
    settings.cache_clear()
    auth = headers(await login(auth_client, ctx))
    today = business_today()
    response = await auth_client.post(
        "/api/v1/financeiro/exportacoes/pdf",
        params={
            "source": "demo",
            "start_date": str((today - timedelta(days=89))),
            "end_date": str(today),
        },
        headers=auth,
    )
    jid = UUID(response.json()["id"])
    await generate(jid, ctx.tenant_id)
    await generate(jid, ctx.tenant_id)
    result = await auth_client.get(
        f"/api/v1/financeiro/exportacoes/{jid}/download", headers=auth
    )
    assert result.status_code == 200, result.text[:100]
    assert result.content.startswith(b"%PDF")
    async with factory(info={"audit_context": ctx}) as session:
        row = await session.scalar(select(ReportJob).where(ReportJob.id == jid))
        assert row.status == "ready"
    settings.cache_clear()


async def test_concurrent_sales_no_overselling_postgres(
    auth_client, ctx, seeded, factory
):
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks")
    auth = headers(await login(auth_client, ctx))
    pid = await product(auth_client, auth)
    purchase = await order(auth_client, auth, pid, "compras", 1)
    await auth_client.post(f"/api/v1/compras/pedidos/{purchase}/concluir", headers=auth)
    ids = [await order(auth_client, auth, pid, quantity=1) for _ in range(2)]
    # Use authenticated principal ID as the financial actor.
    actor = UUID((await login(auth_client, ctx)).json()["user"]["user_id"])

    async def complete(identity):
        try:
            async with factory(info={"audit_context": ctx}) as session:
                async with session.begin():
                    await OperationsRepository(session).complete(
                        UUID(identity), "sale", actor
                    )
            return True
        except BusinessError:
            return False

    assert sorted(await asyncio.gather(*(complete(i) for i in ids))) == [False, True]
    async with factory(info={"audit_context": ctx}) as session:
        row = await session.scalar(select(Product).where(Product.id == UUID(pid)))
        assert row.balance == 0


async def test_module_exports_and_formula_safety(auth_client, ctx, seeded):
    from erp.modules.reports.infrastructure.render import grid_file

    auth = headers(await login(auth_client, ctx))
    for module, count in [("estoque", 9), ("vendas", 19), ("compras", 22)]:
        response = await auth_client.get(
            f"/api/v1/{module}/exportar?source=demo&format=csv", headers=auth
        )
        assert response.status_code == 200, response.text
        assert len(response.text.splitlines()) == count
    body = grid_file(["Nome"], [["=HYPERLINK(1)"]], "xlsx")
    cell = load_workbook(io.BytesIO(body)).active["A2"]
    assert cell.data_type == "s" and cell.value.startswith("'")
    assert b"'=HYPERLINK" in grid_file(["Nome"], [["=HYPERLINK(1)"]], "csv")


async def test_multi_line_failure_rolls_back_first_stock_change(
    auth_client, ctx, seeded, factory
):
    auth = headers(await login(auth_client, ctx))
    ids = [await product(auth_client, auth, f"ATOMIC-{i}") for i in range(2)]
    first, second = sorted(ids)
    response = await auth_client.post(
        f"/api/v1/estoque/produtos/{first}/movimentos",
        headers=auth | {"Idempotency-Key": str(uuid4())},
        json={"quantity": 5, "reason": "Saldo inicial teste"},
    )
    assert response.status_code == 201
    sale = await auth_client.post(
        "/api/v1/vendas/pedidos",
        headers=auth | {"Idempotency-Key": str(uuid4())},
        json={
            "counterparty": "Teste atômico",
            "ordered_on": str(business_today()),
            "due_date": str(business_today()),
            "lines": [
                {"product_id": pid, "quantity": 1, "unit_price": "10.00"}
                for pid in [first, second]
            ],
        },
    )
    assert sale.status_code == 201
    result = await auth_client.post(
        f"/api/v1/vendas/pedidos/{sale.json()['id']}/concluir", headers=auth
    )
    assert result.status_code == 409
    async with factory(info={"audit_context": ctx}) as session:
        row = await session.scalar(select(Product).where(Product.id == UUID(first)))
        assert row.balance == 5
        assert (
            await session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.product_id == row.id)
            )
            == 1
        )
