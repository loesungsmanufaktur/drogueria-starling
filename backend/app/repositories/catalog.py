from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import ActiveIngredient, Product, ProductIngredient


def search_products_stmt(
    q: str | None = None,
    category_id: int | None = None,
    active: bool | None = True,
) -> Select[Product]:
    stmt = select(Product)
    if active is not None:
        stmt = stmt.where(Product.is_active.is_(active))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if q:
        term = q.strip().lower()
        by_ingredient = (
            select(ProductIngredient.product_id)
            .join(ActiveIngredient)
            .where(func.lower(ActiveIngredient.name).contains(term))
        )
        stmt = stmt.where(
            or_(
                Product.barcode == q.strip(),
                func.lower(Product.name).contains(term),
                func.similarity(func.lower(Product.name), term) > 0.3,
                Product.id.in_(by_ingredient),
            )
        ).order_by(func.similarity(func.lower(Product.name), term).desc(), Product.name)
    else:
        stmt = stmt.order_by(Product.name)
    return stmt


async def get_by_barcode(session: AsyncSession, barcode: str) -> Product | None:
    result = await session.execute(select(Product).where(Product.barcode == barcode))
    return result.unique().scalar_one_or_none()
