from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.models.catalog import Product

# "Consumidor final": the NIT used when a customer has no NIT/CUI (SAL-13).
CONSUMIDOR_FINAL = "CF"
CONSUMIDOR_FINAL_NAME = "Consumidor Final"


class Customer(IdMixin, CreatedAtMixin, Base):
    """Personal data (SEC-3): never logged, readable only by roles that need it."""

    __tablename__ = "customers"
    __table_args__ = (
        # SAL-13: unique per real NIT/CUI; any number of customers can be CF.
        Index(
            "uq_customers_document_id_not_cf",
            "document_id",
            unique=True,
            postgresql_where=text(f"document_id <> '{CONSUMIDOR_FINAL}'"),
        ),
    )

    full_name: Mapped[str] = mapped_column(String(160))
    # NIT or CUI, normalized (no spaces/hyphens, upper case); CF when the customer has none.
    document_id: Mapped[str] = mapped_column(
        String(30), default=CONSUMIDOR_FINAL, server_default=CONSUMIDOR_FINAL
    )
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(120))


class Prescription(IdMixin, CreatedAtMixin, Base):
    """Health data (SEC-3). The scanned prescription is required (CAT-2)."""

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
