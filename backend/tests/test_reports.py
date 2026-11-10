from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import store_today
from app.models import Register, RegisterShift, Role
from app.services import reports
from tests.factories import approval, auth, make_lot, make_product, make_user


def test_rule23_business_day_uses_store_timezone() -> None:
    # Guatemala is UTC-6 all year: the store day starts at 06:00 UTC.
    start, end = reports.day_bounds(date(2026, 3, 10))
    assert start == datetime(2026, 3, 10, 6, 0, tzinfo=UTC)
    assert end - start == timedelta(days=1)


async def test_daily_sales_excludes_voids_and_subtracts_returns(
    client: AsyncClient, session: AsyncSession
) -> None:
    register = Register(code="R1", name="Caja")
    session.add(register)
    cashier = await make_user(session, Role.CASHIER)
    pharmacist = await make_user(session, Role.PHARMACIST)
    session.add(RegisterShift(register_id=register.id, user_id=cashier.id, opening_cash=Decimal(0)))
    await session.commit()
    product = await make_product(session, price="10.00", cost="1.00")
    await make_lot(session, product, 20)
    h = auth(cashier)

    async def sell(qty: int, method: str = "cash") -> dict:  # type: ignore[type-arg]
        resp = await client.post(
            "/api/v1/sales",
            headers=h,
            json={
                "register_id": register.id,
                "lines": [{"product_id": product.id, "quantity": qty}],
                "payments": [{"method": method, "amount": f"{qty * 10}.00"}],
            },
        )
        return resp.json()  # type: ignore[no-any-return]

    kept = await sell(2)
    await sell(3, "card")
    voided = await sell(1)
    await client.post(
        f"/api/v1/sales/{voided['id']}/void",
        headers={**h, **approval(pharmacist)},
        json={"reason": "Error"},
    )
    await client.post(
        f"/api/v1/sales/{kept['id']}/returns",
        headers=h,
        json={
            "reason": "Devuelto",
            "lines": [{"sale_line_id": kept["lines"][0]["id"], "quantity": 1}],
        },
    )

    report = (await client.get("/api/v1/reports/daily-sales", headers=auth(pharmacist))).json()
    assert report["sales_count"] == 2
    assert report["gross_total"] == "50.00"
    assert report["voided_count"] == 1
    assert report["returns_total"] == "10.00"
    assert report["net_total"] == "40.00"
    assert report["by_payment_method"] == [
        {"method": "card", "amount": "30.00"},
        {"method": "cash", "amount": "20.00"},
    ]


async def test_expiring_low_stock_and_daily_alerts(
    client: AsyncClient, session: AsyncSession
) -> None:
    admin = await make_user(session, Role.ADMIN)
    h = auth(admin)
    product = await make_product(session, name="Amoxicilina", min_stock=10)
    await make_lot(session, product, 3, days=30)
    await make_lot(session, product, 2, expiry=store_today())
    await make_lot(session, product, 50, days=400)  # outside the 90-day window
    other = await make_product(session, name="Loratadina", min_stock=5)
    await make_lot(session, other, 1, days=400)

    expiring = (await client.get("/api/v1/reports/expiring", headers=h)).json()
    assert [(e["quantity"], e["expired"]) for e in expiring] == [(2, True), (3, False)]

    low = (await client.get("/api/v1/reports/low-stock", headers=h)).json()
    assert [r["product_name"] for r in low] == ["Loratadina"]

    valuation = (await client.get("/api/v1/reports/stock-valuation", headers=h)).json()
    assert valuation["total_value"] == "336.00"  # 56 units x 6.00

    first = await client.post("/api/v1/alerts/run", headers=h)
    assert first.json() == {"created": 3}
    again = await client.post("/api/v1/alerts/run", headers=h)
    assert again.json() == {"created": 0}  # idempotent per day

    alerts = (await client.get("/api/v1/alerts", headers=h)).json()
    assert {a["type"] for a in alerts} == {"expired", "expiring", "low_stock"}
    ack = await client.post(f"/api/v1/alerts/{alerts[0]['id']}/acknowledge", headers=h)
    assert ack.json()["acknowledged_by"] == admin.id
    assert len((await client.get("/api/v1/alerts", headers=h)).json()) == 2


async def test_cashier_cannot_read_reports(client: AsyncClient, session: AsyncSession) -> None:
    cashier = await make_user(session, Role.CASHIER)
    resp = await client.get("/api/v1/reports/daily-sales", headers=auth(cashier))
    assert resp.status_code == 403
