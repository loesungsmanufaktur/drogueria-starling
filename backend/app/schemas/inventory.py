from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import MovementType
from app.schemas.common import Money, ORMModel

Reason = Field(min_length=3, max_length=500)


class LotOut(ORMModel):
    id: int
    product_id: int
    lot_number: str
    expiry_date: date
    quantity: int
    unit_cost: Decimal
    created_at: datetime


class OpeningLotIn(BaseModel):
    product_id: int
    lot_number: str = Field(min_length=1, max_length=60)
    expiry_date: date
    quantity: int = Field(gt=0)
    unit_cost: Money
    reason: str = Reason


class AdjustmentIn(BaseModel):
    lot_id: int
    quantity: int = Field(description="Signed: positive adds units, negative removes them")
    reason: str = Reason


class WriteOffIn(BaseModel):
    reason: str = Reason


class MovementOut(ORMModel):
    id: int
    product_id: int
    lot_id: int
    type: MovementType
    quantity: int
    reason: str | None
    reference_type: str | None
    reference_id: int | None
    user_id: int | None
    created_at: datetime
