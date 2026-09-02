from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.adapters import register_adapter
from core.models import MemoryEntity, MemoryType


@register_adapter
class GeminiAdapter:
    name = "gemini"

    def load(self, path: str) -> list[dict]:
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
        entities: list[MemoryEntity] = []

        for conv in raw:
            entities.extend(self._extract_conversation(conv, filters))

        return entities

    def _extract_conversation(
        self, conv: dict, filters: dict | None
    ) -> list[MemoryEntity]:
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
            text = self._extract_text(m)
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
        timestamp = self._parse_timestamp(ts_str)

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

    def _extract_text(self, msg: dict) -> str:
        if "text" in msg:
            return msg["text"] or ""
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, str):
                    texts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            return "\n".join(texts)
        return str(content)

    def _parse_timestamp(self, ts) -> datetime | None:
        if ts is None:
            return None
        try:
            if isinstance(ts, str):
                for fmt in (
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S",
                ):
                    try:
                        return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            pass
        return None

    def get_source_stats(self) -> dict:
        return {
            "source": self.name,
            "total_conversations": 0,
            "total_messages": 0,
            "date_range": {"first": None, "last": None},
        }
