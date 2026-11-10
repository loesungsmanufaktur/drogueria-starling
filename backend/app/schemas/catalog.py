from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Money, ORMModel, Percent


class NamedIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class NamedOut(ORMModel):
    id: int
    name: str


class ProductIngredientIn(BaseModel):
    ingredient_id: int
    strength: str | None = Field(default=None, max_length=60)


class ProductIngredientOut(ORMModel):
    ingredient_id: int
    name: str
    strength: str | None


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    presentation: str | None = Field(default=None, max_length=120)
    category_id: int | None = None
    barcode: str | None = Field(default=None, min_length=1, max_length=64)
    sanitary_registration: str | None = Field(default=None, max_length=60)
    requires_prescription: bool = False
    controlled: bool = False
    tax_rate: Percent = Decimal("12.00")
    price: Money
    cost: Money = Decimal("0")
    min_stock: int = Field(default=0, ge=0)


class ProductCreate(ProductBase):
    ingredients: list[ProductIngredientIn] = []

    @model_validator(mode="after")
    def controlled_implies_rx(self) -> "ProductCreate":
        if self.controlled:
            self.requires_prescription = True
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    presentation: str | None = Field(default=None, max_length=120)
    category_id: int | None = None
    barcode: str | None = Field(default=None, min_length=1, max_length=64)
    sanitary_registration: str | None = Field(default=None, max_length=60)
    requires_prescription: bool | None = None
    controlled: bool | None = None
    tax_rate: Percent | None = None
    price: Money | None = None
    cost: Money | None = None
    min_stock: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    ingredients: list[ProductIngredientIn] | None = None


class ProductOut(ORMModel):
    id: int
    name: str
    description: str | None
    presentation: str | None
    category_id: int | None
    category_name: str | None
    barcode: str | None
    sanitary_registration: str | None
    requires_prescription: bool
    controlled: bool
    tax_rate: Decimal
    price: Decimal
    cost: Decimal
    min_stock: int
    is_active: bool
    ingredients: list[ProductIngredientOut] = []
    stock: int = 0
