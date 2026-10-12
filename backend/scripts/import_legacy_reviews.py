"""One-off: copy the OLD anonymous reviews from data/app_storage.db into PostgreSQL.

Run once, from the project root:
    python backend/scripts/import_legacy_reviews.py

- Reviews keep their text, rating, service and date; they have no author (shown as "Traveller").
- Old History items are NOT copied: they belonged to nobody (decided with the project owner).
- Safe to run twice: reviews already imported are skipped.
"""

import asyncio
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.db_models import Feedback  # noqa: E402


def _read_old_reviews(sqlite_path: Path):
    con = sqlite3.connect(str(sqlite_path))
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT id, rating, comment, service_used, created_at FROM feedback").fetchall()
    finally:
        con.close()


def _parse_local(value: str) -> datetime:
    """Old dates were saved as local time 'YYYY-MM-DD HH:MM'; store them as UTC."""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


async def main() -> None:
    sqlite_path = settings.PROJECT_ROOT / "data" / "app_storage.db"
    if not sqlite_path.is_file():
        print(f"No old database found at {sqlite_path}. Nothing to import.")
        return

    await db.init_db()
    info = db.db_status()
    if not info["ready"]:
        print("Could not connect to the database:", info["error"])
        return

    rows = _read_old_reviews(sqlite_path)
    imported = skipped = 0
    async with AsyncSession(db.get_engine()) as session:
        for r in rows:
            new_id = f"legacy_{r['id']}"[:40]
            exists = (await session.execute(select(Feedback.id).where(Feedback.id == new_id))).first()
            if exists:
                skipped += 1
                continue
            session.add(Feedback(
                id=new_id, user_id=None, rating=int(r["rating"]), comment=r["comment"],
                service_used=r["service_used"], created_at=_parse_local(r["created_at"]),
            ))
            imported += 1
        await session.commit()
    await db.dispose_db()
    print(f"Done. Imported {imported} review(s), skipped {skipped} already present.")


if __name__ == "__main__":
    asyncio.run(main())
