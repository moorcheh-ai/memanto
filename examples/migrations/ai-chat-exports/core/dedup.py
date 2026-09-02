from __future__ import annotations

import re
from pathlib import Path

from core.models import MemoryEntity

_RESOURCE_RE = re.compile(r"^resource:\s*(.+?)\s*$")


def collect_existing_refs(bundle_dir: str | Path) -> set[str]:
    """Collect source_ref values already present in an OKF bundle.

    Reads every memory markdown file under ``<bundle>/memories/**`` and pulls
    the YAML ``resource:`` value (the stable source ref Memanto preserves).
    """
    root = Path(bundle_dir)
    refs: set[str] = set()
    if not root.is_dir():
        return refs

    for md in root.glob("memories/**/*.md"):
        if md.name == "index.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        in_frontmatter = False
        for line in text.splitlines():
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                m = _RESOURCE_RE.match(line)
                if m:
                    refs.add(m.group(1).strip())
    return refs


def dedupe_entities(
    entities: list[MemoryEntity], existing_refs: set[str]
) -> tuple[list[MemoryEntity], list[MemoryEntity]]:
    """Split entities into keep/skipped by whether their source_ref is new.

    An entity whose ``source_ref`` is already in ``existing_refs`` is treated
    as a duplicate and returned in ``skipped``.
    """
    keep: list[MemoryEntity] = []
    skipped: list[MemoryEntity] = []
    for e in entities:
        if e.source_ref and e.source_ref in existing_refs:
            skipped.append(e)
        else:
            keep.append(e)
    return keep, skipped
