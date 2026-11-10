from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, false, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, IdMixin


class Category(IdMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True)


class ActiveIngredient(IdMixin, Base):
    __tablename__ = "active_ingredients"

    name: Mapped[str] = mapped_column(String(120), unique=True)


class ProductIngredient(Base):
    __tablename__ = "product_ingredients"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("active_ingredients.id", ondelete="RESTRICT"), primary_key=True
    )
    strength: Mapped[str | None] = mapped_column(String(60))

    ingredient: Mapped[ActiveIngredient] = relationship(lazy="joined")

    @property
    def name(self) -> str:
        return self.ingredient.name


class Product(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("cost >= 0", name="cost_non_negative"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="tax_rate_range"),
        CheckConstraint("min_stock >= 0", name="min_stock_non_negative"),
        # A controlled product is always a prescription product.
        CheckConstraint("NOT controlled OR requires_prescription", name="controlled_requires_rx"),
        # Fuzzy name search (requires the pg_trgm extension).
        Index("ix_products_name_trgm", text("lower(name) gin_trgm_ops"), postgresql_using="gin"),
    )

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    presentation: Mapped[str | None] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Rule 7: sanitary registration is optional.
    sanitary_registration: Mapped[str | None] = mapped_column(String(60))
    requires_prescription: Mapped[bool] = mapped_column(default=False, server_default=false())
    controlled: Mapped[bool] = mapped_column(default=False, server_default=false())
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    price: Mapped[Decimal]  # tax included
    cost: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    min_stock: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    category: Mapped[Category | None] = relationship(lazy="joined")
    ingredients: Mapped[list[ProductIngredient]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None
