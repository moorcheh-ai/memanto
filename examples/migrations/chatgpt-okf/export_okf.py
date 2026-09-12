"""
Export a ChatGPT data export into a portable OKF (Open Knowledge Format)
bundle.

This is the "portability" half of the #1609 migration showcase: after you map
your ChatGPT statements into memory records, this script renders them as an
OKF bundle -- one self-contained markdown file per conversation, with YAML
frontmatter that round-trips back into Memanto via ``memanto migrate okf``.

Usage:
    python3 export_okf.py <conversations.json> <out-dir> [--limit N]

The output layout matches Memanto's own OKF exports:
    <out-dir>/
        memories/
            <slug>-<conversation-id>.md

Each file uses the ``<!-- okf-entry -->`` delimiter so multiple memories from
the same conversation stay in one readable document, exactly like Memanto's
``memory export --okf`` output.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from memanto.cli.migrate.chatgpt_export import (
        export_chatgpt_memories,
        load_conversations,
    )
except ImportError:  # running from a source checkout without installing the package
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from memanto.cli.migrate.chatgpt_export import (  # type: ignore[no-redef]
        export_chatgpt_memories,
        load_conversations,
    )

import yaml  # type: ignore[import-untyped]

ENTRY_DELIMITER = "<!-- okf-entry -->"
_MAX_SLUG = 60
_MAX_DESC = 200
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _slugify(title: str) -> str:
    """Turn a conversation title into a short lowercase slug for filenames."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:_MAX_SLUG] or "conversation"


def _safe_component(value: Any, fallback: str = "conv") -> str:
    """Return a filesystem-safe identifier from an untrusted source string.

    Only ASCII letters/digits/hyphen/underscore survive; anything else is
    stripped. This neutralizes path-traversal attempts (``../``, absolute
    paths) and over-long or exotic IDs before they reach the output path.
    """
    text = str(value or "")
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", text)
    cleaned = cleaned[:_MAX_SLUG].rstrip(". ")
    if cleaned.upper() in _WINDOWS_RESERVED or not cleaned:
        return fallback
    return cleaned


def _unique_name(prefix: str, key: str) -> str:
    """Return ``prefix-<hash8>`` so sanitized keys never collide."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _conversation_id(mem: dict[str, Any]) -> str:
    """Extract the conversation id from a memory's ``id`` (``<conv>:<node>``)."""
    raw = str(mem.get("id") or "")
    return raw.split(":", 1)[0] if ":" in raw else raw


def _render_mem_to_okf(mem: dict[str, Any]) -> str:
    """Render one memory record as an OKF markdown document."""
    content = (mem.get("content") or "").strip()
    content = content.replace(ENTRY_DELIMITER, "<!-- okf-entry (escaped) -->")
    raw_tags = mem.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    tags = [str(t) for t in raw_tags if t]
    created = mem.get("created_at")
    source_ref = mem.get("id") or ""

    front: dict[str, Any] = {
        "type": "memory",
        "title": mem.get("title") or content[:_MAX_SLUG] or "Untitled",
        "okf_version": "0.2",
    }
    first_line = ""
    if content:
        first_line = content.splitlines()[0].strip().lstrip("#").strip()
        first_line = first_line[:_MAX_DESC]
    if first_line:
        front["description"] = first_line
    if tags:
        front["tags"] = tags
    if created:
        # OKF v0.2: exporters carry provenance + generated-at metadata in a
        # top-level `generated` block; the loader keeps it as `extra` and
        # map_okf reads `extra.generated.at` for created_at.
        source = mem.get("source") or "process:chatgpt"
        front["generated"] = {
            "by": source,
            "at": _iso_timestamp(created),
        }
    if source_ref:
        front["resource"] = source_ref

    front["x_memanto"] = {
        "source": "chatgpt",
        "provenance": "imported",
        "confidence": 0.7,
    }

    rendered = yaml.safe_dump(
        front,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{rendered}\n---\n\n{content}\n"


def write_okf_bundle(
    export: dict[str, Any],
    out_dir: Path,
    *,
    limit: int | None = None,
    force: bool = False,
) -> list[Path]:
    """Write one .md file per conversation (memories joined by OKF delimiter)."""
    memories = export.get("memories", [])
    if limit is not None:
        memories = memories[:limit]

    # Group by conversation id (unique) rather than title (may repeat), so
    # same-titled conversations never cross-contaminate one file.
    by_conv: dict[str, list[dict[str, Any]]] = {}
    conv_titles: dict[str, str] = {}
    for mem in memories:
        conv_id = _conversation_id(mem) or "misc"
        by_conv.setdefault(conv_id, []).append(mem)
        conv_tag = next(
            (t for t in (mem.get("tags") or []) if str(t).startswith("conversation:")),
            None,
        )
        if conv_tag:
            conv_titles.setdefault(conv_id, str(conv_tag).split(":", 1)[1])

    out_dir.mkdir(parents=True, exist_ok=True)
    memories_dir = out_dir / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1 — compute every target and validate collisions BEFORE writing
    # anything, so a conflict never leaves a partially-written bundle behind.
    plans: list[tuple[Path, str]] = []
    for conv_id, items in by_conv.items():
        title = conv_titles.get(conv_id, "conversation")
        slug = _slugify(title)
        safe_id = _safe_component(conv_id)
        target = memories_dir / f"{_unique_name(f'{slug}-{safe_id}', conv_id)}.md"
        docs = [_render_mem_to_okf(mem) for mem in items]
        plans.append((target, f"\n{ENTRY_DELIMITER}\n".join(docs)))

    if not force:
        existing = [p for p, _ in plans if p.exists()]
        if existing:
            names = ", ".join(p.name for p in existing[:5])
            raise FileExistsError(
                f"{len(existing)} file(s) already exist ({names}); "
                "pass --force to overwrite"
            )

    # Phase 2 — write everything.
    written: list[Path] = []
    for target, body in plans:
        target.write_text(body, encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse a ChatGPT export and write an OKF bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conversations", type=Path, help="path to conversations.json")
    parser.add_argument("out_dir", type=Path, help="output OKF bundle directory")
    parser.add_argument("--limit", type=int, default=None, help="max memories to export")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args(argv)

    if not args.conversations.exists():
        parser.error(f"not found: {args.conversations}")

    try:
        conversations = load_conversations(args.conversations)
        export = export_chatgpt_memories(conversations)
        written = write_okf_bundle(
            export, args.out_dir, limit=args.limit, force=args.force
        )
    except (FileNotFoundError, OSError, ValueError, FileExistsError, TypeError) as exc:
        parser.error(f"{exc}")
    print(f"Exported {len(written)} files -> {args.out_dir}")
    return 0


def _iso_timestamp(value: Any) -> str:
    """Normalize a unix-epoch or ISO timestamp into an ISO-8601 UTC string."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(value)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return text
    return dt.isoformat() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
