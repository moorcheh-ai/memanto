from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.adapters import register_adapter
from core.models import MemoryEntity, MemoryType


@register_adapter
class ClaudeAdapter:
    name = "claude"

    def load(self, path: str) -> list[dict]:
        data_path = Path(path)
        if not data_path.exists():
            raise FileNotFoundError(
                f"File not found: {path}\nPlease check the path and try again."
            )
        try:
            if data_path.suffix == ".zip":
                import zipfile

                with zipfile.ZipFile(data_path) as zf:
                    names = zf.namelist()
                    conv_file = next(
                        (
                            n
                            for n in names
                            if "conversation" in n.lower() and n.endswith(".json")
                        ),
                        None,
                    )
                    if not conv_file:
                        raise FileNotFoundError(
                            "No conversation JSON found in zip archive"
                        )
                    with zf.open(conv_file) as f:
                        data = json.load(f)
            else:
                with open(data_path, encoding="utf-8") as f:
                    data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}") from e
        except PermissionError:
            raise PermissionError(f"Permission denied: {path}")

        if isinstance(data, dict):
            return data.get("conversations", [data])
        return data if isinstance(data, list) else [data]

    def get_conversation_list(self, raw: list[dict]) -> list[dict]:
        result = []
        for conv in raw:
            conv_id = conv.get("uuid", conv.get("id", "unknown"))
            conv_name = conv.get("name", f"Claude {str(conv_id)[:8]}")
            messages = conv.get("chat_messages") or conv.get("messages", [])
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
            conv_entities = self._extract_conversation(conv, filters)
            entities.extend(conv_entities)

        return entities

    def _extract_conversation(
        self, conv: dict, filters: dict | None
    ) -> list[MemoryEntity]:
        conv_id = conv.get("uuid", conv.get("id", "unknown"))
        conv_name = conv.get("name", f"Claude {str(conv_id)[:8]}")
        conv_type = conv.get("type", "conversation")

        if filters and filters.get("chat_ids") and conv_id not in filters["chat_ids"]:
            return []

        messages = conv.get("chat_messages") or conv.get("messages", [])
        if not messages:
            return []

        kw = filters.get("keyword") if filters else None
        keyword = kw.lower() if kw else None

        parts = []
        for m in messages:
            role = m.get("sender") or m.get("role", "unknown")
            text = self._extract_text(m)
            if text.strip():
                label = "Human" if role == "human" else "Assistant"
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

        ts_str = messages[-1].get("created_at") or messages[0].get("created_at")
        timestamp = self._parse_timestamp(ts_str)

        entity = MemoryEntity(
            source_type=MemoryType.CONTEXT,
            title=conv_name,
            content=full_content,
            tags=["claude", str(conv_id)[:8]],
            timestamp=timestamp,
            confidence=0.85,
            provenance="explicit_statement",
            source="claude",
            source_ref=f"claude://conversation/{conv_id}",
            metadata={"chat_id": conv_id, "conversation_type": conv_type},
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
