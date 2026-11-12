"""LangMem concept -> Memanto type / OKF field mapping.

LangMem's semantic memory is *untyped* free text: each item is just
``{"content": "..."}`` under a namespace. Memanto has 13 typed primitives
(fact, preference, goal, decision, ...), so bridging the two means picking a
type for each memory. This uses the same approach as Memanto's shipped Mem0
mapper: a deterministic lexical classifier instead of a hardcoded label.

Notes on the approach:

* Type is inferred from lightweight lexical cues (see ``_TYPE_RULES``). When no
  rule matches it falls back to ``observation`` rather than guessing -- the
  original text is always kept verbatim, so a wrong type never loses data.
* The inferred type is written to OKF's ``x_memanto.type`` so Memanto's loader
  can use it directly (``map_okf`` honours ``x_memanto.type`` when it's a
  valid Memanto type) instead of re-classifying from scratch.
* LangMem fields with no Memanto slot (namespace, key, timestamps) are kept
  around: namespace -> a ``user=<id>`` scope tag, key -> ``source_ref``,
  created_at -> OKF ``timestamp``.

Mapping table (LangMem -> Memanto / OKF):

    value.content        -> memory content (body) + derived title
    namespace[1] (user)  -> tag  "user=<id>"  and  x_memanto.source="langmem"
    key (uuid)           -> source_ref / OKF resource "langmem:<key>"
    created_at           -> OKF timestamp (temporal recall fidelity)
    (inferred)           -> memory type via _TYPE_RULES -> x_memanto.type
    (constant)           -> provenance="imported", confidence=0.75
"""

from __future__ import annotations

import re
from typing import Any

# Ordered rules: the first whose pattern matches the content wins. Patterns are
# intentionally conservative -- they encode the vocabulary LangMem memories
# actually use, and anything unmatched falls through to ``observation``.
_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "preference",
        re.compile(
            r"\b(prefer|prefers|likes?|dislikes?|favou?rite|uses? .*(mode|theme)|runs? .*(pytest|vitest|jest|test runner|linter)|never deploys?|always)\b",
            re.I,
        ),
    ),
    (
        "decision",
        re.compile(r"\b(decision|decided|we (chose|use|will use)|agreed to)\b", re.I),
    ),
    (
        "goal",
        re.compile(
            r"\b(goal|wants? to|plans? to|aims? to|by end of|ship .* by|eventually)\b",
            re.I,
        ),
    ),
    (
        "commitment",
        re.compile(
            r"\b(needs? to|must|to-?do|reminder|remind|will write|action item)\b", re.I
        ),
    ),
    (
        "relationship",
        re.compile(
            r"\b(pairing with|works? with|teammate|reports? to|moved (from|to) the|sole engineer|solo)\b",
            re.I,
        ),
    ),
    (
        "event",
        re.compile(
            r"\b(happened|occurred|shipped|merged|released|rolled off|on \d{4}-\d{2}-\d{2})\b",
            re.I,
        ),
    ),
    (
        "fact",
        re.compile(
            r"\b(is a|is an|is the|written in|backed by|based in|located|works? at|on the .* team)\b",
            re.I,
        ),
    ),
]

_FALLBACK_TYPE = "observation"

# Kept in sync with memanto.app.constants.VALID_MEMORY_TYPES. Duplicated here so
# the adapter can be reasoned about standalone; a unit test asserts they match.
VALID_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
}

_TITLE_CHARS = 80
DEFAULT_CONFIDENCE = 0.75


def classify(content: str) -> str:
    """Infer a Memanto memory type from LangMem free-text content."""
    for mem_type, pattern in _TYPE_RULES:
        if pattern.search(content):
            return mem_type
    return _FALLBACK_TYPE


def title_from(content: str) -> str:
    text = " ".join(content.strip().split())
    if len(text) <= _TITLE_CHARS:
        return text
    return text[: _TITLE_CHARS - 3].rstrip() + "..."


def map_record(record: dict[str, Any]) -> dict[str, Any]:
    """Map one LangMem export record to a Memanto memory dict.

    The output shape matches what ``OkfExportService.write_okf_bundle`` expects
    per memory (``title``, ``content``, ``tags``, ``created_at``, ``source``,
    ``source_ref``, ``confidence``, ``provenance``, plus the resolved ``type``).
    """
    value = record.get("value") or {}
    content = str(value.get("content") or "").strip()
    namespace = record.get("namespace") or []
    user = namespace[1] if len(namespace) > 1 else None
    key = record.get("key")

    mem_type = classify(content)
    tags: list[str] = []
    if user:
        tags.append(f"user={user}")

    # Anything LangMem carried beyond `content` is preserved in a footer so the
    # migration is lossless even for custom-schema LangMem memories.
    extra = {k: v for k, v in value.items() if k != "content"}
    body = content
    if extra:
        footer_lines = "\n".join(f"- {k}: {v}" for k, v in extra.items())
        body = f"{content}\n\n---\n[Supporting data]\n{footer_lines}"

    return {
        "title": title_from(content),
        "content": body,
        "type": mem_type,
        "tags": tags,
        "confidence": DEFAULT_CONFIDENCE,
        "source": "langmem",
        "source_ref": f"langmem:{key}" if key else None,
        "provenance": "imported",
        "created_at": record.get("created_at"),
    }


def type_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["type"]] = counts.get(row["type"], 0) + 1
    return dict(sorted(counts.items()))
