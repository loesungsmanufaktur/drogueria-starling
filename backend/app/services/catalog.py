from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, Conflict, NotFound
from app.models.catalog import ActiveIngredient, Category, Product, ProductIngredient
from app.schemas.catalog import ProductCreate, ProductIngredientIn, ProductUpdate


async def list_named[Named: (Category, ActiveIngredient)](
    session: AsyncSession, model: type[Named]
) -> list[Named]:
    return list((await session.execute(select(model).order_by(model.name))).scalars())


async def save_named[Named: (Category, ActiveIngredient)](
    session: AsyncSession, model: type[Named], name: str, item_id: int | None = None
) -> Named:
    item = model(name=name) if item_id is None else await session.get(model, item_id)
    if item is None:
        raise NotFound("NOT_FOUND", f"{model.__name__} not found")
    item.name = name.strip()
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict("NAME_TAKEN", "Name already exists") from exc
    return item


async def get_product(session: AsyncSession, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFound("PRODUCT_NOT_FOUND", "Product not found")
    return product


async def _ingredients(
    session: AsyncSession, items: list[ProductIngredientIn]
) -> list[ProductIngredient]:
    ids = {i.ingredient_id for i in items}
    found = set(
        (
            await session.execute(select(ActiveIngredient.id).where(ActiveIngredient.id.in_(ids)))
        ).scalars()
    )
    if missing := ids - found:
        raise NotFound("INGREDIENT_NOT_FOUND", f"Unknown ingredients: {sorted(missing)}")
    return [ProductIngredient(ingredient_id=i.ingredient_id, strength=i.strength) for i in items]


async def _commit_product(session: AsyncSession, product: Product) -> Product:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        message = str(exc.orig)
        if "uq_products_barcode" in message:
            raise Conflict("BARCODE_TAKEN", "Another product already uses this barcode") from exc
        if "controlled_requires_rx" in message:
            raise AppError(
                "CONTROLLED_REQUIRES_RX", "A controlled product must require a prescription"
            ) from exc
        if "fk_products_category_id" in message:
            raise NotFound("CATEGORY_NOT_FOUND", "Category not found") from exc
        raise
    await session.refresh(product)
    return product


async def create_product(session: AsyncSession, data: ProductCreate) -> Product:
    ingredients = await _ingredients(session, data.ingredients)
    product = Product(**data.model_dump(exclude={"ingredients"}), ingredients=ingredients)
    session.add(product)
    return await _commit_product(session, product)


async def update_product(session: AsyncSession, product_id: int, data: ProductUpdate) -> Product:
    product = await get_product(session, product_id)
    changes = data.model_dump(exclude_unset=True, exclude={"ingredients"})
    if changes.get("controlled"):
        changes["requires_prescription"] = True
    for key, value in changes.items():
        setattr(product, key, value)
    if data.ingredients is not None:
        product.ingredients = await _ingredients(session, data.ingredients)
    return await _commit_product(session, product)


async def delete_product(session: AsyncSession, product_id: int) -> None:
    """Rule 10: only a product without stock movements or sales can be deleted;
    otherwise it must be deactivated. Foreign keys (ON DELETE RESTRICT) enforce it."""
    product = await get_product(session, product_id)
    await session.delete(product)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict(
            "PRODUCT_HAS_HISTORY",
            "Product has stock or sales history; deactivate it instead",
        ) from exc
