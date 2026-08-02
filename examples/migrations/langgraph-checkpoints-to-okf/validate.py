"""Round-trip recall-parity validation (offline, deterministic).

For each golden probe question we check that the expected answer content is
retrievable BOTH from the source checkpoint memories AND from the emitted OKF
bundle. This proves the migration preserved answer-bearing content — i.e. the
agent does not come back with amnesia. (The live `memanto migrate okf` run
adds server-side semantic search on top; this step validates fidelity of the
artifact itself, no API keys needed.)
"""

from __future__ import annotations

import glob
import json
import os

from adapter import BUNDLE_DIR, SUMMARY_PATH, read_thread_memories

# (question, keywords that must ALL appear in at least one memory body)
PROBES: list[tuple[str, list[str]]] = [
    ("What is the user's name?", ["alex rivera"]),
    ("Which seat does the user prefer?", ["aisle"]),
    ("What is the user's home airport?", ["sfo"]),
    ("What is the user's hotel budget?", ["$250"]),
    ("What hotel style does the user prefer?", ["boutique"]),
    ("Is the user still vegetarian?", ["no longer vegetarian"]),
    ("What is the user's United loyalty number?", ["8842-1190"]),
    ("What fares must work trips use?", ["refundable"]),
    ("When are receipts due?", ["48 hours"]),
]


def _corpus_from_source() -> list[str]:
    texts: list[str] = []
    for data in read_thread_memories().values():
        texts.extend(m["text"] for m in data["memories"])
    return texts


def _corpus_from_bundle() -> list[str]:
    texts: list[str] = []
    for path in glob.glob(os.path.join(BUNDLE_DIR, "memories", "*.md")):
        with open(path, encoding="utf-8") as f:
            texts.append(f.read())
    return texts


def _hit(corpus: list[str], keywords: list[str]) -> bool:
    return any(all(k in doc.lower() for k in keywords) for doc in corpus)


def run() -> bool:
    source = _corpus_from_source()
    bundle = _corpus_from_bundle()
    print(f"Source memories: {len(source)} | OKF documents: {len(bundle)}\n")
    passed = 0
    for q, keywords in PROBES:
        s = _hit(source, keywords)
        b = _hit(bundle, keywords)
        ok = s and b
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {q}  (source={s}, okf={b})")
    parity = 100 * passed / len(PROBES)
    print(f"\nRecall parity: {passed}/{len(PROBES)} ({parity:.0f}%)")

    report = {"parity_pct": parity, "passed": passed, "total": len(PROBES)}
    with open(
        os.path.join(os.path.dirname(SUMMARY_PATH), "validation.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(report, f, indent=2)
    return passed == len(PROBES)


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
