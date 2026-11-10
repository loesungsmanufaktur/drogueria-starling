"""Database-level guarantees that back the business rules.

The same statements run from Alembic migrations (production) and from
``metadata.create_all`` (tests), so both schemas behave identically.
"""

from typing import Any

from sqlalchemy import MetaData, event, text
from sqlalchemy.engine import Connection

FORBID_CHANGES_FN = """
CREATE OR REPLACE FUNCTION forbid_changes() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% on % is not allowed: rows are immutable', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def immutable_table(table: str) -> list[str]:
    """Block UPDATE and DELETE on an append-only table."""
    return [
        f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}",
        f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION forbid_changes()",
    ]


# Statements grouped by the migration that introduces them, applied in order.
STATEMENTS: dict[str, list[str]] = {}


def register(group: str, statements: list[str]) -> None:
    STATEMENTS[group] = statements


def run_group(conn: Connection, group: str) -> None:
    for stmt in STATEMENTS[group]:
        conn.execute(text(stmt))


def install(metadata: MetaData) -> None:
    @event.listens_for(metadata, "after_create")
    def _after_create(target: MetaData, conn: Connection, **_: Any) -> None:
        for group in STATEMENTS:
            run_group(conn, group)
