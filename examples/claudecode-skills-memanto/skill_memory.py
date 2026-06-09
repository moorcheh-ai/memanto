#!/usr/bin/env python3
"""Reviewer-safe Memanto SkillChain bridge for Claude Code skills.

Local mode is deterministic and credential-free. Live mode shells out to the
public Memanto CLI only when MEMANTO_LIVE=1 and MOORCHEH_API_KEY is set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(".skillchain")
LOCAL_MEMORY = STATE_DIR / "memory.jsonl"
INJECTED_CONTEXT = STATE_DIR / "injected-context.md"


@dataclass(frozen=True)
class MemoryCard:
    content: str
    memory_type: str
    source_skill: str
    task: str
    created_at: str

    def to_text(self) -> str:
        return f"[{self.memory_type}] {self.content} (from {self.source_skill}; task={self.task!r})"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def live_enabled() -> bool:
    return os.environ.get("MEMANTO_LIVE") == "1" and bool(os.environ.get("MOORCHEH_API_KEY"))


def classify(line: str) -> str:
    lowered = line.lower()
    if "decision" in lowered or "decided" in lowered:
        return "decision"
    if "prefer" in lowered or "style" in lowered or "convention" in lowered:
        return "preference"
    if "must" in lowered or "never" in lowered or "always" in lowered:
        return "instruction"
    if "artifact" in lowered or "created" in lowered or "wrote" in lowered:
        return "artifact"
    return "context"


def durable_lines(text: str) -> list[str]:
    marker = re.compile(
        r"\b(decision|decided|prefer|preference|must|never|always|required|constraint|artifact|created|wrote|context|adr|test)\b",
        re.IGNORECASE,
    )
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = " ".join(raw.strip(" -\t").split())
        if len(line) < 20 or not marker.search(line):
            continue
        if looks_secretish(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line[:500])
    return lines[:12]


def looks_secretish(text: str) -> bool:
    patterns = [
        r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S{8,}",
        r"sk-[A-Za-z0-9_-]{20,}",
        r"ghp_[A-Za-z0-9_]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def read_local() -> list[MemoryCard]:
    if not LOCAL_MEMORY.exists():
        return []
    cards: list[MemoryCard] = []
    for line in LOCAL_MEMORY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cards.append(MemoryCard(**json.loads(line)))
    return cards


def write_local(cards: list[MemoryCard]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_MEMORY.write_text("\n".join(json.dumps(asdict(card)) for card in cards) + "\n", encoding="utf-8")


def store_local(new_cards: list[MemoryCard]) -> None:
    cards = read_local()
    existing = {(card.content, card.source_skill, card.task) for card in cards}
    for card in new_cards:
        key = (card.content, card.source_skill, card.task)
        if key not in existing:
            cards.append(card)
            existing.add(key)
    write_local(cards)


def recall_local(query: str, limit: int) -> list[MemoryCard]:
    words = {word.lower() for word in re.findall(r"[a-zA-Z0-9_/-]{3,}", query)}
    scored: list[tuple[int, MemoryCard]] = []
    for card in read_local():
        haystack = f"{card.content} {card.memory_type} {card.source_skill} {card.task}".lower()
        score = sum(1 for word in words if word in haystack)
        if score:
            scored.append((score, card))
    scored.sort(key=lambda item: (-item[0], item[1].created_at))
    return [card for _, card in scored[:limit]]


def run_memanto(args: list[str]) -> str:
    result = subprocess.run(["memanto", *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def before(args: argparse.Namespace) -> int:
    if live_enabled():
        context = run_memanto(["recall", args.query, "--limit", str(args.limit)])
        mode = "live"
    else:
        recalled = recall_local(args.query, args.limit)
        context = "\n".join(f"- {card.to_text()}" for card in recalled) or "No relevant prior memories found."
        mode = "local"

    body = (
        "MEMANTO SKILLCHAIN MEMORY STACK\n"
        f"mode: {mode}\n"
        f"current_skill: {args.skill}\n"
        f"task: {args.task}\n\n"
        f"{context}\n"
    )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    INJECTED_CONTEXT.write_text(body, encoding="utf-8")
    print(body)
    return 0


def after(args: argparse.Namespace) -> int:
    transcript = Path(args.transcript).read_text(encoding="utf-8")
    cards = [
        MemoryCard(
            content=line,
            memory_type=classify(line),
            source_skill=args.skill,
            task=args.task,
            created_at=now_iso(),
        )
        for line in durable_lines(transcript)
    ]
    if live_enabled():
        for card in cards:
            run_memanto(["remember", card.to_text(), "--type", card.memory_type])
        print(f"Stored {len(cards)} cards in live Memanto mode")
    else:
        store_local(cards)
        print(f"Stored {len(cards)} cards in local mode")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memanto SkillChain bridge for Claude Code skills")
    sub = parser.add_subparsers(dest="command", required=True)

    p_before = sub.add_parser("before")
    p_before.add_argument("--skill", required=True)
    p_before.add_argument("--task", required=True)
    p_before.add_argument("--query", required=True)
    p_before.add_argument("--limit", type=int, default=5)
    p_before.set_defaults(func=before)

    p_after = sub.add_parser("after")
    p_after.add_argument("--skill", required=True)
    p_after.add_argument("--task", required=True)
    p_after.add_argument("--transcript", required=True)
    p_after.set_defaults(func=after)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
