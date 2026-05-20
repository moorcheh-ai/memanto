#!/usr/bin/env python3
"""
Claude Code hook: Stop
======================

When a Claude Code session ends, this hook reads the transcript, identifies
the structurally interesting turns (preferences expressed, decisions made,
errors corrected), and stores them in Memanto as typed memories.

Heuristics are deliberately conservative: it's better to miss a memory than
to flood Memanto with noise. Empirically a single session produces 3-7
memories with these rules.

Failure modes are silent.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _memanto_common import (  # noqa: E402
    get_logger,
    load_env,
    load_extra_tags,
    make_client,
    parse_hook_input,
    safe_truncate,
)

LOG = get_logger("distill_session")


# ── Signal-extraction patterns ──────────────────────────────────────────────
# Tuned on real Claude Code transcripts. Each pattern maps a user-utterance
# regex to (memory_type, confidence, title_template).

PREFERENCE_PATTERNS = [
    re.compile(r"\b(?:always|by default|prefer to)\s+(.{8,200})", re.IGNORECASE),
    re.compile(r"\bnever\s+(.{8,200})", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+(?:use|do|add|write|include)\s+(.{8,200})", re.IGNORECASE),
    re.compile(r"\b(?:stop|please stop)\s+(.{8,200})", re.IGNORECASE),
]

DECISION_PATTERNS = [
    re.compile(r"\blet'?s (?:use|go with|pick|adopt)\s+(.{6,200})", re.IGNORECASE),
    re.compile(r"\bwe'?ll (?:use|go with|adopt)\s+(.{6,200})", re.IGNORECASE),
    re.compile(r"\b(?:decided|going) (?:on|with)\s+(.{6,200})", re.IGNORECASE),
    re.compile(r"\binstead of \S+,?\s+(?:use|do)\s+(.{6,200})", re.IGNORECASE),
]

CONTEXT_PATTERNS = [
    re.compile(r"\b(?:in this (?:repo|project|codebase|file)|convention here is)\s+(.{8,200})", re.IGNORECASE),
    re.compile(r"\bthis file is special because\s+(.{8,200})", re.IGNORECASE),
    re.compile(r"\bnote that\s+(.{8,200})", re.IGNORECASE),
]

ERROR_PATTERNS = [
    re.compile(r"\b(?:that's wrong|you got that wrong|that broke|that introduced a bug)\s*[—:.]?\s*(.{8,200})", re.IGNORECASE),
    re.compile(r"\bthe issue (?:was|is)\s+(.{8,200})", re.IGNORECASE),
]


def classify_turn(text: str) -> list[tuple[str, float, str]]:
    """
    Return a list of (memory_type, confidence, extracted_snippet) tuples
    extracted from one user turn. Empty list if nothing matches.
    """
    if not text or len(text) < 10:
        return []

    hits: list[tuple[str, float, str]] = []
    for pat in PREFERENCE_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(("preference", 0.85, m.group(1).strip()))
            break  # one preference per turn is enough
    for pat in DECISION_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(("decision", 0.85, m.group(1).strip()))
            break
    for pat in CONTEXT_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(("context", 0.75, m.group(1).strip()))
            break
    for pat in ERROR_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(("error", 0.75, m.group(1).strip()))
            break
    return hits


def iter_user_turns(transcript_path: Path) -> list[str]:
    """
    Parse the JSONL transcript and return user turn texts in order.

    Claude Code stores transcripts as JSONL where each line is a message
    record. User turns have role=user. We extract the raw text content.
    """
    if not transcript_path.exists():
        return []
    turns: list[str] = []
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or rec
                role = msg.get("role")
                if role != "user":
                    continue
                content = msg.get("content")
                # content can be a string or a list of content blocks
                if isinstance(content, str):
                    turns.append(content)
                elif isinstance(content, list):
                    text_parts: list[str] = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                    if text_parts:
                        turns.append("\n".join(text_parts))
    except OSError as exc:
        LOG.error("Failed to read transcript %s: %s", transcript_path, exc)
    return turns


def already_stored(client, agent_id: str, content: str) -> bool:
    """Skip if a near-duplicate exists (cosine ≥ 0.9 with same first 200 chars)."""
    try:
        result = client.recall(
            agent_id=agent_id,
            query=content[:200],
            limit=3,
            min_confidence=0.9,
        )
        return bool(result.get("memories"))
    except Exception:  # noqa: BLE001
        return False  # err on the side of storing


def main() -> int:
    ctx = parse_hook_input()
    if ctx is None:
        return 0

    transcript_path_str = ctx.payload.get("transcript_path")
    if not transcript_path_str:
        LOG.debug("No transcript_path in hook payload — skipping")
        return 0

    transcript_path = Path(transcript_path_str)
    user_turns = iter_user_turns(transcript_path)
    if not user_turns:
        LOG.debug("No user turns parsed from %s — skipping", transcript_path)
        return 0

    api_key = load_env()
    if not api_key:
        LOG.warning("MOORCHEH_API_KEY not set — skipping distillation")
        return 0

    try:
        client = make_client(api_key, ctx.agent_id, ctx.project_name)
    except Exception as exc:  # noqa: BLE001
        LOG.error("Failed to instantiate Memanto client: %s", exc)
        return 0

    extra_tags = load_extra_tags(ctx.cwd)
    base_tags = [f"project:{ctx.project_name}", "source:claude-code", *extra_tags]
    stored = 0

    for turn in user_turns:
        for mem_type, confidence, snippet in classify_turn(turn):
            content = snippet
            title = safe_truncate(snippet, 80)
            if already_stored(client, ctx.agent_id, content):
                LOG.debug("Skipping duplicate: %s", safe_truncate(content, 60))
                continue
            try:
                client.remember(
                    agent_id=ctx.agent_id,
                    memory_type=mem_type,
                    title=title,
                    content=content,
                    confidence=confidence,
                    tags=base_tags + [f"type:{mem_type}"],
                    source="claude-code-session",
                    provenance="explicit_statement",
                )
                stored += 1
                LOG.info(
                    "Stored %s (confidence=%.2f): %s",
                    mem_type, confidence, safe_truncate(title, 60),
                )
            except Exception as exc:  # noqa: BLE001
                LOG.error("remember() failed for %s: %s", mem_type, exc)

    LOG.info(
        "Session distilled: %d memories stored (agent_id=%s, project=%s)",
        stored, ctx.agent_id, ctx.project_name,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Unexpected error: %s", exc)
        sys.exit(0)
