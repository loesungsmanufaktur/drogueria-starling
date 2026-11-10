from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.db.session import get_session
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

Session = Annotated[AsyncSession, Depends(get_session)]
ApprovalToken = Annotated[str | None, Header(alias="X-Approval-Token")]


async def get_current_user(
    session: Session, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> User:
    if not token:
        raise Unauthorized("NOT_AUTHENTICATED", "Authentication required")
    payload = decode_token(token, "access")
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise Unauthorized("USER_INACTIVE", "User is inactive or does not exist")
    # The audit trail attributes every change in this request to this user.
    session.info["actor_id"] = user.id
    return user


def require_roles(*roles: Role) -> Callable[[User], Awaitable[User]]:
    """Backend role check (SEC-2). With no roles, any authenticated user passes."""

    async def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if roles and user.role not in roles:
            raise Forbidden("FORBIDDEN_ROLE", "Your role cannot perform this action")
        return user

    return dependency


AnyUser = Annotated[User, Depends(require_roles())]
Staff = Annotated[User, Depends(require_roles(Role.ADMIN, Role.PHARMACIST))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
