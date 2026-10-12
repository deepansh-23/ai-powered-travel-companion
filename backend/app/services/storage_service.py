"""Persistent SQLite storage for Search/Planning History and User Feedback (Reviews).
Survives application restarts and browser reloads (Sections 21, 24).
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.helpers import generate_id


class StorageService:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            data_dir = settings.PROJECT_ROOT / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "app_storage.db"
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY,
                    feature_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    rating INTEGER NOT NULL,
                    comment TEXT NOT NULL,
                    service_used TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    # --- History Operations ---

    def list_history(self, feature_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if feature_type and feature_type.strip().lower() not in ("all", ""):
                target = feature_type.strip().lower()
                # Support alias normalization (e.g. area_guide -> area, quiet_cafes -> cafes, medical_care -> medical)
                type_map = {
                    "area_guide": "area",
                    "quiet_cafes": "cafes",
                    "medical_care": "medical",
                }
                alias = type_map.get(target, target)
                cursor.execute(
                    "SELECT id, feature_type, title, preview, payload, created_at FROM history WHERE feature_type = ? OR feature_type = ? ORDER BY created_at DESC",
                    (target, alias)
                )
            else:
                cursor.execute(
                    "SELECT id, feature_type, title, preview, payload, created_at FROM history ORDER BY created_at DESC"
                )
            rows = cursor.fetchall()

        results = []
        for r in rows:
            try:
                payload = json.loads(r["payload"])
            except Exception:
                payload = {}
            results.append({
                "id": r["id"],
                "feature_type": r["feature_type"],
                "title": r["title"],
                "preview": r["preview"],
                "payload": payload,
                "created_at": r["created_at"]
            })
        return results

    def create_history(
        self,
        feature_type: str,
        title: str,
        preview: str,
        payload: Dict[str, Any],
        item_id: Optional[str] = None
    ) -> Dict[str, Any]:
        item_id = item_id or generate_id("hist")
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        payload_json = json.dumps(payload, ensure_ascii=False)

        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO history (id, feature_type, title, preview, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (item_id, feature_type, title, preview, payload_json, created_at)
            )
            conn.commit()

        return {
            "id": item_id,
            "feature_type": feature_type,
            "title": title,
            "preview": preview,
            "payload": payload,
            "created_at": created_at
        }

    def delete_history(self, item_id: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history WHERE id = ?", (item_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    # --- Feedback / Reviews Operations ---

    def list_feedback(self) -> List[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, rating, comment, service_used, created_at FROM feedback ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def create_feedback(self, rating: int, comment: str, service_used: Optional[str] = None) -> Dict[str, Any]:
        if not (1 <= rating <= 5):
            raise ValueError("Rating must be an integer between 1 and 5.")
        if not comment or not comment.strip():
            raise ValueError("Comment cannot be empty.")

        item_id = generate_id("rev")
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO feedback (id, rating, comment, service_used, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, rating, comment.strip(), service_used, created_at)
            )
            conn.commit()

        return {
            "id": item_id,
            "rating": rating,
            "comment": comment.strip(),
            "service_used": service_used,
            "created_at": created_at
        }


storage_service = StorageService()
