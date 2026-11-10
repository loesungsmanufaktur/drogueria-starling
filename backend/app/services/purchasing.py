from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import store_today
from app.core.errors import AppError, Conflict, NotFound
from app.models import Lot, MovementType, Product, User
from app.models.purchasing import PurchaseOrder, PurchaseOrderLine, PurchaseStatus, Supplier
from app.schemas.purchasing import PurchaseOrderIn, ReceiptIn, SupplierIn
from app.services import inventory


async def save_supplier(
    session: AsyncSession, data: SupplierIn, supplier_id: int | None = None
) -> Supplier:
    supplier = Supplier() if supplier_id is None else await session.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFound("SUPPLIER_NOT_FOUND", "Supplier not found")
    for key, value in data.model_dump().items():
        setattr(supplier, key, value)
    session.add(supplier)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict("NAME_TAKEN", "A supplier with this name already exists") from exc
    return supplier


async def get_order(session: AsyncSession, order_id: int, lock: bool = False) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
    if lock:
        stmt = stmt.with_for_update(of=PurchaseOrder).execution_options(populate_existing=True)
    order = (await session.execute(stmt)).unique().scalar_one_or_none()
    if order is None:
        raise NotFound("PURCHASE_ORDER_NOT_FOUND", "Purchase order not found")
    return order


async def _lines(session: AsyncSession, data: PurchaseOrderIn) -> list[PurchaseOrderLine]:
    ids = {line.product_id for line in data.lines}
    found = set((await session.execute(select(Product.id).where(Product.id.in_(ids)))).scalars())
    if missing := ids - found:
        raise NotFound("PRODUCT_NOT_FOUND", f"Unknown products: {sorted(missing)}")
    return [
        PurchaseOrderLine(
            product_id=line.product_id, quantity=line.quantity, unit_cost=line.unit_cost
        )
        for line in data.lines
    ]


async def create_order(session: AsyncSession, user: User, data: PurchaseOrderIn) -> PurchaseOrder:
    if await session.get(Supplier, data.supplier_id) is None:
        raise NotFound("SUPPLIER_NOT_FOUND", "Supplier not found")
    order = PurchaseOrder(
        supplier_id=data.supplier_id,
        notes=data.notes,
        created_by=user.id,
        lines=await _lines(session, data),
    )
    session.add(order)
    await session.commit()
    return await get_order(session, order.id)


def _require_draft(order: PurchaseOrder) -> None:
    if order.status != PurchaseStatus.DRAFT:
        raise Conflict("PURCHASE_ORDER_NOT_DRAFT", f"Purchase order is {order.status.value}")


async def update_order(
    session: AsyncSession, order_id: int, data: PurchaseOrderIn
) -> PurchaseOrder:
    order = await get_order(session, order_id, lock=True)
    _require_draft(order)
    order.supplier_id = data.supplier_id
    order.notes = data.notes
    order.lines = await _lines(session, data)
    await session.commit()
    return await get_order(session, order.id)


async def cancel_order(session: AsyncSession, order_id: int) -> PurchaseOrder:
    order = await get_order(session, order_id, lock=True)
    _require_draft(order)
    order.status = PurchaseStatus.CANCELLED
    await session.commit()
    return order


async def _receiving_lot(
    session: AsyncSession, product_id: int, lot_number: str, expiry_date: object, unit_cost: object
) -> Lot:
    existing = (
        (
            await session.execute(
                select(Lot)
                .where(Lot.product_id == product_id, Lot.lot_number == lot_number)
                .with_for_update(of=Lot)
                .execution_options(populate_existing=True)
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if existing is not None:
        if existing.expiry_date != expiry_date:
            raise Conflict(
                "LOT_EXPIRY_MISMATCH",
                f"Lot {lot_number} already exists with expiry {existing.expiry_date}",
            )
        return existing
    lot = Lot(
        product_id=product_id, lot_number=lot_number, expiry_date=expiry_date, unit_cost=unit_cost
    )
    session.add(lot)
    await session.flush()
    return lot


async def receive_order(
    session: AsyncSession, user: User, order_id: int, data: ReceiptIn
) -> PurchaseOrder:
    """Goods receipt: every received line becomes stock in a lot (INV-2) through a
    purchase movement (INV-5). All lines are received in one transaction."""
    order = await get_order(session, order_id, lock=True)
    _require_draft(order)
    lines = {line.id: line for line in order.lines}
    today = store_today()

    received: dict[int, int] = defaultdict(int)
    for item in data.lines:
        line = lines.get(item.line_id)
        if line is None:
            raise NotFound("PURCHASE_LINE_NOT_FOUND", f"Line {item.line_id} is not in this order")
        if item.expiry_date <= today:
            raise AppError(
                "RECEIVING_EXPIRED_LOT", f"Lot {item.lot_number} is expired or expires today"
            )
        received[line.id] += item.quantity
        if received[line.id] > line.quantity:
            raise AppError(
                "RECEIVED_EXCEEDS_ORDERED",
                f"{line.product.name}: received {received[line.id]}, ordered {line.quantity}",
            )

    for item in data.lines:
        line = lines[item.line_id]
        unit_cost = item.unit_cost if item.unit_cost is not None else line.unit_cost
        lot = await _receiving_lot(
            session, line.product_id, item.lot_number, item.expiry_date, unit_cost
        )
        await inventory.record_movement(
            session,
            lot,
            item.quantity,
            MovementType.PURCHASE,
            user,
            reference=("purchase_order", order.id),
        )
        line.product.cost = unit_cost

    for line_id, quantity in received.items():
        lines[line_id].received_quantity = quantity
    order.status = PurchaseStatus.RECEIVED
    order.received_by = user.id
    order.received_at = datetime.now(UTC)
    await session.commit()
    return await get_order(session, order.id)
