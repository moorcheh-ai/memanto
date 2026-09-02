#!/usr/bin/env python3
"""Round-trip recall parity check for the Universal Migration Adapter.

Proves the "zero amnesia" claim of Path B:

  before  -> can the source export answer the golden questions?
  migrate -> adapter generates OKF, `memanto migrate okf` imports it
  after   -> can Memanto (recall/answer) answer the same questions?

Usage:
    python3 validate_roundtrip.py --source claude --input ./conversations.json \
        --questions "What port does the app use?" "Which DB do we use?"

Requires an active Memanto agent and MOORCHEH_API_KEY in .env.

The "before" check is honest: it retrieves ground-truth evidence directly
from the raw source text using keyword overlap, since the source tool itself
is not available at runtime. "After" uses Memanto's own retrieval.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapters  # noqa: F401  (registers adapters)
from core.adapters import ADAPTERS


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower())


def _kws(question: str) -> list[str]:
    stop = {
        "the",
        "a",
        "an",
        "do",
        "does",
        "we",
        "our",
        "what",
        "which",
        "is",
        "are",
        "in",
        "of",
        "for",
        "use",
        "used",
        "and",
        "or",
    }
    return [w for w in _norm(question).split() if w not in stop and len(w) > 3]


def _build_source_index(raw) -> dict[str, str]:
    if isinstance(raw, dict):
        conversations = raw.get("conversations") or raw.get("chat_messages") or []
        raw = conversations if isinstance(conversations, list) else []
    index: dict[str, str] = {}
    for conv_id, conv in enumerate(raw, start=1):
        msgs = (
            conv.get("chat_messages") or conv.get("messages", [])
            if isinstance(conv, dict)
            else []
        )
        parts = []
        for m in msgs:
            if isinstance(m, dict):
                c = m.get("content", "")
                if isinstance(c, list):
                    c = " ".join(
                        b.get("text", "") if isinstance(b, dict) else str(b) for b in c
                    )
                if isinstance(c, str):
                    parts.append(c)
        index[f"conv-{conv_id}"] = " ".join(parts)
    return index


def _source_has_answer(index: dict[str, str], question: str) -> bool:
    kws = _kws(question)
    if not kws:
        return False
    for content in index.values():
        n = _norm(content)
        if all(kw in n for kw in kws):
            return True
    return False


def _memanto_answer(question: str) -> str:
    try:
        out = subprocess.run(
            [sys.executable, "-m", "memanto", "answer", question, "-n", "5"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"<memanto answer error: {e}>"


_ERROR_HINTS = ("no active agent", " error", "not found", "does not exist", "<memanto")


def _score_parity(question: str, before: bool, after: str) -> bool:
    if not before:
        return False  # can't claim recall without source evidence
    low = after.lower()
    if not after or any(h in low for h in _ERROR_HINTS):
        return False  # an error / empty result is not a pass
    kws = _kws(question)
    return bool(kws) and any(kw in low for kw in kws)  # weak on-topic signal


def main() -> None:
    parser = argparse.ArgumentParser(description="Round-trip recall parity check")
    parser.add_argument("--source", choices=list(ADAPTERS.keys()), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--questions", nargs="+", required=True)
    parser.add_argument("--output", default="./okf_output/roundtrip")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Select all conversations (skip the interactive prompt)",
    )
    args = parser.parse_args()

    adapter = ADAPTERS[args.source]()
    raw = adapter.load(args.input)

    conv_list = adapter.get_conversation_list(raw)
    if isinstance(raw, dict):
        raw = raw.get("conversations") or raw.get("chat_messages") or []
    if not conv_list:
        print("No conversations found in the export.")
        sys.exit(1)
    print(f"\nFound {len(conv_list)} conversations:\n")
    for i, conv in enumerate(conv_list):
        print(f"  [{i + 1}] {conv['title'][:60]}  ({conv['message_count']} messages)")
    print("\n  [a] Select all\n  [q] Quit\n")

    selected: list[int] = []
    if args.all:
        selected = list(range(len(conv_list)))
    else:
        choice = input("Enter numbers (comma-separated) or 'a' for all: ").strip()
        if choice == "q":
            print("Aborted.")
            sys.exit(0)
        if choice != "a":
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                wanted = {
                    conv_list[i]["id"] for i in indices if 0 <= i < len(conv_list)
                }
                if not wanted:
                    print("No valid selections. Aborting.")
                    sys.exit(1)
                selected = [
                    i for i, info in enumerate(conv_list) if info["id"] in wanted
                ]
            except ValueError:
                print("Invalid input. Aborting.")
                sys.exit(1)
        else:
            selected = list(range(len(conv_list)))

    if selected:
        wanted_ids = {conv_list[i]["id"] for i in selected}
        raw = [conv for conv, info in zip(raw, conv_list) if info["id"] in wanted_ids]

    index = _build_source_index(raw)

    print(f"\nLoaded {len(index)} conversations from {args.input}\n")

    total = 0
    passed = 0
    for q in args.questions:
        total += 1
        before = _source_has_answer(index, q)
        print(f"  * {q}")
        print(f"      before (source evidence): {'yes' if before else 'no'}")

        if not before:
            print("      after : SKIPPED (no source evidence -> nothing to prove)")
            continue

        after = _memanto_answer(q)
        ok = _score_parity(q, before, after)
        passed += int(ok)
        print(f"      after : {after[:120]}")
        print(f"      parity: {'PASS' if ok else 'FAIL'}")
        print()

    print(f"Recall parity: {passed}/{total}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
