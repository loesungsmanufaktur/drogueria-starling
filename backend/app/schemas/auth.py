from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import Role
from app.schemas.common import ORMModel


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ApprovalRequest(BaseModel):
    username: str
    password: str


class ApprovalToken(BaseModel):
    approval_token: str
    approver_id: int
    approver_name: str
    expires_in_seconds: int


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class AuditOut(ORMModel):
    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
