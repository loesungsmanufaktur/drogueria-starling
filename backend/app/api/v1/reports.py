from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import Admin, Session, Staff
from app.core.config import store_today
from app.models.alerts import Alert
from app.schemas.reports import (
    AlertOut,
    DailySales,
    ExpiringLot,
    LowStockRow,
    StockValuation,
)
from app.services import reports as reports_service

router = APIRouter(tags=["reports"])


@router.get("/reports/daily-sales", response_model=DailySales)
async def daily_sales(session: Session, _: Staff, day: date | None = None) -> DailySales:
    return await reports_service.daily_sales(session, day or store_today())


@router.get("/reports/stock-valuation", response_model=StockValuation)
async def stock_valuation(session: Session, _: Staff) -> StockValuation:
    return await reports_service.stock_valuation(session)


@router.get("/reports/expiring", response_model=list[ExpiringLot])
async def expiring(
    session: Session, _: Staff, days: int | None = Query(None, ge=0, le=730)
) -> list[ExpiringLot]:
    return await reports_service.expiring_lots(session, days)


@router.get("/reports/low-stock", response_model=list[LowStockRow])
async def low_stock(session: Session, _: Staff) -> list[LowStockRow]:
    return await reports_service.low_stock(session)


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    session: Session, _: Staff, include_acknowledged: bool = False
) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.alert_date.desc(), Alert.id.desc()).limit(200)
    if not include_acknowledged:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))
    return list((await session.execute(stmt)).scalars())


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(session: Session, user: Staff, alert_id: int) -> Alert:
    return await reports_service.acknowledge(session, user, alert_id)


@router.post("/alerts/run", response_model=dict[str, int])
async def run_alerts(session: Session, _: Admin) -> dict[str, int]:
    """Run the daily alert job now (it also runs on schedule)."""
    return {"created": await reports_service.generate_alerts(session)}
