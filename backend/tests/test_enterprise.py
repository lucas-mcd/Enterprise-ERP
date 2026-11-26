from datetime import date
from decimal import Decimal
from uuid import uuid4, UUID
from sqlalchemy import select, func
from test_auth_seed import headers, login
from erp.modules.financeiro.domain.cash import business_today
from erp.modules.assets.domain.depreciation import depreciation
from erp.modules.financeiro.infrastructure.models import CashEntry
from erp.modules.projects.infrastructure.models import Delivery
from erp.shared.infrastructure.database.audit import AuditLog

pytest_plugins = ["test_auth_seed"]


def test_linear_depreciation_residual_and_final_rounding():
    args = (Decimal("10000"), Decimal("1000"), 36, date(2025, 1, 15))
    assert depreciation(*args, date(2025, 1, 31))["accumulated"] == "0.00"
    assert depreciation(*args, date(2025, 2, 1))["accumulated"] == "250.00"
    assert depreciation(*args, date(2030, 1, 1))["book_value"] == "1000.00"
    assert depreciation(*args, date(2024, 1, 1))["months"] == 0
    assert (
        depreciation(
            Decimal("100"), Decimal("0"), 3, date(2025, 1, 1), date(2025, 4, 1)
        )["accumulated"]
        == "100.00"
    )


async def project(client, auth, code="TEST-1"):
    response = await client.post(
        "/api/v1/projetos",
        headers=auth,
        json={
            "code": code,
            "name": "Projeto Atlas",
            "customer": "Atlas Software",
            "budget": "20000.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_project_billing_atomic_idempotent_and_rbac(
    auth_client, ctx, seeded, factory
):
    auth = headers(await login(auth_client, ctx))
    p = await project(auth_client, auth)
    url = f"/api/v1/projetos/{p['id']}"
    body = {
        "description": "Marco de implantação",
        "amount": "7500.00",
        "due_date": str(business_today()),
    }
    key = {"Idempotency-Key": str(uuid4())}
    assert (
        await auth_client.post(url + "/entregas", headers=auth | key, json=body)
    ).status_code == 409
    r = await auth_client.patch(
        url + "/status",
        headers=auth,
        json={"version": p["version"], "status": "em_execucao"},
    )
    assert r.status_code == 200, r.text
    allocation = {
        "description": "Implementação de integração",
        "worked_on": str(business_today()),
        "hours": "8.50",
        "hourly_cost": "120.00",
    }
    hkey = {"Idempotency-Key": str(uuid4())}
    for _ in range(2):
        r = await auth_client.post(url + "/horas", headers=auth | hkey, json=allocation)
        assert r.status_code == 201, r.text
    ids = []
    for _ in range(2):
        r = await auth_client.post(url + "/entregas", headers=auth | key, json=body)
        assert r.status_code == 201, r.text
        ids.append(r.json()["cash_entry_id"])
    assert ids[0] == ids[1]
    assert (
        await auth_client.post(
            url + "/entregas", headers=auth | key, json=body | {"amount": "7501.00"}
        )
    ).status_code == 409
    rows = (await auth_client.get("/api/v1/projetos", headers=auth)).json()["items"]
    assert Decimal(rows[0]["cost"]) == 1020 and Decimal(rows[0]["hours"]) == Decimal(
        "8.5"
    )
    async with factory(info={"audit_context": ctx}) as session:
        cash = await session.scalar(
            select(CashEntry).where(CashEntry.id == UUID(ids[0]))
        )
        assert cash.status == "aguardando_aprovacao" and cash.kind == "receita"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(Delivery.project_id == UUID(p["id"]))
            )
            == 1
        )
    seller = headers(await login(auth_client, ctx, "vendedor@enterprise.com"))
    assert (
        await auth_client.get("/api/v1/projetos", headers=seller)
    ).status_code == 403
    assert (
        await auth_client.post(
            f"/api/v1/projetos/{uuid4()}/entregas",
            headers=auth | {"Idempotency-Key": str(uuid4())},
            json=body,
        )
    ).status_code == 409


