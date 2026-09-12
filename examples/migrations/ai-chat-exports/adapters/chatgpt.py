"""ChatGPT conversation export adapter.

Converts OpenAI ChatGPT conversation archives (JSON or ZIP) into
``MemoryEntity`` records suitable for OKF bundle generation.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.adapters import register_adapter
from core.models import MemoryEntity, MemoryType
from core.text import extract_text, parse_timestamp


@register_adapter
class ChatGPTAdapter:
    """Adapter for ChatGPT conversation exports."""

    name = "chatgpt"

    def load(self, path: str) -> dict:
        """Load a ChatGPT export from *path* (JSON file or ZIP archive).

        Returns a dict with a ``conversations`` key holding the list of
        conversation objects.
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

        if isinstance(data, list):
            return {"conversations": data}
        return data

    def get_conversation_list(self, raw: dict) -> list[dict]:
        """Return a summary list of conversations for the interactive picker."""
        result = []
        conversations = raw.get("conversations", [])
        for conv in conversations:
            conv_id = conv.get("id", conv.get("conversation_id", "unknown"))
            title = conv.get("title")
            if not isinstance(title, str) or not title.strip():
                title = f"ChatGPT {str(conv_id)[:8]}"
            messages = conv.get("messages") or []
            result.append(
                {
                    "id": str(conv_id),
                    "title": title,
                    "message_count": len(messages),
                }
            )
        return result

    def extract(self, raw: dict, filters: dict | None = None) -> list[MemoryEntity]:
        """Extract ``MemoryEntity`` records from all conversations.

        Supports both the ``conversations`` list format and the legacy
        ``mapping`` graph format used by older ChatGPT exports.
        """
        entities: list[MemoryEntity] = []

        conversations = raw.get("conversations", [])
        if conversations:
            for conv in conversations:
                entities.extend(self._extract_conversation(conv, filters))
            return entities

        mapping = raw.get("mapping", {})
        if mapping:
            entities.extend(self._extract_from_mapping(mapping, filters))
            return entities

        return entities

    def _extract_conversation(
        self, conv: dict, filters: dict | None
    ) -> list[MemoryEntity]:
        """Convert a single conversation dict into a list of memory entities."""
        conv_id = conv.get("id", conv.get("conversation_id", "unknown"))
        title = conv.get("title")
        if not isinstance(title, str) or not title.strip():
            title = f"ChatGPT {str(conv_id)[:8]}"

        if filters and filters.get("chat_ids") and conv_id not in filters["chat_ids"]:
            return []

        messages = conv.get("messages") or conv.get("mapping", {})
        if isinstance(messages, dict):
            messages = self._flatten_mapping(messages)

        parts = []
        for user_msg, assistant_msg in self._pair_messages(messages):
            content_parts = []
            if user_msg:
                content_parts.append(f"**User:** {extract_text(user_msg)}")
            if assistant_msg:
                content_parts.append(
                    f"**Assistant:** {extract_text(assistant_msg)}"
                )

            if content_parts:
                parts.append("\n\n".join(content_parts))

        if not parts:
            return []

        content = "\n\n".join(parts)

        if filters and filters.get("keyword"):
            kw = filters["keyword"].lower()
            if kw not in content.lower() and kw not in title.lower():
                return []

        timestamp = None
        for msg in reversed(messages):
            if msg.get("create_time"):
                timestamp = parse_timestamp(msg["create_time"])
                break

        return [
            MemoryEntity(
                source_type=MemoryType.CONTEXT,
                title=title,
                content=content,
                tags=["chatgpt", str(conv_id)[:8]],
                timestamp=timestamp,
                confidence=0.85,
                provenance="explicit_statement",
                source="chatgpt",
                source_ref=f"chatgpt://conversation/{conv_id}",
                metadata={"chat_id": conv_id},
            )
        ]

    def _extract_from_mapping(
        self, mapping: dict, filters: dict | None
    ) -> list[MemoryEntity]:
        """Extract memories from the legacy ``mapping`` graph format."""
        root_id = next(
            (nid for nid, node in mapping.items() if node.get("parent") is None),
            None,
        )
        if not root_id:
            root_id = next(iter(mapping), None)
        if not root_id:
            return []

        ordered = self._traverse_graph(mapping, root_id)

        messages = []
        for node_id in ordered:
            node = mapping.get(node_id, {})
            msg = node.get("message")
            if msg and msg.get("content"):
                text = extract_text(msg)
                if text.strip():
                    messages.append(
                        {
                            "role": msg.get("author", {}).get("role", "unknown"),
                            "text": text,
                            "create_time": msg.get("create_time"),
                            "node_id": node_id,
                        }
                    )

        conv_id = messages[0]["node_id"][:8] if messages else "unknown"

        if filters:
            if filters.get("chat_ids") and conv_id not in filters["chat_ids"]:
                return []
            if filters.get("keyword"):
                kw = filters["keyword"].lower()
                if not any(kw in m["text"].lower() for m in messages):
                    return []

        parts = []
        i = 0
        while i < len(messages):
            if messages[i]["role"] != "user":
                i += 1
                continue

            user_m = messages[i]
            asst_m = None
            j = i + 1
            while j < len(messages) and messages[j]["role"] not in ("user", "assistant"):
                j += 1
            if j < len(messages) and messages[j]["role"] == "assistant":
                asst_m = messages[j]
                i = j + 1
            else:
                i += 1

            block = []
            block.append(f"**User:** {user_m['text']}")
            if asst_m:
                block.append(f"**Assistant:** {asst_m['text']}")
            parts.append("\n\n".join(block))

        if not parts:
            return []

        timestamp = parse_timestamp(messages[-1].get("create_time"))

        return [
            MemoryEntity(
                source_type=MemoryType.CONTEXT,
                title=f"ChatGPT {conv_id}",
                content="\n\n".join(parts),
                tags=["chatgpt", conv_id],
                timestamp=timestamp,
                confidence=0.85,
                provenance="explicit_statement",
                source="chatgpt",
                source_ref=f"chatgpt://conversation/{conv_id}",
                metadata={"chat_id": conv_id},
            )
        ]

    def _traverse_graph(self, mapping: dict, start_id: str) -> list[str]:
        """Walk the mapping graph in breadth-first order from *start_id*."""
        children: dict[str | None, list[str]] = {}
        for nid, node in mapping.items():
            parent = node.get("parent")
            children.setdefault(parent, []).append(nid)

        order: list[str] = []
        stack = [start_id]
        visited: set[str] = set()

        while stack:
            nid = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            order.append(nid)
            kids = children.get(nid, [])
            stack.extend(reversed(kids))

        return order

    def _flatten_mapping(self, mapping: dict) -> list[dict]:
        """Flatten the mapping graph into an ordered list of message dicts."""
        root_id = next(
            (nid for nid, node in mapping.items() if node.get("parent") is None),
            None,
        )
        if not root_id:
            return []

        order = self._traverse_graph(mapping, root_id)
        messages = []
        for nid in order:
            node = mapping.get(nid, {})
            msg = node.get("message")
            if msg:
                messages.append(msg)
        return messages

    def _pair_messages(
        self, messages: list[dict]
    ) -> list[tuple[dict | None, dict | None]]:
        """Pair consecutive user/assistant messages by role.

        Handles system messages (skipped), odd-length conversations (last
        user message paired with ``None``), and consecutive same-role messages.
        """
        pairs: list[tuple[dict | None, dict | None]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("author", {}).get("role", "unknown")
            if role == "user":
                user_msg = msg
                asst_msg = None
                j = i + 1
                while j < len(messages) and messages[j].get("author", {}).get("role") not in ("user", "assistant"):
                    j += 1
                if j < len(messages) and messages[j].get("author", {}).get("role") == "assistant":
                    asst_msg = messages[j]
                    i = j + 1
                else:
                    i += 1
                pairs.append((user_msg, asst_msg))
            else:
                i += 1
        return pairs

    def get_source_stats(self) -> dict:
        """Return aggregate statistics for this source (stub)."""
        return {
            "source": self.name,
            "total_conversations": 0,
            "total_messages": 0,
            "date_range": {"first": None, "last": None},
        }
