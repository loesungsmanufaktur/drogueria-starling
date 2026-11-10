from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.alerts import AlertType
from app.schemas.common import ORMModel


class PaymentTotal(BaseModel):
    method: str
    amount: Decimal


class DailySales(BaseModel):
    date: date
    sales_count: int
    gross_total: Decimal
    discount_total: Decimal
    tax_total: Decimal
    voided_count: int
    voided_total: Decimal
    returns_total: Decimal
    net_total: Decimal
    by_payment_method: list[PaymentTotal]


class StockValuationRow(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    value: Decimal


class StockValuation(BaseModel):
    total_value: Decimal
    rows: list[StockValuationRow]


class ExpiringLot(BaseModel):
    lot_id: int
    product_id: int
    product_name: str
    lot_number: str
    expiry_date: date
    quantity: int
    days_left: int
    expired: bool


class LowStockRow(BaseModel):
    product_id: int
    product_name: str
    stock: int
    min_stock: int


class AlertOut(ORMModel):
    id: int
    type: AlertType
    product_id: int
    lot_id: int | None
    alert_date: date
    message: str
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    created_at: datetime
