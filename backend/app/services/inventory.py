from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import store_today
from app.core.errors import AppError, Conflict, NotFound
from app.models import Lot, MovementType, Product, StockMovement, User
from app.schemas.inventory import AdjustmentIn, OpeningLotIn
from app.services import audit


class InsufficientStock(AppError):
    status_code = 409


async def stock_by_product(session: AsyncSession, product_ids: list[int]) -> dict[int, int]:
    """Stock on hand is derived from lots."""
    if not product_ids:
        return {}
    rows = await session.execute(
        select(Lot.product_id, func.sum(Lot.quantity))
        .where(Lot.product_id.in_(product_ids))
        .group_by(Lot.product_id)
    )
    return {pid: int(qty) for pid, qty in rows}


def is_sellable(lot: Lot, today: date | None = None) -> bool:
    """Rule 3: a lot is sellable only if it expires strictly after today (store tz)."""
    return lot.expiry_date > (today or store_today())


async def lock_lot(session: AsyncSession, lot_id: int) -> Lot:
    lot = (
        (
            await session.execute(
                select(Lot)
                .where(Lot.id == lot_id)
                .with_for_update(of=Lot)
                .execution_options(populate_existing=True)
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if lot is None:
        raise NotFound("LOT_NOT_FOUND", "Lot not found")
    return lot


async def lock_sellable_lots(session: AsyncSession, product_id: int) -> list[Lot]:
    """Sellable lots in FEFO order (rule 4), locked for the current transaction."""
    stmt = (
        select(Lot)
        .where(Lot.product_id == product_id, Lot.quantity > 0, Lot.expiry_date > store_today())
        .order_by(Lot.expiry_date, Lot.id)
        .with_for_update(of=Lot)
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(stmt)).unique().scalars())


async def record_movement(
    session: AsyncSession,
    lot: Lot,
    quantity: int,
    type_: MovementType,
    user: User | None,
    reason: str | None = None,
    reference: tuple[str, int] | None = None,
) -> StockMovement:
    """The only way stock changes (rule 5). The caller must hold a lock on ``lot``."""
    if lot.quantity + quantity < 0:
        raise InsufficientStock(
            "INSUFFICIENT_STOCK",
            f"Lot {lot.lot_number} has {lot.quantity} units; cannot remove {-quantity}",
        )
    movement = StockMovement(
        product_id=lot.product_id,
        lot_id=lot.id,
        type=type_,
        quantity=quantity,
        reason=reason,
        reference_type=reference[0] if reference else None,
        reference_id=reference[1] if reference else None,
        user_id=user.id if user else None,
    )
    session.add(movement)
    await session.flush()
    await session.refresh(lot, ["quantity"])
    return movement


@dataclass
class Allocation:
    lot: Lot
    quantity: int


async def allocate(
    session: AsyncSession, product: Product, quantity: int, lot_id: int | None = None
) -> list[Allocation]:
    """Pick lots for a sale: FEFO, or one explicit lot when overridden (rule 4).
    Rejects the whole request if stock is short (rule 1) or the lot is expired (rule 3)."""
    if lot_id is not None:
        lot = await lock_lot(session, lot_id)
        if lot.product_id != product.id:
            raise AppError("LOT_PRODUCT_MISMATCH", "Lot does not belong to this product")
        if not is_sellable(lot):
            raise AppError("LOT_EXPIRED", f"Lot {lot.lot_number} is expired and cannot be sold")
        if lot.quantity < quantity:
            raise InsufficientStock(
                "INSUFFICIENT_STOCK", f"Lot {lot.lot_number} has only {lot.quantity} units"
            )
        return [Allocation(lot, quantity)]

    lots = await lock_sellable_lots(session, product.id)
    available = sum(lot.quantity for lot in lots)
    if available < quantity:
        raise InsufficientStock(
            "INSUFFICIENT_STOCK",
            f"{product.name}: {available} sellable units available, {quantity} requested",
        )
    allocations, remaining = [], quantity
    for lot in lots:
        take = min(lot.quantity, remaining)
        allocations.append(Allocation(lot, take))
        remaining -= take
        if remaining == 0:
            break
    return allocations


async def fefo_first_lot_id(session: AsyncSession, product_id: int) -> int | None:
    lots = await lock_sellable_lots(session, product_id)
    return lots[0].id if lots else None


async def create_opening_lot(session: AsyncSession, user: User, data: OpeningLotIn) -> Lot:
    """Load existing stock at go-live (or a found lot) as an audited adjustment."""
    product = await session.get(Product, data.product_id)
    if product is None:
        raise NotFound("PRODUCT_NOT_FOUND", "Product not found")
    lot = Lot(
        product_id=product.id,
        lot_number=data.lot_number,
        expiry_date=data.expiry_date,
        unit_cost=data.unit_cost,
    )
    session.add(lot)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict("LOT_EXISTS", "This product already has a lot with that number") from exc
    await record_movement(session, lot, data.quantity, MovementType.ADJUSTMENT, user, data.reason)
    await session.commit()
    return lot


async def adjust(session: AsyncSession, user: User, data: AdjustmentIn) -> StockMovement:
    """Rule 6: manual adjustments need pharmacist/admin (checked by the route) and a reason."""
    lot = await lock_lot(session, data.lot_id)
    movement = await record_movement(
        session, lot, data.quantity, MovementType.ADJUSTMENT, user, data.reason
    )
    await session.commit()
    return movement


async def write_off_expired(
    session: AsyncSession, user: User, lot_id: int, reason: str
) -> StockMovement:
    """Rule 6: remove the remaining units of an expired lot, with a reason."""
    lot = await lock_lot(session, lot_id)
    if is_sellable(lot):
        raise AppError("LOT_NOT_EXPIRED", "Only expired lots can be written off")
    if lot.quantity == 0:
        raise AppError("LOT_EMPTY", "Lot has no units left")
    movement = await record_movement(
        session, lot, -lot.quantity, MovementType.EXPIRY_WRITE_OFF, user, reason
    )
    await session.commit()
    return movement


async def record_fefo_override(
    session: AsyncSession, approver: User, product_id: int, lot_id: int, fefo_lot_id: int | None
) -> None:
    """Rule 4: a pharmacist overriding FEFO is audited."""
    audit.record(
        session.sync_session,
        "fefo_override",
        "lots",
        lot_id,
        {"product_id": product_id, "fefo_lot_id": fefo_lot_id, "approved_by": approver.id},
    )
