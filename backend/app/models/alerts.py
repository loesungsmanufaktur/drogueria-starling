from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin, enum_type


class AlertType(StrEnum):
    EXPIRED = "expired"
    EXPIRING = "expiring"
    LOW_STOCK = "low_stock"


class Alert(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # One alert per product/lot and day, even when re-run.
        UniqueConstraint(
            "type",
            "product_id",
            "lot_id",
            "alert_date",
            name="uq_alerts_daily",
            postgresql_nulls_not_distinct=True,
        ),
    )

    type: Mapped[AlertType] = mapped_column(enum_type(AlertType))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"))
    alert_date: Mapped[date]
    message: Mapped[str] = mapped_column(String(300))
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None]
