import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.reports import generate_alerts

log = logging.getLogger(__name__)


async def daily_alerts() -> None:
    async with SessionLocal() as session:
        created = await generate_alerts(session)
    log.info("daily alerts job created %s alerts", created)


def start_scheduler() -> AsyncIOScheduler:
    tz = get_settings().tz
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        daily_alerts,
        CronTrigger(hour=7, minute=0, timezone=tz),
        id="daily_alerts",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    return scheduler
