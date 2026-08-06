"""Write mapped memories out as an OKF bundle.

This is the adapter's primary output because OKF is the only import path that
survives the trip with its provenance intact. ``memanto migrate okf`` reads
``x_memanto`` back out of the frontmatter, which means the resulting memories
land in Memanto labelled ``source: graphiti`` with the exact type and
confidence chosen here -- where the provider-JSON path would stamp everything
with the borrowed provider's name and a flat default confidence.

Layout mirrors Memanto's own exporter (``memories/<type>/<slug>.md`` plus
navigational ``index.md`` files) so the bundle is byte-compatible with the
loader in ``memanto/cli/migrate/okf_loader.py``: index documents are declared
``type: index`` and skipped on import, and everything importable sits under
``memories/``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from graphiti_okf.mapping import MappedMemory

# Keys the OKF loader recognises natively. Anything else we put in the
# frontmatter is preserved as "extra" and rendered into the [Supporting data]
# footer on import -- which is exactly where the temporal fields need to land.
_OKF_BASELINE_KEYS = ("type", "title", "description", "tags", "timestamp", "resource")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:60].rstrip("-") or "memory"


def _unique_slug(title: str, used: set[str]) -> str:
    base = _slugify(title)
    slug = base
    counter = 2
    while slug in used:
        slug = f"{base}-{counter}"
        counter += 1
    used.add(slug)
    return slug


def _first_line(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:200]
    return ""


def build_frontmatter(record: MappedMemory) -> dict[str, Any]:
    """Assemble one OKF document's YAML frontmatter."""
    frontmatter: dict[str, Any] = {"type": record.type, "title": record.title}

    description = _first_line(record.content)
    if description:
        frontmatter["description"] = description
    if record.tags:
        frontmatter["tags"] = list(record.tags)
    if record.created_at:
        frontmatter["timestamp"] = record.created_at.isoformat()
    if record.source_ref:
        frontmatter["resource"] = record.source_ref

    frontmatter["x_memanto"] = {
        "confidence": record.confidence,
        "provenance": "imported",
        "source": "graphiti",
        "type": record.type,
    }

    # Temporal validity + Graphiti provenance ride along as non-baseline keys.
    for key, value in record.temporal.items():
        if value not in (None, ""):
            frontmatter[f"graphiti_{key}" if key == "status" else key] = value
    for key, value in record.extra.items():
        if value not in (None, ""):
            frontmatter[key] = value

    return frontmatter


def render_document(record: MappedMemory) -> str:
    """Render one memory as a single OKF markdown document."""
    front = yaml.safe_dump(
        build_frontmatter(record),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{front}\n---\n\n{record.content}\n"


def _write_index(directory: Path, title: str, heading: str, links: list[tuple[str, str]]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "---",
        "type: index",
        f"title: {title}",
        f"timestamp: {now}",
        "---",
        "",
        f"# {heading}",
        "",
    ]
    lines += [f"- [{text}]({rel})" for text, rel in links]
    lines.append("")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_bundle(
    records: list[MappedMemory],
    output_dir: Path,
    *,
    agent_label: str = "graphiti-import",
) -> dict[str, Any]:
    """Write an OKF bundle and return a summary of what was written."""
    output_dir = Path(output_dir)
    memories_dir = output_dir / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    by_type: dict[str, list[MappedMemory]] = {}
    for record in records:
        by_type.setdefault(record.type, []).append(record)

    per_type_counts: dict[str, int] = {}
    for mem_type, group in sorted(by_type.items()):
        type_dir = memories_dir / mem_type
        type_dir.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()
        links: list[tuple[str, str]] = []
        for record in group:
            slug = _unique_slug(record.title, used)
            (type_dir / f"{slug}.md").write_text(render_document(record), encoding="utf-8")
            links.append((record.title, f"{slug}.md"))
        _write_index(type_dir, mem_type, f"{mem_type} ({len(links)})", links)
        per_type_counts[mem_type] = len(group)

    _write_index(
        memories_dir,
        "memories",
        f"Memories ({len(records)})",
        [(mem_type, f"{mem_type}/index.md") for mem_type in sorted(per_type_counts)],
    )
    _write_index(
        output_dir,
        f"{agent_label} knowledge bundle",
        f"{agent_label} — OKF bundle (migrated from Graphiti)",
        [("memories", "memories/index.md")],
    )

    return {
        "output_path": str(output_dir.resolve()),
        "total_memories": len(records),
        "per_type_counts": per_type_counts,
    }
