from uuid import uuid4
from datetime import timedelta
from erp.config import settings
from erp.modules.financeiro.domain.cash import business_today
from test_auth_seed import login, headers

pytest_plugins = ["test_auth_seed"]


async def test_refresh_rotation_replay_logout_origin(
    auth_client, ctx, seeded, monkeypatch
):
    monkeypatch.setenv("REFRESH_COOKIE_SECURE", "false")
    settings.cache_clear()
    first = await login(auth_client, ctx)
    assert first.status_code == 200
    original = auth_client.cookies.get("erp_refresh")
    assert "HttpOnly" in first.headers["set-cookie"] and original
    assert (await auth_client.post("/api/v1/identity/auth/refresh")).status_code == 403
    assert (
        await auth_client.post(
            "/api/v1/identity/auth/refresh",
            headers={"X-ERP-Refresh": "1", "Origin": "https://evil.example"},
        )
    ).status_code == 403
    refreshed = await auth_client.post(
        "/api/v1/identity/auth/refresh", headers={"X-ERP-Refresh": "1"}
    )
    assert refreshed.status_code == 200, refreshed.text
    assert original != auth_client.cookies.get("erp_refresh")
    replay = await auth_client.post(
        "/api/v1/identity/auth/refresh",
        headers={"X-ERP-Refresh": "1", "Cookie": f"erp_refresh={original}"},
    )
    assert replay.status_code == 401
    assert (
        await auth_client.get("/api/v1/identity/me", headers=headers(refreshed))
    ).status_code == 401
    again = await login(auth_client, ctx)
    assert (
        await auth_client.post("/api/v1/identity/auth/logout", headers=headers(again))
    ).status_code == 204
    assert (
        await auth_client.post(
            "/api/v1/identity/auth/refresh", headers={"X-ERP-Refresh": "1"}
        )
    ).status_code == 401


async def test_crm_credit_conversion_idempotency(auth_client, ctx, seeded):
    h = headers(await login(auth_client, ctx))
    customer = await auth_client.post(
        "/api/v1/crm/clientes",
        headers=h,
        json={
            "name": "Cliente real",
            "document": "11222333000181",
            "segment": "TI",
            "email": "cliente@example.com",
            "credit_limit": "500.00",
        },
    )
    assert customer.status_code == 201, customer.text
    product = await auth_client.post(
        "/api/v1/estoque/produtos",
        headers=h,
        json={"sku": "CRM-REAL", "name": "Produto CRM", "category": "TI", "minimum": 2},
    )
    assert product.status_code == 201, product.text

    async def opportunity():
        body = {
            "title": "Proposta real",
            "customer_id": customer.json()["id"],
            "expected_on": (business_today() + timedelta(days=5)).isoformat(),
            "items": [
                {
                    "product_id": product.json()["id"],
                    "quantity": 1,
                    "unit_price": "400.00",
                }
            ],
        }
        key = str(uuid4())
        response = await auth_client.post(
            "/api/v1/crm/oportunidades", headers=h | {"Idempotency-Key": key}, json=body
        )
        assert response.status_code == 201, response.text
        retry = await auth_client.post(
            "/api/v1/crm/oportunidades", headers=h | {"Idempotency-Key": key}, json=body
        )
        assert retry.json()["id"] == response.json()["id"]
        row = response.json()
        for stage in ("proposta", "negociacao"):
            moved = await auth_client.patch(
                f"/api/v1/crm/oportunidades/{row['id']}/etapa",
                headers=h,
                json={"version": row["version"], "stage": stage},
            )
            assert moved.status_code == 200, moved.text
            row = moved.json()
        return row

    row = await opportunity()
    converted = await auth_client.post(
        f"/api/v1/crm/oportunidades/{row['id']}/converter",
        headers=h,
        json={"version": row["version"]},
    )
    assert converted.status_code == 200, converted.text
    retry = await auth_client.post(
        f"/api/v1/crm/oportunidades/{row['id']}/converter",
        headers=h,
        json={"version": row["version"]},
    )
    assert retry.json()["order_id"] == converted.json()["order_id"]
    second = await opportunity()
    denied = await auth_client.post(
        f"/api/v1/crm/oportunidades/{second['id']}/converter",
        headers=h,
        json={"version": second["version"]},
    )
    assert denied.status_code == 409 and "crédito" in denied.text


