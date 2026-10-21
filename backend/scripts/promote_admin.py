#!/usr/bin/env python3
"""One-time admin promotion script.

Usage (from the project root):
    python backend/scripts/promote_admin.py <username>

This script connects to the configured Aiven PostgreSQL database and
sets is_admin=True for the given username. It does NOT modify passwords
or expose any credentials. Run it only from a trusted, local environment.

The script is safe to run multiple times — promoting an already-admin
account is a no-op.
"""

import asyncio
import sys
from pathlib import Path

# Allow running from the project root or from the backend directory
_script_dir = Path(__file__).resolve().parent          # backend/scripts/
_backend_dir = _script_dir.parent                      # backend/
_project_root = _backend_dir.parent                    # project root

sys.path.insert(0, str(_backend_dir))
sys.path.insert(0, str(_project_root))

from sqlalchemy import select, update

# Load .env from project root before importing settings
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from app.db import get_engine, init_db
from app.db_models import User


async def promote(username: str) -> None:
    await init_db()
    engine = get_engine()

    async with engine.begin() as conn:
        # Find user
        result = await conn.execute(
            select(User.id, User.username, User.is_admin).where(
                User.username_lower == username.strip().lower()
            )
        )
        row = result.first()

        if row is None:
            print(f"[ERROR] No user found with username '{username}'.")
            return

        user_id, actual_username, already_admin = row

        if already_admin:
            print(f"[INFO] '{actual_username}' is already an admin. No changes made.")
            return

        await conn.execute(
            update(User).where(User.id == user_id).values(is_admin=True)
        )

    print(f"[SUCCESS] '{actual_username}' has been promoted to admin.")
    print("You can now log in and visit /admin to access the Admin Control Center.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python backend/scripts/promote_admin.py <username>")
        sys.exit(1)

    asyncio.run(promote(sys.argv[1]))
