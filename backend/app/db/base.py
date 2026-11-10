from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Numeric(14, 2)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        Decimal: Money,  # rule 11: money is NUMERIC(14,2), never float
        datetime: DateTime(timezone=True),  # rule 23: timestamps are timestamptz (UTC)
    }


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
