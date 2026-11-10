import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import store_today
from app.models import (
    AuditLog,
    Customer,
    Lot,
    Product,
    Register,
    RegisterShift,
    Role,
    Sale,
    ShiftStatus,
    StockMovement,
    User,
)
from tests.factories import CARD, approval, auth, make_lot, make_product, make_user

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@dataclass
class Pos:
    register: Register
    cashier: User
    pharmacist: User
    admin: User
    shift: RegisterShift

    @property
    def h(self) -> dict[str, str]:
        return auth(self.cashier)


@pytest.fixture
async def pos(session: AsyncSession) -> Pos:
    register = Register(code="C1", name="Caja 1")
    session.add(register)
    cashier = await make_user(session, Role.CASHIER)
    pharmacist = await make_user(session, Role.PHARMACIST)
    admin = await make_user(session, Role.ADMIN)
    shift = RegisterShift(
        register_id=register.id, user_id=cashier.id, opening_cash=Decimal("100.00")
    )
    session.add(shift)
    await session.commit()
    return Pos(register, cashier, pharmacist, admin, shift)


def sale(pos: Pos, lines: list[dict[str, Any]], total: str | None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"register_id": pos.register.id, "lines": lines, **extra}
    if total is not None and "payments" not in extra:
        body["payments"] = [{"method": "cash", "amount": total}]
    return body


async def checkout(
    client: AsyncClient, pos: Pos, body: dict[str, Any], headers: dict[str, str] | None = None
) -> Any:
    return await client.post("/api/v1/sales", headers={**pos.h, **(headers or {})}, json=body)


# --- happy path, pricing and receipts --------------------------------------


