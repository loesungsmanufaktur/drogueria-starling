from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import ddl
from app.db.base import Base, CreatedAtMixin, IdMixin, enum_type
from app.models.catalog import Product


class MovementType(StrEnum):
    PURCHASE = "purchase"
    SALE = "sale"
    SALE_RETURN = "sale_return"
    VOID = "void"
    ADJUSTMENT = "adjustment"
    EXPIRY_WRITE_OFF = "expiry_write_off"


class Lot(IdMixin, CreatedAtMixin, Base):
    """Every unit in stock belongs to a lot with an expiry date (INV-2)."""

    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint("product_id", "lot_number", name="uq_lots_product_lot_number"),
        # INV-1: stock can never go negative.
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        Index("ix_lots_product_expiry", "product_id", "expiry_date"),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    lot_number: Mapped[str] = mapped_column(String(60))
    expiry_date: Mapped[date]
    # Maintained only by the stock_movements trigger (INV-5).
    quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    unit_cost: Mapped[Decimal]

    product: Mapped[Product] = relationship(lazy="joined")


class StockMovement(IdMixin, CreatedAtMixin, Base):
    """Append-only stock ledger (INV-5)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="quantity_non_zero"),
        Index("ix_stock_movements_reference", "reference_type", "reference_id"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="RESTRICT"), index=True)
    type: Mapped[MovementType] = mapped_column(enum_type(MovementType))
    quantity: Mapped[int]  # signed: positive adds stock, negative removes it
    reason: Mapped[str | None] = mapped_column(Text)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


ddl.register(
    "inventory",
    [
        *ddl.immutable_table("stock_movements"),
        """
        CREATE OR REPLACE FUNCTION apply_stock_movement() RETURNS trigger AS $$
        BEGIN
            UPDATE lots SET quantity = quantity + NEW.quantity
             WHERE id = NEW.lot_id AND product_id = NEW.product_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'lot % does not belong to product %', NEW.lot_id, NEW.product_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        "DROP TRIGGER IF EXISTS trg_stock_movements_apply ON stock_movements",
        "CREATE TRIGGER trg_stock_movements_apply AFTER INSERT ON stock_movements "
        "FOR EACH ROW EXECUTE FUNCTION apply_stock_movement()",
        """
        CREATE OR REPLACE FUNCTION guard_lot_quantity() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' AND NEW.quantity <> 0 THEN
                RAISE EXCEPTION 'lots start empty; add stock through stock_movements'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            -- Depth 1 means a direct UPDATE; the movement trigger runs at depth 2.
            IF TG_OP = 'UPDATE' AND NEW.quantity <> OLD.quantity AND pg_trigger_depth() < 2 THEN
                RAISE EXCEPTION 'lot quantity changes only through stock_movements'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        "DROP TRIGGER IF EXISTS trg_lots_guard_quantity ON lots",
        "CREATE TRIGGER trg_lots_guard_quantity BEFORE INSERT OR UPDATE ON lots "
        "FOR EACH ROW EXECUTE FUNCTION guard_lot_quantity()",
    ],
)
