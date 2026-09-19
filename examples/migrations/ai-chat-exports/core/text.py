"""Shared text extraction and timestamp parsing helpers.

These utilities are duplicated across provider adapters. Centralising them
here avoids drift and makes ISO-8601 offset handling consistent.
"""

from __future__ import annotations

from datetime import datetime, timezone


def extract_text(msg: dict) -> str:
    """Extract plain text from a chat message dict.

    Handles the ``text`` field (Claude/Gemini style), ``content`` as a
    string, ``content.parts`` (ChatGPT style), or a list of content blocks.
    """
    if "text" in msg:
        return msg["text"] or ""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = content.get("parts", [])
        return "".join(p for p in parts if isinstance(p, str))
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts)
    return str(content)


def parse_timestamp(ts) -> datetime | None:
    """Parse a timestamp from Unix epoch, ISO-8601 string, or None.

    Supports:
      - Numeric (int/float) Unix timestamps.
      - ISO-8601 strings with or without fractional seconds, ``Z`` suffix,
        or numeric UTC offsets (``+00:00``).
      - Naive datetimes (assumed UTC).

    Returns ``None`` for unrecognised or unparseable values.
    """
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            try:
                parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    except (ValueError, OSError, OverflowError):
        pass
    return None