async def test_checkout_prices_taxes_and_change(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="11.20", tax_rate="12.00")
    await make_lot(session, product, 10)
    resp = await checkout(
        client,
        pos,
        sale(
            pos,
            [{"product_id": product.id, "quantity": 3, "discount_percent": "5"}],
            None,
            payments=[{"method": "cash", "amount": "31.92"}],
            cash_tendered="50.00",
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 3 x 11.20 = 33.60; 5% = 1.68 → 31.92; IVA incl. = 31.92 * 12/112 = 3.42
    assert body["total"] == "31.92"
    assert body["discount_total"] == "1.68"
    assert body["tax_total"] == "3.42"
    assert body["subtotal"] == "28.50"
    assert body["change_given"] == "18.08"
    assert body["receipt_number"] == 1


async def test_sal1_half_up_rounding_per_line(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="0.25", tax_rate="12.00", cost="0.01")
    await make_lot(session, product, 10)
    # 0.25 * 1 = 0.25; 10% = 0.025 → 0.03 (half-up), total 0.22
    resp = await checkout(
        client,
        pos,
        sale(pos, [{"product_id": product.id, "quantity": 1, "discount_percent": "10"}], "0.22"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["lines"][0]["discount_amount"] == "0.03"


async def test_sal8_receipt_numbers_are_sequential_without_gaps(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    await make_lot(session, product, 2)
    line = [{"product_id": product.id, "quantity": 1}]
    assert (await checkout(client, pos, sale(pos, line, "10.00"))).json()["receipt_number"] == 1
    failed = await checkout(client, pos, sale(pos, [{**line[0], "quantity": 5}], "50.00"))
    assert failed.status_code == 409  # a failed checkout must not burn a number
    assert (await checkout(client, pos, sale(pos, line, "10.00"))).json()["receipt_number"] == 2


# --- stock -----------------------------------------------------------------


async def test_inv1_sal2_short_stock_rejects_whole_sale(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    ok = await make_product(session, price="10.00")
    short = await make_product(session, price="10.00")
    await make_lot(session, ok, 5)
    await make_lot(session, short, 1)
    resp = await checkout(
        client,
        pos,
        sale(
            pos,
            [{"product_id": ok.id, "quantity": 2}, {"product_id": short.id, "quantity": 2}],
            "40.00",
        ),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "INSUFFICIENT_STOCK"
    # Nothing was written: no sale, no movements beyond the test stock.
    assert (await session.execute(select(Sale))).first() is None
    sale_moves = await session.execute(
        select(StockMovement).where(StockMovement.reference_type == "sale")
    )
    assert sale_moves.first() is None


async def test_inv3_inv4_sale_uses_fefo_and_skips_expired(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="5.00", cost="1.00")
    await make_lot(session, product, 10, expiry=store_today())
    late = await make_lot(session, product, 10, days=300)
    early = await make_lot(session, product, 2, days=20)
    resp = await checkout(
        client, pos, sale(pos, [{"product_id": product.id, "quantity": 3}], "15.00")
    )
    assert resp.status_code == 201, resp.text
    lots = resp.json()["lines"][0]["lots"]
    assert lots == [{"lot_id": early.id, "quantity": 2}, {"lot_id": late.id, "quantity": 1}]


async def test_inv4_fefo_override_needs_pharmacist_and_is_audited(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="5.00", cost="1.00")
    await make_lot(session, product, 5, days=20)
    late = await make_lot(session, product, 5, days=300)
    body = sale(pos, [{"product_id": product.id, "quantity": 1, "lot_id": late.id}], "5.00")

    denied = await checkout(client, pos, body)
    assert denied.json()["code"] == "FEFO_OVERRIDE_APPROVAL_REQUIRED"

    ok = await checkout(client, pos, body, approval(pos.pharmacist))
    assert ok.status_code == 201, ok.text
    assert ok.json()["approved_by"] == pos.pharmacist.id
    entry = (
        await session.execute(select(AuditLog).where(AuditLog.action == "fefo_override"))
    ).scalar_one()
    assert entry.after is not None and entry.after["approved_by"] == pos.pharmacist.id


# --- payments, discounts, cost -----------------------------------------------


async def test_sal3_payments_must_equal_total(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    await make_lot(session, product, 5)
    line = [{"product_id": product.id, "quantity": 1}]
    resp = await checkout(client, pos, sale(pos, line, "9.99"))
    assert resp.json()["code"] == "PAYMENT_MISMATCH"
    split = await checkout(
        client,
        pos,
        sale(
            pos,
            line,
            None,
            payments=[
                {"method": "cash", "amount": "4.00"},
                {"method": "card", "amount": "6.00", **CARD},
            ],
            cash_tendered="5.00",
        ),
    )
    assert split.status_code == 201, split.text
    assert split.json()["change_given"] == "1.00"
    assert len(split.json()["payments"]) == 2


async def test_sal7_discount_above_limit_needs_approval(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="100.00", cost="10.00")
    await make_lot(session, product, 5)
    body = sale(pos, [{"product_id": product.id, "quantity": 1, "discount_percent": "20"}], "80.00")
    denied = await checkout(client, pos, body)
    assert denied.status_code == 403
    assert denied.json()["code"] == "DISCOUNT_APPROVAL_REQUIRED"
    ok = await checkout(client, pos, body, approval(pos.pharmacist))
    assert ok.status_code == 201


async def test_sal7_below_cost_needs_admin(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00", cost="9.50")
    await make_lot(session, product, 5)
    body = sale(pos, [{"product_id": product.id, "quantity": 1, "discount_percent": "10"}], "9.00")
    as_pharmacist = await checkout(client, pos, body, approval(pos.pharmacist))
    assert as_pharmacist.json()["code"] == "BELOW_COST_APPROVAL_REQUIRED"
    as_admin = await checkout(client, pos, body, approval(pos.admin))
    assert as_admin.status_code == 201
    assert as_admin.json()["approved_by"] == pos.admin.id


async def test_cashier_cannot_approve_own_discount(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="100.00", cost="1.00")
    await make_lot(session, product, 5)
    body = sale(pos, [{"product_id": product.id, "quantity": 1, "discount_percent": "50"}], "50.00")
    resp = await checkout(client, pos, body, approval(pos.cashier))
    assert resp.status_code == 403


# --- shifts --------------------------------------------------------------------


async def test_sal9_cannot_sell_without_own_open_shift(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    await make_lot(session, product, 5)
    other = await make_user(session, Role.CASHIER)
    resp = await client.post(
        "/api/v1/sales",
        headers=auth(other),
        json=sale(pos, [{"product_id": product.id, "quantity": 1}], "10.00"),
    )
    assert resp.json()["code"] == "NO_OPEN_SHIFT"


async def test_sal9_close_shift_records_difference(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    await make_lot(session, product, 10)
    line = [{"product_id": product.id, "quantity": 2}]
    await checkout(client, pos, sale(pos, line, "20.00"))
    await checkout(
        client, pos, sale(pos, line, None, payments=[{"method": "card", "amount": "20.00", **CARD}])
    )

    current = (await client.get("/api/v1/shifts/current", headers=pos.h)).json()
    assert current["summary"]["expected_cash"] == "120.00"
    assert current["summary"]["sales_total"] == "40.00"

    closed = await client.post(
        f"/api/v1/shifts/{pos.shift.id}/close", headers=pos.h, json={"counted_cash": "115.50"}
    )
    body = closed.json()
    assert body["status"] == "closed"
    assert body["expected_cash"] == "120.00"
    assert body["difference"] == "-4.50"


async def test_only_one_open_shift_per_register(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    other = await make_user(session, Role.CASHIER)
    resp = await client.post(
        "/api/v1/shifts/open",
        headers=auth(other),
        json={"register_id": pos.register.id, "opening_cash": "50.00"},
    )
    assert resp.json()["code"] == "SHIFT_ALREADY_OPEN"


# --- immutability, voids, returns -------------------------------------------------


async def test_sal4_past_sales_keep_their_price(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00", tax_rate="12.00")
    await make_lot(session, product, 5)
    sale_id = (
        await checkout(client, pos, sale(pos, [{"product_id": product.id, "quantity": 1}], "10.00"))
    ).json()["id"]
    await client.patch(
        f"/api/v1/products/{product.id}",
        headers=auth(pos.admin),
        json={"price": "99.00", "tax_rate": "0"},
    )
    line = (await client.get(f"/api/v1/sales/{sale_id}", headers=pos.h)).json()["lines"][0]
    assert (line["unit_price"], line["tax_rate"], line["line_total"]) == ("10.00", "12.00", "10.00")


async def test_sal5_completed_sales_are_immutable(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    await make_lot(session, product, 5)
    await checkout(client, pos, sale(pos, [{"product_id": product.id, "quantity": 1}], "10.00"))
    for stmt in (
        "UPDATE sales SET total = 0",
        "DELETE FROM payments",
        "UPDATE sale_lines SET quantity = 9",
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(text(stmt))
        await session.rollback()


async def test_sal6_void_needs_approval_same_shift_and_restocks(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    lot = await make_lot(session, product, 5)
    sale_id = (
        await checkout(client, pos, sale(pos, [{"product_id": product.id, "quantity": 2}], "20.00"))
    ).json()["id"]
    url = f"/api/v1/sales/{sale_id}/void"

    denied = await client.post(url, headers=pos.h, json={"reason": "Error de cobro"})
    assert denied.json()["code"] == "VOID_APPROVAL_REQUIRED"

    ok = await client.post(
        url, headers={**pos.h, **approval(pos.pharmacist)}, json={"reason": "Error de cobro"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["void"]["document_number"] == 1
    await session.refresh(lot)
    assert lot.quantity == 5

    shift = (await client.get("/api/v1/shifts/current", headers=pos.h)).json()
    assert shift["summary"]["expected_cash"] == "100.00"

    again = await client.post(
        url, headers={**pos.h, **approval(pos.pharmacist)}, json={"reason": "Otra vez"}
    )
    assert again.json()["code"] == "SALE_ALREADY_VOIDED"


async def test_sal6_void_not_allowed_after_shift_closed(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    await make_lot(session, product, 5)
    sale_id = (
        await checkout(client, pos, sale(pos, [{"product_id": product.id, "quantity": 1}], "10.00"))
    ).json()["id"]
    await client.post(
        f"/api/v1/shifts/{pos.shift.id}/close", headers=pos.h, json={"counted_cash": "110.00"}
    )
    resp = await client.post(
        f"/api/v1/sales/{sale_id}/void",
        headers=auth(pos.pharmacist),
        json={"reason": "Tarde"},
    )
    assert resp.json()["code"] == "VOID_SHIFT_CLOSED"


async def test_sal5_partial_returns_restock_and_refund_exactly(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="3.33", cost="1.00")
    lot = await make_lot(session, product, 10)
    created = (
        await checkout(client, pos, sale(pos, [{"product_id": product.id, "quantity": 3}], "9.99"))
    ).json()
    line_id = created["lines"][0]["id"]
    url = f"/api/v1/sales/{created['id']}/returns"

    first = await client.post(
        url,
        headers=pos.h,
        json={"reason": "Cliente devuelve", "lines": [{"sale_line_id": line_id, "quantity": 2}]},
    )
    assert first.status_code == 201, first.text
    assert first.json()["refund_total"] == "6.66"
    second = await client.post(
        url,
        headers=pos.h,
        json={"reason": "Cliente devuelve", "lines": [{"sale_line_id": line_id, "quantity": 1}]},
    )
    assert second.json()["refund_total"] == "3.33"
    too_many = await client.post(
        url,
        headers=pos.h,
        json={"reason": "Cliente devuelve", "lines": [{"sale_line_id": line_id, "quantity": 1}]},
    )
    assert too_many.json()["code"] == "RETURN_EXCEEDS_SOLD"
    await session.refresh(lot)
    assert lot.quantity == 10
    assert [first.json()["document_number"], second.json()["document_number"]] == [1, 2]


# --- prescriptions and controlled products (CAT-2, CAT-3, SEC-3) -------------------


async def _customer(session: AsyncSession, document_id: str = "1234567890101") -> Customer:
    customer = Customer(full_name="Juan Pérez", document_id=document_id)
    session.add(customer)
    await session.commit()
    return customer


async def _prescription(
    client: AsyncClient,
    pos: Pos,
    customer: Customer,
    product: Product,
    max_quantity: int = 2,
    license: str | None = "COL-123",
    filename: str = "receta.png",
    content: bytes = PNG,
) -> Any:
    meta = {
        "customer_id": customer.id,
        "prescriber_name": "Dra. López",
        "prescriber_license": license,
        "issued_on": str(store_today()),
        "items": [{"product_id": product.id, "max_quantity": max_quantity}],
    }
    return await client.post(
        "/api/v1/prescriptions",
        headers=pos.h,
        data={"meta": json.dumps(meta)},
        files={"file": (filename, content, "application/octet-stream")},
    )


async def test_cat2_prescription_file_types(
    client: AsyncClient, session: AsyncSession, pos: Pos, tmp_path: Any, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    customer = await _customer(session)
    product = await make_product(session, requires_prescription=True)
    for name, content in [
        ("a.png", PNG),
        ("b.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 16),
        ("c.jpeg", b"\xff\xd8\xff\xe1" + b"\x00" * 16),
        ("d.pdf", b"%PDF-1.7\n" + b"\x00" * 16),
    ]:
        resp = await _prescription(client, pos, customer, product, filename=name, content=content)
        assert resp.status_code == 201, (name, resp.text)
    for name, content in [("e.gif", b"GIF89a"), ("fake.png", b"%PDF-1.7 renamed")]:
        resp = await _prescription(client, pos, customer, product, filename=name, content=content)
        assert resp.json()["code"] == "INVALID_FILE_TYPE", name


async def test_cat2_rx_product_needs_prescription_with_quantity_limit(
    client: AsyncClient, session: AsyncSession, pos: Pos, tmp_path: Any, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    customer = await _customer(session)
    product = await make_product(session, price="20.00", requires_prescription=True)
    await make_lot(session, product, 10)
    rx = (await _prescription(client, pos, customer, product, max_quantity=2)).json()

    missing = await checkout(
        client, pos, sale(pos, [{"product_id": product.id, "quantity": 1}], "20.00")
    )
    assert missing.json()["code"] == "PRESCRIPTION_REQUIRED"

    line = {"product_id": product.id, "quantity": 2, "prescription_id": rx["id"]}
    ok = await checkout(client, pos, sale(pos, [line], "40.00"))
    assert ok.status_code == 201, ok.text
    assert ok.json()["customer_id"] == customer.id

    exceeded = await checkout(client, pos, sale(pos, [{**line, "quantity": 1}], "20.00"))
    assert exceeded.json()["code"] == "PRESCRIPTION_QUANTITY_EXCEEDED"


async def test_cat3_controlled_needs_id_prescriber_and_pharmacist(
    client: AsyncClient, session: AsyncSession, pos: Pos, tmp_path: Any, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    product = await make_product(
        session, price="50.00", requires_prescription=True, controlled=True
    )
    await make_lot(session, product, 10)

    anonymous = await _customer(session, document_id="CF")
    rx = (await _prescription(client, pos, anonymous, product)).json()
    line = {"product_id": product.id, "quantity": 1, "prescription_id": rx["id"]}
    resp = await checkout(client, pos, sale(pos, [line], "50.00"), approval(pos.pharmacist))
    assert resp.json()["code"] == "CUSTOMER_ID_REQUIRED"

    customer = await _customer(session, document_id="999")
    no_license = (await _prescription(client, pos, customer, product, license=None)).json()
    resp = await checkout(
        client,
        pos,
        sale(pos, [{**line, "prescription_id": no_license["id"]}], "50.00"),
        approval(pos.pharmacist),
    )
    assert resp.json()["code"] == "PRESCRIBER_DATA_REQUIRED"

    rx = (await _prescription(client, pos, customer, product, max_quantity=1)).json()
    body = sale(pos, [{**line, "prescription_id": rx["id"]}], "50.00")
    no_approval = await checkout(client, pos, body)
    assert no_approval.json()["code"] == "CONTROLLED_APPROVAL_REQUIRED"

    too_many = await checkout(
        client,
        pos,
        sale(pos, [{**line, "prescription_id": rx["id"], "quantity": 2}], "100.00"),
        approval(pos.pharmacist),
    )
    assert too_many.json()["code"] == "PRESCRIPTION_QUANTITY_EXCEEDED"

    ok = await checkout(client, pos, body, approval(pos.pharmacist))
    assert ok.status_code == 201, ok.text
    assert ok.json()["approved_by"] == pos.pharmacist.id


async def test_sal6_rx_return_needs_pharmacist(
    client: AsyncClient, session: AsyncSession, pos: Pos, tmp_path: Any, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    customer = await _customer(session)
    product = await make_product(session, price="20.00", requires_prescription=True)
    await make_lot(session, product, 10)
    rx = (await _prescription(client, pos, customer, product)).json()
    created = (
        await checkout(
            client,
            pos,
            sale(
                pos,
                [{"product_id": product.id, "quantity": 1, "prescription_id": rx["id"]}],
                "20.00",
            ),
        )
    ).json()
    body = {
        "reason": "Devolución",
        "lines": [{"sale_line_id": created["lines"][0]["id"], "quantity": 1}],
    }
    url = f"/api/v1/sales/{created['id']}/returns"
    denied = await client.post(url, headers=pos.h, json=body)
    assert denied.json()["code"] == "RETURN_APPROVAL_REQUIRED"
    ok = await client.post(url, headers={**pos.h, **approval(pos.pharmacist)}, json=body)
    assert ok.status_code == 201
    # The prescription quantity is released again.
    rx_after = (await client.get(f"/api/v1/prescriptions/{rx['id']}", headers=pos.h)).json()
    assert rx_after["items"][0]["dispensed_quantity"] == 0


async def test_sec3_prescription_file_only_for_pharmacist(
    client: AsyncClient, session: AsyncSession, pos: Pos, tmp_path: Any, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    customer = await _customer(session)
    product = await make_product(session, requires_prescription=True)
    rx = (await _prescription(client, pos, customer, product)).json()
    url = f"/api/v1/prescriptions/{rx['id']}/file"
    assert (await client.get(url, headers=pos.h)).status_code == 403
    resp = await client.get(url, headers=auth(pos.pharmacist))
    assert resp.status_code == 200
    assert resp.content == PNG


async def test_sec3_customer_search_uses_body_not_url(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    await _customer(session)
    resp = await client.post("/api/v1/customers/search", headers=pos.h, json={"q": "1234567890101"})
    assert [c["full_name"] for c in resp.json()] == ["Juan Pérez"]


async def test_shift_status_and_lot_state_after_sale(
    client: AsyncClient, session: AsyncSession, pos: Pos
) -> None:
    product = await make_product(session, price="10.00")
    lot = await make_lot(session, product, 5)
    await checkout(client, pos, sale(pos, [{"product_id": product.id, "quantity": 2}], "20.00"))
    await session.refresh(lot)
    assert lot.quantity == 3
    shift = await session.get(RegisterShift, pos.shift.id)
    assert shift is not None and shift.status == ShiftStatus.OPEN
    assert (await session.execute(select(Lot))).first() is not None
