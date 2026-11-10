from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role
from tests.factories import auth, make_lot, make_product, make_user

PRODUCT = {
    "name": "Acetaminofén 500 mg",
    "presentation": "Caja x 100 tabletas",
    "barcode": "7401234567890",
    "price": "25.00",
    "cost": "15.50",
}


async def test_rule7_sanitary_registration_is_optional(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    resp = await client.post("/api/v1/products", headers=auth(pharmacist), json=PRODUCT)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["sanitary_registration"] is None
    assert body["tax_rate"] == "12.00"
    assert body["stock"] == 0


async def test_cashier_cannot_create_products(client: AsyncClient, session: AsyncSession) -> None:
    cashier = await make_user(session, Role.CASHIER)
    resp = await client.post("/api/v1/products", headers=auth(cashier), json=PRODUCT)
    assert resp.status_code == 403


async def test_money_rejects_more_than_two_decimals(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    resp = await client.post(
        "/api/v1/products", headers=auth(pharmacist), json={**PRODUCT, "price": "1.005"}
    )
    assert resp.status_code == 422


async def test_controlled_product_always_requires_prescription(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    resp = await client.post(
        "/api/v1/products",
        headers=auth(pharmacist),
        json={**PRODUCT, "controlled": True, "requires_prescription": False},
    )
    assert resp.json()["requires_prescription"] is True


async def test_search_by_name_ingredient_and_barcode(
    client: AsyncClient, session: AsyncSession
) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    h = auth(pharmacist)
    ing = (await client.post("/api/v1/ingredients", headers=h, json={"name": "Ibuprofeno"})).json()
    await client.post(
        "/api/v1/products",
        headers=h,
        json={
            "name": "Advil 400",
            "barcode": "111",
            "price": "30.00",
            "ingredients": [{"ingredient_id": ing["id"], "strength": "400 mg"}],
        },
    )
    await client.post("/api/v1/products", headers=h, json={**PRODUCT, "barcode": "222"})

    def names(resp: object) -> list[str]:
        return [p["name"] for p in resp.json()]  # type: ignore[attr-defined]

    assert names(await client.get("/api/v1/products", headers=h, params={"q": "ibupro"})) == [
        "Advil 400"
    ]
    assert names(await client.get("/api/v1/products", headers=h, params={"q": "acetaminofen"}))
    assert names(await client.get("/api/v1/products", headers=h, params={"q": "222"})) == [
        PRODUCT["name"]
    ]
    by_code = await client.get("/api/v1/products/barcode/111", headers=h)
    assert by_code.json()["ingredients"][0] == {
        "ingredient_id": ing["id"],
        "name": "Ibuprofeno",
        "strength": "400 mg",
    }


async def test_duplicate_barcode_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    pharmacist = await make_user(session, Role.PHARMACIST)
    await client.post("/api/v1/products", headers=auth(pharmacist), json=PRODUCT)
    resp = await client.post("/api/v1/products", headers=auth(pharmacist), json=PRODUCT)
    assert resp.status_code == 409
    assert resp.json()["code"] == "BARCODE_TAKEN"


async def test_rule10_product_with_history_is_deactivated_not_deleted(
    client: AsyncClient, session: AsyncSession
) -> None:
    admin = await make_user(session, Role.ADMIN)
    unused = await make_product(session)
    used = await make_product(session)
    await make_lot(session, used, 5)

    assert (
        await client.delete(f"/api/v1/products/{unused.id}", headers=auth(admin))
    ).status_code == 204

    resp = await client.delete(f"/api/v1/products/{used.id}", headers=auth(admin))
    assert resp.status_code == 409
    assert resp.json()["code"] == "PRODUCT_HAS_HISTORY"

    resp = await client.patch(
        f"/api/v1/products/{used.id}", headers=auth(admin), json={"is_active": False}
    )
    assert resp.json()["is_active"] is False
    listed = await client.get("/api/v1/products", headers=auth(admin))
    assert used.id not in [p["id"] for p in listed.json()]
