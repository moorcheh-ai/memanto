import sqlite3
import os
from datetime import datetime, timedelta

class IdempotencyStore:
    def __init__(self, db_path=""idempotency.db""):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _clean_expired(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM idempotency WHERE expires_at < datetime('now')")
            conn.commit()

    def exists(self, key):
        self._clean_expired()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM idempotency WHERE key = ?", (key,))
            return cursor.fetchone() is not None

    def create(self, key, ttl_seconds=3600):
        self._clean_expired()
        expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO idempotency (key, created_at, expires_at) VALUES (?, ?, ?)",
                (key, datetime.now().isoformat(), expires_at)
            )
            conn.commit()
