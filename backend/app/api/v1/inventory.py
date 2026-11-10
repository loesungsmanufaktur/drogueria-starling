from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import AnyUser, Session, Staff
from app.models import Lot, StockMovement
from app.schemas.inventory import AdjustmentIn, LotOut, MovementOut, OpeningLotIn, WriteOffIn
from app.services import inventory as inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/lots", response_model=list[LotOut])
async def list_lots(
    session: Session,
    _: AnyUser,
    product_id: int | None = None,
    include_empty: bool = False,
    limit: int = Query(200, ge=1, le=500),
) -> list[Lot]:
    stmt = select(Lot).order_by(Lot.expiry_date, Lot.id).limit(limit)
    if product_id is not None:
        stmt = stmt.where(Lot.product_id == product_id)
    if not include_empty:
        stmt = stmt.where(Lot.quantity > 0)
    return list((await session.execute(stmt)).unique().scalars())


@router.post("/lots", response_model=LotOut, status_code=201)
async def create_opening_lot(session: Session, user: Staff, body: OpeningLotIn) -> Lot:
    return await inventory_service.create_opening_lot(session, user, body)


@router.post("/adjustments", response_model=MovementOut, status_code=201)
async def adjust(session: Session, user: Staff, body: AdjustmentIn) -> StockMovement:
    return await inventory_service.adjust(session, user, body)


@router.post("/lots/{lot_id}/write-off", response_model=MovementOut, status_code=201)
async def write_off(session: Session, user: Staff, lot_id: int, body: WriteOffIn) -> StockMovement:
    return await inventory_service.write_off_expired(session, user, lot_id, body.reason)


@router.get("/movements", response_model=list[MovementOut])
async def list_movements(
    session: Session,
    _: Staff,
    product_id: int | None = None,
    lot_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[StockMovement]:
    stmt = select(StockMovement).order_by(StockMovement.id.desc()).limit(limit).offset(offset)
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if lot_id is not None:
        stmt = stmt.where(StockMovement.lot_id == lot_id)
    return list((await session.execute(stmt)).scalars())