async def test_banking_cost_center_atomic_idempotent_match(auth_client, ctx, seeded):
    h = headers(await login(auth_client, ctx))
    centers = await auth_client.get("/api/v1/financeiro/centros-custo", headers=h)
    assert centers.status_code == 200 and len(centers.json()) == 4
    today = business_today().isoformat()
    entry = await auth_client.post(
        "/api/v1/financeiro/lancamentos",
        headers=h | {"Idempotency-Key": str(uuid4())},
        json={
            "description": "Recebimento real",
            "counterparty": "Cliente",
            "category": "Vendas",
            "kind": "receita",
            "status": "pendente",
            "amount": "1250.50",
            "due_date": today,
            "cost_center_id": centers.json()[0]["id"],
        },
    )
    assert entry.status_code == 201, entry.text
    body = {
        "account": "Conta teste",
        "reference": "EXTRATO-001",
        "entries": [
            {
                "external_id": "FITID-1",
                "posted_on": today,
                "description": "Crédito cliente",
                "amount": "1250.50",
            }
        ],
    }
    imported = await auth_client.post(
        "/api/v1/financeiro/conciliacao/importar", headers=h, json=body
    )
    assert imported.status_code == 201, imported.text
    retry = await auth_client.post(
        "/api/v1/financeiro/conciliacao/importar", headers=h, json=body
    )
    assert retry.json()["id"] == imported.json()["id"]
    movements = (
        await auth_client.get("/api/v1/financeiro/conciliacao/movimentos", headers=h)
    ).json()["items"]
    path = f"/api/v1/financeiro/conciliacao/movimentos/{movements[0]['id']}"
    candidates = await auth_client.get(path + "/candidatos", headers=h)
    assert (
        candidates.status_code == 200
        and candidates.json()[0]["id"] == entry.json()["id"]
    )
    for _ in range(2):
        matched = await auth_client.post(
            path + "/conciliar", headers=h, json={"cash_entry_id": entry.json()["id"]}
        )
        assert matched.status_code == 200, matched.text
    result = await auth_client.get(
        "/api/v1/financeiro/lancamentos",
        params={"start_date": today, "end_date": today, "source": "real"},
        headers=h,
    )
    assert result.json()["items"][0]["status"] == "concluido"
    assert result.json()["items"][0]["cost_center_id"] == centers.json()[0]["id"]


async def test_alerts_demo_and_permissions(auth_client, ctx, seeded):
    h = headers(await login(auth_client, ctx))
    for path in (
        "crm/clientes",
        "crm/oportunidades",
        "financeiro/conciliacao/movimentos",
    ):
        response = await auth_client.get(f"/api/v1/{path}?source=demo", headers=h)
        assert response.status_code == 200 and response.json()["total"] > 0
    assert (await auth_client.get("/api/v1/notificacoes", headers=h)).json()[
        "total"
    ] == 0
    product = await auth_client.post(
        "/api/v1/estoque/produtos",
        headers=h,
        json={"sku": "LOW", "name": "Estoque crítico", "category": "TI", "minimum": 2},
    )
    assert product.status_code == 201
    assert (await auth_client.get("/api/v1/notificacoes", headers=h)).json()[
        "total"
    ] == 1
    sales = headers(await login(auth_client, ctx, email="vendedor@enterprise.com"))
    assert (
        await auth_client.get(
            "/api/v1/financeiro/conciliacao/movimentos", headers=sales
        )
    ).status_code == 403


