from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from app.core.config import get_settings


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=get_settings().tz)
    scheduler.start()
    return scheduler
