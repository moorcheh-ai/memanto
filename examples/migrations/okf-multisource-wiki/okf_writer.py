"""Write valid OKF v0.2 bundles consumable by ``memanto migrate okf``."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

VALID_TYPES = {
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


def _slug(title: str, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (text or fallback)[:80]


def _dump_frontmatter(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()


def memory_to_okf_doc(mem: dict[str, Any]) -> tuple[str, str]:
    """Return (relative_path_under_memories, markdown_document)."""
    mem_type = mem.get("type") if mem.get("type") in VALID_TYPES else "observation"
    title = (mem.get("title") or mem.get("content", "")[:80]).strip()
    created = mem.get("created_at") or datetime.now(timezone.utc).isoformat()
    if isinstance(created, datetime):
        created = created.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    frontmatter: dict[str, Any] = {
        "type": mem_type,
        "title": title,
        "description": (mem.get("description") or title)[:200],
        "tags": list(mem.get("tags") or []),
        "generated": {
            "by": f"process:{mem.get('source', 'migration')}",
            "at": created,
        },
        "resource": mem.get("source_ref")
        or f"urn:memanto-migration:{_slug(title, 'm')}",
        "x_memanto": {
            "type": mem_type,
            "confidence": float(mem.get("confidence", 0.85)),
            "provenance": mem.get("provenance", "imported"),
            "source": mem.get("source", "okf"),
            "id": mem.get("id"),
        },
    }
    # Lossless extras — unknown OKF keys ride in frontmatter; map_okf preserves them.
    for key in ("chroma_id", "sqlite_id", "session_id", "supersedes", "sources"):
        if mem.get(key) is not None:
            frontmatter[key] = mem[key]

    body = (mem.get("content") or title).strip()
    doc = f"---\n{_dump_frontmatter(frontmatter)}\n---\n\n{body}\n"
    filename = f"{_slug(title, mem.get('id', 'memory'))}.md"
    return f"{mem_type}/{filename}", doc


def write_okf_bundle(
    memories: list[dict[str, Any]],
    bundle_dir: Path,
    *,
    agent_id: str = "multisource-wiki",
    session_notes: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Write a Memanto-compatible OKF bundle. Returns a summary dict."""
    if bundle_dir.exists():
        for path in sorted(bundle_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    memories_root = bundle_dir / "memories"
    memories_root.mkdir(parents=True, exist_ok=True)

    by_type: dict[str, int] = defaultdict(int)
    written: list[str] = []
    for mem in memories:
        rel, doc = memory_to_okf_doc(mem)
        target = memories_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Avoid collisions when two titles slug the same way.
        if target.exists():
            stem = target.stem
            target = target.with_name(f"{stem}-{mem.get('id', 'x')[:8]}.md")
        target.write_text(doc, encoding="utf-8")
        mem_type = mem.get("type") if mem.get("type") in VALID_TYPES else "observation"
        by_type[str(mem_type)] += 1
        written.append(str(target.relative_to(bundle_dir)))

    # Per-type indexes
    for type_name, count in by_type.items():
        type_dir = memories_root / type_name
        type_dir.mkdir(parents=True, exist_ok=True)
        (type_dir / "index.md").write_text(
            f"---\ntype: index\ntitle: {type_name}\n---\n\n"
            f"# {type_name}\n\n{count} memories in this type.\n",
            encoding="utf-8",
        )

    (memories_root / "index.md").write_text(
        "---\ntype: index\ntitle: memories\n---\n\n"
        f"# Memories\n\n{len(memories)} consolidated memories.\n",
        encoding="utf-8",
    )

    if session_notes:
        sessions_dir = bundle_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        for name, body in session_notes:
            (sessions_dir / f"{_slug(name, 'session')}.md").write_text(
                f"---\ntype: index\ntitle: {name}\n---\n\n{body}\n",
                encoding="utf-8",
            )

    sections = ["memories"]
    if session_notes:
        sections.append("sessions")
    section_lines = "\n".join(f"- [{s}/](./{s}/)" for s in sections)
    (bundle_dir / "index.md").write_text(
        f'---\nokf_version: "0.2"\ntype: index\ntitle: {agent_id}\n'
        f"generated:\n  by: process:okf-multisource-wiki\n"
        f"  at: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}\n"
        f"---\n\n# {agent_id}\n\n"
        f"Consolidated portable memory wiki ({len(memories)} memories).\n\n"
        f"## Sections\n\n{section_lines}\n",
        encoding="utf-8",
    )

    return {
        "total_memories": len(memories),
        "per_type_counts": dict(by_type),
        "files": written,
        "bundle_dir": str(bundle_dir.resolve()),
    }
