#!/usr/bin/env python3
"""
chatgpt-to-okf exporter — Path B showcase for the Memanto "Great Memory Migration"
bounty (https://github.com/moorcheh-ai/memanto/issues/1609).

Reads a ChatGPT conversation export JSON (the shape the OpenAI "Export your data"
download produces, or the synthetic ``sample_chatgpt_export.json`` provided here)
and emits a valid Open Knowledge Format (OKF) bundle that Memanto can import with:

    memanto migrate okf <bundle-dir>

Output layout (standard OKF):
    <bundle>/index.json           — bundle manifest
    <bundle>/entries/<slug>.md    — one markdown file per extracted memory,
                                    each with YAML frontmatter

OKF frontmatter fields used:
    title, description, type, tags, timestamp, resource, source, links,
    x_memanto.source (= "chatgpt" so Memanto records provenance on import)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Type inference from assistant prose
# ---------------------------------------------------------------------------
_KEYWORD_PATTERNS: list[tuple[str, list[str]]] = [
    ("preference", [
        r"(?:you\s+prefer|you said you like|you want|you would rather|you like)",
    ]),
    ("decision", [
        r"(?:you decided|you chose|you decided to|you're going with)",
    ]),
    ("goal", [
        r"(?:you want to build|you want to|you're working toward|you aim to)",
    ]),
    ("commitment", [
        r"(?:you're going to|you committed to|you plan to|you're shipping)",
    ]),
    ("fact", [
        r"(?:you (?:work(?: as)?|are a)|your (?:job|role)|you live in|you use(?:d)?|you're on)",
    ]),
    ("artifact", [
        r"(?:here it is:|here's the|snippet|config|a docker)",
    ]),
    ("context", [
        r"(?:for your|your .* (?:project|workflow|dashboard)|in your)",
    ]),
]

_FALLBACK = "observation"


def _infer_type(text: str) -> str:
    """Infer a memory type label from assistant text by matching keyword patterns.

    Returns one of the ``_KEYWORD_PATTERNS`` labels (preference, decision,
    goal, etc.) or the fallback ``observation`` when no pattern matches.
    """
    low = text.lower()
    for mem_type, pats in _KEYWORD_PATTERNS:
        for pat in pats:
            if re.search(pat, low):
                return mem_type
    return _FALLBACK


# ---------------------------------------------------------------------------
# Slug / content helpers
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"[^0-9a-zA-Z]+")


def _slug(text: str, idx: int) -> str:
    """Produce a URL-safe filename slug from the given text.

    Strips non-ASCII characters, collapses runs of non-alphanumeric
    characters into a single hyphen, and appends a zero-padded index
    to guarantee uniqueness.
    """
    s = text.strip().lower()
    s = re.sub(r"[^\x00-\x7f]+", " ", s)
    s = _SLUG_RE.sub("-", s).strip("-")
    return (s[:50] or "entry") + f"-{idx:03d}"


def _yaml_value(value: Any) -> str:
    """Emit a YAML-safe scalar. Quotes strings that contain colons, dashes,
    brackets, or other characters that could be mis-parsed by PyYAML's loader,
    and falls back to PyYAML's dumper for lists/dicts."""
    import yaml  # type: ignore  # noqa: PLC0415 — kept lazy to stay stdlib-only when safe
    if isinstance(value, (list, dict)):
        return str(yaml.safe_dump(value, default_flow_style=None, width=120)).rstrip("\n")
    if value is None:
        return "null"
    s = str(value)
    needs_quote = any(ch in s for ch in ":[]{}>,|*\`") or s.startswith("- ") or s in ("true", "false", "yes", "no", "on", "off")
    if needs_quote:
        return yaml.safe_dump(s, default_style="'").rstrip("\n")  # type: ignore
    return s


