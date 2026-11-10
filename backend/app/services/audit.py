"""Automatic audit trail (SEC-1).

Every flush that creates, updates or deletes an ORM row writes an
``audit_log`` entry with who, when, what and before/after values. The actor is
read from ``session.info["actor_id"]``, which the auth dependency sets.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import Session, UOWTransaction

from app.models.audit import AuditLog

# Never copied into the audit trail.
_REDACTED = {"password_hash"}
_SKIP_TABLES = {AuditLog.__tablename__}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _columns(obj: Any) -> list[str]:
    return [a.key for a in inspect(obj).mapper.column_attrs if a.key not in _REDACTED]


def _snapshot(obj: Any) -> dict[str, Any]:
    return {key: _jsonable(getattr(obj, key)) for key in _columns(obj)}


def _previous(obj: Any) -> dict[str, Any]:
    state = inspect(obj)
    before = {}
    for key in _columns(obj):
        history = state.attrs[key].history
        value = history.deleted[0] if history.deleted else getattr(obj, key)
        before[key] = _jsonable(value)
    return before


def _entity_id(obj: Any) -> str | None:
    # Read the primary key from the instance: new rows have no identity key yet.
    key = inspect(obj).mapper.primary_key_from_instance(obj)
    return None if any(v is None for v in key) else ",".join(str(v) for v in key)


def actor_id(session: Session) -> int | None:
    value = session.info.get("actor_id")
    return int(value) if value is not None else None


def record(
    session: Session,
    action: str,
    entity: str,
    entity_id: Any = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Write an explicit audit entry for events that are not plain row changes."""
    session.add(
        AuditLog(
            user_id=actor_id(session),
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            after={k: _jsonable(v) for k, v in (after or {}).items()},
        )
    )


@event.listens_for(Session, "after_flush")
def _audit_after_flush(session: Session, _: UOWTransaction) -> None:
    user_id = actor_id(session)
    rows: list[dict[str, Any]] = []

    def add(action: str, obj: Any, before: Any, after: Any) -> None:
        table = inspect(obj).mapper.local_table.name
        if table in _SKIP_TABLES:
            return
        rows.append(
            {
                "user_id": user_id,
                "action": action,
                "entity": table,
                "entity_id": _entity_id(obj),
                "before": before,
                "after": after,
            }
        )

    for obj in session.new:
        add("create", obj, None, _snapshot(obj))
    for obj in session.dirty:
        if session.is_modified(obj, include_collections=False):
            before, after = _previous(obj), _snapshot(obj)
            if before != after:
                add("update", obj, before, after)
    for obj in session.deleted:
        add("delete", obj, _snapshot(obj), None)

    if rows:
        session.connection().execute(insert(AuditLog), rows)
