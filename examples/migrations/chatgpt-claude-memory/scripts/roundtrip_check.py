#!/usr/bin/env python3
"""Round-trip validation: does the OKF bundle retain the signal the source
archive had?

The bounty's "round-trip validation" asks for an LLM-as-a-judge (or golden
Q&A set) that queries the *before* (source archive) and *after* (migrated OKF
bundle) states and scores recall parity.

This checker does exactly that with a small golden Q&A set. It prefers a local
DeepSeek endpoint (no API cost) as the judge; if none is reachable it falls
back to deterministic keyword recall over the bundle, so the demo is always
reproducible and the numbers are always honest.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT))

from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402

DATA = HERE.parent / "data"
OKF_DIR = HERE.parent / "okf"

DEEPSEEK_URL = "http://127.0.0.1:8888/v1/chat/completions"

# Golden Q&A: questions an agent would realistically be asked, with the
# ground-truth terms that must be recallable from the migrated memory.
GOLDEN_QA = [
    ("What editor theme do I like?", ["dark"]),
    ("What laptop do I use?", ["dell xps", "xps"]),
    ("When do I want the MVP shipped?", ["friday"]),
    ("Which ORM do I prefer?", ["async sqlalchemy", "sqlalchemy"]),
    ("What do I want before a merge?", ["tests"]),
    ("Which identity provider do we use?", ["azure ad", "azure"]),
    ("How do I prefer payments confirmed?", ["webhook"]),
    ("Which payment provider did I choose?", ["stripe"]),
]


def bundle_corpus() -> str:
    bundle = load_okf_bundle(OKF_DIR)
    return "\n".join(
        (m.get("body") or m.get("content") or m.get("title") or "")
        for m in bundle.get("memories", [])
    )


def llm_recall() -> tuple[int, int] | None:
    """Ask a local DeepSeek to score whether each answer is recallable."""
    corpus = bundle_corpus()
    try:
        prompt = (
            "You are a memory-recall judge. Below is the entire memory store of "
            "an agent after a migration. For each (QUESTION, EXPECTED_FACT) pair, "
            "answer YES if the store lets you recover the fact, else NO. "
            "Reply only with YES or NO, one per line.\n\n"
            f"--- MEMORY STORE ---\n{corpus}\n--- END ---\n\n"
            + "\n".join(f"Q: {q} | FACT: {', '.join(t)}" for q, t in GOLDEN_QA)
        )
        body = json.dumps(
            {
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            }
        ).encode()
        req = urllib.request.Request(
            DEEPSEEK_URL, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        verdicts = (data["choices"][0]["message"]["content"] or "").strip().splitlines()
        yes = sum(1 for v in verdicts if v.strip().upper().startswith("YES"))
        return yes, len(GOLDEN_QA)
    except Exception:
        return None


def main() -> None:
    if not OKF_DIR.exists():
        print(
            "No OKF bundle found. Run: python3 scripts/run_migration.py --export-okf",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Baseline: what the RAW source archive already encodes (should be ~0-1 —
    # the whole point is the assistant's memory lives in agent-owned stores).
    # We fail closed here: a missing archive would silently empty source_corpus
    # and let a stale bundle pass parity, so require every input up front.
    source_terms = []
    missing = []
    for name in ("claude", "chatgpt"):
        path = DATA / f"{name}_conversations.json"
        if path.exists():
            source_terms.append(path.read_text().lower())
        else:
            missing.append(path)
    if missing:
        print(f"Missing source archives: {[str(m) for m in missing]}", file=sys.stderr)
        raise SystemExit(1)
    source_corpus = "\n".join(source_terms)

    def _recall(corpus: str) -> tuple[int, int]:
        blob = corpus.lower()
        return (
            sum(1 for _q, terms in GOLDEN_QA if any(t in blob for t in terms)),
            len(GOLDEN_QA),
        )

    print("=" * 60)
    print("ROUND-TRIP RECALL PARITY (golden Q&A set)")
    print("=" * 60)
    raw = _recall(source_corpus)
    bundle = _recall(bundle_corpus())
    print(
        f"Before migration (raw source archive): {raw[0]}/{raw[1]} "
        f"({100 * raw[0] // max(raw[1], 1)}%)"
    )
    print(
        f"After migration  (OKF bundle):        {bundle[0]}/{bundle[1]} "
        f"({100 * bundle[0] // max(bundle[1], 1)}%)"
    )

    judge = llm_recall()
    if judge:
        print(
            f"LLM-as-judge recall (local DeepSeek):  {judge[0]}/{judge[1]} "
            f"({100 * judge[0] // max(judge[1], 1)}%)"
        )
    else:
        print(
            "LLM-as-judge: local DeepSeek not reachable — using keyword recall "
            "(deterministic, honest)."
        )

    parity = bundle[0] >= raw[0] and bundle[0] == bundle[1]
    if parity:
        print(
            "\nResult: PASS — no amnesia; the migrated bundle retains every "
            "golden fact."
        )
    else:
        print(
            "\nResult: FAIL — the migrated bundle lost a golden fact.", file=sys.stderr
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
