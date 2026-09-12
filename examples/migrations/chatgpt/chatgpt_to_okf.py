#!/usr/bin/env python3
"""
ChatGPT data export -> OKF bundle adapter.

Liberates the durable memory ChatGPT has built about you — the entries it
saves through its ``bio`` tool ("Model set context") plus your custom
instructions — from an official ChatGPT data export, and rewrites it as an
OKF (Open Knowledge Format) bundle that the shipped Memanto CLI imports
directly:

    python3 chatgpt_to_okf.py ./chatgpt-export.zip -o ./okf-bundle
    memanto migrate okf ./okf-bundle --dry-run
    memanto migrate okf ./okf-bundle

The adapter deliberately *feeds* the existing ``memanto migrate okf``
pipeline instead of re-implementing any of it: it only performs the
source-specific work (parsing the export, deduplicating memory writes,
inferring a memory type) and emits standard OKF markdown documents whose
frontmatter fields — ``type``, ``title``, ``description``, ``resource``,
``tags``, ``timestamp``, ``x_memanto`` — are exactly the ones
``memanto.cli.migrate.okf_loader`` understands. Unknown frontmatter keys
(the source conversation title) ride along losslessly as OKF "extra"
fields and end up in the imported memory's ``[Supporting data]`` footer.

Sources extracted from ``conversations.json``:

1. **bio tool writes** — assistant messages with ``recipient == "bio"``.
   These are the moments ChatGPT decided something about you was worth
   remembering permanently.
2. **model_set_context snapshots** — ``model_editable_context`` messages
   that replay the accumulated memory list into a conversation. Parsed as
   numbered entries (``1. [2026-01-15]. …``) and deduplicated against the
   bio writes, so snapshot + deltas never double-import.
3. **custom instructions** — ``user_context_message_data`` blocks
   (about-user / about-model), deduplicated across conversations.

Account PII from ``user.json`` (email, phone, ids) is intentionally
**never** ingested.

Stdlib only — no dependencies beyond Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keep in sync with memanto.app.services.okf_export_service.ENTRY_DELIMITER —
# the sentinel the Memanto OKF loader uses to split stacked documents.
ENTRY_DELIMITER = "<!-- okf-entry -->"

# Matches memanto.app.services.okf_export_service.DEFAULT_SPLIT_THRESHOLD:
# in `auto` split mode a type with more memories than this collapses into a
# single stacked file instead of one file per memory.
DEFAULT_SPLIT_THRESHOLD = 50

TITLE_MAX_CHARS = 80
DESCRIPTION_MAX_CHARS = 200
SLUG_MAX_CHARS = 60

# Confidence assigned to imported rows — mirrors the 0.8 the built-in
# provider mappers use for migrated memories.
IMPORT_CONFIDENCE = 0.8

# ``model_set_context`` snapshots list entries as "1. [2026-01-15]. Text" —
# the bracketed date is optional and sometimes absent.
_SNAPSHOT_ENTRY_RE = re.compile(
    r"^\s*\d+\.\s*(?:\[(?P<date>\d{4}-\d{2}-\d{2})\]\.?\s*)?(?P<text>\S.*)$"
)

# Ordered, first-match-wins keyword heuristics mapping a memory sentence to
# one of Memanto's fixed memory types. ``memanto migrate okf`` coerces the
# OKF ``type`` onto the matching Memanto type, so these names must stay
# within memanto.app.constants.VALID_MEMORY_TYPES.
_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "preference",
        (
            "prefers",
            "prefer ",
            "likes",
            "dislikes",
            "favorite",
            "favourite",
            "enjoys",
            "loves",
            "hates",
            "would rather",
        ),
    ),
    (
        "goal",
        (
            "wants to",
            "plans to",
            "is planning",
            "is training for",
            "aims to",
            "goal is",
            "hopes to",
            "is working toward",
            "is saving for",
        ),
    ),
    (
        "commitment",
        (
            "will ",
            "has committed",
            "promised",
            "deadline",
            "is due",
            "scheduled for",
            "signed up for",
        ),
    ),
    (
        "relationship",
        (
            "partner",
            "wife",
            "husband",
            "girlfriend",
            "boyfriend",
            "daughter",
            "son",
            "mother",
            "father",
            "sister",
            "brother",
            "friend",
            "coworker",
            "colleague",
            "their dog",
            "their cat",
            "named",
        ),
    ),
    (
        "decision",
        ("decided to", "has decided", "chose to", "switched to", "opted for"),
    ),
    (
        "event",
        ("attended", "visited", "traveled to", "travelled to", "went to", "moved to"),
    ),
)


# Dedup fidelity ranking: an original bio write beats a replayed snapshot
# entry, which beats a custom-instruction block, regardless of timestamp.
_KIND_PRECEDENCE = {"custom_instructions": 0, "model_set_context": 1, "bio": 2}


@dataclass(frozen=True)
class ExtractedMemory:
    """One deduplicated memory liberated from the export."""

    text: str
    kind: str  # "bio" | "model_set_context" | "custom_instructions"
    memory_type: str
    created_at: str | None  # ISO 8601 UTC
    conversation_id: str | None
    conversation_title: str | None
    message_id: str | None


@dataclass
class ExtractionStats:
    """What the adapter saw while scanning the export."""

    conversations: int = 0
    bio_writes: int = 0
    snapshot_entries: int = 0
    custom_instruction_blocks: int = 0
    duplicates_skipped: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversations_scanned": self.conversations,
            "bio_writes_found": self.bio_writes,
            "model_set_context_entries_found": self.snapshot_entries,
            "custom_instruction_blocks_found": self.custom_instruction_blocks,
            "duplicates_skipped": self.duplicates_skipped,
            "memories_by_type": dict(sorted(self.type_counts.items())),
            "total_memories": sum(self.type_counts.values()),
        }


# --------------------------------------------------------------------------
# Export loading
# --------------------------------------------------------------------------


def load_conversations(source: Path) -> list[dict[str, Any]]:
    """Load ``conversations.json`` from an export zip, directory, or file."""
    if not source.exists():
        raise FileNotFoundError(f"ChatGPT export not found: {source}")

    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if Path(name).name == "conversations.json":
                    raw = archive.read(name).decode("utf-8")
                    return _coerce_conversations(json.loads(raw), name)
        raise ValueError(f"No conversations.json found inside {source}")

    if source.is_file():
        return _coerce_conversations(
            json.loads(source.read_text(encoding="utf-8")), str(source)
        )

    candidate = source / "conversations.json"
    if not candidate.exists():
        raise FileNotFoundError(
            f"{source} does not contain conversations.json — "
            "point at the export zip, its extracted folder, or the file itself."
        )
    return _coerce_conversations(
        json.loads(candidate.read_text(encoding="utf-8")), str(candidate)
    )


def _coerce_conversations(data: Any, origin: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    raise ValueError(
        f"{origin} is not a ChatGPT conversations.json (expected a JSON array)"
    )


# --------------------------------------------------------------------------
# Memory extraction
# --------------------------------------------------------------------------


def extract_memories(
    conversations: list[dict[str, Any]],
    *,
    include_custom_instructions: bool = True,
) -> tuple[list[ExtractedMemory], ExtractionStats]:
    """Walk every conversation and pull out deduplicated durable memories."""
    stats = ExtractionStats()
    seen: dict[str, int] = {}  # normalized text -> index into memories
    memories: list[ExtractedMemory] = []

    def add(memory: ExtractedMemory) -> None:
        key = _normalize(memory.text)
        if not key:
            return
        existing_idx = seen.get(key)
        if existing_idx is not None:
            stats.duplicates_skipped += 1
            existing = memories[existing_idx]
            # Original bio writes carry exact timestamps and the conversation
            # where ChatGPT learned the fact; snapshot replays are day-granular
            # echoes. Prefer higher-fidelity kinds; within the same kind keep
            # the earliest sighting (when the fact was first learned).
            if _KIND_PRECEDENCE[memory.kind] > _KIND_PRECEDENCE[existing.kind] or (
                memory.kind == existing.kind
                and _is_earlier(memory.created_at, existing.created_at)
            ):
                memories[existing_idx] = memory
            return
        seen[key] = len(memories)
        memories.append(memory)
        stats.type_counts[memory.memory_type] += 1

    for conv in conversations:
        stats.conversations += 1
        conv_id = conv.get("conversation_id") or conv.get("id")
        conv_title = conv.get("title")
        mapping = conv.get("mapping") or {}
        if not isinstance(mapping, dict):
            continue

        for node in mapping.values():
            message = (node or {}).get("message")
            if not isinstance(message, dict):
                continue

            for memory in _memories_from_message(
                message,
                conv_id=str(conv_id) if conv_id else None,
                conv_title=str(conv_title) if conv_title else None,
                include_custom_instructions=include_custom_instructions,
                stats=stats,
            ):
                add(memory)

    memories.sort(key=lambda m: (m.created_at or "9999", m.text))
    return memories, stats


def _memories_from_message(
    message: dict[str, Any],
    *,
    conv_id: str | None,
    conv_title: str | None,
    include_custom_instructions: bool,
    stats: ExtractionStats,
) -> list[ExtractedMemory]:
    author = message.get("author") or {}
    role = author.get("role")
    content = message.get("content") or {}
    created_at = _iso_from_unix(message.get("create_time"))
    message_id = str(message.get("id")) if message.get("id") else None

    # 1. The assistant writing to its bio tool — a deliberate "remember this".
    if role == "assistant" and message.get("recipient") == "bio":
        text = _text_from_content(content)
        if text:
            stats.bio_writes += 1
            return [
                ExtractedMemory(
                    text=text,
                    kind="bio",
                    memory_type=infer_memory_type(text),
                    created_at=created_at,
                    conversation_id=conv_id,
                    conversation_title=conv_title,
                    message_id=message_id,
                )
            ]
        return []

    # 2. A replayed model_set_context snapshot — the accumulated memory list.
    if content.get("content_type") == "model_editable_context":
        snapshot = content.get("model_set_context")
        results: list[ExtractedMemory] = []
        for entry_date, entry_text in _parse_snapshot(snapshot):
            stats.snapshot_entries += 1
            results.append(
                ExtractedMemory(
                    text=entry_text,
                    kind="model_set_context",
                    memory_type=infer_memory_type(entry_text),
                    created_at=entry_date or created_at,
                    conversation_id=conv_id,
                    conversation_title=conv_title,
                    message_id=message_id,
                )
            )
        return results

    # 3. Custom instructions embedded as user context metadata.
    if include_custom_instructions:
        metadata = message.get("metadata") or {}
        context_data = metadata.get("user_context_message_data")
        if isinstance(context_data, dict):
            results = []
            for key in ("about_user_message", "about_model_message"):
                text = (context_data.get(key) or "").strip()
                if not text:
                    continue
                stats.custom_instruction_blocks += 1
                label = (
                    "About the user"
                    if key == "about_user_message"
                    else "How the user wants responses"
                )
                results.append(
                    ExtractedMemory(
                        text=f"{label} (custom instructions): {text}",
                        kind="custom_instructions",
                        memory_type="instruction",
                        created_at=created_at,
                        conversation_id=conv_id,
                        conversation_title=conv_title,
                        message_id=message_id,
                    )
                )
            return results

    return []


def _parse_snapshot(snapshot: Any) -> list[tuple[str | None, str]]:
    """Parse a ``model_set_context`` blob into ``(iso_date, text)`` entries."""
    if not isinstance(snapshot, str) or not snapshot.strip():
        return []
    entries: list[tuple[str | None, str]] = []
    for line in snapshot.splitlines():
        match = _SNAPSHOT_ENTRY_RE.match(line)
        if not match:
            continue
        text = match.group("text").strip()
        if not text:
            continue
        date = match.group("date")
        entries.append((f"{date}T00:00:00+00:00" if date else None, text))
    return entries


def _text_from_content(content: dict[str, Any]) -> str:
    parts = content.get("parts") or []
    texts = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return "\n".join(texts).strip()


def infer_memory_type(text: str) -> str:
    """Best-effort mapping of a memory sentence onto a Memanto memory type.

    Falls back to ``fact`` — bio writes are, by construction, statements
    ChatGPT considered durably true about the user.
    """
    lowered = f" {text.lower()} "
    for memory_type, keywords in _TYPE_RULES:
        if any(keyword in lowered for keyword in keywords):
            return memory_type
    return "fact"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold().rstrip(".")


def _iso_from_unix(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _is_earlier(candidate: str | None, current: str | None) -> bool:
    if candidate is None:
        return False
    if current is None:
        return True
    return candidate < current


# --------------------------------------------------------------------------
# OKF bundle writing
# --------------------------------------------------------------------------


def write_okf_bundle(
    memories: list[ExtractedMemory],
    output_dir: Path,
    *,
    split: str = "auto",
    threshold: int = DEFAULT_SPLIT_THRESHOLD,
) -> dict[str, int]:
    """Write memories as an OKF bundle under ``output_dir``.

    Layout mirrors Memanto's own OKF exports so the bundle feels native::

        <output_dir>/
          index.md
          memories/
            index.md
            <type>/
              index.md
              <slug>.md            (or a stacked <type>.md when large)

    Returns per-type counts.
    """
    if split not in ("auto", "file", "type"):
        raise ValueError("split must be one of: auto, file, type")

    by_type: dict[str, list[ExtractedMemory]] = {}
    for memory in memories:
        by_type.setdefault(memory.memory_type, []).append(memory)

    memories_dir = output_dir / "memories"
    type_links: list[tuple[str, str]] = []

    for memory_type in sorted(by_type):
        group = by_type[memory_type]
        type_dir = memories_dir / memory_type
        type_dir.mkdir(parents=True, exist_ok=True)

        use_stacked = split == "type" or (split == "auto" and len(group) > threshold)
        if use_stacked:
            docs = [_render_okf_doc(m) for m in group]
            stacked = f"\n{ENTRY_DELIMITER}\n".join(docs)
            (type_dir / f"{memory_type}.md").write_text(stacked, encoding="utf-8")
            doc_links = [(_title_from(m.text), f"{memory_type}.md") for m in group]
        else:
            used_slugs: set[str] = set()
            doc_links = []
            for memory in group:
                slug = _unique_slug(_title_from(memory.text), used_slugs)
                (type_dir / f"{slug}.md").write_text(
                    _render_okf_doc(memory), encoding="utf-8"
                )
                doc_links.append((_title_from(memory.text), f"{slug}.md"))

        _write_index(type_dir, memory_type, f"{memory_type} ({len(group)})", doc_links)
        type_links.append((memory_type, f"{memory_type}/index.md"))

    total = len(memories)
    if type_links:
        memories_dir.mkdir(parents=True, exist_ok=True)
        _write_index(memories_dir, "memories", f"Memories ({total})", type_links)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_root_index(output_dir, total, sorted(by_type))
    return {memory_type: len(group) for memory_type, group in by_type.items()}


def _render_okf_doc(memory: ExtractedMemory) -> str:
    """Render one memory as an OKF markdown document.

    Frontmatter is emitted by hand (stdlib only, no PyYAML). All values are
    JSON-quoted strings, which is valid YAML 1.1 scalar syntax and survives
    any content ChatGPT can produce.
    """
    lines = ["---"]
    lines.append(f"type: {memory.memory_type}")
    lines.append(f"title: {_yaml_str(_title_from(memory.text))}")
    description = memory.text.strip().splitlines()[0][:DESCRIPTION_MAX_CHARS]
    lines.append(f"description: {_yaml_str(description)}")
    lines.append("tags:")
    lines.append("- chatgpt")
    lines.append(f"- {memory.kind.replace('_', '-')}")
    if memory.created_at:
        lines.append(f"timestamp: {_yaml_str(memory.created_at)}")
    resource = _resource_ref(memory)
    if resource:
        lines.append(f"resource: {_yaml_str(resource)}")
    if memory.conversation_title:
        # Not an OKF baseline field: the Memanto loader preserves it as an
        # "extra" and surfaces it in the [Supporting data] footer on import.
        lines.append(f"conversation: {_yaml_str(memory.conversation_title)}")
    lines.append("x_memanto:")
    lines.append("  source: chatgpt")
    lines.append(f"  type: {memory.memory_type}")
    lines.append(f"  confidence: {IMPORT_CONFIDENCE}")
    lines.append("---")
    lines.append("")
    lines.append(memory.text.strip())
    lines.append("")
    return "\n".join(lines)


def _resource_ref(memory: ExtractedMemory) -> str | None:
    if memory.conversation_id and memory.message_id:
        return f"chatgpt:{memory.conversation_id}:{memory.message_id}"
    if memory.conversation_id:
        return f"chatgpt:{memory.conversation_id}"
    return None


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _title_from(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= TITLE_MAX_CHARS:
        return flat
    return flat[: TITLE_MAX_CHARS - 3].rstrip() + "..."


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:SLUG_MAX_CHARS].rstrip("-") or "memory"


def _unique_slug(title: str, used: set[str]) -> str:
    base = _slugify(title)
    slug = base
    counter = 2
    while slug in used:
        slug = f"{base}-{counter}"
        counter += 1
    used.add(slug)
    return slug


def _write_index(
    directory: Path, title: str, heading: str, links: list[tuple[str, str]]
) -> None:
    """Write a navigational ``index.md`` (type: index — skipped on import)."""
    lines = [
        "---",
        "type: index",
        f"title: {_yaml_str(title)}",
        "---",
        "",
        f"# {heading}",
        "",
    ]
    seen_links: set[tuple[str, str]] = set()
    for text, target in links:
        if (text, target) in seen_links:
            continue
        seen_links.add((text, target))
        lines.append(f"- [{text}]({target})")
    lines.append("")
    (directory / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_root_index(base: Path, total: int, types: list[str]) -> None:
    lines = [
        "---",
        "type: index",
        "title: ChatGPT liberated memory",
        "---",
        "",
        "# ChatGPT -> OKF memory bundle",
        "",
        f"> {total} memories liberated from a ChatGPT data export.",
        "> Import with: `memanto migrate okf <this-directory>`",
        "",
        "- [memories](memories/index.md) — "
        + f"{total} memories across {len(types)} type(s)",
        "",
    ]
    (base / "index.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a ChatGPT data export into an OKF bundle for "
            "`memanto migrate okf`."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        help="ChatGPT export zip, extracted folder, or conversations.json",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("./okf-bundle"),
        help="Output OKF bundle directory (default: ./okf-bundle)",
    )
    parser.add_argument(
        "--split",
        choices=("auto", "file", "type"),
        default="auto",
        help="Bundle layout: one file per memory, stacked per type, or auto",
    )
    parser.add_argument(
        "--no-custom-instructions",
        action="store_true",
        help="Skip custom-instruction blocks (bio memories only)",
    )
    args = parser.parse_args(argv)

    conversations = load_conversations(args.source)
    memories, stats = extract_memories(
        conversations,
        include_custom_instructions=not args.no_custom_instructions,
    )

    if not memories:
        print(
            "No durable memories found in this export. "
            "(Does the account have ChatGPT Memory enabled?)",
            file=sys.stderr,
        )
        return 1

    per_type = write_okf_bundle(memories, args.output, split=args.split)

    summary = {
        "source": str(args.source),
        "output_bundle": str(args.output),
        **stats.as_dict(),
    }
    summary_path = args.output / "migration_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("ChatGPT -> OKF extraction complete")
    print(f"  Conversations scanned:      {stats.conversations}")
    print(f"  bio writes found:           {stats.bio_writes}")
    print(f"  snapshot entries found:     {stats.snapshot_entries}")
    print(f"  custom instruction blocks:  {stats.custom_instruction_blocks}")
    print(f"  duplicates collapsed:       {stats.duplicates_skipped}")
    print(f"  unique memories written:    {len(memories)}")
    type_breakdown = ", ".join(f"{t}: {n}" for t, n in sorted(per_type.items()))
    print(f"  type breakdown:             {type_breakdown}")
    print(f"  bundle:                     {args.output}")
    print(f"  summary:                    {summary_path}")
    print()
    print("Next: preview the import (no API key needed):")
    print(f"  memanto migrate okf {args.output} --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
