from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import PaymentMethod, ShiftStatus
from app.schemas.common import Money, ORMModel, Percent


class RegisterIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class RegisterOut(ORMModel):
    id: int
    store_id: int
    code: str
    name: str
    is_active: bool


class ShiftOpenIn(BaseModel):
    register_id: int
    opening_cash: Money


class ShiftCloseIn(BaseModel):
    counted_cash: Money
    notes: str | None = Field(default=None, max_length=500)


class ShiftSummary(BaseModel):
    sales_count: int
    sales_total: Decimal
    cash_sales: Decimal
    voided_cash: Decimal
    cash_refunds: Decimal
    expected_cash: Decimal


class ShiftOut(ORMModel):
    id: int
    register_id: int
    register_code: str
    register_name: str
    user_id: int
    status: ShiftStatus
    opened_at: datetime
    opening_cash: Decimal
    closed_at: datetime | None
    closed_by: int | None
    expected_cash: Decimal | None
    counted_cash: Decimal | None
    difference: Decimal | None
    notes: str | None
    summary: ShiftSummary | None = None


class SaleLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    discount_percent: Percent = Decimal("0")
    lot_id: int | None = Field(default=None, description="FEFO override; needs a pharmacist")
    prescription_id: int | None = None


class PaymentIn(BaseModel):
    method: PaymentMethod
    amount: Money = Field(gt=0)
    reference: str | None = Field(default=None, max_length=80)


class SaleIn(BaseModel):
    register_id: int
    customer_id: int | None = None
    lines: list[SaleLineIn] = Field(min_length=1)
    payments: list[PaymentIn] = []
    cash_tendered: Money | None = None


class SaleLineLotOut(ORMModel):
    lot_id: int
    quantity: int


class SaleLineOut(ORMModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    tax_rate: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    line_total: Decimal
    tax_amount: Decimal
    prescription_id: int | None
    lots: list[SaleLineLotOut]


class PaymentOut(ORMModel):
    method: PaymentMethod
    amount: Decimal
    reference: str | None


class SaleVoidOut(ORMModel):
    id: int
    document_number: int
    reason: str
    user_id: int
    approved_by: int
    shift_id: int
    created_at: datetime


class SaleReturnLineOut(ORMModel):
    sale_line_id: int
    quantity: int
    amount: Decimal


class SaleReturnOut(ORMModel):
    id: int
    sale_id: int
    register_id: int
    shift_id: int
    document_number: int
    reason: str
    refund_method: PaymentMethod
    refund_total: Decimal
    user_id: int
    approved_by: int | None
    created_at: datetime
    lines: list[SaleReturnLineOut]


class SaleOut(ORMModel):
    id: int
    register_id: int
    register_code: str
    register_name: str
    shift_id: int
    receipt_number: int
    user_id: int
    customer_id: int | None
    approved_by: int | None
    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal
    cash_tendered: Decimal | None
    change_given: Decimal
    created_at: datetime
    lines: list[SaleLineOut]
    payments: list[PaymentOut]
    void: SaleVoidOut | None
    returns: list[SaleReturnOut]


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReturnLineIn(BaseModel):
    sale_line_id: int
    quantity: int = Field(gt=0)


class ReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    refund_method: PaymentMethod = PaymentMethod.CASH
    lines: list[ReturnLineIn] = Field(min_length=1)
