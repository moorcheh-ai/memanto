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
        "expires_at": datetime, # source expiration timestamp (when present)
        "ttl_seconds": int,     # source retention window (when present)
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

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from memanto.app.constants import VALID_MEMORY_TYPES, VALID_PROVENANCE_TYPES

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
_MAX_TITLE_CHARS = 100  # MemoryRecord.title max_length
_MAX_CONTENT_CHARS = 10000  # MemoryRecord.content max_length
_MAX_FOOTER_CHARS = 800  # cap supporting-data footer so it never dominates


def _title_from(content: str) -> str:
    """Derive a short memory title from the first line of content."""
    text = content.strip().replace("\n", " ")
    if len(text) <= _DEFAULT_TITLE_CHARS:
        return text
    return text[: _DEFAULT_TITLE_CHARS - 3].rstrip() + "..."


def _coerce_type(raw: str | None) -> str | None:
    """Normalize a raw type string to a valid Memanto type, else None."""
    if not raw:
        return None
    t = raw.strip().lower()
    return t if t in VALID_MEMORY_TYPES else None


def _coerce_provenance(raw: Any) -> str:
    """Normalize a provenance value to a valid one, defaulting to 'imported'."""
    if not isinstance(raw, str):
        return "imported"
    provenance = raw.strip().lower()
    return provenance if provenance in VALID_PROVENANCE_TYPES else "imported"


def _normalize_mem0_categories(raw: Any) -> list[str]:
    """Normalize Mem0 category payloads into lower-case category labels."""
    if raw in (None, "", [], {}):
        return []
    if isinstance(raw, str):
        values: list[Any] = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = [raw]
    return [text for item in values if (text := str(item).strip().lower())]


def _scope_tag(scope: dict[str, Any] | None) -> str | None:
    """Render the first non-empty scope field as a ``key=value`` tag."""
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
    # ``bool`` subclasses ``int``; without this guard, YAML ``true`` becomes
    # 1970-01-01T00:00:01Z and can accidentally expire a durable memory.
    if isinstance(value, bool):
        return None
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
    """Return the first parseable timestamp among the given record keys."""
    for key in keys:
        dt = _parse_dt(record.get(key))
        if dt is not None:
            return dt
    return None


def _parse_positive_int(value: Any) -> int | None:
    """Parse a positive integer without silently truncating fractional values."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return parsed if parsed > 0 else None


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
    """Return the current UTC time (migration timestamp)."""
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

        categories = _normalize_mem0_categories(mem.get("categories"))
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
                ("Letta passage source", passage.get("source")),
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
    mapped_memory_ids: set[str] = set()
    represented_document_ids: set[str] = set()
    migrated_at = _now_utc()

    for mem in export.get("memories", []) or []:
        content = (
            mem.get("content") or mem.get("memory") or mem.get("text") or ""
        ).strip()
        if not content:
            continue

        raw_tags = mem.get("container_tags") or mem.get("containerTags") or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        elif not isinstance(raw_tags, (list, tuple, set)):
            raw_tags = []

        tags: list[str] = []
        for tag in [*raw_tags, mem.get("container_tag")]:
            if tag:
                tag = str(tag)
                if tag not in tags:
                    tags.append(tag)

        created_at = _pick_first_dt(mem, ("createdAt", "created_at"))

        footer = _format_supporting_data(
            [
                (
                    "Source",
                    f"supermemory:{mem.get('id')}" if mem.get("id") else None,
                ),
                ("Container tags", tags),
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

        memory_id = mem.get("id")
        if memory_id:
            mapped_memory_ids.add(str(memory_id))
        document_id = mem.get("documentId") or mem.get("document_id")
        if document_id:
            represented_document_ids.add(str(document_id))

    # Harvest chunks from documents that have no mapped extracted memory. This
    # is a full fallback when memories[] is empty, and preserves fresh or
    # still-unprocessed documents in mixed accounts that already have some
    # extracted memories elsewhere.
    for doc in export.get("documents", []) or []:
        doc_tags = [str(t) for t in (doc.get("container_tags") or []) if t]
        doc_id = doc.get("id")
        doc_memory_ids = {
            str(memory_id) for memory_id in (doc.get("memory_ids") or []) if memory_id
        }
        if (doc_id and str(doc_id) in represented_document_ids) or (
            doc_memory_ids & mapped_memory_ids
        ):
            continue
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
# ChatGPT (official account export)
# --------------------------------------------------------------------------


def map_chatgpt(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a ChatGPT account export to Memanto memory payloads.

    Each user-authored message in the active branch of a conversation becomes
    one memory. ``type`` stays ``None`` so the parsing service auto-classifies
    (a user message can be a preference, a commitment, or a fact depending on
    its content). The conversation title is kept as a tag, and the source
    reference points back to the exact ``conversation:node`` in the export so
    the original is always findable.
    """
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for mem in export.get("memories", []) or []:
        content = (mem.get("content") or "").strip()
        if not content:
            continue

        tags = [str(t) for t in (mem.get("tags") or []) if t]
        raw_created = mem.get("created_at")
        # _parse_dt handles int/float epoch values itself (line ~123) and
        # deliberately returns None for 0 and bool. Do NOT fall back to
        # fromtimestamp here: it would resurrect 1970 for a 0/None/bool
        # value that the parser intentionally rejected.
        created_at = _parse_dt(raw_created)

        footer = _format_supporting_data(
            [
                ("Source", f"chatgpt:{mem.get('id')}" if mem.get("id") else None),
                ("Conversation", next((t for t in tags if t.startswith("conversation:")), None)),
                ("Source created_at", created_at.isoformat() if created_at else None),
            ]
        )

        rows.append(
            {
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": None,
                "tags": tags,
                "confidence": 0.7,
                "source": "chatgpt",
                "source_ref": str(mem.get("id")) if mem.get("id") else None,
                "provenance": "imported",
                "created_at": created_at,
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
        provenance = _coerce_provenance(x_memanto.get("provenance"))

        extra = entry.get("extra") or {}
        generated = extra.get("generated", {})
        gen_at = generated.get("at") if isinstance(generated, dict) else None
        created_at = _parse_dt(gen_at) or _parse_dt(entry.get("timestamp"))

        updated_at = _parse_dt(x_memanto.get("updated_at")) or migrated_at
        expires_at = _parse_dt(x_memanto.get("expires_at"))
        ttl_seconds = _parse_positive_int(x_memanto.get("ttl_seconds"))

        original_title = None
        if title and len(title) > _MAX_TITLE_CHARS:
            original_title = title
            title = title[: _MAX_TITLE_CHARS - 3].rstrip() + "..."

        footer_items: list[tuple[str, Any]] = [
            ("Original OKF title", original_title),
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
                "provenance": provenance,
                "created_at": created_at,
                "updated_at": updated_at,
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds,
            }
        )
    return rows


# Langfuse is deliberately absent: its rows are observability events, not
# memories, so one incident collapses into a single grouped payload rather
# than mapping row-for-row. That needs the user's capture settings, which
# this registry's signature cannot carry — see ``langfuse_rules.build_rows``.
MAPPERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "mem0": map_mem0,
    "letta": map_letta,
    "supermemory": map_supermemory,
    "chatgpt": map_chatgpt,
    "okf": map_okf,
}


def type_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count mapped rows by resolved (or unclassified) type — for previews."""
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("type") or "auto"
        counts[key] = counts.get(key, 0) + 1
    return counts
