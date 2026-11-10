from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthorized
from app.core.security import create_token, decode_token, verify_password
from app.models import Role, User
from app.repositories import users as users_repo
from app.schemas.auth import ApprovalToken, TokenPair
from app.services import audit

APPROVER_ROLES = (Role.ADMIN, Role.PHARMACIST)


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    user = await users_repo.get_by_username(session, username)
    if user is None or not verify_password(user.password_hash, password):
        raise Unauthorized("INVALID_CREDENTIALS", "Invalid username or password")
    if not user.is_active:
        raise Unauthorized("USER_INACTIVE", "User is inactive")
    return user


def issue_tokens(user: User) -> TokenPair:
    settings = get_settings()
    return TokenPair(
        access_token=create_token(
            user.id, "access", settings.access_token_expire_minutes, role=user.role.value
        ),
        refresh_token=create_token(user.id, "refresh", settings.refresh_token_expire_minutes),
    )


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, "refresh")
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise Unauthorized("USER_INACTIVE", "User is inactive or does not exist")
    return issue_tokens(user)


async def grant_approval(session: AsyncSession, username: str, password: str) -> ApprovalToken:
    """A pharmacist/admin authorizes an action on someone else's terminal."""
    approver = await authenticate(session, username, password)
    if approver.role not in APPROVER_ROLES:
        raise Forbidden("APPROVER_ROLE_REQUIRED", "Only a pharmacist or admin can approve")
    minutes = get_settings().approval_token_expire_minutes
    token = create_token(approver.id, "approval", minutes, role=approver.role.value)
    audit.record(
        session.sync_session,
        "approval_granted",
        "users",
        approver.id,
        {"approver_id": approver.id},
    )
    await session.commit()
    return ApprovalToken(
        approval_token=token,
        approver_id=approver.id,
        approver_name=approver.full_name,
        expires_in_seconds=minutes * 60,
    )


async def resolve_approver(
    session: AsyncSession,
    actor: User,
    approval_token: str | None,
    roles: tuple[Role, ...] = APPROVER_ROLES,
) -> User | None:
    """Who authorizes a restricted action: the actor if their role allows it,
    otherwise the holder of a valid approval token with an allowed role."""
    if actor.role in roles:
        return actor
    if not approval_token:
        return None
    payload = decode_token(approval_token, "approval")
    approver = await session.get(User, int(payload["sub"]))
    if approver is None or not approver.is_active or approver.role not in roles:
        return None
    return approver


async def require_approver(
    session: AsyncSession,
    actor: User,
    approval_token: str | None,
    code: str,
    message: str,
    roles: tuple[Role, ...] = APPROVER_ROLES,
) -> User:
    approver = await resolve_approver(session, actor, approval_token, roles)
    if approver is None:
        raise Forbidden(code, message)
    return approver
