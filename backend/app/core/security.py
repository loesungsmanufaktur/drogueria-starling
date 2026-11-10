from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.errors import Unauthorized

TokenType = Literal["access", "refresh", "approval"]

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(subject: int, token_type: TokenType, minutes: int, **claims: Any) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        **claims,
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, get_settings().jwt_secret, algorithms=[_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("TOKEN_EXPIRED", "Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("TOKEN_INVALID", "Token is invalid") from exc
    if payload.get("type") != expected_type:
        raise Unauthorized("TOKEN_INVALID", "Wrong token type")
    return payload
