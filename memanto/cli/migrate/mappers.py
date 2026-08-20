"""
Source -> Memanto schema mappers.

Each mapper takes a provider export dict (the same shape produced by the
``cli/analyze/*_export.py`` modules) and yields memory dicts in the format
accepted by ``SdkClient.batch_remember``:

    {
        "title": str,
        "content": str,         # original text + a [Supporting data] footer
        "type": str | None,     # None lets the parsing service auto-classify
        "tags": list[str],
        "confidence": float,
        "source": str,          # provider name ("mem0", "letta", ...)
        "source_ref": str,      # original record id
        "provenance": "imported",
        "created_at": datetime, # original source timestamp (when present)
        "updated_at": datetime, # migration time = now
    }

Mappers extract every useful field from the source. Anything that maps
naturally onto Memanto's schema (id, created_at, tags) goes into the right
slot. Everything else (provider metadata, scope ids, hashes, scores) gets
packed into a bounded ``[Supporting data]`` markdown block appended to the
content, so it stays searchable and visible without bloating the schema.

Adding a new provider: write a ``map_<provider>`` function returning
``list[dict]``, register it in ``MAPPERS``, and add a per-provider source
count helper in ``runner.py``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from memanto.app.constants import VALID_MEMORY_TYPES

# Mem0 ships category labels per memory. Map the common ones to Memanto's
# typed primitives; everything else falls through to None (auto-classify).
_MEM0_CATEGORY_TO_TYPE: dict[str, str] = {
    "personal_details": "fact",
    "personal_preferences": "preference",
    "preferences": "preference",
    "professional_info": "fact",
    "work": "fact",
    "skills": "fact",
    "goals_and_plans": "goal",
    "tasks": "commitment",
    "relationships": "relationship",
    "events": "event",
    "decisions": "decision",
    "observations": "observation",
}

_DEFAULT_TITLE_CHARS = 80
_MAX_CONTENT_CHARS = 10000  # MemoryRecord.content max_length
_MAX_FOOTER_CHARS = 800  # cap supporting-data footer so it never dominates


def _title_from(content: str) -> str:
    text = content.strip().replace("\n", " ")
    if len(text) <= _DEFAULT_TITLE_CHARS:
        return text
    return text[: _DEFAULT_TITLE_CHARS - 3].rstrip() + "..."


def _coerce_type(raw: str | None) -> str | None:
    if not raw:
        return None
    t = raw.strip().lower()
    return t if t in VALID_MEMORY_TYPES else None


def _scope_tag(scope: dict[str, Any] | None) -> str | None:
    if not scope:
        return None
    for k, v in scope.items():
        if v:
            return f"{k}={v}"
    return None


def _parse_dt(value: Any) -> datetime | None:
    """Best-effort parse of a timestamp from a source record into UTC datetime.

    Handles ISO 8601 strings (with/without ``Z``), Unix epoch ints/floats,
    and already-parsed ``datetime`` objects. Returns ``None`` when nothing
    sensible can be extracted — the caller falls back to the server default.
    """
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Python <3.11 doesn't accept the trailing 'Z' shorthand.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _pick_first_dt(record: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        dt = _parse_dt(record.get(key))
        if dt is not None:
            return dt
    return None


def _format_supporting_data(items: list[tuple[str, Any]]) -> str:
    """Render the ``[Supporting data]`` footer.

    Filters out empties, truncates over-long values, and caps the total
    footer length so it never overruns ``MemoryRecord.content``.
    """
    lines: list[str] = []
    for label, value in items:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value if v not in (None, ""))
            if not value:
                continue
        elif isinstance(value, dict):
            # one-line compact dict so the footer doesn't sprawl
            value = "; ".join(
                f"{k}={v}" for k, v in value.items() if v not in (None, "")
            )
            if not value:
                continue
        text = str(value)
        if len(text) > 200:
            text = text[:197] + "..."
        lines.append(f"- {label}: {text}")

    if not lines:
        return ""

    body = "\n".join(lines)
    if len(body) > _MAX_FOOTER_CHARS:
        body = body[: _MAX_FOOTER_CHARS - 4] + "\n..."
    return "\n\n---\n[Supporting data]\n" + body


def _attach_footer(content: str, footer: str) -> str:
    """Append the supporting-data footer, trimming content if it overflows."""
    if not footer:
        return content
    budget = _MAX_CONTENT_CHARS - len(footer)
    if budget < 0:
        # Pathological — footer somehow exceeds content limit on its own.
        return content[:_MAX_CONTENT_CHARS]
    trimmed = content if len(content) <= budget else content[: budget - 4] + "\n..."
    return trimmed + footer


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Mem0
# --------------------------------------------------------------------------


def map_mem0(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a Mem0 export to rich Memanto memory payloads."""
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for mem in export.get("memories", []) or []:
        content = (mem.get("memory") or mem.get("content") or "").strip()
        if not content:
            continue

        categories = [str(c).lower() for c in (mem.get("categories") or []) if c]
        memory_type: str | None = None
        for cat in categories:
            memory_type = _MEM0_CATEGORY_TO_TYPE.get(cat) or _coerce_type(cat)
            if memory_type:
                break

        tags = list(dict.fromkeys(categories))
        scope = mem.get("export_scope") or {}
        scope_tag = _scope_tag(scope)
        if scope_tag:
            tags.append(scope_tag)

        created_at = _pick_first_dt(mem, ("created_at", "createdAt"))
        expires_at = _pick_first_dt(mem, ("expiration_date", "expires_at"))

        # Anything we couldn't slot directly goes into the footer.
        footer = _format_supporting_data(
            [
                ("Source", f"mem0:{mem.get('id')}" if mem.get("id") else None),
                ("Mem0 scope", scope_tag),
                ("Categories", categories),
                ("Mem0 metadata", mem.get("metadata")),
                ("Mem0 score", mem.get("score")),
                ("Hash", mem.get("hash")),
                ("Immutable", mem.get("immutable")),
                ("Source created_at", created_at.isoformat() if created_at else None),
                ("Expires at", expires_at.isoformat() if expires_at else None),
            ]
        )

        rows.append(
            {
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": memory_type,
                "tags": tags,
                "confidence": 0.8,
                "source": "mem0",
                "source_ref": str(mem.get("id")) if mem.get("id") else None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Letta
# --------------------------------------------------------------------------


def map_letta(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map Letta archival passages to rich Memanto memory payloads."""
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for passage in export.get("passages", []) or []:
        content = (passage.get("text") or passage.get("content") or "").strip()
        if not content:
            continue

        tags: list[str] = []
        agent_name = passage.get("export_agent_name")
        agent_id = passage.get("export_agent_id")
        if agent_name:
            tags.append(f"agent={agent_name}")
        elif agent_id:
            tags.append(f"agent_id={agent_id}")

        source_tags = [str(t) for t in (passage.get("tags") or []) if t]
        for t in source_tags:
            if t not in tags:
                tags.append(t)

        created_at = _pick_first_dt(passage, ("created_at", "createdAt"))

        footer = _format_supporting_data(
            [
                ("Source", f"letta:{passage.get('id')}" if passage.get("id") else None),
                ("Letta agent_id", agent_id),
                ("Letta agent_name", agent_name),
                ("Letta tags", source_tags),
                ("Letta metadata", passage.get("metadata")),
                ("Source", passage.get("source")),  # passage may carry its own
                ("Source created_at", created_at.isoformat() if created_at else None),
            ]
        )

        rows.append(
            {
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": "observation",
                "tags": tags,
                "confidence": 0.8,
                "source": "letta",
                "source_ref": str(passage.get("id")) if passage.get("id") else None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Supermemory
# --------------------------------------------------------------------------


def map_supermemory(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a Supermemory export to rich Memanto memory payloads.

    Primary source is the ``memories[]`` array — Supermemory's AI-extracted
    facts. Falls back to document chunks when no extracted memories exist
    (mostly fresh accounts). Each row keeps its container tag and links
    back to the source via ``source_ref``.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    migrated_at = _now_utc()

    for mem in export.get("memories", []) or []:
        content = (
            mem.get("content") or mem.get("memory") or mem.get("text") or ""
        ).strip()
        if not content:
            continue

        tags: list[str] = []
        tag = mem.get("container_tag")
        if tag:
            tags.append(str(tag))

        created_at = _pick_first_dt(mem, ("createdAt", "created_at"))

        footer = _format_supporting_data(
            [
                (
                    "Source",
                    f"supermemory:{mem.get('id')}" if mem.get("id") else None,
                ),
                ("Container tag", tag),
                ("Document id", mem.get("documentId") or mem.get("document_id")),
                ("Supermemory metadata", mem.get("metadata")),
                ("Score", mem.get("score")),
                ("Source created_at", created_at.isoformat() if created_at else None),
            ]
        )

        rows.append(
            {
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": None,
                "tags": tags,
                "confidence": 0.8,
                "source": "supermemory",
                "source_ref": str(mem.get("id")) if mem.get("id") else None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )
        seen.add(content)

    if rows:
        return rows

    # Fallback: harvest chunk text when extracted memories are empty.
    for doc in export.get("documents", []) or []:
        doc_tags = [str(t) for t in (doc.get("container_tags") or []) if t]
        doc_id = doc.get("id")
        doc_created = _pick_first_dt(
            doc.get("detail") or doc, ("createdAt", "created_at")
        )
        for chunk in doc.get("chunks", []) or []:
            content = (chunk.get("content") or chunk.get("text") or "").strip()
            if not content or content in seen:
                continue
            seen.add(content)
            footer = _format_supporting_data(
                [
                    (
                        "Source",
                        f"supermemory:doc:{doc_id}:chunk:{chunk.get('id')}"
                        if doc_id
                        else None,
                    ),
                    ("Container tags", doc_tags),
                    ("Document id", doc_id),
                    ("Chunk id", chunk.get("id")),
                    (
                        "Source created_at",
                        doc_created.isoformat() if doc_created else None,
                    ),
                ]
            )
            rows.append(
                {
                    "title": _title_from(content),
                    "content": _attach_footer(content, footer),
                    "type": "artifact",
                    "tags": doc_tags,
                    "confidence": 0.7,
                    "source": "supermemory",
                    "source_ref": (f"{doc_id}:{chunk.get('id')}" if doc_id else None),
                    "provenance": "imported",
                    "created_at": doc_created,
                    "updated_at": migrated_at,
                }
            )
    return rows


# --------------------------------------------------------------------------
# OKF (Open Knowledge Format)
# --------------------------------------------------------------------------


def map_okf(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map OKF bundle entries (from ``okf_loader.load_okf_bundle``) to Memanto
    memory payloads.

    OKF's ``type`` is free-form domain vocabulary, so it can't map onto
    Memanto's fixed types. We use it only when it happens to equal a Memanto
    type (or when a Memanto ``x_memanto.type`` round-trip value is present);
    otherwise we leave ``type=None`` for auto-classification and record the
    original OKF type in the footer. Everything with no schema slot (OKF type,
    resource, links, unknown frontmatter keys) goes into ``[Supporting data]``.
    """
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for entry in export.get("memories", []) or []:
        body = (entry.get("body") or "").strip()
        description = (entry.get("description") or "").strip()
        title = (entry.get("title") or "").strip()

        if description and description not in body:
            content = f"{description}\n\n{body}".strip()
        else:
            content = body
        if not content:
            content = title
        if not content:
            continue

        x_memanto = entry.get("x_memanto") or {}
        okf_type = entry.get("type")
        memory_type = _coerce_type(x_memanto.get("type")) or _coerce_type(okf_type)

        tags = [str(t) for t in (entry.get("tags") or []) if t]
        resource = entry.get("resource")

        raw_conf = x_memanto.get("confidence")
        try:
            confidence = float(raw_conf) if raw_conf is not None else 0.8
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = min(1.0, max(0.0, confidence))

        source = x_memanto.get("source") or "okf"
        created_at = _parse_dt(entry.get("timestamp"))

        footer_items: list[tuple[str, Any]] = [
            ("OKF source", entry.get("source_path")),
            # Only surface the OKF type when we couldn't map it to a slot.
            ("OKF type", okf_type if not memory_type else None),
            ("OKF resource", resource),
            ("Links", entry.get("links")),
        ]
        for key, value in (entry.get("extra") or {}).items():
            footer_items.append((f"OKF {key}", value))
        footer = _format_supporting_data(footer_items)

        if footer:
            content = _attach_footer(content, footer)
        elif len(content) > _MAX_CONTENT_CHARS:
            content = content[: _MAX_CONTENT_CHARS - 4] + "\n..."

        rows.append(
            {
                "title": title or _title_from(content),
                "content": content,
                "type": memory_type,
                "tags": tags,
                "confidence": confidence,
                "source": source,
                "source_ref": str(resource) if resource else None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Claude.ai / ChatGPT (GenAI conversation memory)
# --------------------------------------------------------------------------
#
# Unlike store-based providers (mem0/letta) which already expose extracted
# memories, a raw conversation export is just a sequence of user/assistant
# turns. We distill those turns into typed, deduplicated "memory candidates"
# so the migration doesn't echo every message verbatim (which would drown
# the memory store in noise). Mapping heuristics are intentionally
# conservative: if a message doesn't clearly signal a durable fact we tag it
# ``type=None`` and let the parsing service auto-classify, rather than guess.
#
# Two export shapes are handled under one core:
#   * Claude.ai  -> {"<uuid>": {"name": ..., "chat_messages": [{sender,
#                    text, created_at, uuid}, ...]}}
#   * ChatGPT    -> [{"title": ..., "create_time": ..., "mapping":
#                    {"<id>": {"message": {"role", "content", "create_time"},
#                    "parent": <id>}}}]

# Signal phrases -> Memanto type. Order matters: earlier, more specific rules
# win. The dict maps a tuple of substrings to a type; anything with no match
# stays untyped (auto-classify).
_GENAI_TYPE_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "i prefer ",
            "i'd prefer ",
            "i like ",
            "i love ",
            "i enjoy ",
            "my favorite ",
            "i'd rather ",
            "i would rather ",
            "preferred ",
            "preference ",
        ),
        "preference",
    ),
    (
        (
            "i want to ",
            "my goal ",
            "i'm trying to ",
            "i aim to ",
            "my plan ",
            "plan to ",
            "i intend ",
            "i'll learn ",
            "i'm learning ",
            "goal",
            "objective",
        ),
        "goal",
    ),
    (
        ("i decided ", "we decided ", "let's go with ", "made the call ", "decision"),
        "decision",
    ),
    (
        (
            "always ",
            "never ",
            "please ",
            "remember to ",
            "make sure ",
            "rule ",
            "from now on ",
            "do not ",
            "don't ",
        ),
        "instruction",
    ),
    (
        (
            "turns out ",
            "i learned ",
            "i found ",
            "good to know ",
            "interesting ",
            "discovered ",
            "turns out ",
            "tip",
            "trick",
            "how to ",
        ),
        "learning",
    ),
    (
        (
            "my partner ",
            "my friend ",
            "my brother ",
            "my sister ",
            "my mom ",
            "my dad ",
            "my colleague ",
            "my manager ",
            "my wife ",
            "my husband ",
            "relationship",
        ),
        "relationship",
    ),
    (
        (
            "tomorrow ",
            "next week ",
            "on monday ",
            "on tuesday ",
            "on wednesday ",
            "on thursday ",
            "on friday ",
            "on saturday ",
            "on sunday ",
            "this weekend ",
            "meeting on ",
            "event ",
        ),
        "event",
    ),
    (
        (
            "i use ",
            "i work ",
            "i'm working on ",
            "i built ",
            "i run ",
            "my project ",
            "i made ",
            "artifact",
            "repo",
            "app ",
            "tool ",
        ),
        "context",
    ),
    (
        (
            "key",
            "password",
            "token",
            "apikey",
            "api key ",
            "credentials",
            "connection string",
            "endpoint",
        ),
        "context",
    ),
]

# The provenance footer marker; used to strip the footer before deduplicating
# so identical statements made in different messages still collapse together.
_SUPPORTING_DATA_LABEL = "[Supporting data]"


def _classify_conversation_type(text: str) -> str | None:
    """Best-effort type for a distilled conversation candidate."""
    low = text.lower()
    for substrings, mtype in _GENAI_TYPE_RULES:
        if any(s in low for s in substrings):
            return mtype
    return None


def _msg_text(content: Any) -> str:
    """Extract plain text from a ChatGPT message content blob.

    ChatGPT content is usually ``{"content_type": "text", "parts": ["..."]}``,
    but can also be a bare string or a list of ``{"text": "..."}`` parts.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        parts = content.get("parts") or content.get("content") or content.get("text")
        if parts is None:
            return ""
        return _msg_text(parts)
    if isinstance(content, list):
        bits = []
        for part in content:
            if isinstance(part, dict):
                p = part.get("text") or part.get("content")
                if isinstance(p, str):
                    bits.append(p.strip())
            elif isinstance(part, str):
                bits.append(part.strip())
        return "\n".join(b for b in bits if b).strip()
    return str(content).strip()


_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|ok|okay|thanks|thank you|got it|cool|sure|yes|no|yep|"
    r"nope|right|certainly|great)[!?,.]*\s*$",
    re.I,
)


def _dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop near-duplicate memory candidates (same durable text).

    Dedupe on the *durable surface* of each candidate — the memory text, with
    the appended provenance footer stripped — so identical statements made in
    different messages still collapse into one row. Source references from
    dropped duplicates are merged into the surviving row so provenance stays
    complete.
    """
    seen: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for c in candidates:
        body = (c.get("content") or "").split(_SUPPORTING_DATA_LABEL)[0]
        key = re.sub(r"\s+", " ", body).strip().lower()
        if not key:
            continue
        prior = seen.get(key)
        if prior is not None:
            left = prior.get("source_ref") or ""
            right = c.get("source_ref") or ""
            for x in right.split("|"):
                if x and x not in left.split("|"):
                    left = f"{left}|{x}" if left else x
            if left:
                prior["source_ref"] = left
            continue
        seen[key] = c
        out.append(c)
    return out


def _distill_turns(turns: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Turn a chronological list of {role, text, time, ref} into memory rows.

    Only *durable user turns* become memories. Assistant acknowledgements,
    commitments ("Got it — I'll pin versions"), debugging chatter and greetings
    aren't memories about the user, so they're deliberately dropped rather than
    echoed into the destination store.
    """
    migrated_at = _now_utc()
    candidates: list[dict[str, Any]] = []
    for t in turns:
        text = (t.get("text") or "").strip()
        if t.get("role") != "user" or not text:
            continue
        if len(text) < 4 or _GREETING_RE.match(text):
            continue

        mtype = _classify_conversation_type(text)
        ref = t.get("ref")
        created_at = _parse_dt(t.get("time"))
        footer_items: list[tuple[str, Any]] = [
            ("Source", "claude" if source == "claude" else "chatgpt"),
            ("Role", "user"),
            ("Message refs", ref or None),
            ("Original timestamp", created_at),
        ]
        footer = _format_supporting_data(footer_items)
        content = _attach_footer(text, footer) if footer else text

        candidates.append(
            {
                "title": _title_from(text),
                "content": content,
                "type": mtype,
                "tags": ["genai", source],
                "confidence": 0.6,
                "source": source,
                "source_ref": ref or None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )
    return candidates


def _main_branch(node_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the message chain (oldest -> newest) of the primary ChatGPT branch.

    ChatGPT ``mapping`` is a tree — edits and retries create sibling branches
    under a shared parent. Only the lineage reaching the latest leaf is the
    "current" conversation; walking its ``parent`` chain keeps alternate
    branches from being imported and merged into incompatible memories.

    The lineage is selected and walked over *all* nodes, including unsupported
    ones (tool/system children that can sit between user/assistant turns);
    roles are filtered only when appending emitted turns. This keeps the
    traversal connected when a supported node's only child is unsupported, so
    the latest leaf is always reachable and the walk never dead-ends.
    """
    if not node_map:
        return []
    children: dict[str, list[str]] = {}
    for nid, node in node_map.items():
        p = node.get("parent")
        if p:
            children.setdefault(p, []).append(nid)

    def _ts(nid: str) -> float:
        msg = node_map[nid].get("message") or {}
        return float(msg.get("create_time") or 0)

    leaves = [nid for nid in node_map if not children.get(nid)]
    if not leaves:
        return []
    current = max(leaves, key=_ts)

    roles = {"user", "assistant"}
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    while current and current in node_map and current not in seen:
        seen.add(current)
        node = node_map[current]
        msg = node.get("message") or {}
        role = (msg.get("author") or {}).get("role") or msg.get("role")
        if role in roles:
            chain.append(
                {
                    "role": role,
                    "text": _msg_text(msg.get("content")),
                    "time": msg.get("create_time"),
                    "ref": current,
                }
            )
        current = node_map[current].get("parent")
    chain.reverse()
    return chain


def map_claude(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a Claude.ai ``conversations.json`` export into memory rows.

    Claude's export maps conversation uuid -> {name, chat_messages:[{sender,
    text, created_at, uuid}, ...]}. ``sender`` is 'human' for the user and
    'assistant' for the model; only 'human' turns carry durable user memory.
    """
    rows: list[dict[str, Any]] = []
    for convo in export.get("conversations") or []:
        turns: list[dict[str, Any]] = []
        for msg in convo.get("chat_messages", []) or []:
            sender = (msg.get("sender") or "").lower()
            # Skip system/tool/unknown senders; only real user turns are kept.
            if sender not in ("human", "user"):
                continue
            turns.append(
                {
                    "role": "user",
                    "text": msg.get("text") or "",
                    "time": msg.get("created_at"),
                    "ref": msg.get("uuid"),
                }
            )
        rows.extend(_distill_turns(turns, "claude"))
    return _dedupe(rows)


def map_chatgpt(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a ChatGPT export ``conversations.json`` into memory rows.

    ChatGPT's export is a list of conversations; each has a ``mapping`` tree
    of message nodes with ``parent`` links. We follow the main branch's parent
    lineage (see :func:`_main_branch`) and keep only user turns.
    """
    rows: list[dict[str, Any]] = []
    for convo in export.get("conversations", []):
        node_map = convo.get("mapping") or {}
        chain = _main_branch(node_map)
        turns = [r for r in chain if r["role"] == "user"]
        rows.extend(_distill_turns(turns, "chatgpt"))
    return _dedupe(rows)


# Langfuse is deliberately absent: its rows are observability events, not
# memories, so one incident collapses into a single grouped payload rather
# than mapping row-for-row. That needs the user's capture settings, which
# this registry's signature cannot carry — see ``langfuse_rules.build_rows``.
MAPPERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "mem0": map_mem0,
    "letta": map_letta,
    "supermemory": map_supermemory,
    "okf": map_okf,
    "claude": map_claude,
    "chatgpt": map_chatgpt,
}


def type_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count mapped rows by resolved (or unclassified) type — for previews."""
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("type") or "auto"
        counts[key] = counts.get(key, 0) + 1
    return counts
