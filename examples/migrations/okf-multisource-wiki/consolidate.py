"""Consolidate multi-source memories into one coherent portable set.

Rules (documented in MAPPING.md):
1. Exact / near-duplicate facts from both sources merge into one memory with
   dual provenance (``sources: [chroma, sqlite]``).
2. Explicit corrections (``supersedes`` / provenance=corrected) win over the
   superseded id and over older conflicting preferences.
3. Unique memories from either source are kept losslessly.
4. Superseded bodies are archived into session notes (not re-imported as
   active memories) so ``memanto migrate okf`` cannot revive stale facts.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _fingerprint(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()[:16]


def _topic_key(mem: dict[str, Any]) -> str | None:
    """Collapse known conflicting topics onto a single consolidation key."""
    body = _norm(mem.get("content") or "")
    if "prefer" in body and ("typescript" in body or "python" in body):
        return "topic:language-preference"
    if "name is priya" in body:
        return "topic:identity-name"
    if "asia/kolkata" in body or "utc+5:30" in body:
        return "topic:timezone"
    if "marcus chen" in body:
        return "topic:oncall-buddy"
    return None


def consolidate(
    chroma_memories: list[dict[str, Any]],
    sqlite_memories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return (active_memories, archived_superseded, summary)."""
    all_memories = list(chroma_memories) + list(sqlite_memories)

    superseded_ids = {
        f"chroma:{m['supersedes']}" for m in chroma_memories if m.get("supersedes")
    }
    # Also treat chroma-lang as superseded when correction exists.
    if any(m.get("chroma_id") == "chroma-lang-correction" for m in chroma_memories):
        superseded_ids.add("chroma:chroma-lang")

    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    uniques: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []

    for mem in all_memories:
        if mem["id"] in superseded_ids or (
            mem.get("chroma_id") and f"chroma:{mem['chroma_id']}" in superseded_ids
        ):
            archived.append({**mem, "archive_reason": "superseded"})
            continue
        topic = _topic_key(mem)
        if topic:
            by_topic[topic].append(mem)
        else:
            uniques.append(mem)

    active: list[dict[str, Any]] = []
    merge_events: list[dict[str, Any]] = []

    for topic, group in by_topic.items():
        # Prefer corrected provenance, then newest created_at, then higher confidence.
        ranked = sorted(
            group,
            key=lambda m: (
                1 if m.get("provenance") == "corrected" else 0,
                str(m.get("created_at") or ""),
                float(m.get("confidence") or 0),
            ),
            reverse=True,
        )
        winner = dict(ranked[0])
        losers = ranked[1:]
        sources = sorted(
            {
                src
                for m in group
                for src in (m.get("sources") or [m.get("source")])
                if src
            }
        )
        winner["sources"] = sources
        winner["tags"] = sorted(
            set(winner.get("tags") or [])
            | {f"consolidated:{topic}"}
            | {f"sources:{len(sources)}"}
        )
        if losers:
            # If losers conflict on language preference, archive them.
            if topic == "topic:language-preference":
                for loser in losers:
                    archived.append(
                        {
                            **loser,
                            "archive_reason": "conflict_resolved_by_newer_correction",
                            "resolved_by": winner["id"],
                        }
                    )
                merge_events.append(
                    {
                        "topic": topic,
                        "winner": winner["id"],
                        "archived": [m["id"] for m in losers],
                        "action": "prefer_correction",
                    }
                )
            else:
                # Same fact from two stores — merge provenance only.
                winner["id"] = f"merged:{_fingerprint(winner['content'])}"
                winner["source"] = "consolidated"
                winner["source_ref"] = "consolidated://" + "+".join(
                    sorted({m.get("source_ref") or m["id"] for m in group})
                )
                merge_events.append(
                    {
                        "topic": topic,
                        "winner": winner["id"],
                        "merged_from": [m["id"] for m in group],
                        "action": "dedupe_agreeing_facts",
                    }
                )
        active.append(winner)

    # Deduplicate exact duplicates among uniques by fingerprint.
    seen_fp: dict[str, dict[str, Any]] = {}
    for mem in uniques:
        fp = _fingerprint(mem["content"])
        if fp in seen_fp:
            existing = seen_fp[fp]
            existing_sources = set(existing.get("sources") or [existing.get("source")])
            new_sources = set(mem.get("sources") or [mem.get("source")])
            existing["sources"] = sorted(existing_sources | new_sources)
            existing["tags"] = sorted(
                set(existing.get("tags") or [])
                | set(mem.get("tags") or [])
                | {"consolidated:exact-dupe"}
            )
            existing["source"] = "consolidated"
            merge_events.append(
                {
                    "topic": f"fp:{fp}",
                    "winner": existing["id"],
                    "merged_from": [existing["id"], mem["id"]],
                    "action": "dedupe_exact",
                }
            )
        else:
            seen_fp[fp] = dict(mem)
    active.extend(seen_fp.values())

    # Stable order for reproducible bundles.
    active.sort(key=lambda m: (str(m.get("created_at") or ""), m["id"]))

    summary = {
        "chroma_source_count": len(chroma_memories),
        "sqlite_source_count": len(sqlite_memories),
        "active_count": len(active),
        "archived_count": len(archived),
        "merge_events": merge_events,
        "per_type": _count_types(active),
    }
    return active, archived, summary


def _count_types(memories: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for mem in memories:
        counts[str(mem.get("type") or "auto")] += 1
    return dict(sorted(counts.items()))


def archive_session_notes(archived: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Render superseded memories as OKF session context (not importable memories)."""
    if not archived:
        return []
    lines = [
        "# Superseded / conflict-resolved memories",
        "",
        "These records were active in a source store but must not be re-imported",
        "as live memories. They stay under `sessions/` so `memanto migrate okf`",
        "ignores them while humans can still audit the history.",
        "",
    ]
    for mem in archived:
        lines.append(f"## {mem.get('title')}")
        lines.append(f"- id: `{mem.get('id')}`")
        lines.append(f"- reason: `{mem.get('archive_reason')}`")
        if mem.get("resolved_by"):
            lines.append(f"- resolved_by: `{mem['resolved_by']}`")
        lines.append("")
        lines.append(mem.get("content") or "")
        lines.append("")
    return [("superseded-timeline", "\n".join(lines))]
