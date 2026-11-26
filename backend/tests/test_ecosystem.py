from decimal import Decimal
from uuid import UUID
from dataclasses import replace
from sqlalchemy import select
from test_auth_seed import login, headers, options
from test_financeiro import submit, payload, parameters
from test_operations_reports import product, order
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.identity.infrastructure.models import User
from erp.shared.infrastructure.database.seed import populate

pytest_plugins = ["test_auth_seed"]


async def test_approval_threshold_current_limit_and_atomic_batch(
    auth_client, ctx, seeded, factory
):
    small = (
        await submit(
            auth_client,
            ctx,
            payload(amount="5000.00", status="pendente", settled_on=None),
        )
    ).json()
    big = (await submit(auth_client, ctx, payload(amount="5000.01"))).json()
    assert small["status"] == "pendente"
    assert big["status"] == "aguardando_aprovacao" and big["settled_on"] is None
    auth = headers(await login(auth_client, ctx, "financeiro@enterprise.com"))
    path = f"/api/v1/governanca/aprovar/cash/{big['id']}"
    assert (await auth_client.post(path, headers=auth)).status_code == 403
    body = {
        "rows": [{"id": r["id"], "version": r["version"]} for r in [small, big]],
        "settled_on": str(business_today()),
    }
    assert (
        await auth_client.post(
            "/api/v1/financeiro/lotes/baixar", headers=auth, json=body
        )
    ).status_code == 409
    async with factory(info={"audit_context": ctx}) as session:
        row = await session.scalar(
            select(CashEntry).where(CashEntry.id == UUID(small["id"]))
        )
        assert row.status == "pendente"
        user = await session.scalar(
            select(User).where(User.email == "financeiro@enterprise.com")
        )
        user.approval_limit = Decimal("6000")
        await session.commit()
    assert (await auth_client.post(path, headers=auth)).status_code == 200
    assert (await auth_client.post(path, headers=auth)).status_code == 200
    stale = await auth_client.post(
        "/api/v1/financeiro/lotes/baixar", headers=auth, json=body
    )
    assert stale.status_code == 409
    rows = (
        await auth_client.get(
            "/api/v1/financeiro/lancamentos", headers=auth, params=parameters()
        )
    ).json()["items"]
    body["rows"] = [{"id": r["id"], "version": r["version"]} for r in rows]
    for _ in range(2):
        result = await auth_client.post(
            "/api/v1/financeiro/lotes/baixar", headers=auth, json=body
        )
        assert result.status_code == 200, result.text
    export = await auth_client.post(
        "/api/v1/financeiro/lotes/exportar",
        headers=auth,
        json=body | {"format": "xlsx"},
    )
    assert export.status_code == 200 and export.content[:2] == b"PK"


async def test_purchase_requires_approval_and_fiscal_snapshot(
    auth_client, ctx, seeded, factory
):
    auth = headers(await login(auth_client, ctx))
    pid = await product(auth_client, auth)
    purchase = await order(auth_client, auth, pid, "compras", 50)
    url = f"/api/v1/compras/pedidos/{purchase}/concluir"
    assert (await auth_client.post(url, headers=auth)).status_code == 409
    approved = await auth_client.post(
        f"/api/v1/governanca/aprovar/purchase/{purchase}", headers=auth
    )
    assert approved.status_code == 200, approved.text
    assert (await auth_client.post(url, headers=auth)).status_code == 200
    body = {"order_id": purchase, "kind": "nfe", "regime": "real"}
    first = await auth_client.post("/api/v1/fiscal/notas", headers=auth, json=body)
    assert first.status_code == 202, first.text
    invoice = first.json()
    assert invoice["status"] == "processando" and invoice["fiscal_simulation"]
    assert invoice["taxes"]["ICMS"]["amount"] == "1129.50"
    again = await auth_client.post("/api/v1/fiscal/notas", headers=auth, json=body)
    assert again.json()["id"] == invoice["id"]
    assert (
        await auth_client.post(
            "/api/v1/fiscal/notas", headers=auth, json=body | {"regime": "simples"}
        )
    ).status_code == 409
    origins = await auth_client.get("/api/v1/fiscal/origens", headers=auth)
    assert origins.status_code == 200 and origins.json()[0]["id"] == purchase
    async with factory(info={"audit_context": ctx}) as session:
        cash = await session.scalar(
            select(CashEntry).where(CashEntry.is_simulated.is_(False))
        )
        assert cash.status == "aguardando_aprovacao"


async def test_payroll_snapshot_idempotent_provision_and_admin_audit(
    auth_client, ctx, seeded
):
    auth = headers(await login(auth_client, ctx))
    body = {
        "registration": "REAL-001",
        "name": "Ana Silva",
        "department": "Produto",
        "job_title": "Engenheira",
        "base_salary": "6000.00",
        "hired_on": "2024-01-01",
        "is_active": True,
    }
    result = await auth_client.post("/api/v1/rh/colaboradores", headers=auth, json=body)
    assert result.status_code == 201, result.text
    month = str(business_today())[:7]
    result = await auth_client.post(
        "/api/v1/rh/folhas", headers=auth, json={"month": month}
    )
    assert result.status_code in (200, 201), result.text
    payroll = result.json()
    assert Decimal(payroll["net"]) == 6000
    repeat = await auth_client.post(
        "/api/v1/rh/folhas", headers=auth, json={"month": month}
    )
    assert repeat.json()["id"] == payroll["id"]
    ids = []
    for _ in range(2):
        result = await auth_client.post(
            f"/api/v1/rh/folhas/{payroll['id']}/provisionar",
            headers=auth,
            json={"due_date": str(business_today())},
        )
        assert result.status_code == 200, result.text
        ids.append(result.json()["cash_entry_id"])
    assert ids[0] == ids[1]
    audit = await auth_client.get(
        "/api/v1/governanca/auditoria", headers=auth, params={"table": "employees"}
    )
    assert audit.status_code == 200, audit.text
    finance = headers(await login(auth_client, ctx, "financeiro@enterprise.com"))
    assert (
        await auth_client.get("/api/v1/governanca/auditoria", headers=finance)
    ).status_code == 403
    assert (
        await auth_client.get("/api/v1/rh/folhas", headers=finance)
    ).status_code == 403


async def test_bi_seed_and_budget_and_tenant_isolation(
    auth_client, ctx, seeded, factory
):
    auth = headers(await login(auth_client, ctx))
    data = await auth_client.get(
        "/api/v1/bi/overview", headers=auth, params=parameters("demo")
    )
    assert data.status_code == 200, data.text
    assert Decimal(data.json()["sales"]["margin"]) == 37
    assert data.json()["budgets"] and data.json()["sales"]["categories"]
    body = {
        "month": str(business_today())[:7],
        "category": "Vendas",
        "kind": "receita",
        "amount": "10000.00",
    }
    assert (
        await auth_client.put("/api/v1/bi/orcamento", headers=auth, json=body)
    ).status_code == 200
    assert (
        await auth_client.put("/api/v1/bi/orcamento", headers=auth, json=body)
    ).status_code == 200
    from uuid import uuid4

    other = replace(ctx, tenant_id=uuid4())
    await populate(factory, options(other))
    otherauth = headers(await login(auth_client, other))
    data = await auth_client.get(
        "/api/v1/bi/overview", headers=otherauth, params=parameters()
    )
    assert all(Decimal(r["budget_income"]) == 0 for r in data.json()["budgets"])