async def test_asset_ownership_maintenance_soft_delete(
    auth_client, ctx, seeded, factory
):
    auth = headers(await login(auth_client, ctx))
    employee = await auth_client.post(
        "/api/v1/rh/colaboradores",
        headers=auth,
        json={
            "registration": "ASSET-1",
            "name": "Ana Souza",
            "department": "Produto",
            "job_title": "Analista",
            "base_salary": "5000.00",
            "hired_on": "2020-01-01",
            "is_active": True,
        },
    )
    assert employee.status_code == 201, employee.text
    body = {
        "tag": "PAT-01",
        "name": "Notebook de trabalho",
        "category": "Equipamentos",
        "cost": "10000.00",
        "residual": "1000.00",
        "life_months": 36,
        "service_on": "2025-01-15",
    }
    result = await auth_client.post("/api/v1/ativos", headers=auth, json=body)
    assert result.status_code == 201, result.text
    asset = result.json()
    url = f"/api/v1/ativos/{asset['id']}"
    assert (
        await auth_client.put(
            url + "/posse",
            headers=auth,
            json={"version": asset["version"], "employee_id": str(uuid4())},
        )
    ).status_code == 409
    assigned = await auth_client.put(
        url + "/posse",
        headers=auth,
        json={"version": asset["version"], "employee_id": employee.json()["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    version = assigned.json()["version"]
    assert (
        await auth_client.delete(url, headers=auth, params={"version": version})
    ).status_code == 409
    key = {"Idempotency-Key": str(uuid4())}
    maintenance = {
        "description": "Limpeza preventiva",
        "performed_on": str(business_today()),
        "cost": "120.00",
    }
    for _ in range(2):
        assert (
            await auth_client.post(
                url + "/manutencoes", headers=auth | key, json=maintenance
            )
        ).status_code == 201
    assert (
        len((await auth_client.get(url + "/manutencoes", headers=auth)).json()["items"])
        == 1
    )
    cleared = await auth_client.put(
        url + "/posse", headers=auth, json={"version": version, "employee_id": None}
    )
    assert cleared.status_code == 200, cleared.text
    assert (
        await auth_client.delete(
            url, headers=auth, params={"version": cleared.json()["version"]}
        )
    ).status_code == 204
    assert (await auth_client.get("/api/v1/ativos", headers=auth)).json()["total"] == 0
    assert (
        await auth_client.post("/api/v1/ativos", headers=auth, json=body)
    ).status_code == 409
    async with factory(info={"audit_context": ctx}) as session:
        logs = list(
            await session.scalars(
                select(AuditLog).where(AuditLog.entity_id == UUID(asset["id"]))
            )
        )
        assert any(r.operation == "DELETE" for r in logs)


async def test_cockpit_scope_and_continuous_demo(auth_client, ctx, seeded):
    admin = headers(await login(auth_client, ctx))
    response = await auth_client.get("/api/v1/cockpit?source=demo", headers=admin)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["stock"]["critical"] >= 2
        and data["projects"]
        and data["assets"]["count"] == 6
    )
    assert len(data["audit"]) == 5 and data["people"] and data["fiscal"]
    for p in data["cash"]["points"]:
        assert Decimal(p["income"]) > 0 and Decimal(p["expense"]) > 0
    sales = headers(await login(auth_client, ctx, "vendedor@enterprise.com"))
    result = (
        await auth_client.get("/api/v1/cockpit?source=demo", headers=sales)
    ).json()
    assert result["sales"] is not None and result["stock"] is not None
    assert all(
        result[k] is None
        for k in [
            "cash",
            "fiscal",
            "people",
            "audit",
            "projects",
            "assets",
            "purchases",
            "approvals",
        ]
    )
    assert (await auth_client.get("/api/v1/cockpit", headers=admin)).json()["sales"][
        "revenue"
    ] == "0.00"


async def test_archive_project_preserves_audit(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx))
    p = await project(auth_client, auth)
    assert (
        await auth_client.delete(
            f"/api/v1/projetos/{p['id']}",
            headers=auth,
            params={"version": p["version"]},
        )
    ).status_code == 204
    assert (await auth_client.get("/api/v1/projetos", headers=auth)).json()[
        "total"
    ] == 0
    assert (
        await auth_client.post(
            "/api/v1/projetos",
            headers=auth,
            json={
                "code": "TEST-1",
                "name": "Outro projeto",
                "customer": "Cliente",
                "budget": "0.00",
            },
        )
    ).status_code == 409


async def test_cross_tenant_enterprise_references_are_rejected(
    auth_client, ctx, seeded, factory
):
    from dataclasses import replace
    from erp.shared.infrastructure.database.seed import populate
    from test_auth_seed import options

    other = replace(ctx, tenant_id=uuid4())
    await populate(factory, options(other, demo=False))
    auth = headers(await login(auth_client, ctx))
    other_auth = headers(await login(auth_client, other))
    p = await project(auth_client, auth)
    assert (
        await auth_client.get(
            f"/api/v1/projetos/{p['id']}/historico", headers=other_auth
        )
    ).status_code == 404
    result = await auth_client.patch(
        f"/api/v1/projetos/{p['id']}/status",
        headers=other_auth,
        json={"version": p["version"], "status": "em_execucao"},
    )
    assert result.status_code == 409
    assert (await auth_client.get("/api/v1/projetos", headers=other_auth)).json()[
        "total"
    ] == 0
    result = await auth_client.get("/api/v1/cockpit?source=demo", headers=other_auth)
    assert result.status_code == 200 and result.json()["assets"]["count"] == 0
