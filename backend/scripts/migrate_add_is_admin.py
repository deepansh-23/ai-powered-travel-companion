"""Apply minimal migration: add is_admin column to users table if not present.

Run from the project root:
    python backend/scripts/migrate_add_is_admin.py
"""
import asyncio
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_backend_dir = _script_dir.parent
_project_root = _backend_dir.parent

sys.path.insert(0, str(_backend_dir))
sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv
load_dotenv(_project_root / ".env")

from sqlalchemy import text


async def run():
    from app.db import get_engine, init_db
    await init_db()
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='is_admin'"
        ))
        exists = result.scalar_one_or_none()
        if exists:
            print("[OK] is_admin column already exists — no migration needed.")
        else:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            print("[SUCCESS] is_admin column added to users table.")


if __name__ == "__main__":
    asyncio.run(run())
