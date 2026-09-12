"""Gemini conversation export adapter.

Converts Google Gemini conversation archives (JSON or ZIP) into
``MemoryEntity`` records suitable for OKF bundle generation.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.adapters import register_adapter
from core.models import MemoryEntity, MemoryType
from core.text import extract_text, parse_timestamp


@register_adapter
class GeminiAdapter:
    """Adapter for Google Gemini conversation exports."""

    name = "gemini"

    def load(self, path: str) -> list[dict]:
        """Load a Gemini export from *path* (JSON file or ZIP archive).

        Returns a list of conversation dicts.
        """
        data_path = Path(path)
        if data_path.suffix == ".zip":
            import zipfile

            with zipfile.ZipFile(data_path) as zf:
                names = zf.namelist()
                conv_file = next(
                    (n for n in names if n.endswith("conversations.json")), None
                )
                if not conv_file:
                    raise FileNotFoundError(
                        "No conversations.json found in zip archive"
                    )
                with zf.open(conv_file) as f:
                    data = json.load(f)
        else:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

        if isinstance(data, dict):
            return data.get("conversations", [data])
        return data if isinstance(data, list) else [data]

    def get_conversation_list(self, raw: list[dict]) -> list[dict]:
        """Return a summary list of conversations for the interactive picker."""
        result = []
        for conv in raw:
            conv_id = conv.get("id", conv.get("conversation_id", "unknown"))
            conv_name = conv.get("title", f"Gemini {str(conv_id)[:8]}")
            messages = conv.get("messages") or conv.get("chat_messages", [])
            result.append(
                {
                    "id": str(conv_id),
                    "title": conv_name,
                    "message_count": len(messages),
                }
            )
        return result

    def extract(
        self, raw: list[dict], filters: dict | None = None
    ) -> list[MemoryEntity]:
        """Extract ``MemoryEntity`` records from all conversations."""
        entities: list[MemoryEntity] = []

        for conv in raw:
            entities.extend(self._extract_conversation(conv, filters))

        return entities

    def _extract_conversation(
        self, conv: dict, filters: dict | None
    ) -> list[MemoryEntity]:
        """Convert a single conversation dict into a list of memory entities."""
        conv_id = conv.get("id", conv.get("conversation_id", "unknown"))
        conv_name = conv.get("title", f"Gemini {str(conv_id)[:8]}")

        if filters and filters.get("chat_ids") and conv_id not in filters["chat_ids"]:
            return []

        messages = conv.get("messages") or conv.get("chat_messages", [])
        if not messages:
            return []

        kw = filters.get("keyword") if filters else None
        keyword = kw.lower() if kw else None

        parts = []
        for m in messages:
            role = m.get("role") or m.get("sender", "unknown")
            text = extract_text(m)
            if text.strip():
                label = "User" if role == "user" else "Assistant"
                parts.append(f"**{label}:** {text}")

        if not parts:
            return []

        full_content = "\n\n".join(parts)

        if (
            keyword
            and keyword not in full_content.lower()
            and keyword not in conv_name.lower()
        ):
            return []

        ts_str = (
            messages[-1].get("timestamp")
            or messages[-1].get("created_at")
            or conv.get("create_time")
        )
        timestamp = parse_timestamp(ts_str)

        entity = MemoryEntity(
            source_type=MemoryType.CONTEXT,
            title=conv_name,
            content=full_content,
            tags=["gemini", str(conv_id)[:8]],
            timestamp=timestamp,
            confidence=0.85,
            provenance="explicit_statement",
            source="gemini",
            source_ref=f"gemini://conversation/{conv_id}",
            metadata={"chat_id": conv_id},
        )

        return [entity]

    def get_source_stats(self) -> dict:
        """Return aggregate statistics for this source (stub)."""
        return {
            "source": self.name,
            "total_conversations": 0,
            "total_messages": 0,
            "date_range": {"first": None, "last": None},
        }
