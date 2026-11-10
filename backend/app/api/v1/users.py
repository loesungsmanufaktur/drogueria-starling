from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import Admin, Session
from app.models import AuditLog
from app.repositories import users as users_repo
from app.schemas.auth import AuditOut, UserCreate, UserOut, UserUpdate
from app.services import users as users_service

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserOut])
async def list_users(session: Session, _: Admin) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await users_repo.list_users(session)]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(session: Session, _: Admin, body: UserCreate) -> UserOut:
    return UserOut.model_validate(await users_service.create_user(session, body))


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(session: Session, _: Admin, user_id: int, body: UserUpdate) -> UserOut:
    return UserOut.model_validate(await users_service.update_user(session, user_id, body))


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    session: Session,
    _: Admin,
    entity: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AuditOut]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    rows = (await session.execute(stmt)).scalars()
    return [AuditOut.model_validate(r) for r in rows]
