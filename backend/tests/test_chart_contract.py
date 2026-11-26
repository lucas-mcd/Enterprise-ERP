"""Regression contract for UI date parsing, using PostgreSQL and the actual seed."""

from datetime import date, datetime
import re

from test_auth_seed import headers, login
from test_financeiro import parameters

pytest_plugins = ["test_auth_seed"]


def assert_daily_points(points):
    assert points
    for point in points:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", point["day"])
        assert date.fromisoformat(point["day"]).isoformat() == point["day"]
        for key in ("income", "expense", "pending_income", "pending_expense"):
            assert re.fullmatch(r"-?\d+\.\d{2}", point[key])


async def test_seed_chart_date_contract(auth_client, ctx, seeded):
    auth = headers(await login(auth_client, ctx))
    cash = await auth_client.get(
        "/api/v1/financeiro/fluxo-caixa", params=parameters("demo"), headers=auth
    )
    assert cash.status_code == 200, cash.text
    assert_daily_points(cash.json()["points"])
    cockpit = await auth_client.get("/api/v1/cockpit?source=demo", headers=auth)
    assert cockpit.status_code == 200, cockpit.text
    data = cockpit.json()
    assert_daily_points(data["cash"]["points"])
    assert datetime.fromisoformat(data["updated_at"]).utcoffset() is not None
    for record in data["audit"]:
        assert datetime.fromisoformat(record["date"]).utcoffset() is not None
    bi = await auth_client.get(
        "/api/v1/bi/overview", params=parameters("demo"), headers=auth
    )
    assert bi.status_code == 200, bi.text
    assert bi.json()["budgets"]
    for budget in bi.json()["budgets"]:
        assert re.fullmatch(r"\d{4}-\d{2}", budget["month"])
