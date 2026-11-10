from fastapi import APIRouter, Query, Response

from app.api.deps import Admin, AnyUser, Session, Staff
from app.core.errors import NotFound
from app.models.catalog import ActiveIngredient, Category, Product
from app.repositories import catalog as catalog_repo
from app.schemas.catalog import NamedIn, NamedOut, ProductCreate, ProductOut, ProductUpdate
from app.services import catalog as catalog_service
from app.services import inventory as inventory_service

router = APIRouter(tags=["catalog"])


@router.get("/categories", response_model=list[NamedOut])
async def list_categories(session: Session, _: AnyUser) -> list[Category]:
    return await catalog_service.list_named(session, Category)


@router.post("/categories", response_model=NamedOut, status_code=201)
async def create_category(session: Session, _: Staff, body: NamedIn) -> Category:
    return await catalog_service.save_named(session, Category, body.name)


@router.patch("/categories/{category_id}", response_model=NamedOut)
async def rename_category(session: Session, _: Staff, category_id: int, body: NamedIn) -> Category:
    return await catalog_service.save_named(session, Category, body.name, category_id)


@router.get("/ingredients", response_model=list[NamedOut])
async def list_ingredients(session: Session, _: AnyUser) -> list[ActiveIngredient]:
    return await catalog_service.list_named(session, ActiveIngredient)


@router.post("/ingredients", response_model=NamedOut, status_code=201)
async def create_ingredient(session: Session, _: Staff, body: NamedIn) -> ActiveIngredient:
    return await catalog_service.save_named(session, ActiveIngredient, body.name)


async def _out(session: Session, products: list[Product]) -> list[ProductOut]:
    stock = await inventory_service.stock_by_product(session, [p.id for p in products])
    return [
        ProductOut.model_validate(p).model_copy(update={"stock": stock.get(p.id, 0)})
        for p in products
    ]


@router.get("/products", response_model=list[ProductOut])
async def search_products(
    session: Session,
    _: AnyUser,
    q: str | None = Query(None, description="Name, active ingredient or barcode"),
    category_id: int | None = None,
    active: bool | None = True,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ProductOut]:
    stmt = catalog_repo.search_products_stmt(q, category_id, active).limit(limit).offset(offset)
    products = list((await session.execute(stmt)).unique().scalars())
    return await _out(session, products)


@router.get("/products/barcode/{barcode}", response_model=ProductOut)
async def product_by_barcode(session: Session, _: AnyUser, barcode: str) -> ProductOut:
    product = await catalog_repo.get_by_barcode(session, barcode)
    if product is None:
        raise NotFound("PRODUCT_NOT_FOUND", "No product with this barcode")
    return (await _out(session, [product]))[0]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(session: Session, _: AnyUser, product_id: int) -> ProductOut:
    return (await _out(session, [await catalog_service.get_product(session, product_id)]))[0]


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(session: Session, _: Staff, body: ProductCreate) -> ProductOut:
    return (await _out(session, [await catalog_service.create_product(session, body)]))[0]


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    session: Session, _: Staff, product_id: int, body: ProductUpdate
) -> ProductOut:
    product = await catalog_service.update_product(session, product_id, body)
    return (await _out(session, [product]))[0]


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(session: Session, _: Admin, product_id: int) -> Response:
    await catalog_service.delete_product(session, product_id)
    return Response(status_code=204)
