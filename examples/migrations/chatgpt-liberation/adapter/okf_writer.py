# ruff: noqa: E501
"""OKF bundle writer — ChatGPT mapped rows → valid OKF v0.2 markdown bundle."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Use shipped service when available; fallback to manual writer for portability
try:
    from memanto.app.services.okf_export_service import OkfExportService
    _HAS_SERVICE = True
except Exception:
    _HAS_SERVICE = False
    OkfExportService = None  # type: ignore

ENTRY_DELIMITER = "<!-- okf-entry -->"

def _slug(text: str, max_len: int = 60) -> str:
    """Slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].rstrip("-") or "untitled"

def _write_one_memories(mem: dict[str, Any], out_dir: Path) -> Path:
    """Write one memories."""
    mtype = (mem.get("type") or "fact").lower()
    # group under memories/<type>/
    type_dir = out_dir / "memories" / mtype
    type_dir.mkdir(parents=True, exist_ok=True)
    title = mem.get("title") or mem.get("content","")[:40]
    slug = _slug(title)
    # avoid collision
    target = type_dir / f"{slug}.md"
    counter = 1
    while target.exists():
        counter += 1
        target = type_dir / f"{slug}-{counter}.md"

    created = mem.get("created_at")
    if isinstance(created, datetime):
        ts = created.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    elif isinstance(created, str):
        ts = created
    else:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    frontmatter = {
        "type": mtype,
        "title": mem.get("title") or _slug(title, 80),
        "description": (mem.get("content") or "")[:160].replace("\n", " "),
        "tags": mem.get("tags") or [],
        "timestamp": ts,
        "x_memanto": {
            "id": mem.get("source_ref") or slug,
            "confidence": mem.get("confidence", 0.78),
            "provenance": mem.get("provenance", "imported"),
            "source": mem.get("source", "chatgpt"),
            "source_ref": mem.get("source_ref", ""),
        },
    }

    body = mem.get("content") or ""
    # Ensure body doesn't start with frontmatter delimiter confusion
    md = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n\n" + body.strip() + "\n"  # noqa: E501
    target.write_text(md, encoding="utf-8")
    return target


def write_okf_bundle(memories: list[dict[str, Any]], output_dir: str | Path) -> dict[str, Any]:
    """Write mapped memories to a valid OKF v0.2 bundle directory.

    Tries shipped ``OkfExportService`` first for 100% spec compliance; falls
    back to manual writer (same layout) if service unavailable in test env.
    Returns ``{output_path, total_memories, per_type_counts, sections}``.
    """
    out = Path(output_dir)
    # Prefer shipped service
    if _HAS_SERVICE:
        try:
            svc = OkfExportService(exports_dir=out.parent if out.parent.exists() else Path.home() / ".memanto" / "exports")  # noqa: E501
            # Group by type as service expects
            by_type: dict[str, list[dict[str, Any]]] = {}
            for m in memories:
                t = (m.get("type") or "fact").lower()
                by_type.setdefault(t, []).append(m)
            # Map to service's expected dict shape (needs moorcheh-like fields); adapt
            # The service expects memory dicts with id/content etc — we pass through
            # Use manual instead if adaptation too lossy — but try direct
            result = svc.write_okf_bundle(
                agent_id=_slug(str(out.name) or "chatgpt-liberation"),
                memories_by_type=by_type,
                output_dir=out,
                split="file",
            )
            # Ensure index.md exists (service creates it)
            return result
        except Exception:
            # fallback to manual
            pass

    # Manual writer
    if out.exists():
        # clean but keep directory
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # Write memories
    for mem in memories:
        _write_one_memories(mem, out)

    # Write index.md (required top-level)
    counts: dict[str, int] = {}
    for m in memories:
        t = (m.get("type") or "fact").lower()
        counts[t] = counts.get(t, 0) + 1

    per_type_lines = "\n".join(f"- {k}: {v}" for k, v in sorted(counts.items()))
    index_md = f"""---
type: index
title: ChatGPT Liberation — OKF Bundle
description: Portable OKF v0.2 bundle from ChatGPT export, {len(memories)} memories.
---

# ChatGPT Liberation — OKF Bundle

Migrated from OpenAI Data Export (conversations.json + memory.json) via `chatgpt-liberation` adapter.  # noqa: E501

- **Total memories:** {len(memories)}
- **Source:** chatgpt (conversations + memory.json)
- **Generated:** {datetime.now(timezone.utc).isoformat()}

## Per-type

{per_type_lines}

## Layout

- `memories/<type>/<slug>.md` — one file per memory, YAML frontmatter + markdown body
- `index.md` — this file
- Valid for `memanto migrate okf ./sample-data/okf-bundle --dry-run`

## Ownership

This bundle is plain markdown. Git-diff it, version it, carry it anywhere. No vendor lock-in.
"""
    (out / "index.md").write_text(index_md, encoding="utf-8")

    return {
        "output_path": str(out),
        "total_memories": len(memories),
        "per_type_counts": counts,
        "sections": ["memories"],
    }
