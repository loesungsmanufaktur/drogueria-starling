from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.models.catalog import Product


class Customer(IdMixin, CreatedAtMixin, Base):
    """Personal data (rule 22): never logged, readable only by roles that need it."""

    __tablename__ = "customers"

    full_name: Mapped[str] = mapped_column(String(160))
    document_id: Mapped[str | None] = mapped_column(String(30), unique=True)  # DPI / NIT
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(120))


class Prescription(IdMixin, CreatedAtMixin, Base):
    """Health data (rule 22). The scanned prescription is required (rule 8)."""

    __tablename__ = "prescriptions"

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    prescriber_name: Mapped[str] = mapped_column(String(160))
    prescriber_license: Mapped[str | None] = mapped_column(String(40))
    issued_on: Mapped[date]
    notes: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(200))
    file_path: Mapped[str] = mapped_column(String(300))
    file_content_type: Mapped[str] = mapped_column(String(60))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    customer: Mapped[Customer] = relationship(lazy="joined")
    items: Mapped[list["PrescriptionItem"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PrescriptionItem.id"
    )


class PrescriptionItem(IdMixin, Base):
    __tablename__ = "prescription_items"
    __table_args__ = (
        UniqueConstraint("prescription_id", "product_id", name="uq_prescription_items_product"),
        CheckConstraint("max_quantity > 0", name="max_quantity_positive"),
        CheckConstraint(
            "dispensed_quantity >= 0 AND dispensed_quantity <= max_quantity",
            name="dispensed_within_max",
        ),
    )

    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    max_quantity: Mapped[int]
    dispensed_quantity: Mapped[int] = mapped_column(default=0, server_default="0")

    product: Mapped[Product] = relationship(lazy="joined")

    @property
    def product_name(self) -> str:
        return self.product.name

    @property
    def remaining(self) -> int:
        return self.max_quantity - self.dispensed_quantity
