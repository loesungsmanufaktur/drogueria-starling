from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import Admin, AnyUser, ApprovalToken, Session, Staff
from app.core.errors import NotFound
from app.models import Register, RegisterShift, Role, Sale, SaleReturn, ShiftStatus
from app.schemas.sales import (
    RegisterIn,
    RegisterOut,
    ReturnIn,
    SaleIn,
    SaleOut,
    SaleReturnOut,
    ShiftCloseIn,
    ShiftOpenIn,
    ShiftOut,
    VoidIn,
)
from app.services import sales as sales_service
from app.services import shifts as shifts_service

router = APIRouter(tags=["pos"])


@router.get("/registers", response_model=list[RegisterOut])
async def list_registers(session: Session, _: AnyUser) -> list[Register]:
    return list((await session.execute(select(Register).order_by(Register.code))).scalars())


@router.post("/registers", response_model=RegisterOut, status_code=201)
async def create_register(session: Session, _: Admin, body: RegisterIn) -> Register:
    return await shifts_service.save_register(session, body)


@router.put("/registers/{register_id}", response_model=RegisterOut)
async def update_register(
    session: Session, _: Admin, register_id: int, body: RegisterIn
) -> Register:
    return await shifts_service.save_register(session, body, register_id)


@router.post("/shifts/open", response_model=ShiftOut, status_code=201)
async def open_shift(session: Session, user: AnyUser, body: ShiftOpenIn) -> ShiftOut:
    shift = await shifts_service.open_shift(session, user, body)
    return await shifts_service.shift_out(session, shift)


@router.get("/shifts/current", response_model=ShiftOut | None)
async def current_shift(session: Session, user: AnyUser) -> ShiftOut | None:
    shift = await shifts_service.current_shift(session, user)
    return await shifts_service.shift_out(session, shift) if shift else None


@router.get("/shifts", response_model=list[ShiftOut])
async def list_shifts(
    session: Session,
    _: Staff,
    register_id: int | None = None,
    status: ShiftStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[RegisterShift]:
    stmt = select(RegisterShift).order_by(RegisterShift.id.desc()).limit(limit)
    if register_id is not None:
        stmt = stmt.where(RegisterShift.register_id == register_id)
    if status is not None:
        stmt = stmt.where(RegisterShift.status == status)
    return list((await session.execute(stmt)).unique().scalars())


@router.get("/shifts/{shift_id}", response_model=ShiftOut)
async def get_shift(session: Session, user: AnyUser, shift_id: int) -> ShiftOut:
    shift = await shifts_service.get_shift(session, shift_id)
    shifts_service.ensure_can_view(user, shift)
    return await shifts_service.shift_out(session, shift)


@router.post("/shifts/{shift_id}/close", response_model=ShiftOut)
async def close_shift(
    session: Session, user: AnyUser, shift_id: int, body: ShiftCloseIn
) -> ShiftOut:
    shift = await shifts_service.close_shift(session, user, shift_id, body)
    return await shifts_service.shift_out(session, shift)


@router.post("/sales", response_model=SaleOut, status_code=201)
async def checkout(
    session: Session, user: AnyUser, body: SaleIn, x_approval_token: ApprovalToken = None
) -> Sale:
    return await sales_service.checkout(session, user, x_approval_token, body)


@router.get("/sales", response_model=list[SaleOut])
async def list_sales(
    session: Session,
    user: AnyUser,
    shift_id: int | None = None,
    register_id: int | None = None,
    receipt_number: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Sale]:
    stmt = select(Sale).order_by(Sale.id.desc()).limit(limit).offset(offset)
    if user.role == Role.CASHIER:
        stmt = stmt.where(Sale.user_id == user.id)
    if shift_id is not None:
        stmt = stmt.where(Sale.shift_id == shift_id)
    if register_id is not None:
        stmt = stmt.where(Sale.register_id == register_id)
    if receipt_number is not None:
        stmt = stmt.where(Sale.receipt_number == receipt_number)
    return list((await session.execute(stmt)).unique().scalars())


@router.get("/sales/{sale_id}", response_model=SaleOut)
async def get_sale(session: Session, user: AnyUser, sale_id: int) -> Sale:
    sale = await sales_service.get_sale(session, sale_id)
    if user.role == Role.CASHIER and sale.user_id != user.id:
        raise NotFound("SALE_NOT_FOUND", "Sale not found")
    return sale


@router.post("/sales/{sale_id}/void", response_model=SaleOut)
async def void_sale(
    session: Session,
    user: AnyUser,
    sale_id: int,
    body: VoidIn,
    x_approval_token: ApprovalToken = None,
) -> Sale:
    return await sales_service.void_sale(session, user, x_approval_token, sale_id, body.reason)


@router.post("/sales/{sale_id}/returns", response_model=SaleReturnOut, status_code=201)
async def return_sale(
    session: Session,
    user: AnyUser,
    sale_id: int,
    body: ReturnIn,
    x_approval_token: ApprovalToken = None,
) -> SaleReturn:
    return await sales_service.return_sale(session, user, x_approval_token, sale_id, body)
