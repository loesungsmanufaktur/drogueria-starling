"""Small helpers to build test data directly through the ORM."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_token, hash_password
from app.models import Role, User

PASSWORD = "secret-pass-123"


async def make_user(
    session: AsyncSession, role: Role = Role.CASHIER, username: str | None = None
) -> User:
    user = User(
        username=username or f"{role.value}{id(object())}",
        full_name=f"Test {role.value}",
        role=role,
        password_hash=hash_password(PASSWORD),
    )
    session.add(user)
    await session.commit()
    return user


def auth(user: User) -> dict[str, str]:
    token = create_token(user.id, "access", get_settings().access_token_expire_minutes)
    return {"Authorization": f"Bearer {token}"}


def approval(user: User) -> dict[str, str]:
    token = create_token(user.id, "approval", get_settings().approval_token_expire_minutes)
    return {"X-Approval-Token": token}
