from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    document_id: str | None = Field(default=None, min_length=1, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    document_id: str | None = Field(default=None, min_length=1, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)


class CustomerSearch(BaseModel):
    """Sent in the body, not the URL, so personal data stays out of access logs (rule 22)."""

    q: str = Field(min_length=1, max_length=160)


class CustomerOut(ORMModel):
    id: int
    full_name: str
    document_id: str | None
    phone: str | None
    email: str | None
    created_at: datetime


class PrescriptionItemIn(BaseModel):
    product_id: int
    max_quantity: int = Field(gt=0)


class PrescriptionMeta(BaseModel):
    customer_id: int
    prescriber_name: str = Field(min_length=1, max_length=160)
    prescriber_license: str | None = Field(default=None, max_length=40)
    issued_on: date
    notes: str | None = None
    items: list[PrescriptionItemIn] = Field(min_length=1)


class PrescriptionItemOut(ORMModel):
    id: int
    product_id: int
    product_name: str
    max_quantity: int
    dispensed_quantity: int
    remaining: int


class PrescriptionOut(ORMModel):
    id: int
    customer_id: int
    prescriber_name: str
    prescriber_license: str | None
    issued_on: date
    notes: str | None
    file_name: str
    file_content_type: str
    created_by: int
    created_at: datetime
    items: list[PrescriptionItemOut]