def _make_markdown(
    *,
    title: str,
    description: str,
    body: str,
    mem_type: str,
    tags: list[str],
    timestamp: str,
    source_id: str,
) -> str:
    """Build a single OKF entry markdown file with YAML frontmatter.

    Args:
        title: Entry title.
        description: Short summary.
        body: Full markdown body.
        mem_type: Memory type label (e.g. ``fact``, ``preference``).
        tags: List of tag strings.
        timestamp: ISO-formatted timestamp string.
        source_id: Original ChatGPT conversation message identifier.

    Returns:
        A complete OKF markdown document with ``---`` delimited frontmatter.
    """
    lines: list[str] = []
    lines.append("---")
    lines.append(f"title: {_yaml_value(title)}")
    lines.append(f"description: {_yaml_value(description)}")
    lines.append(f"type: {_yaml_value(mem_type)}")
    lines.append(f"tags: {_yaml_value(tags)}")
    lines.append(f"timestamp: {_yaml_value(timestamp)}")
    lines.append(f"resource: {_yaml_value('chatgpt:' + source_id)}")
    lines.append("source: chatgpt")
    lines.append("links: []")
    lines.append("x_memanto:")
    lines.append("  source: chatgpt")
    lines.append(f"  source_ref: {_yaml_value(source_id)}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core export
# ---------------------------------------------------------------------------
def load_messages(path: Path) -> list[dict[str, Any]]:
    """Load a chat export. Handles both a flat list of messages and the
    wrapper the real OpenAI export uses (``{"conversations": [...]}``).
    Each message must at minimum have ``role`` and ``content``.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    # common wrapper shapes
    if isinstance(raw, dict):
        for key in ("conversations", "conversations.messages", "messages", "data"):
            v = raw.get(key)
            if isinstance(v, list):
                return v
        # also accept ``{"id": ..., "messages": [...]}`` objects nested in a list
        if isinstance(raw.get("conversations"), list):
            out: list[dict[str, Any]] = []
            for conv in raw["conversations"]:
                msgs = conv.get("messages") or []
                for m in msgs:
                    if isinstance(m, dict):
                        out.append(m)
            return out
    raise ValueError(f"Unrecognized export format in {path}")


def extract_memories(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only assistant turns that carry knowledge *about the user*."""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if role != "assistant" or not content:
            continue
        # skip empty / placeholder turns
        if len(content) < 25:
            continue
        mem_type = _infer_type(content)
        ts = m.get("created_at") or m.get("timestamp") or m.get("created") or ""
        source_id = m.get("id") or ""
        conv_id = m.get("conversation_id") or m.get("conv_id") or m.get("conversation") or ""

        out.append(
            {
                "title": content.split(".")[0][:110].strip(),
                "description": content[:220].strip(),
                "body": content,
                "type": mem_type,
                "tags": [mem_type, "chatgpt"],
                "timestamp": ts,
                "resource": f"chatgpt:{source_id}" if source_id else "chatgpt",
                "source": "chatgpt",
                "links": [],
                "x_memanto": {"source": "chatgpt", "source_ref": source_id or conv_id},
                "conv_id": conv_id,
            }
        )
    return out


def write_okf_bundle(
    memories: list[dict[str, Any]],
    dest: Path,
) -> tuple[Path, list[Path]]:
    """Write an OKF bundle directory. Returns (bundle_root, [entry files])."""
    dest.mkdir(parents=True, exist_ok=True)
    memories_dir = dest / "memories"
    entries_dir = memories_dir
    entries_dir.mkdir(parents=True, exist_ok=True)

    entry_files: list[Path] = []
    for idx, mem in enumerate(memories, 1):
        slug = _slug(mem["title"], idx)
        p = entries_dir / f"{slug}.md"
        p.write_text(
            _make_markdown(
                title=mem["title"],
                description=mem["description"],
                body=mem["body"],
                mem_type=mem["type"],
                tags=mem["tags"],
                timestamp=mem["timestamp"],
                source_id=mem.get("resource", "").split(":", 1)[1],
            ),
            encoding="utf-8",
        )
        entry_files.append(p)

    # index.json — the manifest OKF readers expect
    index = {
        "version": "0.1",
        "title": "ChatGPT Conversation Memory — OKF Migration Showcase",
        "description": (
            "Memories extracted from a ChatGPT assistant chat history, mapped "
            "into portable Open Knowledge Format markdown. Built for the Memanto "
            '"Great Memory Migration" bounty (Path B).'
        ),
        "entry_count": len(entry_files),
        "entries": [str(p.relative_to(dest)) for p in entry_files],
    }
    (dest / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return dest, entry_files


def _okf_type_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count how many entries belong to each memory type.

    Args:
        entries: List of extracted memory dictionaries.

    Returns:
        A mapping of memory type label to count.
    """
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    """CLI entry point: read a ChatGPT export JSON and write an OKF bundle."""
    p = argparse.ArgumentParser(description="ChatGPT conversation export → OKF bundle")
    p.add_argument("--input", "-i", required=True, help="ChatGPT export JSON file")
    p.add_argument("--output", "-o", required=True, help="Output OKF bundle directory")
    args = p.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)

    messages = load_messages(in_path)
    memories = extract_memories(messages)

    bundle, files = write_okf_bundle(memories, out_dir)

    print(f"Loaded {len(messages)} messages from {in_path}")
    print(f"Extracted {len(memories)} user memories")
    print("Type breakdown:", _okf_type_counts(memories))
    print(f"OKF bundle written to: {bundle}")
    print("\nTo import into Memanto:")
    print(f"  memanto migrate okf {bundle}          # import (needs API key / session)")
    print(f"  memanto migrate okf {bundle} --dry-run # preview only")


if __name__ == "__main__":
    main()
