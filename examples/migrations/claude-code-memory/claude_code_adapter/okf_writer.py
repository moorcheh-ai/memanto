"""OKF bundle writer for extracted Claude Code memories.

Produces the directory layout expected by ``memanto migrate okf``:

    <bundle>/
      index.md
      memories/
        <type>/
          index.md
          <slug>.md

Each memory document uses Memanto's OKF frontmatter contract (type, title,
description, tags, timestamp, resource, and the namespaced ``x_memanto``
block) so imports are lossless.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

_MEMORY_TYPE_ORDER = [
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
]

# Fixed timestamp so regenerated bundles are byte-stable across runs. The
# demo session and its bundle are deterministic artifacts; index documents
# must not drift with the wall clock.
_BUNDLE_TIMESTAMP = "2026-07-28T09:00:00+00:00"


def _slugify(title: str) -> str:
    """Turn a memory title into a lowercase, filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:60].rstrip("-") or "memory"


def _unique_slug(title: str, used: set[str]) -> str:
    """Return a slug that does not collide with any already-used slug."""
    base = _slugify(title)
    slug = base
    counter = 2
    while slug in used:
        slug = f"{base}-{counter}"
        counter += 1
    used.add(slug)
    return slug


def _render_doc(entry: dict[str, Any], mem_type: str) -> str:
    """Render one OKF entry as a markdown document with YAML frontmatter."""
    content = (entry.get("body") or "").strip()
    frontmatter: dict[str, Any] = {
        "type": mem_type,
        "title": entry.get("title") or "Untitled",
    }
    description = entry.get("description")
    if description:
        frontmatter["description"] = description
    tags = entry.get("tags") or []
    if tags:
        frontmatter["tags"] = list(tags)
    if entry.get("timestamp"):
        frontmatter["timestamp"] = entry["timestamp"]
    if entry.get("resource"):
        frontmatter["resource"] = entry["resource"]
    x_memanto = entry.get("x_memanto") or {}
    if x_memanto:
        frontmatter["x_memanto"] = x_memanto

    front = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{front}\n---\n\n{content}\n"


def _write_index(
    directory: Path, title: str, heading: str, links: list[tuple[str, str]]
) -> None:
    """Write a navigation index document with deterministic frontmatter."""
    frontmatter = {
        "type": "index",
        "title": title,
        "timestamp": _BUNDLE_TIMESTAMP,
    }
    front = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    lines = [
        f"---\n{front}\n---",
        "",
        f"# {heading}",
        "",
    ]
    lines += [f"- [{text}]({rel})" for text, rel in links]
    lines.append("")
    (directory / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_okf_bundle(
    memories: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    bundle_title: str = "Claude Code memory bundle",
) -> dict[str, Any]:
    """Write extracted memories to an OKF bundle directory.

    Returns a dict with the output path and per-type counts.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    memories_dir = output / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    by_type: dict[str, list[dict[str, Any]]] = {}
    for entry in memories:
        mem_type = str(entry.get("type") or "fact")
        if mem_type not in _MEMORY_TYPE_ORDER:
            mem_type = "fact"
        by_type.setdefault(mem_type, []).append(entry)

    per_type: dict[str, int] = {}
    for mem_type in _MEMORY_TYPE_ORDER:
        entries = by_type.get(mem_type) or []
        if not entries:
            continue
        type_dir = memories_dir / mem_type
        type_dir.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()
        links: list[tuple[str, str]] = []
        for entry in entries:
            slug = _unique_slug(entry.get("title") or "memory", used)
            (type_dir / f"{slug}.md").write_text(
                _render_doc(entry, mem_type), encoding="utf-8"
            )
            links.append((entry.get("title") or "Untitled", f"{slug}.md"))
        _write_index(type_dir, mem_type, f"{mem_type} ({len(links)})", links)
        per_type[mem_type] = len(entries)

    total = sum(per_type.values())
    _write_index(
        memories_dir,
        "memories",
        f"Memories ({total})",
        [(mem_type, f"{mem_type}/index.md") for mem_type in per_type],
    )

    root_frontmatter = {
        "type": "index",
        "title": bundle_title,
        "timestamp": _BUNDLE_TIMESTAMP,
    }
    front = yaml.safe_dump(
        root_frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    root_lines = [
        f"---\n{front}\n---",
        "",
        f"# {bundle_title}",
        "",
        f"- [memories](memories/index.md) — {total} memories across {len(per_type)} type(s)",
        "",
    ]
    (output / "index.md").write_text("\n".join(root_lines), encoding="utf-8")

    return {
        "output_path": str(output.resolve()),
        "total_memories": total,
        "per_type_counts": per_type,
    }
