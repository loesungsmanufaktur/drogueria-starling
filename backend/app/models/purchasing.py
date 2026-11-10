from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, IdMixin, enum_type
from app.models.catalog import Product


class Supplier(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(160), unique=True)
    tax_id: Mapped[str | None] = mapped_column(String(30))  # NIT
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class PurchaseStatus(StrEnum):
    DRAFT = "draft"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class PurchaseOrder(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "purchase_orders"

    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[PurchaseStatus] = mapped_column(
        enum_type(PurchaseStatus), default=PurchaseStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None]

    supplier: Mapped[Supplier] = relationship(lazy="joined")
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PurchaseOrderLine.id"
    )


class PurchaseOrderLine(IdMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("received_quantity >= 0", name="received_non_negative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity: Mapped[int]
    unit_cost: Mapped[Decimal]
    received_quantity: Mapped[int] = mapped_column(default=0, server_default="0")

    product: Mapped[Product] = relationship(lazy="joined")

    @property
    def product_name(self) -> str:
        return self.product.name
