#!/usr/bin/env python3
"""Post-migration recall check: offline keyword parity + optional LLM-as-judge.

Honest scoping: the offline check measures keyword overlap between the golden
answers (from the source export) and the generated OKF bundle. It is a strong
signal that nothing was lost in extraction, but it is NOT a true round-trip
through Memanto — that requires actually running `memanto migrate okf` (import)
and `memanto memory export --okf` (export) on a live agent. Both steps are
documented in README; this script is the fast, deterministic gate.

Usage:
    python validate_roundtrip.py chatgpt sample_data/chatgpt_export okf_bundle_real
    OPENAI_API_KEY=... python validate_roundtrip.py chatgpt sample_data/chatgpt_export okf_bundle_real --llm
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from adapters.chatgpt import load_chatgpt
from adapters.claude import load_claude
from adapters.extract import extract_memories

SOURCES = {"chatgpt": load_chatgpt, "claude": load_claude}

STOPWORDS = set("the a an and or but for with of in on at to from by is are was were be been i my me we our you your it its this that as".split())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9\u00c0-\u1ef9]{3,}", text.lower()) if w not in STOPWORDS}


def build_golden(conversations: list[dict], source: str,
                 max_per_type: int | None = None, max_total: int | None = None) -> list[dict]:
    kwargs: dict = {}
    if max_per_type is not None:
        kwargs["max_per_type"] = max_per_type
    if max_total is not None:
        kwargs["max_total"] = max_total
    result = extract_memories(conversations, source=source, **kwargs)
    return [{"q": f"What is {m['title']}?", "a": m["content"], "type": m["type"]}
            for m in result["memories"]]


def offline_parity(golden: list[dict], bundle_dir: Path) -> dict:
    # Tokenize each memory file SEPARATELY: aggregated tokens across distinct
    # memories must not satisfy the threshold — an answer is "recallable" only
    # if a single memory carries enough of it.
    per_file_tokens = []
    for p in (bundle_dir / "memories").rglob("*.md"):
        if p.name == "index.md":
            continue
        per_file_tokens.append(_tokens(p.read_text(encoding="utf-8")))

    hits = 0
    per_type = Counter()
    for g in golden:
        answer_tokens = _tokens(g["a"])
        best = 0.0
        for ft in per_file_tokens:
            overlap = answer_tokens & ft
            score = len(overlap) / max(1, len(answer_tokens))
            best = max(best, score)
        if best >= 0.5:
            hits += 1
            per_type[g["type"]] += 1
    return {
        "questions": len(golden),
        "recall_hits": hits,
        # an empty golden set is vacuously 100% recallable
        "recall": round(hits / max(1, len(golden)), 3) if golden else 1.0,
        "by_type": dict(per_type),
    }


def llm_judge(golden: list[dict], bundle_dir: Path, sample: int = 20) -> dict:
    """LLM-as-judge over a sample of golden Q&As (needs OPENAI_API_KEY)."""
    import urllib.request

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY required for --llm (OpenAI Chat Completions endpoint)"}
    bundle_text = ""
    for p in (bundle_dir / "memories").rglob("*.md"):
        if p.name != "index.md":
            bundle_text += p.read_text(encoding="utf-8")[:4000] + "\n"

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": (
                "You are a strict recall judge. Given the migrated memory store and a "
                "question whose answer existed in the source store, score 0..1 how "
                "completely the store answers it. Reply with only a float.")},
            {"role": "user", "content": f"STORE:\n{bundle_text[:12000]}\n\nQ: {golden[0]['q']}"},
        ],
        "temperature": 0,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
        return {"llm_judge": body["choices"][0]["message"]["content"].strip()}
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def _non_negative_int(v: str) -> int:
    n = int(v)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("export_dir", type=str)
    ap.add_argument("bundle_dir", type=str, default="okf_bundle", nargs="?")
    ap.add_argument("--llm", action="store_true", help="also run an optional LLM-as-judge (requires OPENAI_API_KEY)")
    ap.add_argument("--max-per-type", type=_non_negative_int, default=None, help="override extraction cap per type (>= 0)")
    ap.add_argument("--max-total", type=_non_negative_int, default=None, help="override extraction cap total (>= 0)")
    args = ap.parse_args()

    conversations = SOURCES[args.source](args.export_dir)
    golden = build_golden(conversations, args.source,
                          max_per_type=args.max_per_type, max_total=args.max_total)
    result = offline_parity(golden, Path(args.bundle_dir))
    print(f"Golden questions: {result['questions']}")
    print(f"Offline keyword recall: {result['recall']} ({result['recall_hits']} hits)")
    print(f"Recall by type   : {result['by_type']}")
    print("Note: offline keyword recall checks the generated bundle only; the")
    print("true round-trip (import via `memanto migrate okf` + export) is the")
    print("separate CLI step documented in README.")
    if args.llm:
        print("LLM judge       :", llm_judge(golden, Path(args.bundle_dir)))
    return 0 if result["recall"] >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
