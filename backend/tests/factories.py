"""Small helpers to build test data directly through the ORM."""

import itertools
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, store_today
from app.core.security import create_token, hash_password
from app.models import Lot, MovementType, Product, Role, StockMovement, User

PASSWORD = "secret-pass-123"
# A complete card payment (SAL-11, SAL-12) to merge into payment dicts.
CARD = {"reference": "AUTH-0001", "card_type": "visa", "card_last4": "4242"}
_seq = itertools.count(1)


async def make_user(
    session: AsyncSession, role: Role = Role.CASHIER, username: str | None = None
) -> User:
    user = User(
        username=username or f"{role.value}{next(_seq)}",
        full_name=f"Test {role.value}",
        role=role,
        password_hash=hash_password(PASSWORD),
    )
    session.add(user)
    await session.commit()
    return user


def auth(user: User) -> dict[str, str]:
    token = create_token(user.id, "access", get_settings().access_token_expire_minutes)
    return {"Authorization": f"Bearer {token}"}


def approval(user: User) -> dict[str, str]:
    token = create_token(user.id, "approval", get_settings().approval_token_expire_minutes)
    return {"X-Approval-Token": token}


async def make_product(
    session: AsyncSession,
    name: str | None = None,
    price: str = "10.00",
    cost: str = "6.00",
    tax_rate: str = "12.00",
    **kwargs: object,
) -> Product:
    n = next(_seq)
    product = Product(
        name=name or f"Producto {n}",
        barcode=kwargs.pop("barcode", f"BC{n:08d}"),
        price=Decimal(price),
        cost=Decimal(cost),
        tax_rate=Decimal(tax_rate),
        **kwargs,
    )
    session.add(product)
    await session.commit()
    return product


async def make_lot(
    session: AsyncSession,
    product: Product,
    quantity: int,
    expiry: date | None = None,
    days: int = 365,
    unit_cost: str = "6.00",
) -> Lot:
    lot = Lot(
        product_id=product.id,
        lot_number=f"L{next(_seq)}",
        expiry_date=expiry or store_today() + timedelta(days=days),
        unit_cost=Decimal(unit_cost),
    )
    session.add(lot)
    await session.flush()
    if quantity:
        session.add(
            StockMovement(
                product_id=product.id,
                lot_id=lot.id,
                type=MovementType.ADJUSTMENT,
                quantity=quantity,
                reason="test stock",
            )
        )
    await session.commit()
    await session.refresh(lot)
    return lot
