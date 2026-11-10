"""Point of sale: checkout, voids and returns.

Every operation runs in a single transaction (SAL-2): if any check fails the
exception propagates, nothing is committed, and the session rolls back.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.money import ZERO, q2
from app.models import (
    Customer,
    MovementType,
    Payment,
    PaymentMethod,
    Prescription,
    PrescriptionItem,
    Product,
    Register,
    RegisterShift,
    Role,
    Sale,
    SaleLine,
    SaleLineLot,
    SaleReturn,
    SaleReturnLine,
    SaleReturnLot,
    SaleVoid,
    ShiftStatus,
    User,
)
from app.models.customers import CONSUMIDOR_FINAL, CONSUMIDOR_FINAL_NAME
from app.schemas.sales import PaymentIn, ReturnIn, SaleIn, SaleLineIn
from app.services import auth, inventory, shifts


async def get_sale(session: AsyncSession, sale_id: int, lock: bool = False) -> Sale:
    stmt = select(Sale).where(Sale.id == sale_id).execution_options(populate_existing=True)
    if lock:
        # Row lock only; it does not UPDATE the immutable sale row.
        stmt = stmt.with_for_update(of=Sale)
    sale = (await session.execute(stmt)).unique().scalar_one_or_none()
    if sale is None:
        raise NotFound("SALE_NOT_FOUND", "Sale not found")
    return sale


async def _lock_register(session: AsyncSession, register_id: int) -> Register:
    stmt = (
        select(Register)
        .where(Register.id == register_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    register = (await session.execute(stmt)).scalar_one_or_none()
    if register is None or not register.is_active:
        raise NotFound("REGISTER_NOT_FOUND", "Register not found or inactive")
    return register


async def _lock_prescription(
    session: AsyncSession, prescription_id: int
) -> tuple[Prescription, dict[int, PrescriptionItem]]:
    prescription = (
        (await session.execute(select(Prescription).where(Prescription.id == prescription_id)))
        .unique()
        .scalar_one_or_none()
    )
    if prescription is None:
        raise NotFound("PRESCRIPTION_NOT_FOUND", f"Prescription {prescription_id} not found")
    items = (
        (
            await session.execute(
                select(PrescriptionItem)
                .where(PrescriptionItem.prescription_id == prescription_id)
                .with_for_update(of=PrescriptionItem)
                .execution_options(populate_existing=True)
            )
        )
        .unique()
        .scalars()
    )
    return prescription, {item.product_id: item for item in items}


@dataclass
class PricedLine:
    data: SaleLineIn
    product: Product
    gross: Decimal
    discount: Decimal
    total: Decimal
    tax: Decimal


def price_line(product: Product, data: SaleLineIn) -> PricedLine:
    """SAL-1: Decimal math, half-up rounding per line; prices include tax."""
    gross = product.price * data.quantity
    discount = q2(gross * data.discount_percent / 100)
    total = gross - discount
    tax = q2(total * product.tax_rate / (100 + product.tax_rate))
    return PricedLine(data, product, gross, discount, total, tax)


def check_payment_details(payment: PaymentIn) -> None:
    """SAL-11 / SAL-12: card and transfer payments carry their reference details."""
    if payment.method == PaymentMethod.CASH:
        payment.reference = payment.card_type = payment.card_last4 = payment.bank_name = None
        return
    payment.reference = (payment.reference or "").strip() or None
    if payment.reference is None:
        raise AppError("PAYMENT_REFERENCE_REQUIRED", "Card and transfer payments need a reference")
    if payment.method == PaymentMethod.CARD:
        if payment.card_type is None or payment.card_last4 is None:
            raise AppError(
                "CARD_DETAILS_REQUIRED", "Card payments need the card type and its last 4 digits"
            )
        payment.bank_name = None
    else:
        payment.bank_name = (payment.bank_name or "").strip() or None
        if payment.bank_name is None:
            raise AppError("BANK_NAME_REQUIRED", "Transfers need the sending bank's name")
        payment.card_type = payment.card_last4 = None


async def checkout(
    session: AsyncSession, user: User, approval_token: str | None, data: SaleIn
) -> Sale:
    settings = get_settings()

    # SAL-9: the cashier must have an open shift on this register.
    register = await _lock_register(session, data.register_id)
    shift = (
        (
            await session.execute(
                select(RegisterShift).where(
                    RegisterShift.register_id == register.id,
                    RegisterShift.status == ShiftStatus.OPEN,
                )
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if shift is None or shift.user_id != user.id:
        raise AppError("NO_OPEN_SHIFT", "Open a shift on this register before selling", 409)

    ids = {line.product_id for line in data.lines}
    products = {
        p.id: p
        for p in (await session.execute(select(Product).where(Product.id.in_(ids))))
        .unique()
        .scalars()
    }
    customer: Customer | None = None
    if data.customer_id is not None:
        customer = await session.get(Customer, data.customer_id)
        if customer is None:
            raise NotFound("CUSTOMER_NOT_FOUND", "Customer not found")

    # --- price every line and collect what needs authorization -------------
    lines: list[PricedLine] = []
    needs_approval: list[tuple[str, str]] = []
    needs_admin = False
    fefo_overrides: list[tuple[int, int, int | None]] = []
    for item in data.lines:
        product = products.get(item.product_id)
        if product is None:
            raise NotFound("PRODUCT_NOT_FOUND", f"Product {item.product_id} not found")
        if not product.is_active:
            raise AppError("PRODUCT_INACTIVE", f"{product.name} is inactive")
        priced = price_line(product, item)
        lines.append(priced)

        # SAL-7: discounts above the cashier limit need a pharmacist/admin.
        if item.discount_percent > settings.cashier_discount_limit:
            needs_approval.append(
                ("DISCOUNT_APPROVAL_REQUIRED", f"Discount above {settings.cashier_discount_limit}%")
            )
        # SAL-7: selling below cost needs an admin.
        if priced.total < product.cost * item.quantity:
            needs_admin = True
        # CAT-3: controlled products need a pharmacist's approval on the sale.
        if product.controlled:
            needs_approval.append(
                ("CONTROLLED_APPROVAL_REQUIRED", f"{product.name} is a controlled product")
            )
        # INV-4: choosing a lot other than the FEFO one is a pharmacist override.
        if item.lot_id is not None:
            fefo_lot = await inventory.fefo_first_lot_id(session, product.id)
            if item.lot_id != fefo_lot:
                needs_approval.append(
                    ("FEFO_OVERRIDE_APPROVAL_REQUIRED", "Selling out of FEFO order")
                )
                fefo_overrides.append((product.id, item.lot_id, fefo_lot))

    approver: User | None = None
    if needs_approval:
        approver = await auth.resolve_approver(session, user, approval_token)
        if approver is None:
            code, message = needs_approval[0]
            raise Forbidden(code, f"{message}: pharmacist or admin approval required")
    if needs_admin:
        admin = await auth.resolve_approver(session, user, approval_token, (Role.ADMIN,))
        if admin is None:
            raise Forbidden("BELOW_COST_APPROVAL_REQUIRED", "Price below cost needs admin approval")
        approver = admin

    # --- prescriptions (CAT-2 and CAT-3) --------------------------------------
    prescriptions: dict[int, tuple[Prescription, dict[int, PrescriptionItem]]] = {}
    for priced in lines:
        product, item = priced.product, priced.data
        if not product.requires_prescription:
            item.prescription_id = None
            continue
        if item.prescription_id is None:
            raise AppError("PRESCRIPTION_REQUIRED", f"{product.name} requires a prescription")
        if item.prescription_id not in prescriptions:
            prescriptions[item.prescription_id] = await _lock_prescription(
                session, item.prescription_id
            )
        prescription, rx_items = prescriptions[item.prescription_id]
        if customer is None:
            customer = prescription.customer
        elif prescription.customer_id != customer.id:
            raise AppError(
                "PRESCRIPTION_CUSTOMER_MISMATCH", "Prescription belongs to another customer"
            )
        rx_item = rx_items.get(product.id)
        if rx_item is None:
            raise AppError(
                "PRESCRIPTION_PRODUCT_MISSING", f"Prescription does not include {product.name}"
            )
        if item.quantity > rx_item.remaining:
            raise AppError(
                "PRESCRIPTION_QUANTITY_EXCEEDED",
                f"{product.name}: prescription allows {rx_item.remaining} more units",
            )
        rx_item.dispensed_quantity += item.quantity
        if product.controlled:
            # CF is not an identification (CAT-3, SAL-13).
            if customer.document_id == CONSUMIDOR_FINAL:
                raise AppError(
                    "CUSTOMER_ID_REQUIRED", "Controlled products need the customer's document"
                )
            if not prescription.prescriber_name or not prescription.prescriber_license:
                raise AppError(
                    "PRESCRIBER_DATA_REQUIRED",
                    "Controlled products need the prescriber's name and license",
                )

    # --- payments (SAL-3) -------------------------------------------------
    total = sum((p.total for p in lines), ZERO)
    tax_total = sum((p.tax for p in lines), ZERO)
    paid = sum((p.amount for p in data.payments), ZERO)
    if paid != total:
        raise AppError("PAYMENT_MISMATCH", f"Payments add up to {paid}; sale total is {total}")
    cash = sum((p.amount for p in data.payments if p.method == PaymentMethod.CASH), ZERO)
    change = ZERO
    if data.cash_tendered is not None:
        if cash == ZERO:
            raise AppError("CASH_TENDERED_WITHOUT_CASH", "Cash tendered but no cash payment")
        if data.cash_tendered < cash:
            raise AppError("CASH_TENDERED_INSUFFICIENT", "Cash tendered is less than cash due")
        change = data.cash_tendered - cash
    for payment in data.payments:
        check_payment_details(payment)

    # --- write the sale (SAL-8: gap-free receipt number) ------------------
    receipt_number = register.next_receipt_number
    register.next_receipt_number += 1
    sale = Sale(
        store_id=register.store_id,
        register_id=register.id,
        shift_id=shift.id,
        receipt_number=receipt_number,
        user_id=user.id,
        customer_id=customer.id if customer else None,
        # SAL-10: a sale without a customer is to "Consumidor Final", NIT CF.
        customer_name=customer.full_name if customer else CONSUMIDOR_FINAL_NAME,
        customer_tax_id=customer.document_id if customer else CONSUMIDOR_FINAL,
        approved_by=approver.id if approver else None,
        subtotal=total - tax_total,
        tax_total=tax_total,
        discount_total=sum((p.discount for p in lines), ZERO),
        total=total,
        cash_tendered=data.cash_tendered,
        change_given=change,
        payments=[
            Payment(
                method=p.method,
                amount=p.amount,
                reference=p.reference,
                card_type=p.card_type,
                card_last4=p.card_last4,
                bank_name=p.bank_name,
            )
            for p in data.payments
        ],
    )
    session.add(sale)
    await session.flush()

    for priced in lines:
        product, item = priced.product, priced.data
        # INV-1, INV-3, INV-4: FEFO (or approved lot), never expired, never short.
        allocations = await inventory.allocate(session, product, item.quantity, item.lot_id)
        session.add(
            SaleLine(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=product.price,
                tax_rate=product.tax_rate,
                discount_percent=item.discount_percent,
                discount_amount=priced.discount,
                line_total=priced.total,
                tax_amount=priced.tax,
                unit_cost=product.cost,
                prescription_id=item.prescription_id,
                lots=[SaleLineLot(lot_id=a.lot.id, quantity=a.quantity) for a in allocations],
            )
        )
        for a in allocations:
            await inventory.record_movement(
                session, a.lot, -a.quantity, MovementType.SALE, user, reference=("sale", sale.id)
            )

    for product_id, lot_id, fefo_lot_id in fefo_overrides:
        assert approver is not None
        await inventory.record_fefo_override(session, approver, product_id, lot_id, fefo_lot_id)

    await session.commit()
    return await get_sale(session, sale.id)


async def _release_prescription(session: AsyncSession, line: SaleLine, quantity: int) -> None:
    if line.prescription_id is None:
        return
    _, items = await _lock_prescription(session, line.prescription_id)
    item = items.get(line.product_id)
    if item is not None:
        item.dispensed_quantity -= quantity


async def void_sale(
    session: AsyncSession, user: User, approval_token: str | None, sale_id: int, reason: str
) -> Sale:
    """SAL-6: same shift only, pharmacist/admin approval, stock goes back to its lots."""
    approver = await auth.require_approver(
        session, user, approval_token, "VOID_APPROVAL_REQUIRED", "Voids need a pharmacist or admin"
    )
    sale = await get_sale(session, sale_id, lock=True)
    if sale.void is not None:
        raise Conflict("SALE_ALREADY_VOIDED", "Sale is already voided")
    if sale.returns:
        raise Conflict("SALE_HAS_RETURNS", "A sale with returns cannot be voided")
    shift = await shifts.get_shift(session, sale.shift_id, lock=True)
    if shift.status != ShiftStatus.OPEN:
        raise Conflict("VOID_SHIFT_CLOSED", "A sale can only be voided during its own shift")

    register = await _lock_register(session, sale.register_id)
    document_number = register.next_credit_number
    register.next_credit_number += 1
    void = SaleVoid(
        sale_id=sale.id,
        register_id=register.id,
        shift_id=shift.id,
        document_number=document_number,
        reason=reason,
        user_id=user.id,
        approved_by=approver.id,
    )
    session.add(void)
    await session.flush()

    for line in sale.lines:
        for allocation in line.lots:
            lot = await inventory.lock_lot(session, allocation.lot_id)
            await inventory.record_movement(
                session,
                lot,
                allocation.quantity,
                MovementType.VOID,
                user,
                reason,
                reference=("sale_void", void.id),
            )
        await _release_prescription(session, line, line.quantity)

    await session.commit()
    return await get_sale(session, sale.id)


async def return_sale(
    session: AsyncSession, user: User, approval_token: str | None, sale_id: int, data: ReturnIn
) -> SaleReturn:
    """SAL-5: corrections are return documents that reference the sale and restock lots.
    SAL-6: returning Rx/controlled products needs a pharmacist."""
    sale = await get_sale(session, sale_id, lock=True)
    if sale.void is not None:
        raise Conflict("SALE_VOIDED", "Sale was voided")
    shift = await shifts.current_shift(session, user)
    if shift is None:
        raise AppError("NO_OPEN_SHIFT", "Open a shift before processing a return", 409)

    sale_lines = {line.id: line for line in sale.lines}
    returned_qty: dict[int, int] = defaultdict(int)
    returned_amount: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for line_id, qty, amount in await session.execute(
        select(
            SaleReturnLine.sale_line_id,
            func.sum(SaleReturnLine.quantity),
            func.sum(SaleReturnLine.amount),
        )
        .join(SaleReturn)
        .where(SaleReturn.sale_id == sale.id)
        .group_by(SaleReturnLine.sale_line_id)
    ):
        returned_qty[line_id], returned_amount[line_id] = int(qty), Decimal(amount)
    returned_lot: dict[tuple[int, int], int] = defaultdict(int)
    for line_id, lot_id, qty in await session.execute(
        select(SaleReturnLine.sale_line_id, SaleReturnLot.lot_id, func.sum(SaleReturnLot.quantity))
        .join(SaleReturnLine)
        .join(SaleReturn)
        .where(SaleReturn.sale_id == sale.id)
        .group_by(SaleReturnLine.sale_line_id, SaleReturnLot.lot_id)
    ):
        returned_lot[(line_id, lot_id)] = int(qty)

    requested: dict[int, int] = defaultdict(int)
    for item in data.lines:
        if item.sale_line_id not in sale_lines:
            raise NotFound("SALE_LINE_NOT_FOUND", f"Line {item.sale_line_id} is not in this sale")
        requested[item.sale_line_id] += item.quantity

    needs_approval = False
    return_lines: list[SaleReturnLine] = []
    for line_id, quantity in requested.items():
        line = sale_lines[line_id]
        remaining = line.quantity - returned_qty[line_id]
        if quantity > remaining:
            raise AppError(
                "RETURN_EXCEEDS_SOLD",
                f"{line.product_name}: {remaining} units can still be returned",
            )
        product = await session.get(Product, line.product_id)
        if product is not None and (product.requires_prescription or product.controlled):
            needs_approval = True
        # The last return of a line refunds exactly what is left, so rounding never drifts.
        if quantity == remaining:
            amount = line.line_total - returned_amount[line_id]
        else:
            amount = q2(line.line_total * quantity / line.quantity)

        lots, left = [], quantity
        for allocation in reversed(line.lots):
            free = allocation.quantity - returned_lot[(line_id, allocation.lot_id)]
            take = min(free, left)
            if take > 0:
                lots.append(SaleReturnLot(lot_id=allocation.lot_id, quantity=take))
                left -= take
            if left == 0:
                break
        return_lines.append(
            SaleReturnLine(sale_line_id=line_id, quantity=quantity, amount=amount, lots=lots)
        )

    approver = None
    if needs_approval:
        approver = await auth.require_approver(
            session,
            user,
            approval_token,
            "RETURN_APPROVAL_REQUIRED",
            "Returning prescription products needs a pharmacist",
        )

    register = await _lock_register(session, shift.register_id)
    document_number = register.next_credit_number
    register.next_credit_number += 1
    sale_return = SaleReturn(
        sale_id=sale.id,
        register_id=register.id,
        shift_id=shift.id,
        document_number=document_number,
        reason=data.reason,
        refund_method=data.refund_method,
        refund_total=sum((rl.amount for rl in return_lines), ZERO),
        user_id=user.id,
        approved_by=approver.id if approver else None,
        lines=return_lines,
    )
    session.add(sale_return)
    await session.flush()

    for return_line in return_lines:
        for rlot in return_line.lots:
            lot = await inventory.lock_lot(session, rlot.lot_id)
            await inventory.record_movement(
                session,
                lot,
                rlot.quantity,
                MovementType.SALE_RETURN,
                user,
                data.reason,
                reference=("sale_return", sale_return.id),
            )
        await _release_prescription(
            session, sale_lines[return_line.sale_line_id], return_line.quantity
        )

    await session.commit()
    return sale_return
