from datetime import timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import store_today
from app.models import Lot, Product, Role, StockMovement
from tests.factories import auth, make_product, make_user


async def _order(client: AsyncClient, h: dict[str, str], product: Product, qty: int = 10) -> Any:
    supplier = await client.post("/api/v1/suppliers", headers=h, json={"name": "Distribuidora"})
    order = await client.post(
        "/api/v1/purchase-orders",
        headers=h,
        json={
            "supplier_id": supplier.json()["id"],
            "lines": [{"product_id": product.id, "quantity": qty, "unit_cost": "4.50"}],
        },
    )
    assert order.status_code == 201, order.text
    return order.json()


def _expiry(days: int) -> str:
    return str(store_today() + timedelta(days=days))


async def test_goods_receipt_creates_lots_and_purchase_movements(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    h = auth(pharmacist)
    product = await make_product(session, cost="3.00")
    order = await _order(client, h, product)
    line_id = order["lines"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchase-orders/{order['id']}/receive",
        headers=h,
        json={
            "lines": [
                {"line_id": line_id, "lot_number": "A1", "expiry_date": _expiry(90), "quantity": 6},
                {
                    "line_id": line_id,
                    "lot_number": "B2",
                    "expiry_date": _expiry(400),
                    "quantity": 4,
                    "unit_cost": "4.80",
                },
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "received"
    assert body["lines"][0]["received_quantity"] == 10

    lots = (await session.execute(select(Lot).order_by(Lot.lot_number))).unique().scalars().all()
    assert [(lot.lot_number, lot.quantity) for lot in lots] == [("A1", 6), ("B2", 4)]
    movements = (await session.execute(select(StockMovement))).scalars().all()
    assert {m.type.value for m in movements} == {"purchase"}
    assert {m.reference_id for m in movements} == {order["id"]}

    await session.refresh(product)
    assert str(product.cost) == "4.80"

    again = await client.post(
        f"/api/v1/purchase-orders/{order['id']}/receive",
        headers=h,
        json={
            "lines": [
                {"line_id": line_id, "lot_number": "C", "expiry_date": _expiry(90), "quantity": 1}
            ]
        },
    )
    assert again.json()["code"] == "PURCHASE_ORDER_NOT_DRAFT"


async def test_receipt_rejects_expired_lot_and_over_receipt_atomically(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    h = auth(pharmacist)
    product = await make_product(session)
    order = await _order(client, h, product, qty=5)
    line_id = order["lines"][0]["id"]
    url = f"/api/v1/purchase-orders/{order['id']}/receive"

    expired = await client.post(
        url,
        headers=h,
        json={
            "lines": [
                {"line_id": line_id, "lot_number": "X", "expiry_date": _expiry(0), "quantity": 1}
            ]
        },
    )
    assert expired.json()["code"] == "RECEIVING_EXPIRED_LOT"

    over = await client.post(
        url,
        headers=h,
        json={
            "lines": [
                {"line_id": line_id, "lot_number": "X", "expiry_date": _expiry(30), "quantity": 6}
            ]
        },
    )
    assert over.json()["code"] == "RECEIVED_EXCEEDS_ORDERED"
    assert (await session.execute(select(StockMovement))).first() is None


async def test_cashier_cannot_purchase(client: AsyncClient, session: AsyncSession) -> None:
    cashier = await make_user(session, Role.CASHIER)
    resp = await client.get("/api/v1/purchase-orders", headers=auth(cashier))
    assert resp.status_code == 403


async def test_cancelled_order_cannot_be_received(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    h = auth(pharmacist)
    order = await _order(client, h, await make_product(session))
    await client.post(f"/api/v1/purchase-orders/{order['id']}/cancel", headers=h)
    resp = await client.post(
        f"/api/v1/purchase-orders/{order['id']}/receive",
        headers=h,
        json={
            "lines": [
                {
                    "line_id": order["lines"][0]["id"],
                    "lot_number": "X",
                    "expiry_date": _expiry(30),
                    "quantity": 1,
                }
            ]
        },
    )
    assert resp.json()["code"] == "PURCHASE_ORDER_NOT_DRAFT"
