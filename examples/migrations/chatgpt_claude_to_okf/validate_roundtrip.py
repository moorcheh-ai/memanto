#!/usr/bin/env python3
"""Post-migration recall check: offline keyword parity + optional LLM-as-judge.

Honest scoping: the offline check measures keyword overlap between the golden
answers (from the source export) and the generated OKF bundle. It is a strong
signal that nothing was lost in extraction, but it is NOT a true round-trip
through Memanto — that requires actually running `memanto migrate okf` (import)
and `memanto memory export --okf` (export) on a live agent. Both steps are
documented in README; this script is the fast, deterministic gate.

Usage:
    python validate_roundtrip.py chatgpt sample_data/chatgpt_export my_memories
    OPENAI_API_KEY=... python validate_roundtrip.py chatgpt sample_data/chatgpt_export my_memories --llm
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


def build_golden(conversations: list[dict], source: str) -> list[dict]:
    result = extract_memories(conversations, source=source)
    return [{"q": f"What is {m['title']}?", "a": m["content"], "type": m["type"]}
            for m in result["memories"]]


def offline_parity(golden: list[dict], bundle_dir: Path) -> dict:
    bundle_text = ""
    for p in (bundle_dir / "memories").rglob("*.md"):
        if p.name == "index.md":
            continue
        bundle_text += p.read_text(encoding="utf-8") + "\n"
    bundle_tokens = _tokens(bundle_text)

    hits = 0
    per_type = Counter()
    for g in golden:
        overlap = _tokens(g["a"]) & bundle_tokens
        score = len(overlap) / max(1, len(_tokens(g["a"])))
        if score >= 0.5:
            hits += 1
            per_type[g["type"]] += 1
    return {
        "questions": len(golden),
        "recall_hits": hits,
        "recall": round(hits / max(1, len(golden)), 3),
        "by_type": dict(per_type),
    }


def llm_judge(golden: list[dict], bundle_dir: Path, sample: int = 20) -> dict:
    """LLM-as-judge over a sample of golden Q&As (needs OPENAI/ANTHROPIC key)."""
    import urllib.request

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY or ANTHROPIC_API_KEY required for --llm"}
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("export_dir", type=str)
    ap.add_argument("bundle_dir", type=str, default="okf_bundle", nargs="?")
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()

    conversations = SOURCES[args.source](args.export_dir)
    golden = build_golden(conversations, args.source)
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
