"""Memanto adapter for LangGraph integration.

Provides cross-session memory for LangGraph agents using Memanto's semantic storage.
Falls back to local JSON storage when no Memanto API key is configured.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional


class MemantoAdapter:
    """Adapter that wraps Memanto for use inside LangGraph nodes.

    Stores memories as structured records with type, content, tags, and confidence.
    Supports both Memanto cloud (via SdkClient) and local SQLite fallback.
    """

    def __init__(self, api_key: Optional[str] = None, db_path: str = "memories.db"):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY")
        self.db_path = db_path
        self._use_local = not self.api_key
        if self._use_local:
            self._init_local_db()
        else:
            self._init_memanto()

    def _init_local_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                memory_type TEXT,
                title TEXT,
                content TEXT,
                tags TEXT,
                confidence REAL DEFAULT 0.8,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _init_memanto(self):
        try:
            from memanto.cli.client.sdk_client import SdkClient
            self._client = SdkClient(api_key=self.api_key)
            self._agent_id = f"langgraph-agent-{datetime.now().strftime('%Y%m%d')}"
            self._client.create_agent(self._agent_id, pattern="tool", description="LangGraph support agent")
            self._client.activate_agent(self._agent_id, duration_hours=24)
        except Exception as e:
            print(f"Memanto cloud init failed, falling back to local: {e}")
            self._use_local = True
            self._init_local_db()

    def store(self, session_id: str, memory_type: str, title: str, content: str,
              tags: Optional[list[str]] = None, confidence: float = 0.8) -> dict[str, Any]:
        if not self._use_local:
            return self._store_memanto(session_id, memory_type, title, content, tags, confidence)
        return self._store_local(session_id, memory_type, title, content, tags, confidence)

    def recall(self, session_id: str, query: str, limit: int = 5,
               memory_types: Optional[list[str]] = None) -> list[dict[str, Any]]:
        if not self._use_local:
            return self._recall_memanto(session_id, query, limit, memory_types)
        return self._recall_local(session_id, query, limit, memory_types)

    def _store_local(self, session_id, memory_type, title, content, tags, confidence):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO memories (session_id, memory_type, title, content, tags, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, memory_type, title, content, json.dumps(tags or []), confidence,
             datetime.utcnow().isoformat())
        )
        conn.commit()
        memory_id = conn.lastrowid
        conn.close()
        return {"memory_id": str(memory_id), "status": "stored", "mode": "local"}

    def _store_memanto(self, session_id, memory_type, title, content, tags, confidence):
        try:
            result = self._client.remember(
                agent_id=self._agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tags or [],
                source="agent",
                provenance="observed",
            )
            return result
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def _recall_local(self, session_id, query, limit, memory_types):
        conn = sqlite3.connect(self.db_path)
        query_lower = query.lower()
        sql = "SELECT * FROM memories WHERE (LOWER(title) LIKE ? OR LOWER(content) LIKE ?)"
        params = [f"%{query_lower}%", f"%{query_lower}%"]
        if memory_types:
            placeholders = ",".join("?" * len(memory_types))
            sql += f" AND memory_type IN ({placeholders})"
            params.extend(memory_types)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [
            {"id": r[0], "session_id": r[1], "type": r[2], "title": r[3],
             "content": r[4], "tags": json.loads(r[5] or "[]"), "confidence": r[6],
             "created_at": r[7]}
            for r in rows
        ]

    def _recall_memanto(self, session_id, query, limit, memory_types):
        try:
            result = self._client.recall(
                agent_id=self._agent_id,
                query=query,
                limit=limit,
                type=memory_types,
            )
            return result.get("memories", [])
        except Exception as e:
            return [{"error": str(e)}]

    def get_cross_session_memories(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve memories from ALL sessions for a user, demonstrating cross-session recall."""
        return self.recall(session_id=user_id, query="", limit=limit)
