from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.security import hash_password
from app.models import Role, User
from app.repositories import users as users_repo
from app.schemas.auth import UserCreate, UserUpdate


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    username = data.username.lower()
    if await users_repo.get_by_username(session, username):
        raise Conflict("USERNAME_TAKEN", "Username already exists")
    user = User(
        username=username,
        full_name=data.full_name,
        role=data.role,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await session.commit()
    return user


async def update_user(session: AsyncSession, user_id: int, data: UserUpdate) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("USER_NOT_FOUND", "User not found")
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password is not None:
        user.password_hash = hash_password(data.password)
    await session.commit()
    return user


async def create_admin(session: AsyncSession, username: str, full_name: str, password: str) -> User:
    return await create_user(
        session,
        UserCreate(username=username, full_name=full_name, role=Role.ADMIN, password=password),
    )
