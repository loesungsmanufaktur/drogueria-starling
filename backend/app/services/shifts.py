from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.money import ZERO
from app.models import (
    Payment,
    PaymentMethod,
    Register,
    RegisterShift,
    Role,
    Sale,
    SaleReturn,
    SaleVoid,
    ShiftStatus,
    User,
)
from app.schemas.sales import RegisterIn, ShiftCloseIn, ShiftOpenIn, ShiftOut, ShiftSummary


async def save_register(
    session: AsyncSession, data: RegisterIn, register_id: int | None = None
) -> Register:
    register = Register() if register_id is None else await session.get(Register, register_id)
    if register is None:
        raise NotFound("REGISTER_NOT_FOUND", "Register not found")
    for key, value in data.model_dump().items():
        setattr(register, key, value)
    session.add(register)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict("REGISTER_CODE_TAKEN", "Register code already exists") from exc
    return register


async def get_shift(session: AsyncSession, shift_id: int, lock: bool = False) -> RegisterShift:
    stmt = select(RegisterShift).where(RegisterShift.id == shift_id)
    if lock:
        stmt = stmt.with_for_update(of=RegisterShift).execution_options(populate_existing=True)
    shift = (await session.execute(stmt)).unique().scalar_one_or_none()
    if shift is None:
        raise NotFound("SHIFT_NOT_FOUND", "Shift not found")
    return shift


async def current_shift(session: AsyncSession, user: User) -> RegisterShift | None:
    stmt = select(RegisterShift).where(
        RegisterShift.user_id == user.id, RegisterShift.status == ShiftStatus.OPEN
    )
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def open_shift(session: AsyncSession, user: User, data: ShiftOpenIn) -> RegisterShift:
    register = await session.get(Register, data.register_id)
    if register is None or not register.is_active:
        raise NotFound("REGISTER_NOT_FOUND", "Register not found or inactive")
    shift = RegisterShift(
        register_id=register.id,
        user_id=user.id,
        status=ShiftStatus.OPEN,
        opening_cash=data.opening_cash,
    )
    session.add(shift)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict(
            "SHIFT_ALREADY_OPEN", "This register or user already has an open shift"
        ) from exc
    return await get_shift(session, shift.id)


async def _sum(session: AsyncSession, stmt: object) -> Decimal:
    value = (await session.execute(stmt)).scalar_one()  # type: ignore[call-overload]
    return Decimal(value or ZERO)


async def summarize(session: AsyncSession, shift: RegisterShift) -> ShiftSummary:
    in_shift = Sale.shift_id == shift.id
    not_voided = ~select(SaleVoid.id).where(SaleVoid.sale_id == Sale.id).exists()
    count, total = (
        await session.execute(
            select(func.count(Sale.id), func.coalesce(func.sum(Sale.total), 0)).where(
                in_shift, not_voided
            )
        )
    ).one()
    cash_sales = await _sum(
        session,
        select(func.sum(Payment.amount))
        .join(Sale)
        .where(in_shift, Payment.method == PaymentMethod.CASH),
    )
    # Voids only happen inside the sale's own shift, so their cash leaves this drawer.
    voided_cash = await _sum(
        session,
        select(func.sum(Payment.amount))
        .join(Sale)
        .join(SaleVoid, SaleVoid.sale_id == Sale.id)
        .where(in_shift, Payment.method == PaymentMethod.CASH),
    )
    cash_refunds = await _sum(
        session,
        select(func.sum(SaleReturn.refund_total)).where(
            SaleReturn.shift_id == shift.id, SaleReturn.refund_method == PaymentMethod.CASH
        ),
    )
    return ShiftSummary(
        sales_count=count,
        sales_total=Decimal(total),
        cash_sales=cash_sales,
        voided_cash=voided_cash,
        cash_refunds=cash_refunds,
        expected_cash=shift.opening_cash + cash_sales - voided_cash - cash_refunds,
    )


async def shift_out(session: AsyncSession, shift: RegisterShift) -> ShiftOut:
    out = ShiftOut.model_validate(shift)
    out.summary = await summarize(session, shift)
    return out


def ensure_can_view(user: User, shift: RegisterShift) -> None:
    if shift.user_id != user.id and user.role not in (Role.ADMIN, Role.PHARMACIST):
        raise Forbidden("SHIFT_NOT_OWNED", "This shift belongs to another user")


async def close_shift(
    session: AsyncSession, user: User, shift_id: int, data: ShiftCloseIn
) -> RegisterShift:
    """Rule 19: the difference between counted and expected cash is recorded, not hidden."""
    shift = await get_shift(session, shift_id, lock=True)
    ensure_can_view(user, shift)
    if shift.status != ShiftStatus.OPEN:
        raise Conflict("SHIFT_ALREADY_CLOSED", "Shift is already closed")
    summary = await summarize(session, shift)
    shift.expected_cash = summary.expected_cash
    shift.counted_cash = data.counted_cash
    shift.difference = data.counted_cash - summary.expected_cash
    shift.notes = data.notes
    shift.closed_at = datetime.now(UTC)
    shift.closed_by = user.id
    shift.status = ShiftStatus.CLOSED
    await session.commit()
    return await get_shift(session, shift.id)
