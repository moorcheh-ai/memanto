"""okf_bundle.py - Minimal OKF bundle reader/writer used by the demo scripts.

The real OKF spec lives at https://github.com/GoogleCloudPlatform/knowledge-catalog
and Memanto's implementation is documented at https://docs.memanto.ai/integrations/okf.

This module intentionally stays tiny: it is a *helper for the showcase*, not a
re-implementation of Memanto's shipped OKF tooling. It reads and writes the
same on-disk layout Memanto produces:

    <bundle>/
        memories/
            <type>/
                <slug>.md      # one concept per file, YAML frontmatter + markdown body

Known frontmatter fields mirror Memanto's OKF export (baseline OKF fields plus
the namespaced ``x_memanto`` block for round-trip fidelity).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# ---------------------------------------------------------------------------
# OKF constants
# ---------------------------------------------------------------------------

# Memanto memory types, in the canonical order used by memory_export_service.py.
MEMORY_TYPE_ORDER = [
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

# Baseline OKF fields + Memanto's namespaced extension block (lossless import).
KNOWN_FIELDS = {
    "type",
    "title",
    "description",
    "resource",
    "tags",
    "timestamp",
    "x_memanto",
}

_SKIP_FILENAMES = {"index.md", "log.md"}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


@dataclass
class Memory:
    """One OKF memory entry."""

    type: str
    title: str
    body: str = ""
    description: str = ""
    resource: str = ""
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""
    x_memanto: dict[str, Any] = field(default_factory=dict)
    # Path of the file this entry came from (empty for synthetic entries).
    # Excluded from equality: the same memory loaded from two bundle paths
    # (or two git revisions) must compare equal on content alone.
    source_file: str = field(default="", compare=False)

    @property
    def slug(self) -> str:
        return slugify(self.title)

    def frontmatter(self) -> dict[str, Any]:
        fm: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
        }
        if self.description:
            fm["description"] = self.description
        if self.resource:
            fm["resource"] = self.resource
        if self.tags:
            fm["tags"] = self.tags
        if self.timestamp:
            fm["timestamp"] = self.timestamp
        if self.x_memanto:
            fm["x_memanto"] = self.x_memanto
        return fm

    def to_markdown(self) -> str:
        """Serialize to an OKF markdown document (frontmatter + body)."""
        lines = ["---", yaml.safe_dump(self.frontmatter(), sort_keys=False).strip(), "---"]
        body = self.body.strip()
        if body:
            lines.append("")
            lines.append(body)
        return "\n".join(lines) + "\n"

    @classmethod
    def from_markdown(cls, text: str, source_file: str = "") -> "Memory":
        """Parse one OKF markdown document."""
        m = _FRONTMATTER_RE.match(text.strip())
        if not m:
            raise ValueError(f"Missing YAML frontmatter in {source_file or '<memory>'}")
        raw = yaml.safe_load(m.group(1)) or {}
        body = m.group(2).strip()
        mem = cls(
            type=str(raw.get("type", "fact")),
            title=str(raw.get("title", "")).strip() or Path(source_file).stem,
            body=body,
            description=str(raw.get("description", "") or ""),
            resource=str(raw.get("resource", "") or ""),
            tags=list(raw.get("tags", []) or []),
            timestamp=str(raw.get("timestamp", "") or ""),
            x_memanto=dict(raw.get("x_memanto", {}) or {}),
            source_file=source_file,
        )
        return mem


# ---------------------------------------------------------------------------
# Bundle I/O
# ---------------------------------------------------------------------------


def load_bundle(bundle_dir: str | Path) -> dict[str, list[Memory]]:
    """Load every importable memory from an OKF bundle directory.

    Mirrors ``okf_loader.load_okf_bundle`` scoping: when the bundle has a
    ``memories/`` directory, only that subtree is imported; ``index.md`` /
    ``log.md`` navigation files are skipped.
    """
    root = Path(bundle_dir)
    if not root.exists():
        raise FileNotFoundError(f"OKF bundle not found: {bundle_dir}")
    memories_dir = root / "memories"
    scan_root = memories_dir if memories_dir.is_dir() else root
    by_type: dict[str, list[Memory]] = {t: [] for t in MEMORY_TYPE_ORDER}
    for file_path in sorted(scan_root.rglob("*.md")):
        if file_path.name.lower() in _SKIP_FILENAMES:
            continue
        text = file_path.read_text(encoding="utf-8")
        try:
            mem = Memory.from_markdown(text, str(file_path))
        except ValueError:
            continue
        by_type.setdefault(mem.type, []).append(mem)
    return by_type


def all_memories(bundle_dir: str | Path) -> list[Memory]:
    """Flatten a loaded bundle into one list, in canonical type order."""
    by_type = load_bundle(bundle_dir)
    flat: list[Memory] = []
    for t in MEMORY_TYPE_ORDER:
        flat.extend(sorted(by_type.get(t, []), key=lambda m: (m.timestamp, m.title)))
    return flat


def write_bundle(bundle_dir: str | Path, memories: Iterable[Memory]) -> int:
    """Write memories into an OKF bundle directory. Returns the file count."""
    root = Path(bundle_dir)
    root.mkdir(parents=True, exist_ok=True)
    written = 0
    seen: set[str] = set()
    for mem in memories:
        type_dir = root / "memories" / mem.type
        type_dir.mkdir(parents=True, exist_ok=True)
        slug = mem.slug
        if slug in seen:
            slug = f"{slug}-{written}"
        seen.add(slug)
        out = type_dir / f"{slug}.md"
        out.write_text(mem.to_markdown(), encoding="utf-8")
        written += 1
    return written


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Convert a title into a portable, git-friendly filename slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-") or "untitled"


def summary_table(by_type: dict[str, list[Memory]]) -> str:
    """Render a type -> count summary block for docs / README."""
    lines = []
    total = 0
    for t in MEMORY_TYPE_ORDER:
        n = len(by_type.get(t, []))
        if n:
            lines.append(f"  {t}: {n}")
            total += n
    lines.append(f"  total: {total}")
    return "\n".join(lines)
