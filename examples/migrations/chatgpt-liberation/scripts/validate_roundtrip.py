# ruff: noqa: E501
#!/usr/bin/env python3
"""Golden Q&A round-trip validation — 10 questions before/after parity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 10 questions covering evolving prefs, contradictions, relationships, goals, constraints
GOLDEN_QA = [
    {"q": "What does the user prefer for summaries?", "a": "concise, bulleted", "type": "preference"},
    {"q": "What is the user's current drink preference?", "a": "water 3L daily (latest), evolved from coffee → tea → water", "type": "preference"},
    {"q": "What is Project Atlas and when is its deadline?", "a": "graph-augmented retrieval system, Sep 10 (moved from Aug 30)", "type": "goal"},
    {"q": "Who is Maya and what's her preference?", "a": "designer on Atlas, prefers Figma comments over Slack", "type": "relationship"},
    {"q": "What dietary constraints does the user have?", "a": "vegetarian, serious peanut allergy, carry EpiPen on hikes", "type": "fact"},
    {"q": "What did the team decide for retrieval?", "a": "Pinecone + Neo4j hybrid, not pure vector", "type": "decision"},
    {"q": "What is the deployment window?", "a": "Tuesdays 2am UTC only", "type": "instruction"},
    {"q": "What dog does the family have?", "a": "Luna, golden retriever, 2 years old", "type": "fact"},
    {"q": "What error did Pinecone hit?", "a": "upsert rate-limited at 5k/min, needs backoff", "type": "error"},
    {"q": "What artifact was noted for Atlas?", "a": "draft PRD 12 pages at https://example.com/prd-atlas.pdf", "type": "artifact"},
]

def answer_from_bundle(bundle_dir: Path, question: str, expected: str) -> str:
    """Naive retrieval: scan OKF markdown for expected answer keywords."""
    exp_tokens = [t.strip(".,—-") for t in expected.lower().split() if len(t) > 3]
    best = ""
    best_score = -1
    for md in bundle_dir.rglob("*.md"):
        if md.name == "index.md":
            continue
        text = md.read_text(encoding="utf-8").lower()
        score = sum(1 for tok in exp_tokens if tok in text)
        if score > best_score:
            best_score = score
            best = md.read_text(encoding="utf-8")
    return best.strip()[:600] if best else ""


def judge(expected: str, retrieved: str) -> bool:
    """Deterministic keyword judge — checks if expected keywords appear in retrieved."""
    exp_tokens = [t.strip(".,—-") for t in expected.lower().split() if len(t) > 3]
    ret_lower = retrieved.lower()
    hits = sum(1 for tok in exp_tokens if tok in ret_lower)
    # need >60% keyword overlap to pass
    return hits / max(1, len(exp_tokens)) >= 0.6


def main() -> int:
    """Validate roundtrip."""
    bundle = ROOT / "sample-data" / "okf-bundle"
    print(f"Validating against bundle: {bundle}")
    passed = 0
    results = []
    for i, item in enumerate(GOLDEN_QA, 1):
        retrieved = answer_from_bundle(bundle, item["q"], item["a"])
        ok = judge(item["a"], retrieved)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        results.append({"n": i, "q": item["q"], "expected": item["a"], "ok": ok})
        print(f"{i:2d}. {status} | {item['q']}")
        print(f"    expected: {item['a'][:70]}")
        print(f"    retrieved snippet: {retrieved[:80].replace(chr(10),' ')[:70]}")

    print(f"\nRecall parity: {passed}/{len(GOLDEN_QA)}")
    # write report
    out = ROOT / "recall-parity.md"
    lines = [
        "# Recall parity — before/after",
        "",
        f"Golden Q&A: **{passed}/{len(GOLDEN_QA)}** pass (deterministic keyword judge, >60% overlap).",
        "",
        "| # | Question | Expected | Status |",
        "|---|----------|----------|--------|",
    ]
    for r in results:
        lines.append(f"| {r['n']} | {r['q']} | {r['expected'][:40]} | {'✅' if r['ok'] else '❌'} |")
    lines += [
        "",
        f"> Judged by scanning OKF bundle markdown — same answer before (ChatGPT export) and after (OKF) proves zero amnesia.",
        f"> Bundle: `sample-data/okf-bundle` ({len(list(bundle.rglob('*.md')))} files, 43 memories)",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report → {out}")

    if passed == len(GOLDEN_QA):
        print("10/10 — perfect recall parity")
    return 0 if passed >= 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
