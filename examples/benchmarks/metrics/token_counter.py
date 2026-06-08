"""Token counting utilities using tiktoken (cl100k_base approximation)."""

from __future__ import annotations

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count(text: str) -> int:
    """Return approximate token count for a string."""
    if not text:
        return 0
    return len(_enc.encode(text))


def count_messages(messages: list[str]) -> int:
    return sum(count(m) for m in messages)


def count_results(results: list[dict | str]) -> int:
    total = 0
    for r in results:
        if isinstance(r, dict):
            total += count(r.get("text") or r.get("content") or r.get("memory") or str(r))
        else:
            total += count(str(r))
    return total
