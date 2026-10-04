"""
Conversation memory extraction service.

Turns chat-style message history into typed memory candidates using the same
Moorcheh answer-generation path used by the RAG answer endpoint.
"""

from __future__ import annotations

import re
from typing import Any

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.app.utils.json_extraction import iter_json_arrays

_PRIVATE_KEY_HEADER_RUN = re.compile(r"[A-Z0-9_\- ]+")
_PRIVATE_KEY_SUFFIX = "PRIVATE KEY-----"
API_KEY_PATTERNS = [
    re.compile(r"\b(?:sk-(?:proj-|ant-|live-)?[A-Za-z0-9_\-]{20,})\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),
    re.compile(r"\bya29\.[0-9A-Za-z_\-]+\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
]
BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9_\-\.~+/]+={0,2}(?=[^\w\-\.~+/=]|$)"
)
# Search once per scheme-character run, preserving any non-letter prefix.
URL_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9+.-])([0-9+.-]*[a-z][a-z0-9+.-]*://[^:\s]+:)[^@\s/]+(@)"
)
KV_CREDENTIAL_QUOTED = re.compile(
    r"""(?i)\b((?:(?:moorcheh[_-])?api[_-]?key|secret[_-]?key|secret[_-]?access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|client[_-]?secret|password|passwd|(?:auth|access|refresh|id|session)[_-]?token)['"]?\s*[:=]\s*)(['"])(?:\\.|(?!\2)[^\\\n])+\2"""
)
KV_CREDENTIAL_UNQUOTED = re.compile(
    r"""(?i)\b((?:(?:moorcheh[_-])?api[_-]?key|secret[_-]?key|secret[_-]?access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|client[_-]?secret|password|passwd|(?:auth|access|refresh|id|session)[_-]?token)['"]?\s*[:=]\s*)[^\s,;'"}\]]{1,}"""
)


def _redact_private_keys(text: str) -> str:
    """Redact complete PEM blocks without rescanning unterminated prefixes."""
    if "-----BEGIN " not in text or "-----END " not in text:
        return text

    # Headers use only this alphabet. Each run is scanned a constant number
    # of times, including malformed headers with many BEGIN/END markers.
    last_end_at = -1
    for run in _PRIVATE_KEY_HEADER_RUN.finditer(text):
        suffix_at = text.rfind(_PRIVATE_KEY_SUFFIX, run.start(), run.end())
        if suffix_at >= 0:
            end_at = text.rfind("-----END ", run.start(), suffix_at)
            if end_at >= 0:
                last_end_at = end_at
    if last_end_at < 0:
        return text

    parts: list[str] = []
    copied_until = 0
    begin_at: int | None = None
    for run in _PRIVATE_KEY_HEADER_RUN.finditer(text):
        last_suffix = text.rfind(_PRIVATE_KEY_SUFFIX, run.start(), run.end())
        if last_suffix < 0:
            continue

        search_after = run.start()
        if begin_at is None:
            # Preserve the old greedy BEGIN header: choose the last suffix
            # in its run that still leaves a complete END header after it.
            begin_suffix = text.rfind(
                _PRIVATE_KEY_SUFFIX, run.start(), min(run.end(), last_end_at)
            )
            if begin_suffix < 0:
                continue
            candidate = text.find("-----BEGIN ", run.start(), begin_suffix)
            if candidate < 0:
                continue
            begin_at = candidate
            search_after = begin_suffix + len(_PRIVATE_KEY_SUFFIX)

        # The body ends at the earliest END marker; its header is greedy.
        end_at = text.find("-----END ", search_after, last_suffix)
        if end_at < 0:
            continue
        parts.extend((text[copied_until:begin_at], "[REDACTED_PRIVATE_KEY]"))
        copied_until = last_suffix + len(_PRIVATE_KEY_SUFFIX)
        begin_at = None

    if not parts:
        return text
    parts.append(text[copied_until:])
    return "".join(parts)


def redact_sensitive_data(text: str) -> str:
    """Sanitize secrets, API keys, passwords, and tokens before persistence."""
    if not text:
        return text

    text = _redact_private_keys(text)
    text = BEARER_PATTERN.sub("Bearer [REDACTED_TOKEN]", text)
    for pat in API_KEY_PATTERNS:
        text = pat.sub("[REDACTED_API_KEY]", text)
    text = URL_CREDENTIAL_PATTERN.sub(r"\g<1>[REDACTED_PASSWORD]\g<2>", text)
    text = KV_CREDENTIAL_QUOTED.sub(r"\1\2[REDACTED_CREDENTIAL]\2", text)
    text = KV_CREDENTIAL_UNQUOTED.sub(r"\1[REDACTED_CREDENTIAL]", text)

    return text


class ConversationMemoryExtractionService:
    """Extract typed memory candidates from conversation turns."""

    MAX_MESSAGES = 200
    MAX_MEMORIES = 100
    MAX_CONTENT_CHARS = 120_000
    MAX_MEMORY_CONTENT_CHARS = 10_000

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
            "namespace": "",  # Empty namespace invokes the raw LLM mode directly
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
        text = raw_answer.strip()
        if not text:
            raise ValueError("Memory extraction returned an empty response")

        for parsed in iter_json_arrays(text):
            try:
                normalized = self._normalize_candidates(
                    parsed, max_memories=max_memories
                )
                if normalized:
                    return normalized
            except ValueError:
                continue

        raise ValueError("Memory extraction did not return valid JSON")

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
        for i, message in enumerate(messages):
            line = f"{message['role'].strip()}: {message['content'].strip()}"
            # Account for the newline separator that join() adds between
            # accepted messages.  Without this, two lines whose lengths sum
            # to exactly MAX_CONTENT_CHARS produce a query that exceeds it.
            separator_len = 1 if lines else 0
            total += len(line) + separator_len
            if total > self.MAX_CONTENT_CHARS:
                # Always include at least the first message so the query is
                # never empty.  Truncate it if it alone exceeds the budget.
                if i == 0 and not lines:
                    lines.append(line[: self.MAX_CONTENT_CHARS])
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
            f"Keep each memory content at or below {self.MAX_MEMORY_CONTENT_CHARS} characters. "
            f"Return at most {max_memories} memories. Valid types: {memory_types}."
        )

    def _footer_prompt(self) -> str:
        return (
            "Return only JSON. The JSON must be an array of objects with keys: "
            "type, title, content, confidence. Confidence must be 0.0 to 1.0."
        )

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
            content = redact_sensitive_data(content)
            if len(content) > self.MAX_MEMORY_CONTENT_CHARS:
                content = content[: self.MAX_MEMORY_CONTENT_CHARS - 3].rstrip() + "..."

            memory_type = item.get("type")
            if memory_type:
                memory_type = str(memory_type).strip().lower()
                if memory_type not in VALID_MEMORY_TYPES:
                    memory_type = None
            else:
                memory_type = None

            raw_title = str(item.get("title") or content[:80]).strip()
            title = redact_sensitive_data(raw_title)[:100]

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
                    "source": "system",
                    "provenance": "inferred",
                }
            )
            if len(normalized) >= max_memories:
                break

        if not normalized:
            raise ValueError("Memory extraction produced no usable candidates")

        return normalized
