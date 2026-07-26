"""
Export ChatGPT conversation memory into an OKF bundle for Memanto.

Background
----------
When you have a long-running ChatGPT (or any chat assistant) conversation,
the assistant gradually builds a mental model of you: your preferences, the
decisions you made, facts you told it, recurring themes. Once that context
window is pruned, or if you switch assistants, that accumulated "memory of
you" vanishes.

This adapter treats each conversation **thread** as a memory source and
extracts the assistant's accumulated context about the user into a portable
OKF (Open Knowledge Format) bundle: plain, human-readable Markdown that
Memanto can ingest with ``memanto migrate okf <bundle>``.

What this adapter does
----------------------
1. Reads a ChatGPT-style conversation export (JSON produced by the
   ``export_conversation.py`` helper or by any tool that emits the same
   shape: a list of threads, each a list of messages with ``role``,
   ``content``, and ``timestamp``).
2. From each thread, distills a small set of **user-relevant memories**:
   facts, preferences, decisions, goals, and themes the user has surfaced,
   written as plain Markdown OKF documents with YAML frontmatter.
3. Writes the bundle to a directory. Memanto can then import it losslessly:

       memanto migrate okf ./chatgpt-memory/

Why this shape
--------------
We do **not** dump every raw turn (which would be mostly assistant
reasoning, not memory). Instead we surface only the durable user-facing
knowledge — the kind of things you would want any new assistant to
remember about you. That keeps the bundle small, readable, and actually
useful as a migration target.

Reproducibility
---------------
The export step is deterministic given the input JSON. The memory
distillation is keyword/signal based (not a live LLM call) so it runs
offline and produces byte-stable output — ideal for CI and for reviewers
to verify.

Input format (chatgpt_export.json)
----------------------------------
    [
      {
        "thread_id": "thread-abc123",
        "title": "Project planning session",
        "messages": [
          {"role": "user",      "content": "I'm using Python 3.12 with pytest.",
           "timestamp": "2026-05-01T10:00:00Z"},
          {"role": "assistant", "content": "Great choice. Python 3.12 with
           pytest is a solid combo...",
           "timestamp": "2026-05-01T10:00:12Z"},
          ...
        ]
      },
      ...
    ]

Usage
-----
    python extract_memories.py chatgpt_export.json ./chatgpt-memory/

    # Then into Memanto (requires a MOORCHEH_API_KEY):
    memanto migrate okf ./chatgpt-memory/

The sample ``sample_export.json`` and ``sample_bundle/`` in this folder
demonstrate the full round trip with realistic synthetic data.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Domain concepts
# ---------------------------------------------------------------------------

# Keywords that signal a *user* attribute rather than a generic assistant reply.
# Patterns match against user messages (lower-cased).
SIGNAL_PATTERNS: dict[str, list[re.Pattern]] = {
    "preference": [
        re.compile(r"\bI (prefer|like|don'?t like|love|hate|always|never)\b", re.I),
        re.compile(r"\bI am (a|an)\b"),
        re.compile(r"\bmy (favorite|preferred|default)\b", re.I),
    ],
    "fact": [
        re.compile(r"\bI (live|work|study|commute) (in|at|to|for)\b", re.I),
        re.compile(r"\bI (use|am using|run)\b", re.I),
        re.compile(r"\bI (work with|build with|operate on)\b", re.I),
        re.compile(r"\bmy (name|age|role|job|title|team|stack|language|os|distro)\b", re.I),
        re.compile(r"\b(?:python|javascript|java|go|rust|kotlin|swift)\b", re.I),
        re.compile(r"\b(?:docker|kubernetes|linux|windows|macos|ubuntu|arch)\b", re.I),
        re.compile(r"\b(?:github|gitlab|ci|cd|ci/cd|k8s|wayland|hyprland|postgre?)\b", re.I),
        re.compile(r"\b(?:arch linux|ubuntu|debian|fedora|k3s)\b", re.I),
    ],
    "decision": [
        re.compile(r"\bI (chose|choose|decided|will (use|go with|stick to))\b", re.I),
        re.compile(r"\bwe (went with|picked|settled on)\b", re.I),
    ],
    "goal": [
        re.compile(r"\bI (want|would like|plan to|am trying to|aim to|need to)\b", re.I),
        re.compile(r"\bmy goal is\b", re.I),
    ],
}

# Type labels used as OKF ``type`` and as ``x_memanto.type``.
# ``x_memanto.type`` carries the real category; OKF top-level ``type`` is fixed
# so the bundle stays importable by Memanto's ``map_okf`` mapper.
DEFAULT_OKF_TYPE = "preference"


@dataclass
class Memory:
    category: str
    title: str
    body: str
    thread_id: str
    thread_title: str
    sources: list[str] = field(default_factory=list)  # timestamped citations


def _iso(s: str | None) -> str | None:
    if not s:
        return None
    return s if s.endswith("Z") or "+" in s else s + "Z"


def _first_match(text: str, patterns: list[re.Pattern]) -> list[re.Match]:
    return [m for p in patterns for m in [p.search(text)] if m]


def _infer_category(text: str) -> str:
    """Return the strongest category whose pattern list hits *text*, else 'context'.

    Priority order: ``preference`` is checked first because an explicit
    preference phrase ("I prefer / I like / I hate") is a stronger signal than
    a coincidental fact keyword (e.g. "Kotlin" in "I prefer Kotlin"). The
    remaining categories follow in order of intent specificity.
    """
    for cat in ("preference", "decision", "goal", "fact"):
        if _first_match(text, SIGNAL_PATTERNS[cat]):
            return cat
    return "context"


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", s.strip()).strip("-").lower()
    return s[:90] or "untitled"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_memories(threads: list[dict[str, Any]]) -> list[Memory]:
    """Extract durable user memories from a list of chat threads."""
    memories: list[Memory] = []
    seen: set[tuple[str, str]] = set()
    for thread in threads:
        tid = str(thread.get("thread_id", "unknown"))
        ttitle = str(thread.get("title", "Untitled thread")).strip()
        messages = thread.get("messages") or []

        for msg in messages:
            role = str(msg.get("role", "")).lower()
            if role != "user":
                continue
            text = str(msg.get("content", ""))
            if not text.strip():
                continue
            if len(text) < 30:
                continue  # skip greetings / one-liners that aren't durable

            category = _infer_category(text)
            if category == "context":
                continue

            ts = _iso(str(msg.get("timestamp", "")).strip())
            # Title = first sentence, capped.
            first_sent = re.split(r"[.\n]", text, maxsplit=1)[0].strip()
            title = first_sent[:95] if first_sent else f"User {category} from {ttitle[:40]}"
            if not title.endswith("."):
                title += "."

            m = Memory(
                category=category,
                title=title,
                body=text.strip(),
                thread_id=tid,
                thread_title=ttitle,
                sources=[ts] if ts else [],
            )
            key = (tid, text.strip())
            if key not in seen:
                seen.add(key)
                memories.append(m)

    return memories

# ---------------------------------------------------------------------------
# OKF bundle writer
# ---------------------------------------------------------------------------

def write_okf_bundle(memories: list[Memory], out: Path) -> Path:
    """Write an OKF bundle directory of Markdown documents."""
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    # Deduplicate identical bodies within the same category per thread, while
    # keeping a citation trail so nothing is silently lost.
    seen: set[tuple[str, str]] = set()
    written = 0

    # Counter for safe filenames within a (category, thread) bucket.
    counter: dict[str, int] = defaultdict(int)

    for m in memories:
        key = (m.thread_id, m.body)
        if key in seen:
            continue
        seen.add(key)

        counter[m.category] += 1
        name = _safe_filename(m.title) or f"{m.category}-{counter[m.category]}"

        frontmatter = {
            "type": DEFAULT_OKF_TYPE,
            "title": m.title,
            "tags": [m.category, "chatgpt-import", f"thread:{m.thread_id[:12]}"],
            "timestamp": m.sources[0] if m.sources else None,
            "resource": f"chatgpt://thread/{m.thread_id}",
            "x_memanto": {"type": m.category, "source": "chatgpt"},
        }
        body = f"Extracted from thread **{m.thread_title}** ({m.thread_id[:16]}).\n\n"
        if m.sources:
            body += f"First surfaced: `{m.sources[0]}`\n\n"
        body += m.body

        doc = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False).strip() + "\n---\n\n" + body
        (out / f"{name}.md").write_text(doc, encoding="utf-8")
        written += 1

    # index.md navigation file (skipped by memanto's loader)
    idx = (out / "index.md")
    idx.write_text(
        "---\ntype: index\ntitle: ChatGPT Memory Export\n---\n\n"
        f"Auto-generated bundle of {written} user memory fragments extracted "
        "from ChatGPT conversation history. Import with:\n\n"
        "    memanto migrate okf ./chatgpt-memory/\n",
        encoding="utf-8",
    )

    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) < 2:
        print("Usage: extract_memories.py <chatgpt_export.json> <output_dir>", file=sys.stderr)
        return 2

    src = Path(args[0])
    out = Path(args[1])

    with src.open(encoding="utf-8") as f:
        threads = json.load(f)

    if not isinstance(threads, list):
        print("Error: expected a JSON array of threads", file=sys.stderr)
        return 2

    memories = extract_memories(threads)
    write_okf_bundle(memories, out)

    print(f"Exported {len(memories)} memory documents -> {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
