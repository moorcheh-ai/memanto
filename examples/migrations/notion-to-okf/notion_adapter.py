"""
notion_adapter.py
=================
Notion database export → Memanto memory payloads.

Notion stores knowledge as pages inside databases. Each page has:
  - A title and rich-text content block
  - Database properties (Tags, Status, Priority, Type, etc.)
  - Created/last-edited timestamps
  - A canonical Notion URL

This adapter extracts all pages from a Notion export (either from the
official Notion API via ``fetch_notion_export.py`` or from a pre-exported
JSON saved by the populate script) and maps them to Memanto's memory schema.

Notion property → Memanto field mapping:
  page.title          → memory.title
  page.content        → memory.content (+ [Supporting data] footer)
  properties.Type     → memory.type (mapped via NOTION_TYPE_MAP)
  properties.Tags     → memory.tags
  page.created_time   → memory.created_at
  page.id             → memory.source_ref
  page.database       → footer.Notion database
  page.url            → footer.Notion URL

Adding this adapter to the Memanto CLI:
  Register ``map_notion`` in ``memanto/cli/migrate/mappers.py``:

      from examples.migrations.notion_to_okf.notion_adapter import map_notion
      MAPPERS["notion"] = map_notion

  Then run:
      memanto migrate notion --file notion_export.json --agent-id my-agent
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ── Type mapping ──────────────────────────────────────────────────────────────

# Maps Notion database property "Type" values onto Memanto's typed primitives.
# Unrecognised values fall through to None (server auto-classifies).
NOTION_TYPE_MAP: dict[str, str] = {
    "fact": "fact",
    "preference": "preference",
    "decision": "decision",
    "commitment": "commitment",
    "goal": "goal",
    "observation": "observation",
    "event": "event",
    "relationship": "relationship",
    "artifact": "artifact",
    "task": "commitment",  # Notion "task" → Memanto commitment
    "note": "fact",  # generic notes → fact
    "research": "fact",
    "bookmark": "fact",
    "resource": "artifact",
    "meeting": "event",
    "planning": "event",
}

# Notion status values that indicate a page is archived/cancelled/irrelevant.
# These pages are skipped during migration.
_SKIP_STATUSES: set[str] = {"Archived", "Cancelled", "Trash", "Deleted"}

_DEFAULT_TITLE_CHARS = 80
_MAX_CONTENT_CHARS = 10_000
_MAX_FOOTER_CHARS = 800


# ── Helpers (mirrors mappers.py conventions) ───────────────────────────────────


def _title_from(content: str) -> str:
    text = content.strip().replace("\n", " ")
    if len(text) <= _DEFAULT_TITLE_CHARS:
        return text
    return text[: _DEFAULT_TITLE_CHARS - 3].rstrip() + "..."


def _coerce_type(raw: str | None) -> str | None:
    if not raw:
        return None
    return NOTION_TYPE_MAP.get(raw.strip().lower())


def _parse_dt(value: Any) -> datetime | None:
    """Parse ISO 8601 timestamp strings into UTC-aware datetimes."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _format_supporting_data(items: list[tuple[str, Any]]) -> str:
    """Render the [Supporting data] footer (mirrors mappers.py)."""
    lines: list[str] = []
    for label, value in items:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value if v not in (None, ""))
            if not value:
                continue
        elif isinstance(value, dict):
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
    if not footer:
        return content
    budget = _MAX_CONTENT_CHARS - len(footer)
    if budget < 0:
        return content[:_MAX_CONTENT_CHARS]
    trimmed = content if len(content) <= budget else content[: budget - 4] + "\n..."
    return trimmed + footer


# ── Core mapper ────────────────────────────────────────────────────────────────


def map_notion(export: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Map a Notion export to Memanto memory payloads.

    Accepts the JSON shape produced by ``fetch_notion_export.py`` (via the
    official Notion API) or ``populate.py`` (the pre-canned sample).

    Args:
        export: Dict with ``pages`` list and optional ``export_metadata``.

    Returns:
        List of memory dicts ready for ``SdkClient.batch_remember``.
    """
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()
    seen_ids: set[str] = set()

    for page in export.get("pages", []) or []:
        # Skip blank or duplicate pages
        page_id = page.get("id", "")
        if not page_id or page_id in seen_ids:
            continue
        seen_ids.add(page_id)

        title = (page.get("title") or "").strip()
        content = (page.get("content") or "").strip()

        # Skip truly empty pages
        if not content and not title:
            continue

        # Use title as content fallback for pages with no body
        if not content:
            content = title

        # Extract properties
        props = page.get("properties") or {}
        status = str(props.get("Status") or "").strip()

        # Skip archived/cancelled pages
        if status in _SKIP_STATUSES:
            continue

        # Memory type: prefer explicit property, fall back to database-level hint
        raw_type = props.get("Type") or props.get("Category") or props.get("Kind")
        memory_type = _coerce_type(str(raw_type)) if raw_type else None

        # If no explicit type, infer from database name
        if not memory_type:
            db = str(page.get("database") or "").lower()
            if "decision" in db:
                memory_type = "decision"
            elif "meeting" in db:
                memory_type = "event"
            elif "bookmark" in db or "resource" in db:
                memory_type = "fact"

        # Tags: combine Notion tags + database name tag
        notion_tags = [str(t) for t in (props.get("Tags") or []) if t]
        db_name = page.get("database")
        if db_name:
            db_tag = f"notion-db:{db_name.lower().replace(' ', '-')}"
            if db_tag not in notion_tags:
                notion_tags.append(db_tag)

        # Timestamps
        created_at = _parse_dt(page.get("created_time"))
        edited_at = _parse_dt(page.get("last_edited_time"))

        # Confidence: High/Critical priority → 0.9, Medium → 0.8, Low → 0.7
        priority = str(props.get("Priority") or "").strip().lower()
        confidence = {"critical": 0.95, "high": 0.9, "medium": 0.8, "low": 0.7}.get(
            priority, 0.8
        )

        # Build supporting data footer
        attendees = props.get("Attendees")
        meeting_date = props.get("Meeting Date")
        assignee = (
            props.get("Decision Made By") or props.get("Assignee") or props.get("Owner")
        )

        footer = _format_supporting_data(
            [
                ("Source", f"notion:{page_id}"),
                ("Notion database", page.get("database")),
                ("Notion URL", page.get("url")),
                ("Notion status", status or None),
                ("Priority", props.get("Priority")),
                ("Last edited", edited_at.isoformat() if edited_at else None),
                ("Source created_at", created_at.isoformat() if created_at else None),
                ("Attendees", attendees),
                ("Meeting date", meeting_date),
                ("Decision by", assignee),
            ]
        )

        rows.append(
            {
                "title": title or _title_from(content),
                "content": _attach_footer(content, footer),
                "type": memory_type,
                "tags": notion_tags,
                "confidence": confidence,
                "source": "notion",
                "source_ref": page_id,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )

    return rows


def source_count(export: dict[str, Any]) -> int:
    """Count source pages in the export (for migration summary)."""
    return len(export.get("pages", []) or [])
