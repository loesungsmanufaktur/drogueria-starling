from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, store_today
from app.core.errors import NotFound
from app.core.money import ZERO
from app.models import Lot, Payment, Product, Sale, SaleReturn, SaleVoid, User
from app.models.alerts import Alert, AlertType
from app.schemas.reports import (
    DailySales,
    ExpiringLot,
    LowStockRow,
    PaymentTotal,
    StockValuation,
    StockValuationRow,
)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC bounds of a business day in the store's timezone (rule 23)."""
    tz = get_settings().tz
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    return start, start + timedelta(days=1)


async def daily_sales(session: AsyncSession, day: date) -> DailySales:
    start, end = day_bounds(day)
    in_day = and_(Sale.created_at >= start, Sale.created_at < end)
    voided = select(SaleVoid.sale_id).where(SaleVoid.sale_id == Sale.id).exists()

    count, gross, discount, tax = (
        await session.execute(
            select(
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.total), 0),
                func.coalesce(func.sum(Sale.discount_total), 0),
                func.coalesce(func.sum(Sale.tax_total), 0),
            ).where(in_day, ~voided)
        )
    ).one()
    voided_count, voided_total = (
        await session.execute(
            select(func.count(Sale.id), func.coalesce(func.sum(Sale.total), 0)).where(
                in_day, voided
            )
        )
    ).one()
    returns_total = (
        await session.execute(
            select(func.coalesce(func.sum(SaleReturn.refund_total), 0)).where(
                SaleReturn.created_at >= start, SaleReturn.created_at < end
            )
        )
    ).scalar_one()
    methods = await session.execute(
        select(Payment.method, func.sum(Payment.amount))
        .join(Sale)
        .where(in_day, ~voided)
        .group_by(Payment.method)
        .order_by(Payment.method)
    )
    return DailySales(
        date=day,
        sales_count=count,
        gross_total=Decimal(gross),
        discount_total=Decimal(discount),
        tax_total=Decimal(tax),
        voided_count=voided_count,
        voided_total=Decimal(voided_total),
        returns_total=Decimal(returns_total),
        net_total=Decimal(gross) - Decimal(returns_total),
        by_payment_method=[PaymentTotal(method=m.value, amount=Decimal(a)) for m, a in methods],
    )


async def stock_valuation(session: AsyncSession) -> StockValuation:
    rows = await session.execute(
        select(
            Product.id,
            Product.name,
            func.sum(Lot.quantity),
            func.sum(Lot.quantity * Lot.unit_cost),
        )
        .join(Lot, Lot.product_id == Product.id)
        .where(Lot.quantity > 0)
        .group_by(Product.id, Product.name)
        .order_by(Product.name)
    )
    result = [
        StockValuationRow(product_id=pid, product_name=name, quantity=int(qty), value=Decimal(val))
        for pid, name, qty, val in rows
    ]
    return StockValuation(total_value=sum((r.value for r in result), ZERO), rows=result)


async def expiring_lots(session: AsyncSession, days: int | None = None) -> list[ExpiringLot]:
    today = store_today()
    window = days if days is not None else get_settings().expiry_warning_days
    rows = await session.execute(
        select(Lot.id, Lot.product_id, Product.name, Lot.lot_number, Lot.expiry_date, Lot.quantity)
        .join(Product, Product.id == Lot.product_id)
        .where(Lot.quantity > 0, Lot.expiry_date <= today + timedelta(days=window))
        .order_by(Lot.expiry_date, Product.name)
    )
    return [
        ExpiringLot(
            lot_id=lot_id,
            product_id=pid,
            product_name=name,
            lot_number=number,
            expiry_date=expiry,
            quantity=qty,
            days_left=(expiry - today).days,
            expired=expiry <= today,
        )
        for lot_id, pid, name, number, expiry, qty in rows
    ]


async def low_stock(session: AsyncSession) -> list[LowStockRow]:
    stock = func.coalesce(func.sum(Lot.quantity), 0)
    rows = await session.execute(
        select(Product.id, Product.name, stock, Product.min_stock)
        .outerjoin(Lot, Lot.product_id == Product.id)
        .where(Product.is_active.is_(True), Product.min_stock > 0)
        .group_by(Product.id, Product.name, Product.min_stock)
        .having(stock < Product.min_stock)
        .order_by(Product.name)
    )
    return [
        LowStockRow(product_id=pid, product_name=name, stock=int(qty), min_stock=minimum)
        for pid, name, qty, minimum in rows
    ]


async def generate_alerts(session: AsyncSession, today: date | None = None) -> int:
    """Daily job: one alert per expiring/expired lot and low-stock product."""
    day = today or store_today()
    values = []
    for lot in await expiring_lots(session):
        kind = AlertType.EXPIRED if lot.expired else AlertType.EXPIRING
        when = "expired" if lot.expired else f"expires in {lot.days_left} days"
        values.append(
            {
                "type": kind,
                "product_id": lot.product_id,
                "lot_id": lot.lot_id,
                "alert_date": day,
                "message": f"{lot.product_name} lot {lot.lot_number} ({lot.quantity} units) {when}",
            }
        )
    for row in await low_stock(session):
        values.append(
            {
                "type": AlertType.LOW_STOCK,
                "product_id": row.product_id,
                "lot_id": None,
                "alert_date": day,
                "message": f"{row.product_name}: {row.stock} in stock, minimum {row.min_stock}",
            }
        )
    if not values:
        return 0
    stmt = insert(Alert).values(values).on_conflict_do_nothing(constraint="uq_alerts_daily")
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def acknowledge(session: AsyncSession, user: User, alert_id: int) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise NotFound("ALERT_NOT_FOUND", "Alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_by = user.id
        alert.acknowledged_at = datetime.now(UTC)
        await session.commit()
    return alert
