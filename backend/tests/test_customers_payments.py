"""Customer NIT/CUI (SAL-13), receipt customer data (SAL-10) and payment details (SAL-11/12)."""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Register, RegisterShift, Role, User
from tests.factories import CARD, auth, make_lot, make_product, make_user

# --- SAL-13: NIT/CUI is mandatory, CF when missing -----------------------------


async def test_sal13_missing_or_blank_tax_id_becomes_cf(
    client: AsyncClient, session: AsyncSession
) -> None:
    h = auth(await make_user(session, Role.CASHIER))
    no_id = await client.post("/api/v1/customers", headers=h, json={"full_name": "Ana"})
    blank = await client.post(
        "/api/v1/customers", headers=h, json={"full_name": "Luis", "document_id": "  "}
    )
    lower = await client.post(
        "/api/v1/customers", headers=h, json={"full_name": "Eva", "document_id": "cf"}
    )
    # Many customers can share CF; it is not a unique number.
    assert [r.status_code for r in (no_id, blank, lower)] == [201, 201, 201]
    assert {r.json()["document_id"] for r in (no_id, blank, lower)} == {"CF"}


async def test_sal13_tax_id_is_normalized_unique_and_validated(
    client: AsyncClient, session: AsyncSession
) -> None:
    h = auth(await make_user(session, Role.CASHIER))
    created = await client.post(
        "/api/v1/customers", headers=h, json={"full_name": "Eva", "document_id": "123456-k"}
    )
    assert created.json()["document_id"] == "123456K"

    dup = await client.post(
        "/api/v1/customers", headers=h, json={"full_name": "Otra", "document_id": "123 456K"}
    )
    assert dup.json()["code"] == "DOCUMENT_TAKEN"

    bad = await client.post(
        "/api/v1/customers", headers=h, json={"full_name": "X", "document_id": "ABC-1"}
    )
    assert bad.status_code == 422

    cleared = await client.patch(
        f"/api/v1/customers/{created.json()['id']}", headers=h, json={"document_id": None}
    )
    assert cleared.json()["document_id"] == "CF"


async def test_sal13_lookup_by_tax_id(client: AsyncClient, session: AsyncSession) -> None:
    h = auth(await make_user(session, Role.CASHIER))
    session.add(Customer(full_name="Juan Pérez", document_id="1234567890101"))
    await session.commit()

    found = await client.post(
        "/api/v1/customers/lookup", headers=h, json={"document_id": "1234 56789 0101"}
    )
    assert found.json()["full_name"] == "Juan Pérez"

    missing = await client.post("/api/v1/customers/lookup", headers=h, json={"document_id": "999"})
    assert missing.status_code == 404
    assert missing.json()["code"] == "CUSTOMER_NOT_FOUND"

    cf = await client.post("/api/v1/customers/lookup", headers=h, json={"document_id": "CF"})
    assert cf.json()["code"] == "CF_NOT_LOOKUP"


# --- checkout helpers -------------------------------------------------------------


@pytest.fixture
async def till(session: AsyncSession) -> tuple[Register, User, int]:
    register = Register(code="T1", name="Caja T")
    session.add(register)
    cashier = await make_user(session, Role.CASHIER)
    session.add(RegisterShift(register_id=register.id, user_id=cashier.id, opening_cash=Decimal(0)))
    product = await make_product(session, price="10.00", cost="1.00")
    await make_lot(session, product, 50)
    return register, cashier, product.id


async def _sell(
    client: AsyncClient,
    till: tuple[Register, User, int],
    payments: list[dict[str, Any]],
    customer_id: int | None = None,
) -> Any:
    register, cashier, product_id = till
    return await client.post(
        "/api/v1/sales",
        headers=auth(cashier),
        json={
            "register_id": register.id,
            "customer_id": customer_id,
            "lines": [{"product_id": product_id, "quantity": 1}],
            "payments": payments,
        },
    )


# --- SAL-10: receipt customer name and NIT/CUI --------------------------------------


async def test_sal10_sale_keeps_customer_name_and_tax_id(
    client: AsyncClient, session: AsyncSession, till: tuple[Register, User, int]
) -> None:
    walk_in = await _sell(client, till, [{"method": "cash", "amount": "10.00"}])
    assert (walk_in.json()["customer_name"], walk_in.json()["customer_tax_id"]) == (
        "Consumidor Final",
        "CF",
    )

    customer = Customer(full_name="María López", document_id="7654321")
    session.add(customer)
    await session.commit()
    sold = await _sell(client, till, [{"method": "cash", "amount": "10.00"}], customer.id)
    assert (sold.json()["customer_name"], sold.json()["customer_tax_id"]) == (
        "María López",
        "7654321",
    )

    # Later edits to the customer never change the receipt (like SAL-4 for prices).
    customer.full_name = "María L. de Ruiz"
    await session.commit()
    again = await client.get(f"/api/v1/sales/{sold.json()['id']}", headers=auth(till[1]))
    assert again.json()["customer_name"] == "María López"


# --- SAL-11 / SAL-12: card and transfer details ---------------------------------------


async def test_sal11_card_and_transfer_need_reference_details(
    client: AsyncClient, session: AsyncSession, till: tuple[Register, User, int]
) -> None:
    card = {"method": "card", "amount": "10.00"}
    no_ref = await _sell(client, till, [{**card, "card_type": "visa", "card_last4": "1234"}])
    assert no_ref.json()["code"] == "PAYMENT_REFERENCE_REQUIRED"
    no_type = await _sell(client, till, [{**card, "reference": "A1", "card_last4": "1234"}])
    assert no_type.json()["code"] == "CARD_DETAILS_REQUIRED"
    bad_type = await _sell(client, till, [{**card, **CARD, "card_type": "diners"}])
    assert bad_type.status_code == 422

    transfer = {"method": "transfer", "amount": "10.00", "reference": "TRX-9"}
    no_bank = await _sell(client, till, [transfer])
    assert no_bank.json()["code"] == "BANK_NAME_REQUIRED"

    ok = await _sell(client, till, [{**transfer, "bank_name": "Banco Industrial"}])
    assert ok.status_code == 201, ok.text
    assert ok.json()["payments"][0]["bank_name"] == "Banco Industrial"


async def test_sal12_card_stores_only_last_four_digits(
    client: AsyncClient, session: AsyncSession, till: tuple[Register, User, int]
) -> None:
    card = {"method": "card", "amount": "10.00", "reference": "AUTH-7", "card_type": "amex"}
    full_number = await _sell(client, till, [{**card, "card_last4": "4111111111111111"}])
    assert full_number.status_code == 422

    ok = await _sell(client, till, [{**card, "card_last4": "0005"}])
    assert ok.status_code == 201, ok.text
    payment = ok.json()["payments"][0]
    assert (payment["card_type"], payment["card_last4"], payment["reference"]) == (
        "amex",
        "0005",
        "AUTH-7",
    )

    # The database refuses anything but 4 digits, whatever the code path.
    with pytest.raises(DBAPIError, match="ck_payments_card_details"):
        await session.execute(
            text(
                "INSERT INTO payments (sale_id, method, amount, reference, card_type, card_last4) "
                f"VALUES ({ok.json()['id']}, 'card', 1, 'X', 'visa', '12a4')"
            )
        )
    await session.rollback()
