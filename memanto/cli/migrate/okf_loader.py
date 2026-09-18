"""
OKF bundle loader.

Reads an OKF (Open Knowledge Format) bundle — a directory of markdown files
with YAML frontmatter — into the ``{"memories": [...]}`` shape consumed by
``mappers.map_okf``. Handles both foreign OKF bundles (one concept per file)
and Memanto's own stacked exports (multiple documents per file, separated by
the ``okf-entry`` sentinel).

``index.md`` / ``log.md`` navigation files and any document with ``type: index``
are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.app.services.okf_export_service import ENTRY_DELIMITER
from memanto.app.utils.atomic_write import okf_bundle_lock

# Frontmatter must open at the very start of a (stripped) document. ``.*?`` is
# non-greedy so the first ``\n---`` closes the block even when the body below
# contains its own ``---`` rules.
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)

# A stacked file joins documents with the delimiter alone on its own line,
# followed by the next document's frontmatter. Matching that whole frame rather
# than the bare substring keeps a memory that merely mentions the sentinel from
# splitting into a headless fragment on every import.
_ENTRY_SPLIT_RE = re.compile(
    rf"^[ \t]*{re.escape(ENTRY_DELIMITER)}[ \t]*\n(?=---\n)", re.MULTILINE
)

_SKIP_FILENAMES = {"index.md", "log.md"}
# OKF baseline fields + Memanto's namespaced extension block. Anything else in
# the frontmatter is preserved as "extra" so import stays lossless.
_KNOWN_FIELDS = {
    "type",
    "title",
    "description",
    "resource",
    "tags",
    "timestamp",
    "x_memanto",
}


def _extract_links(body: str) -> list[tuple[str, str]]:
    """Extract inline Markdown links in a single left-to-right pass.

    Repeatedly applying a regular expression from every ``[`` candidate makes
    malformed Markdown increasingly expensive to scan. ``str.find`` keeps the
    loader linear while preserving the intentionally small link syntax handled
    here (non-empty ``[text](target)`` pairs).
    """
    links: list[tuple[str, str]] = []
    cursor = 0

    while True:
        opening = body.find("[", cursor)
        if opening == -1:
            break

        closing = body.find("]", opening + 1)
        if closing == -1:
            break

        if closing == opening + 1 or not body.startswith("(", closing + 1):
            cursor = closing + 1
            continue

        target_end = body.find(")", closing + 2)
        if target_end == -1:
            break

        if target_end == closing + 2:
            cursor = target_end + 1
            continue

        links.append((body[opening + 1 : closing], body[closing + 2 : target_end]))
        cursor = target_end + 1

    return links


def load_okf_bundle(path: str | Path) -> dict[str, Any]:
    """Load an OKF bundle directory (or a single ``.md`` file) into an export dict."""
    root = Path(path)
    # Hold the corresponding reader lock through discovery and every file
    # read, so an exporter cannot move the bundle aside midway through a load.
    with okf_bundle_lock(_bundle_lock_root(root), shared=True):
        return _load_okf_bundle(root, path)


def _bundle_lock_root(path: Path) -> Path:
    """Return the bundle path whose lock protects a requested import path."""
    if path.suffix.lower() != ".md":
        return path

    # A Memanto entry lives at ``<bundle>/<section>/<entry>.md`` or deeper.
    # Resolve this lexically so the same bundle lock is selected even while
    # the exporter has temporarily moved the bundle directory aside.
    for parent in path.parents:
        if parent.name in ("memories", "daily-summaries", "sessions", "metrics"):
            return parent.parent

    # Root-level documents belong to their containing bundle. For a standalone
    # Markdown import this merely serializes imports from the same directory.
    return path.parent


def _load_okf_bundle(root: Path, display_path: str | Path) -> dict[str, Any]:
    """Load ``root`` while the caller holds its bundle reader lock."""
    if not root.exists():
        raise FileNotFoundError(f"OKF bundle not found: {display_path}")

    if root.is_file():
        files = [root]
        rel_base = root.parent
    else:
        # Memanto's own bundles nest importable memories under ``memories/``
        # alongside export-only context (daily-summaries/, sessions/, metrics/).
        # Scope import to ``memories/`` when present so context logs are never
        # re-ingested as memories; foreign bundles (no ``memories/``) scan fully.
        memories_dir = root / "memories"
        scan_root = memories_dir if memories_dir.is_dir() else root
        files = sorted(
            f for f in scan_root.rglob("*.md") if f.name.lower() not in _SKIP_FILENAMES
        )
        rel_base = root

    memories: list[dict[str, Any]] = []
    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        for chunk in _ENTRY_SPLIT_RE.split(text):
            chunk = chunk.strip()
            if not chunk:
                continue
            entry = _parse_entry(chunk, file_path, rel_base)
            if entry is not None:
                memories.append(entry)

    return {"memories": memories}


def _parse_entry(chunk: str, file_path: Path, rel_base: Path) -> dict[str, Any] | None:
    """Parse one OKF document (frontmatter + body) into an entry dict."""
    match = _FRONTMATTER_RE.match(chunk)
    if match:
        raw_frontmatter, body = match.group(1), match.group(2)
        try:
            frontmatter = yaml.safe_load(raw_frontmatter) or {}
        except yaml.YAMLError:
            frontmatter = {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}
    else:
        frontmatter, body = {}, chunk

    body = body.strip()

    # Skip navigation index documents.
    if str(frontmatter.get("type", "")).strip().lower() == "index":
        return None
    if not body and not frontmatter.get("title"):
        return None

    tags = frontmatter.get("tags")
    if isinstance(tags, str):
        tags = [tags]
    elif not isinstance(tags, list):
        tags = []

    x_memanto = frontmatter.get("x_memanto")
    if not isinstance(x_memanto, dict):
        x_memanto = {}

    extra = {k: v for k, v in frontmatter.items() if k not in _KNOWN_FIELDS}
    links = [f"{text} -> {target}" for text, target in _extract_links(body)]

    try:
        source_path = str(file_path.relative_to(rel_base))
    except ValueError:
        source_path = file_path.name

    return {
        "type": frontmatter.get("type"),
        "title": frontmatter.get("title"),
        "description": frontmatter.get("description"),
        "resource": frontmatter.get("resource"),
        "tags": tags,
        "timestamp": frontmatter.get("timestamp"),
        "body": body,
        "x_memanto": x_memanto,
        "links": links,
        "extra": extra,
        "source_path": source_path,
    }
