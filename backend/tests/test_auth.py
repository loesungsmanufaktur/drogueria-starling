import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Role
from tests.factories import PASSWORD, auth, make_user


async def login(client: AsyncClient, username: str, password: str = PASSWORD) -> dict:  # type: ignore[type-arg]
    resp = await client.post(
        "/api/v1/auth/token", data={"username": username, "password": password}
    )
    return {"status": resp.status_code, **resp.json()}


async def test_login_returns_tokens_and_me(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session, Role.CASHIER, "ana")
    result = await login(client, "ANA")
    assert result["status"] == 200
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {result['access_token']}"}
    )
    assert me.json()["id"] == user.id

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": result["refresh_token"]}
    )
    assert refreshed.status_code == 200


async def test_login_rejects_bad_password_and_inactive_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session, Role.CASHIER, "bob")
    assert (await login(client, "bob", "wrong-password"))["code"] == "INVALID_CREDENTIALS"
    user.is_active = False
    await session.commit()
    assert (await login(client, "bob"))["code"] == "USER_INACTIVE"


async def test_refresh_token_cannot_be_used_as_access_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(session, Role.ADMIN, "root")
    tokens = await login(client, "root")
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


async def test_sec2_cashier_cannot_manage_users(client: AsyncClient, session: AsyncSession) -> None:
    cashier = await make_user(session, Role.CASHIER)
    resp = await client.get("/api/v1/users", headers=auth(cashier))
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN_ROLE"


async def test_admin_creates_user_and_change_is_audited_without_password(
    client: AsyncClient, session: AsyncSession
) -> None:
    admin = await make_user(session, Role.ADMIN)
    resp = await client.post(
        "/api/v1/users",
        headers=auth(admin),
        json={
            "username": "Maria",
            "full_name": "María",
            "role": "pharmacist",
            "password": "x" * 10,
        },
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]

    entries = (
        (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "users", AuditLog.entity_id == str(new_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == "create"
    assert entry.user_id == admin.id
    assert entry.after is not None and entry.after["username"] == "maria"
    assert "password_hash" not in entry.after

    dup = await client.post(
        "/api/v1/users",
        headers=auth(admin),
        json={"username": "maria", "full_name": "Dup", "role": "cashier", "password": "x" * 10},
    )
    assert dup.json()["code"] == "USERNAME_TAKEN"


async def test_sec1_update_records_before_and_after(
    client: AsyncClient, session: AsyncSession
) -> None:
    admin = await make_user(session, Role.ADMIN)
    cashier = await make_user(session, Role.CASHIER)
    await client.patch(
        f"/api/v1/users/{cashier.id}", headers=auth(admin), json={"is_active": False}
    )
    resp = await client.get(
        "/api/v1/audit", headers=auth(admin), params={"entity": "users", "entity_id": cashier.id}
    )
    update = next(e for e in resp.json() if e["action"] == "update")
    assert update["before"]["is_active"] is True
    assert update["after"]["is_active"] is False


async def test_sec1_audit_log_is_append_only(session: AsyncSession) -> None:
    await make_user(session, Role.ADMIN)
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(text("UPDATE audit_log SET action = 'tampered'"))
    await session.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(text("DELETE FROM audit_log"))
    await session.rollback()


async def test_approval_token_only_for_pharmacist_or_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    cashier = await make_user(session, Role.CASHIER, "cash1")
    await make_user(session, Role.PHARMACIST, "pharma1")

    ok = await client.post(
        "/api/v1/auth/approvals",
        headers=auth(cashier),
        json={"username": "pharma1", "password": PASSWORD},
    )
    assert ok.status_code == 200
    assert ok.json()["approval_token"]

    denied = await client.post(
        "/api/v1/auth/approvals",
        headers=auth(cashier),
        json={"username": "cash1", "password": PASSWORD},
    )
    assert denied.json()["code"] == "APPROVER_ROLE_REQUIRED"
