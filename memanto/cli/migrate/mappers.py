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
# OKF / Markdown (Open Knowledge Format)
# --------------------------------------------------------------------------

_SECTION_LABEL_TO_TYPE: dict[str, str] = {
    "facts": "fact",
    "fact": "fact",
    "preferences": "preference",
    "preference": "preference",
    "instructions": "instruction",
    "instruction": "instruction",
    "decisions": "decision",
    "decision": "decision",
    "events": "event",
    "event": "event",
    "goals": "goal",
    "goal": "goal",
    "commitments": "commitment",
    "commitment": "commitment",
    "observations": "observation",
    "observation": "observation",
    "learnings": "learning",
    "learning": "learning",
    "relationships": "relationship",
    "relationship": "relationship",
    "context": "context",
    "artifacts": "artifact",
    "artifact": "artifact",
    "errors": "error",
    "error": "error",
}


def map_okf(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map an Open Knowledge Format (OKF) memory.md file or dict to Memanto payloads.

    Parses markdown sections (## Section), entries (### Title), metadata lines
    (*Confidence: ... | Tags: ... | Created: ...*), and body content.
    """
    raw_text = ""
    if isinstance(export, str):
        raw_text = export
    elif isinstance(export, dict):
        raw_text = export.get("content") or export.get("markdown") or export.get("text") or ""
        if not raw_text and "memories" in export:
            return map_generic(export)

    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    if not raw_text.strip():
        return rows

    current_type: str | None = None
    current_title: str | None = None
    current_lines: list[str] = []
    current_meta: dict[str, Any] = {}

    def flush_entry() -> None:
        nonlocal current_title, current_lines, current_meta, current_type
        if not current_title:
            return

        body_lines: list[str] = []
        tags: list[str] = list(current_meta.get("tags") or [])
        confidence = float(current_meta.get("confidence") or 0.9)
        created_at = current_meta.get("created_at")

        for line in current_lines:
            stripped = line.strip()
            if stripped.startswith("*") and stripped.endswith("*") and "|" in stripped:
                meta_content = stripped.strip("*").strip()
                parts = [p.strip() for p in meta_content.split("|")]
                for p in parts:
                    if p.lower().startswith("confidence:"):
                        try:
                            confidence = float(p.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                    elif p.lower().startswith("created:"):
                        created_at = _parse_dt(p.split(":", 1)[1].strip())
                    elif p.lower().startswith("tags:"):
                        tag_part = p.split(":", 1)[1].strip()
                        extracted_tags = [
                            t.strip().strip("`").strip("'\"")
                            for t in tag_part.split(",")
                            if t.strip().strip("`").strip("'\"")
                        ]
                        for t in extracted_tags:
                            if t not in tags:
                                tags.append(t)
            elif stripped in ("*No memories of this type.*", "*End of memory export.*"):
                continue
            else:
                body_lines.append(line)

        content = "\n".join(body_lines).strip()
        if not content:
            content = current_title

        safe_title = current_title
        if len(safe_title) > 100:
            footer = _format_supporting_data([("Original OKF Title", safe_title)])
            safe_title = safe_title[:97].rstrip() + "..."
            content = _attach_footer(content, footer)

        rows.append(
            {
                "title": safe_title,
                "content": content,
                "type": current_type,
                "tags": tags,
                "confidence": confidence,
                "source": "okf",
                "source_ref": safe_title,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )

        current_title = None
        current_lines = []
        current_meta = {}

    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("## ") and not stripped.startswith("### "):
            flush_entry()
            section_name = stripped[3:].strip().lower()
            current_type = _SECTION_LABEL_TO_TYPE.get(section_name) or _coerce_type(section_name)
        elif stripped.startswith("### "):
            flush_entry()
            current_title = stripped[4:].strip()
            current_lines = []
            current_meta = {}
        elif stripped == "---":
            if current_title:
                flush_entry()
        else:
            if current_title:
                current_lines.append(line)

    flush_entry()
    return rows


# --------------------------------------------------------------------------
# LangChain / LangGraph
# --------------------------------------------------------------------------


def map_langchain(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map LangChain/LangGraph conversation history, entities, and summaries to Memanto."""
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    summary = export.get("summary") or export.get("conversation_summary")
    if summary and isinstance(summary, str) and summary.strip():
        rows.append(
            {
                "title": _title_from(summary),
                "content": summary.strip(),
                "type": "context",
                "tags": ["langchain", "summary"],
                "confidence": 0.9,
                "source": "langchain",
                "source_ref": "summary",
                "provenance": "imported",
                "created_at": _pick_first_dt(export, ("created_at", "createdAt", "updated_at")),
                "updated_at": migrated_at,
            }
        )

    entities = export.get("entities") or export.get("entity_store") or {}
    if isinstance(entities, dict):
        for entity_name, entity_val in entities.items():
            if not entity_val:
                continue
            entity_str = str(entity_val)
            content = f"{entity_name}: {entity_str}"
            rows.append(
                {
                    "title": _title_from(content),
                    "content": content,
                    "type": "fact",
                    "tags": ["langchain", "entity", f"entity={entity_name}"],
                    "confidence": 0.85,
                    "source": "langchain",
                    "source_ref": f"entity:{entity_name}",
                    "provenance": "imported",
                    "created_at": None,
                    "updated_at": migrated_at,
                }
            )

    messages = (
        export.get("messages")
        or export.get("chat_history")
        or export.get("history")
        or export.get("buffer")
        or []
    )
    if isinstance(messages, list):
        for idx, msg in enumerate(messages):
            content = ""
            msg_type = "human"
            created_at = None

            if isinstance(msg, dict):
                content = (
                    msg.get("content")
                    or msg.get("text")
                    or (msg.get("data", {}).get("content") if isinstance(msg.get("data"), dict) else "")
                    or ""
                ).strip()
                msg_type = (
                    msg.get("type")
                    or (msg.get("data", {}).get("type") if isinstance(msg.get("data"), dict) else "")
                    or "message"
                )
                created_at = _pick_first_dt(msg, ("created_at", "createdAt", "timestamp"))
            elif isinstance(msg, str):
                content = msg.strip()

            if not content:
                continue

            mem_type: str = "context"
            if msg_type in ("human", "user"):
                mem_type = "instruction" if any(w in content.lower() for w in ["always", "never", "prefer", "must", "rule"]) else "context"
            elif msg_type in ("ai", "assistant"):
                mem_type = "learning"

            tags = ["langchain", f"role={msg_type}"]
            rows.append(
                {
                    "title": _title_from(content),
                    "content": content,
                    "type": mem_type,
                    "tags": tags,
                    "confidence": 0.8,
                    "source": "langchain",
                    "source_ref": f"msg:{idx}",
                    "provenance": "imported",
                    "created_at": created_at,
                    "updated_at": migrated_at,
                }
            )

    return rows


# --------------------------------------------------------------------------
# Generic / JSONL
# --------------------------------------------------------------------------


def map_generic(export: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map generic JSON/JSONL memory arrays to Memanto payloads."""
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    items: list[dict[str, Any]] = []
    if isinstance(export, list):
        items = export
    elif isinstance(export, dict):
        items = (
            export.get("memories")
            or export.get("items")
            or export.get("data")
            or export.get("records")
            or []
        )
        if not items and ("content" in export or "text" in export or "memory" in export):
            items = [export]

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        content = (
            item.get("content")
            or item.get("text")
            or item.get("memory")
            or item.get("body")
            or item.get("value")
            or ""
        ).strip()
        if not content:
            continue

        raw_title = item.get("title") or _title_from(content)
        raw_type = item.get("type") or item.get("category")
        mem_type = _coerce_type(raw_type)

        tags_val = item.get("tags") or []
        tags = [str(t) for t in tags_val] if isinstance(tags_val, (list, tuple)) else [str(tags_val)]

        confidence = 0.8
        if "confidence" in item:
            try:
                confidence = float(item["confidence"])
            except (ValueError, TypeError):
                pass

        created_at = _pick_first_dt(item, ("created_at", "createdAt", "timestamp", "date"))
        source_name = str(item.get("source") or "generic")
        source_ref = str(item.get("id") or item.get("source_ref") or f"gen:{idx}")

        rows.append(
            {
                "title": raw_title[:100],
                "content": content,
                "type": mem_type,
                "tags": tags,
                "confidence": confidence,
                "source": source_name,
                "source_ref": source_ref,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )

    return rows


MAPPERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "mem0": map_mem0,
    "letta": map_letta,
    "supermemory": map_supermemory,
    "okf": map_okf,
    "markdown": map_okf,
    "langchain": map_langchain,
    "langgraph": map_langchain,
    "generic": map_generic,
    "jsonl": map_generic,
}


def type_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count mapped rows by resolved (or unclassified) type — for previews."""
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("type") or "auto"
        counts[key] = counts.get(key, 0) + 1
    return counts
