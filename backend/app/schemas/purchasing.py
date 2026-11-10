from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.purchasing import PurchaseStatus
from app.schemas.common import Money, ORMModel


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    tax_id: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class SupplierOut(ORMModel):
    id: int
    name: str
    tax_id: str | None
    phone: str | None
    email: str | None
    is_active: bool


class PurchaseLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_cost: Money


class PurchaseOrderIn(BaseModel):
    supplier_id: int
    notes: str | None = None
    lines: list[PurchaseLineIn] = Field(min_length=1)


class PurchaseLineOut(ORMModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_cost: Decimal
    received_quantity: int


class PurchaseOrderOut(ORMModel):
    id: int
    supplier: SupplierOut
    status: PurchaseStatus
    notes: str | None
    created_by: int
    received_by: int | None
    received_at: datetime | None
    created_at: datetime
    lines: list[PurchaseLineOut]


class ReceiptLineIn(BaseModel):
    line_id: int
    lot_number: str = Field(min_length=1, max_length=60)
    expiry_date: date
    quantity: int = Field(gt=0)
    unit_cost: Money | None = Field(default=None, description="Defaults to the ordered cost")


class ReceiptIn(BaseModel):
    lines: list[ReceiptLineIn] = Field(min_length=1)
