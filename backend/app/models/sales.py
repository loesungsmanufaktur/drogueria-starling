from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import ddl
from app.db.base import Base, CreatedAtMixin, IdMixin, enum_type


class Register(IdMixin, Base):
    __tablename__ = "registers"
    __table_args__ = (
        CheckConstraint("next_receipt_number > 0", name="receipt_positive"),
        CheckConstraint("next_credit_number > 0", name="credit_positive"),
    )

    store_id: Mapped[int] = mapped_column(default=1, server_default="1")
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # SAL-8: gap-free counters, incremented under a row lock in the same transaction.
    next_receipt_number: Mapped[int] = mapped_column(default=1, server_default="1")
    next_credit_number: Mapped[int] = mapped_column(default=1, server_default="1")


class ShiftStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class RegisterShift(IdMixin, Base):
    """SAL-9: selling requires an open shift; closing records counted vs expected cash."""

    __tablename__ = "register_shifts"
    __table_args__ = (
        Index(
            "uq_register_shifts_one_open_per_register",
            "register_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index(
            "uq_register_shifts_one_open_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    register_id: Mapped[int] = mapped_column(ForeignKey("registers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ShiftStatus] = mapped_column(enum_type(ShiftStatus), default=ShiftStatus.OPEN)
    opened_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    opening_cash: Mapped[Decimal]
    closed_at: Mapped[datetime | None]
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    expected_cash: Mapped[Decimal | None]
    counted_cash: Mapped[Decimal | None]
    difference: Mapped[Decimal | None]
    notes: Mapped[str | None] = mapped_column(Text)

    register: Mapped[Register] = relationship(lazy="joined")

    @property
    def register_code(self) -> str:
        return self.register.code

    @property
    def register_name(self) -> str:
        return self.register.name


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"


class Sale(IdMixin, CreatedAtMixin, Base):
    """Completed sales are immutable (SAL-5); see the triggers below."""

    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("register_id", "receipt_number", name="uq_sales_register_receipt"),
    )

    store_id: Mapped[int] = mapped_column(default=1, server_default="1")
    register_id: Mapped[int] = mapped_column(ForeignKey("registers.id"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("register_shifts.id"), index=True)
    receipt_number: Mapped[int]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    subtotal: Mapped[Decimal]  # total without tax
    tax_total: Mapped[Decimal]
    discount_total: Mapped[Decimal]
    total: Mapped[Decimal]
    cash_tendered: Mapped[Decimal | None]
    change_given: Mapped[Decimal]

    register: Mapped[Register] = relationship(lazy="joined")

    @property
    def register_code(self) -> str:
        return self.register.code

    @property
    def register_name(self) -> str:
        return self.register.name

    lines: Mapped[list["SaleLine"]] = relationship(lazy="selectin", order_by="SaleLine.id")
    payments: Mapped[list["Payment"]] = relationship(lazy="selectin", order_by="Payment.id")
    void: Mapped["SaleVoid | None"] = relationship(lazy="selectin")
    returns: Mapped[list["SaleReturn"]] = relationship(lazy="selectin", order_by="SaleReturn.id")


class SaleLine(IdMixin, Base):
    """Prices and tax rates are copied at the moment of sale (SAL-4)."""

    __tablename__ = "sale_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal]
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    discount_amount: Mapped[Decimal]
    line_total: Mapped[Decimal]  # tax included, after discount
    tax_amount: Mapped[Decimal]
    unit_cost: Mapped[Decimal]
    prescription_id: Mapped[int | None] = mapped_column(ForeignKey("prescriptions.id"))

    lots: Mapped[list["SaleLineLot"]] = relationship(lazy="selectin", order_by="SaleLineLot.id")


class SaleLineLot(IdMixin, Base):
    __tablename__ = "sale_line_lots"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    sale_line_id: Mapped[int] = mapped_column(ForeignKey("sale_lines.id"), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    quantity: Mapped[int]


class Payment(IdMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    method: Mapped[PaymentMethod] = mapped_column(enum_type(PaymentMethod))
    amount: Mapped[Decimal]
    reference: Mapped[str | None] = mapped_column(String(80))


class SaleVoid(IdMixin, CreatedAtMixin, Base):
    """Cancels a whole sale within its own shift (SAL-6)."""

    __tablename__ = "sale_voids"

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), unique=True)
    register_id: Mapped[int] = mapped_column(ForeignKey("registers.id"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("register_shifts.id"), index=True)
    document_number: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SaleReturn(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "sale_returns"

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    register_id: Mapped[int] = mapped_column(ForeignKey("registers.id"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("register_shifts.id"), index=True)
    document_number: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    refund_method: Mapped[PaymentMethod] = mapped_column(enum_type(PaymentMethod))
    refund_total: Mapped[Decimal]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    lines: Mapped[list["SaleReturnLine"]] = relationship(
        lazy="selectin", order_by="SaleReturnLine.id"
    )


class SaleReturnLine(IdMixin, Base):
    __tablename__ = "sale_return_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    return_id: Mapped[int] = mapped_column(ForeignKey("sale_returns.id"), index=True)
    sale_line_id: Mapped[int] = mapped_column(ForeignKey("sale_lines.id"), index=True)
    quantity: Mapped[int]
    amount: Mapped[Decimal]

    lots: Mapped[list["SaleReturnLot"]] = relationship(lazy="selectin")


class SaleReturnLot(IdMixin, Base):
    __tablename__ = "sale_return_lots"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    return_line_id: Mapped[int] = mapped_column(ForeignKey("sale_return_lines.id"), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    quantity: Mapped[int]


SALES_DOCUMENT_TABLES = [
    "sales",
    "sale_lines",
    "sale_line_lots",
    "payments",
    "sale_voids",
    "sale_returns",
    "sale_return_lines",
    "sale_return_lots",
]

ddl.register("sales", [s for t in SALES_DOCUMENT_TABLES for s in ddl.immutable_table(t)])
