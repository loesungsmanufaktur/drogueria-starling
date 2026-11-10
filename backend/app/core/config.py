from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_DIR / ".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    jwt_secret: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 12 * 60
    approval_token_expire_minutes: int = 5

    store_timezone: str = "America/Guatemala"
    cashier_discount_limit: Decimal = Decimal("10")  # percent
    expiry_warning_days: int = 90

    upload_dir: Path = BACKEND_DIR / "uploads"
    max_upload_mb: int = 10

    enable_scheduler: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.store_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def store_today() -> date:
    """Business date in the store's timezone (SEC-4)."""
    return datetime.now(get_settings().tz).date()
