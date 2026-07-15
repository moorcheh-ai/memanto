"""
Conversation memory extraction service.

Turns chat-style message history into typed memory candidates using the same
Moorcheh answer-generation path used by the RAG answer endpoint.
"""

from __future__ import annotations

import json
import re
from typing import Any

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.constants import VALID_MEMORY_TYPES


class ConversationMemoryExtractionService:
    """Extract typed memory candidates from conversation turns."""

    MAX_MESSAGES = 200
    MAX_MEMORIES = 100
    MAX_CONTENT_CHARS = 12_000

    def __init__(self, client: Any) -> None:
        self.client = client

    def extract(
        self,
        *,
        namespace: str,
        messages: list[dict[str, str]],
        max_memories: int = 20,
        ai_model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return normalized memory candidates extracted from messages."""

        from memanto.app.config import settings

        self._validate_messages(messages)
        max_memories = max(1, min(max_memories, self.MAX_MEMORIES))

        generate_kwargs: dict[str, Any] = {
            "namespace": namespace,
            "query": self._conversation_text(messages),
            "top_k": 1,
            "temperature": 0,
            "kiosk_mode": False,
            "header_prompt": self._header_prompt(max_memories),
            "footer_prompt": self._footer_prompt(),
        }
        resolved_ai_model = (
            ai_model
            if ai_model is not None
            else get_active_llm_model(settings.ANSWER_MODEL)
        )
        if resolved_ai_model is not None:
            generate_kwargs["ai_model"] = resolved_ai_model

        response = self.client.answer.generate(**generate_kwargs)

        raw_answer = response.get("answer", "")
        parsed = self._parse_json_answer(raw_answer)
        return self._normalize_candidates(parsed, max_memories=max_memories)

    def _validate_messages(self, messages: list[dict[str, str]]) -> None:
        if not messages:
            raise ValueError("Conversation must contain at least one message")
        if len(messages) > self.MAX_MESSAGES:
            raise ValueError(
                f"Conversation has {len(messages)} messages; maximum is {self.MAX_MESSAGES}"
            )

        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValueError(f"Message {index} must be an object")
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or not role.strip():
                raise ValueError(f"Message {index} is missing a non-empty role")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"Message {index} is missing non-empty content")

    def _conversation_text(self, messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        total = 0
        for message in messages:
            line = f"{message['role'].strip()}: {message['content'].strip()}"
            total += len(line)
            if total > self.MAX_CONTENT_CHARS:
                break
            lines.append(line)
        return "\n".join(lines)

    def _header_prompt(self, max_memories: int) -> str:
        memory_types = ", ".join(sorted(VALID_MEMORY_TYPES))
        return (
            "Extract durable agent memories from the conversation. "
            "Only include facts, preferences, decisions, instructions, goals, "
            "commitments, errors, observations, relationships, context, events, "
            "artifacts, or learnings that would be useful in future sessions. "
            "Do not include secrets, API keys, passwords, tokens, or transient chatter. "
            f"Return at most {max_memories} memories. Valid types: {memory_types}."
        )

    def _footer_prompt(self) -> str:
        return (
            "Return only JSON. The JSON must be an array of objects with keys: "
            "type, title, content, confidence. Confidence must be 0.0 to 1.0."
        )

    def _parse_json_answer(self, answer: str) -> Any:
        text = answer.strip()
        if not text:
            raise ValueError("Memory extraction returned an empty response")

        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise ValueError("Memory extraction did not return valid JSON")

    def _normalize_candidates(
        self, parsed: Any, *, max_memories: int
    ) -> list[dict[str, Any]]:
        if not isinstance(parsed, list):
            raise ValueError("Memory extraction response must be a JSON array")

        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str | None, str]] = set()

        for item in parsed:
            if not isinstance(item, dict):
                continue

            content = str(item.get("content", "")).strip()
            if not content:
                continue

            memory_type = item.get("type")
            if memory_type:
                memory_type = str(memory_type).strip().lower()
                if memory_type not in VALID_MEMORY_TYPES:
                    memory_type = None
            else:
                memory_type = None

            title = str(item.get("title") or content[:80]).strip()
            title = title[:100]

            try:
                confidence = float(item.get("confidence", 0.8))
            except (TypeError, ValueError):
                confidence = 0.8
            confidence = max(0.0, min(confidence, 1.0))

            key = (memory_type, re.sub(r"\s+", " ", content).lower())
            if key in seen:
                continue
            seen.add(key)

            normalized.append(
                {
                    "type": memory_type,
                    "title": title,
                    "content": content,
                    "confidence": confidence,
                    "source": "conversation",
                    "provenance": "inferred",
                }
            )
            if len(normalized) >= max_memories:
                break

        if not normalized:
            raise ValueError("Memory extraction produced no usable candidates")

        return normalized
