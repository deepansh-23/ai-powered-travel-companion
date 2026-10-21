"""Migration script for Admin Settings and Feedback enhancements.

Non-destructive:
- Adds `status` and `admin_notes` to `feedback` table (IF NOT EXISTS).
- Creates `app_settings` table (IF NOT EXISTS).
- Seeds initial default settings.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.db import get_engine, is_configured

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    if not is_configured():
        logger.error("Database is not configured.")
        return

    engine = get_engine()
    is_sqlite = str(engine.url).startswith("sqlite")

    async with engine.begin() as conn:
        logger.info("Checking and applying migrations...")

        # 1. Update feedback table
        if is_sqlite:
            # SQLite does not support IF NOT EXISTS in ADD COLUMN directly
            res = await conn.execute(text("PRAGMA table_info(feedback)"))
            cols = [r[1] for r in res.fetchall()]
            if "status" not in cols:
                logger.info("Adding 'status' column to feedback...")
                await conn.execute(text("ALTER TABLE feedback ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
            if "admin_notes" not in cols:
                logger.info("Adding 'admin_notes' column to feedback...")
                await conn.execute(text("ALTER TABLE feedback ADD COLUMN admin_notes TEXT"))
        else:
            logger.info("Adding columns to PostgreSQL feedback table if not existing...")
            await conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"))
            await conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS admin_notes TEXT"))

        # 2. Create app_settings table
        if is_sqlite:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key VARCHAR(60) PRIMARY KEY,
                    value TEXT NOT NULL,
                    description VARCHAR(200),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key VARCHAR(60) PRIMARY KEY,
                    value TEXT NOT NULL,
                    description VARCHAR(200),
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # 3. Seed default settings
        defaults = [
            ("maintenance_mode", "false", "Pause public access while retaining admin access"),
            ("public_notice_enabled", "false", "Display top announcement banner on travel site"),
            ("public_notice_text", "", "Text of announcement banner"),
            ("guest_mode_enabled", "true", "Allow unauthenticated visitors to use planner as guest"),
            ("allow_registration", "true", "Allow new users to create accounts"),
        ]

        for k, v, desc in defaults:
            if is_sqlite:
                await conn.execute(text(
                    "INSERT OR IGNORE INTO app_settings (key, value, description) VALUES (:k, :v, :desc)"
                ), {"k": k, "v": v, "desc": desc})
            else:
                await conn.execute(text("""
                    INSERT INTO app_settings (key, value, description)
                    VALUES (:k, :v, :desc)
                    ON CONFLICT (key) DO NOTHING
                """), {"k": k, "v": v, "desc": desc})

        logger.info("Migration completed successfully.")


if __name__ == "__main__":
    asyncio.run(migrate())
