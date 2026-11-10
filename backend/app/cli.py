"""Management commands.

    uv run python -m app.cli create-admin --username admin --full-name "Store Admin"

The password is read from ADMIN_PASSWORD or prompted, never passed as an argument.
"""

import argparse
import asyncio
import getpass
import os
import sys

from app.core.errors import AppError
from app.db.session import SessionLocal, engine
from app.services.users import create_admin


async def _create_admin(username: str, full_name: str, password: str) -> None:
    async with SessionLocal() as session:
        user = await create_admin(session, username, full_name, password)
        print(f"Created admin '{user.username}' (id {user.id})")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create an admin user")
    admin.add_argument("--username", required=True)
    admin.add_argument("--full-name", required=True)
    args = parser.parse_args()

    if args.command == "create-admin":
        password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
        if len(password) < 8:
            sys.exit("Password must be at least 8 characters")
        try:
            asyncio.run(_create_admin(args.username, args.full_name, password))
        except AppError as exc:
            sys.exit(exc.detail)


if __name__ == "__main__":
    main()