async def test_direct_credit_cancel_and_legacy_retry(auth_client, ctx, seeded):
    h = headers(await login(auth_client, ctx))
    customer = await auth_client.post(
        "/api/v1/crm/clientes",
        headers=h,
        json={
            "name": "Aurora teste",
            "document": "11222333000181",
            "segment": "Distribuição",
            "email": "compras@example.com",
            "credit_limit": "600.00",
        },
    )
    product = await auth_client.post(
        "/api/v1/estoque/produtos",
        headers=h,
        json={"sku": "KIT-C", "name": "Kit crédito", "category": "Peças", "minimum": 1},
    )
    today = business_today().isoformat()
    item = {"product_id": product.json()["id"], "quantity": 3, "unit_price": "200.00"}
    body = {
        "lines": [item],
        "counterparty": "Aurora teste",
        "ordered_on": today,
        "due_date": today,
    }
    key = h | {"Idempotency-Key": str(uuid4())}
    order = await auth_client.post("/api/v1/vendas/pedidos", headers=key, json=body)
    assert order.status_code == 201, order.text
    retry = await auth_client.post("/api/v1/vendas/pedidos", headers=key, json=body)
    assert retry.json()["id"] == order.json()["id"]
    linked = {**body, "customer_id": customer.json()["id"]}
    denied = await auth_client.post(
        "/api/v1/vendas/pedidos",
        headers=h | {"Idempotency-Key": str(uuid4())},
        json=linked,
    )
    assert denied.status_code == 409 and "crédito" in denied.text
    path = "/api/v1/vendas/pedidos/" + order.json()["id"]
    assert (await auth_client.post(path + "/cancelar", headers=h)).json()[
        "status"
    ] == "cancelled"
    assert (await auth_client.post(path + "/concluir", headers=h)).status_code == 409
    allowed = await auth_client.post(
        "/api/v1/vendas/pedidos",
        headers=h | {"Idempotency-Key": str(uuid4())},
        json=linked,
    )
    assert allowed.status_code == 201, allowed.text
    detail = (
        await auth_client.get(
            "/api/v1/vendas/pedidos/" + allowed.json()["id"], headers=h
        )
    ).json()
    assert detail["items"] == [
        {"sku": "KIT-C", "name": "Kit crédito", "quantity": 3, "unit_price": "200.00"}
    ]


async def test_supplier_reuse_and_opportunity_revision(auth_client, ctx, seeded):
    h = headers(await login(auth_client, ctx))
    product = await auth_client.post(
        "/api/v1/estoque/produtos",
        headers=h,
        json={"sku": "PECA", "name": "Peça azul", "category": "Peças", "minimum": 0},
    )
    today = business_today().isoformat()
    line = {"product_id": product.json()["id"], "unit_price": "50.00", "quantity": 2}
    suppliers = []
    for name in ("Peças Ltda", "PEÇAS LTDA"):
        result = await auth_client.post(
            "/api/v1/compras/pedidos",
            json={
                "counterparty": name,
                "ordered_on": today,
                "due_date": today,
                "lines": [line],
            },
            headers=h | {"Idempotency-Key": str(uuid4())},
        )
        assert result.status_code == 201, result.text
        suppliers.append(result.json()["supplier_id"])
    assert suppliers[0] == suppliers[1] and suppliers[0]
    customer = await auth_client.post(
        "/api/v1/crm/clientes",
        headers=h,
        json={
            "name": "Beta",
            "document": "11222333000181",
            "segment": "TI",
            "email": "beta@example.com",
            "credit_limit": "500.00",
        },
    )
    path = "/api/v1/crm/oportunidades"
    body = {
        "title": "Projeto Beta",
        "expected_on": today,
        "customer_id": customer.json()["id"],
        "items": [line],
    }
    excessive = await auth_client.post(
        path,
        headers=h | {"Idempotency-Key": str(uuid4())},
        json={**body, "items": [line] * 51},
    )
    assert excessive.status_code == 422
    row = (
        await auth_client.post(
            path, headers=h | {"Idempotency-Key": str(uuid4())}, json=body
        )
    ).json()
    revised = await auth_client.patch(
        f"{path}/{row['id']}/revisar",
        headers=h,
        json={
            "version": row["version"],
            "expected_on": (business_today() + timedelta(days=3)).isoformat(),
        },
    )
    assert revised.status_code == 200
    lost = await auth_client.patch(
        f"{path}/{row['id']}/revisar",
        headers=h,
        json={"version": revised.json()["version"], "loss_reason": "Prazo do cliente"},
    )
    assert lost.json()["stage"] == "perdido"
    assert (
        await auth_client.post(
            f"{path}/{row['id']}/converter",
            headers=h,
            json={"version": lost.json()["version"]},
        )
    ).status_code == 409
