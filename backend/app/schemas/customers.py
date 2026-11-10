import re
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from app.models.customers import CONSUMIDOR_FINAL
from app.schemas.common import ORMModel

# CUI is 13 digits; NIT is digits with a check digit that may be K.
_TAX_ID = re.compile(rf"^({CONSUMIDOR_FINAL}|\d{{1,29}}[\dK])$")


def normalize_tax_id(value: Any) -> str:
    """SAL-13: NIT/CUI is mandatory; empty means CF. Spaces and hyphens are ignored."""
    if value is None:
        return CONSUMIDOR_FINAL
    if not isinstance(value, str):
        raise ValueError("NIT/CUI must be text")
    normalized = re.sub(r"[\s-]", "", value).upper()
    if not normalized:
        return CONSUMIDOR_FINAL
    if not _TAX_ID.match(normalized):
        raise ValueError("NIT/CUI must be digits (NIT may end in K) or CF")
    return normalized


TaxId = Annotated[str, BeforeValidator(normalize_tax_id)]


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    document_id: TaxId = CONSUMIDOR_FINAL
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    document_id: TaxId | None = None
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)


class CustomerSearch(BaseModel):
    """Sent in the body, not the URL, so personal data stays out of access logs (SEC-3)."""

    q: str = Field(min_length=1, max_length=160)


class CustomerLookup(BaseModel):
    """Exact NIT/CUI lookup used by the POS; in the body for the same reason (SEC-3)."""

    document_id: TaxId


class CustomerOut(ORMModel):
    id: int
    full_name: str
    document_id: str
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
