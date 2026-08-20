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

import errno
import os
import re
import stat
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.app.services.okf_export_service import ENTRY_DELIMITER
from memanto.app.utils.atomic_write import okf_bundle_lock

# Frontmatter must open at the very start of a (stripped) document. ``.*?`` is
# non-greedy so the first ``\n---`` closes the block even when the body below
# contains its own ``---`` rules.
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)

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

_SECURE_DIR_FD = (
    hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.scandir in os.supports_fd
)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)


def _read_open_regular_file(fd: int, display_path: Path) -> str:
    """Read a regular file from an already validated, stable descriptor."""
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise ValueError(f"OKF document is not a regular file: {display_path}")

    with os.fdopen(os.dup(fd), "r", encoding="utf-8") as stream:
        return stream.read()


def _read_document_at(directory_fd: int, name: str, display_path: Path) -> str:
    """Open and read one regular document without following a final symlink."""
    document_fd: int | None = None
    try:
        document_fd = os.open(
            name,
            _READ_FLAGS | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        return _read_open_regular_file(document_fd, display_path)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(
                f"OKF bundle contains a symbolic-link path: {display_path}"
            ) from exc
        raise
    finally:
        if document_fd is not None:
            os.close(document_fd)


def _read_directory_documents(
    directory_fd: int, prefix: Path = Path()
) -> list[tuple[Path, str]]:
    """Read Markdown documents recursively from a pinned directory."""
    try:
        with os.scandir(directory_fd) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError as exc:
        raise ValueError(f"Could not scan OKF bundle directory: {prefix}") from exc

    documents: list[tuple[Path, str]] = []
    for name in names:
        relative_path = prefix / name
        try:
            entry_stat = os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                f"OKF bundle changed during import: {relative_path}"
            ) from exc

        lower_name = name.lower()
        is_markdown = lower_name.endswith(".md")
        if is_markdown and lower_name in _SKIP_FILENAMES:
            continue
        if stat.S_ISLNK(entry_stat.st_mode):
            if is_markdown:
                raise ValueError(
                    f"OKF bundle contains a symbolic-link document: {relative_path}"
                )
            continue
        if stat.S_ISDIR(entry_stat.st_mode):
            if is_markdown:
                raise ValueError(f"OKF document is not a regular file: {relative_path}")
            child_fd: int | None = None
            try:
                child_fd = os.open(
                    name,
                    _READ_FLAGS | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
                if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                    raise ValueError(
                        f"OKF bundle contains an unsafe directory: {relative_path}"
                    )
                documents.extend(_read_directory_documents(child_fd, relative_path))
            except OSError as exc:
                raise ValueError(
                    f"OKF bundle contains an unsafe directory: {relative_path}"
                ) from exc
            finally:
                if child_fd is not None:
                    os.close(child_fd)
            continue
        if not is_markdown:
            continue
        if not stat.S_ISREG(entry_stat.st_mode):
            raise ValueError(f"OKF document is not a regular file: {relative_path}")
        documents.append(
            (
                relative_path,
                _read_document_at(directory_fd, name, relative_path),
            )
        )

    return documents


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


def _load_documents_secure(
    root: Path, original_path: str | Path
) -> tuple[Path, list[tuple[Path, str]]]:
    """Pin the bundle root and read documents through no-follow descriptors."""
    try:
        root_fd = os.open(root, _READ_FLAGS | os.O_NOFOLLOW)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"OKF bundle not found: {original_path}") from exc
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(
                f"OKF bundle path must not be a symbolic link: {original_path}"
            ) from exc
        raise

    scan_fd: int | None = None
    try:
        root_stat = os.fstat(root_fd)
        if stat.S_ISREG(root_stat.st_mode):
            return root.parent, [(root, _read_open_regular_file(root_fd, root))]
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError(f"OKF bundle is not a file or directory: {original_path}")

        scan_fd = root_fd
        scan_prefix = Path()
        try:
            memories_stat = os.stat(
                "memories",
                dir_fd=root_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            memories_stat = None

        if memories_stat is not None and stat.S_ISLNK(memories_stat.st_mode):
            raise ValueError(
                f"OKF bundle directory must not be a symbolic link: {root / 'memories'}"
            )
        if memories_stat is not None and stat.S_ISDIR(memories_stat.st_mode):
            try:
                scan_fd = os.open(
                    "memories",
                    _READ_FLAGS | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            except OSError as exc:
                raise ValueError(
                    "OKF bundle directory changed or became a symbolic link: "
                    f"{root / 'memories'}"
                ) from exc
            if not stat.S_ISDIR(os.fstat(scan_fd).st_mode):
                raise ValueError(
                    f"OKF bundle directory is not a directory: {root / 'memories'}"
                )
            scan_prefix = Path("memories")

        relative_documents = sorted(
            _read_directory_documents(scan_fd, scan_prefix),
            key=lambda item: item[0],
        )
        documents = [
            (root / relative_path, text) for relative_path, text in relative_documents
        ]
        return root, documents
    finally:
        if scan_fd is not None and scan_fd != root_fd:
            os.close(scan_fd)
        os.close(root_fd)


def _load_documents_portable(
    root: Path, original_path: str | Path
) -> tuple[Path, list[tuple[Path, str]]]:
    """Fail closed when the platform cannot enforce no-follow directory reads."""
    try:
        root_stat = root.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"OKF bundle not found: {original_path}")
    if stat.S_ISLNK(root_stat.st_mode):
        raise ValueError(
            f"OKF bundle path must not be a symbolic link: {original_path}"
        )
    raise RuntimeError(
        "Secure OKF import requires descriptor-relative no-follow filesystem "
        "support on this platform."
    )


def load_okf_bundle(path: str | Path) -> dict[str, Any]:
    """Load an OKF bundle directory (or a single ``.md`` file) into an export dict."""
    root = Path(os.path.abspath(os.fspath(path)))
    if root.is_symlink():
        raise ValueError(f"OKF bundle path must not be a symbolic link: {path}")
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
    if _SECURE_DIR_FD:
        rel_base, documents = _load_documents_secure(root, display_path)
    else:
        rel_base, documents = _load_documents_portable(root, display_path)

    memories: list[dict[str, Any]] = []
    for file_path, text in documents:
        for chunk in text.split(ENTRY_DELIMITER):
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
