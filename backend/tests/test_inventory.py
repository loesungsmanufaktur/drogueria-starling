from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import store_today
from app.models import AuditLog, Role, StockMovement
from app.services import inventory
from tests.factories import auth, make_lot, make_product, make_user


async def test_rule2_opening_stock_creates_lot_and_movement(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    product = await make_product(session)
    resp = await client.post(
        "/api/v1/inventory/lots",
        headers=auth(pharmacist),
        json={
            "product_id": product.id,
            "lot_number": "A-1",
            "expiry_date": str(store_today() + timedelta(days=200)),
            "quantity": 40,
            "unit_cost": "5.00",
            "reason": "Inventario inicial",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["quantity"] == 40
    stock = (await client.get(f"/api/v1/products/{product.id}", headers=auth(pharmacist))).json()
    assert stock["stock"] == 40
    movements = (await session.execute(select(StockMovement))).scalars().all()
    assert [(m.type.value, m.quantity) for m in movements] == [("adjustment", 40)]


async def test_rule1_adjustment_cannot_make_stock_negative(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    lot = await make_lot(session, await make_product(session), 3)
    resp = await client.post(
        "/api/v1/inventory/adjustments",
        headers=auth(pharmacist),
        json={"lot_id": lot.id, "quantity": -4, "reason": "Conteo físico"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "INSUFFICIENT_STOCK"


async def test_rule1_database_rejects_negative_lot_quantity(session: AsyncSession) -> None:
    lot = await make_lot(session, await make_product(session), 2)
    with pytest.raises(DBAPIError, match="quantity_non_negative"):
        await session.execute(
            text(
                "INSERT INTO stock_movements (product_id, lot_id, type, quantity) "
                f"VALUES ({lot.product_id}, {lot.id}, 'adjustment', -3)"
            )
        )
    await session.rollback()


async def test_rule5_lot_quantity_changes_only_through_movements(session: AsyncSession) -> None:
    lot = await make_lot(session, await make_product(session), 2)
    lot_id, product_id = lot.id, lot.product_id
    with pytest.raises(DBAPIError, match="only through stock_movements"):
        await session.execute(text(f"UPDATE lots SET quantity = 99 WHERE id = {lot_id}"))
    await session.rollback()
    with pytest.raises(DBAPIError, match="lots start empty"):
        await session.execute(
            text(
                "INSERT INTO lots (product_id, lot_number, expiry_date, quantity, unit_cost) "
                f"VALUES ({product_id}, 'X', '2099-01-01', 5, 1)"
            )
        )
    await session.rollback()


async def test_rule5_movements_are_append_only(session: AsyncSession) -> None:
    await make_lot(session, await make_product(session), 2)
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(text("UPDATE stock_movements SET quantity = 50"))
    await session.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(text("DELETE FROM stock_movements"))
    await session.rollback()


async def test_rule6_adjustments_need_pharmacist_and_reason(
    client: AsyncClient, session: AsyncSession
) -> None:
    cashier = await make_user(session, Role.CASHIER)
    pharmacist = await make_user(session, Role.PHARMACIST)
    lot = await make_lot(session, await make_product(session), 5)
    body = {"lot_id": lot.id, "quantity": -1, "reason": "Producto dañado"}

    denied = await client.post("/api/v1/inventory/adjustments", headers=auth(cashier), json=body)
    assert denied.status_code == 403

    no_reason = await client.post(
        "/api/v1/inventory/adjustments",
        headers=auth(pharmacist),
        json={**body, "reason": ""},
    )
    assert no_reason.status_code == 422

    ok = await client.post("/api/v1/inventory/adjustments", headers=auth(pharmacist), json=body)
    assert ok.status_code == 201
    assert ok.json()["user_id"] == pharmacist.id


async def test_rule6_write_off_only_expired_lots(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    product = await make_product(session)
    fresh = await make_lot(session, product, 5)
    expired = await make_lot(session, product, 4, expiry=store_today())
    h = auth(pharmacist)
    body = {"reason": "Vencido"}

    resp = await client.post(f"/api/v1/inventory/lots/{fresh.id}/write-off", headers=h, json=body)
    assert resp.json()["code"] == "LOT_NOT_EXPIRED"

    resp = await client.post(f"/api/v1/inventory/lots/{expired.id}/write-off", headers=h, json=body)
    assert resp.status_code == 201
    assert resp.json()["quantity"] == -4
    assert resp.json()["type"] == "expiry_write_off"


async def test_rule3_rule4_allocation_is_fefo_and_skips_expired(session: AsyncSession) -> None:
    product = await make_product(session)
    await make_lot(session, product, 10, expiry=store_today())  # expires today: not sellable
    late = await make_lot(session, product, 10, days=300)
    early = await make_lot(session, product, 3, days=30)

    expected = [(early.id, 3), (late.id, 2)]
    allocations = await inventory.allocate(session, product, 5)
    assert [(a.lot.id, a.quantity) for a in allocations] == expected
    await session.rollback()

    await session.refresh(product)
    with pytest.raises(inventory.InsufficientStock):
        await inventory.allocate(session, product, 14)
    await session.rollback()


async def test_rule3_explicit_expired_lot_cannot_be_sold(session: AsyncSession) -> None:
    product = await make_product(session)
    expired = await make_lot(session, product, 5, expiry=store_today() - timedelta(days=1))
    with pytest.raises(inventory.AppError) as err:
        await inventory.allocate(session, product, 1, lot_id=expired.id)
    assert err.value.code == "LOT_EXPIRED"
    await session.rollback()


async def test_rule20_movements_are_audited(client: AsyncClient, session: AsyncSession) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    lot = await make_lot(session, await make_product(session), 5)
    await client.post(
        "/api/v1/inventory/adjustments",
        headers=auth(pharmacist),
        json={"lot_id": lot.id, "quantity": 2, "reason": "Conteo físico"},
    )
    entries = (
        (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "stock_movements", AuditLog.user_id == pharmacist.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 1
