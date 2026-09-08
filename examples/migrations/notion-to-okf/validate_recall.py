"""
validate_recall.py
==================
Golden Q&A recall validation for the Notion → Memanto migration.

Queries the Memanto agent both before (offline, against OKF bundle) and after
(live, against Memanto) to prove round-trip recall parity.

Usage:
    python validate_recall.py --agent notion-migration-demo   # live Memanto
    python validate_recall.py --offline                       # offline bundle check
    python validate_recall.py --bundle ./okf_bundle_live      # custom bundle path

No API key needed for --offline mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent

GOLDEN_QA = [
    {
        "id": "Q001",
        "question": "What decision was made about the memory backend?",
        "must_contain": ["Pinecone", "Memanto"],
        "query_type": "decision",
    },
    {
        "id": "Q002",
        "question": "What is the preferred API response time?",
        "must_contain": ["500ms"],
        "query_type": "preference",
    },
    {
        "id": "Q003",
        "question": "What was agreed in the Q3 planning meeting?",
        "must_contain": ["temporal recall"],
        "query_type": "event",
    },
    {
        "id": "Q004",
        "question": "What bug was found in the datetime handling?",
        "must_contain": ["utcnow", "timezone"],
        "query_type": "fact",
    },
    {
        "id": "Q005",
        "question": "What benchmark was used to evaluate Memanto?",
        "must_contain": ["LoCoMo"],
        "query_type": "fact",
    },
    {
        "id": "Q006",
        "question": "What is the goal for the Memanto bug bounty?",
        "must_contain": ["bugs", "PR"],
        "query_type": "goal",
    },
]


def _score(answer: str, must_contain: list[str]) -> float:
    if not answer:
        return 0.0
    lower = answer.lower()
    hits = sum(1 for kw in must_contain if kw.lower() in lower)
    return round(hits / len(must_contain), 2) if must_contain else 1.0


def validate_offline(bundle_dir: Path) -> list[dict]:
    """Validate recall against OKF bundle files (no API key needed)."""
    results = []
    md_files = list(bundle_dir.glob("memories/**/*.md"))
    corpus = "\n".join(f.read_text(encoding="utf-8") for f in md_files)

    print(f"\n📖 Offline validation against {len(md_files)} OKF files in {bundle_dir}")
    for qa in GOLDEN_QA:
        score = _score(corpus, list(qa["must_contain"]))
        status = "✅" if score >= 0.5 else "❌"
        print(
            f"  {status} {qa['id']} ({qa['query_type']}) score={score:.2f} — {qa['question'][:60]}"
        )
        results.append(
            {
                "id": qa["id"],
                "question": qa["question"],
                "query_type": qa["query_type"],
                "score": score,
                "mode": "offline",
            }
        )
    return results


def validate_live(agent_id: str, moorcheh_key: str) -> list[dict]:
    """Validate recall against live Memanto agent."""
    try:
        from memanto.cli.client.sdk_client import SdkClient

        client = SdkClient(api_key=moorcheh_key)
    except Exception as e:
        print(f"❌ Failed to init Memanto client: {e}")
        return []

    results = []
    print(
        f"\n🔍 Live recall validation — agent '{agent_id}' ({len(GOLDEN_QA)} questions)..."
    )
    for qa in GOLDEN_QA:
        try:
            resp = client.recall(agent_id=agent_id, query=qa["question"], limit=5)
            memories = resp.get("results", []) if isinstance(resp, dict) else []
            answer = " ".join(m.get("content", "") for m in memories)
            score = _score(answer, list(qa["must_contain"]))
        except Exception as e:
            answer = ""
            score = 0.0
            print(f"    ⚠️  {qa['id']} recall error: {e}")

        status = "✅" if score >= 0.5 else "❌"
        print(
            f"  {status} {qa['id']} ({qa['query_type']}) score={score:.2f} — {qa['question'][:60]}"
        )
        results.append(
            {
                "id": qa["id"],
                "question": qa["question"],
                "query_type": qa["query_type"],
                "score": score,
                "answer_preview": answer[:120],
                "mode": "live",
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Notion migration recall validation")
    parser.add_argument("--agent", default="notion-migration-demo")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--bundle", type=Path, default=HERE / "sample_okf_bundle")
    args = parser.parse_args()

    if args.offline:
        results = validate_offline(args.bundle)
        mode = "offline"
    else:
        key = os.getenv("MOORCHEH_API_KEY", "")
        if not key:
            print("❌ MOORCHEH_API_KEY required. Use --offline for no-key validation.")
            sys.exit(1)
        results = validate_live(args.agent, key)
        mode = "live"

    if not results:
        print("No results.")
        return

    avg = sum(r["score"] for r in results) / len(results)
    passing = sum(1 for r in results if r["score"] >= 0.5)
    print(f"\n{'=' * 50}")
    print(f"  Recall parity: {passing}/{len(results)} ({avg:.1%})")
    print(f"  Mode: {mode}")
    print(f"{'=' * 50}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": args.agent,
        "mode": mode,
        "questions": len(results),
        "passing": passing,
        "recall_parity_percent": round(avg * 100, 1),
        "results": results,
    }
    out = HERE / "recall_parity.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n💾 Recall parity report → {out}")


if __name__ == "__main__":
    main()
