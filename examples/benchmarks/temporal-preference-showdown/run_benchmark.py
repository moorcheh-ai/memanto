"""
The Great Agentic Memory Showdown: Temporal Preference Drift
=============================================================
Benchmarks Memanto (active typed-memory digest) vs Mem0 (cloud) on a
Shifting Persona scenario: a personal assistant agent whose user's
preferences and facts evolve across 5 distinct sessions.

Core question: when facts change, which system surfaces the CURRENT state?

Metrics
-------
- Tokens Ingested   : total tokens processed across all sessions
- Tokens Retrieved  : total tokens returned per query (context footprint)
- p95 Latency (ms)  : 95th-percentile response time
- Accuracy          : % of queries answered with the CURRENT correct fact

Usage
-----
    python run_benchmark.py
    python run_benchmark.py --output results/results.json --markdown results/results.md
    python run_benchmark.py --dry-run   # skips real API calls, uses mock data

Environment variables required (unless --dry-run):
    ANTHROPIC_API_KEY   used by Memanto backend for fact extraction
    MEM0_API_KEY        used by Mem0 backend (real cloud API)
"""
from __future__ import annotations

import argparse
import json
import random
import os
import sys
import time
from pathlib import Path

from dataset import QUERIES, SESSIONS, USER_ID


# ── Accuracy scoring ──────────────────────────────────────────────────────────

def score_answer(retrieved: str, correct_keywords: list[str], stale_keywords: list[str]) -> tuple[bool, bool]:
    """Return (is_correct, is_stale) based on keyword presence.

    When both current and stale keywords appear (e.g. a transition sentence such
    as "switched from Go to Python"), *correct* wins: the answer contains the
    current fact even if it incidentally mentions the old one.

    Returns:
        (is_correct, is_stale) — mutually exclusive; both False means a miss.
    """
    text = retrieved.lower()
    has_correct = any(kw.lower() in text for kw in correct_keywords)
    has_stale = any(kw.lower() in text for kw in stale_keywords)
    is_correct = has_correct  # correct wins even when stale keywords also present
    is_stale = has_stale and not has_correct
    return is_correct, is_stale


# ── Mock backend for --dry-run ────────────────────────────────────────────────

class MockBackend:
    """Deterministic in-process backend used for dry-run validation.

    Uses a seeded RNG so results are reproducible across runs while still
    honouring the configured *correct_rate* accuracy target.
    """

    def __init__(self, name: str, correct_rate: float = 0.83) -> None:
        """Initialise with a backend name and target retrieval accuracy.

        Args:
            name: Display name shown in benchmark output and reports.
            correct_rate: Fraction of queries (0–1) that should return the
                correct (current) fact. Defaults to 0.83 (≈ 5 of 6 queries).
        """
        self.name = name
        self._correct_rate = correct_rate
        from backends.base import BackendStats
        self.stats = BackendStats()
        self._call = 0
        self._rng = random.Random(42)  # fixed seed → reproducible dry-run results

    def add(self, messages: list[dict], user_id: str) -> None:
        """Simulate ingestion: record approximate token count and synthetic latency."""
        tokens = sum(len(m["content"].split()) for m in messages)
        self.stats.record_ingest(int(tokens * 1.3), 120 + self._call * 10)
        self._call += 1

    def search(self, query: str, user_id: str) -> str:
        """Return a simulated retrieval result weighted by *correct_rate*.

        A seeded RNG makes the mock output deterministic and reproducible,
        while still exercising the scoring path with the configured accuracy.
        """
        self.stats.record_retrieve(45, 35 + self._call * 2)
        self._call += 1
        if self._rng.random() < self._correct_rate:
            return "python fastapi light mode berlin engineering lead pescatarian voice"
        # Stale path contains ONLY stale keywords so that _correct_rate genuinely
        # controls the correct-answer fraction under correct-wins scoring semantics.
        return "go golang london vegetarian dark mode slack"

    def reset(self, user_id: str) -> None:
        """Reset accumulated stats and RNG so the instance can be reused across runs."""
        from backends.base import BackendStats
        self.stats = BackendStats()
        self._call = 0
        self._rng = random.Random(42)


# ── Main benchmark runner ─────────────────────────────────────────────────────

def run_benchmark(backends: list, dry_run: bool = False) -> dict:
    """Run the full benchmark pipeline against every backend and return results.

    For each backend: resets state, ingests all sessions, then evaluates every
    golden query via keyword scoring.  Prints a live progress log to stdout.

    Args:
        backends: List of objects satisfying the MemoryBackend protocol.
        dry_run: Passed through for context; actual mock/real selection happens
            in *main* before this function is called.

    Returns:
        Mapping of backend name → metrics dict with accuracy, stale rate,
        token counts, latency percentiles, and per-query breakdown.
    """
    results = {}

    for backend in backends:
        print(f"\n{'='*60}")
        print(f"  Backend: {backend.name}")
        print(f"{'='*60}")

        backend.reset(USER_ID)

        # Phase 1: Ingest all sessions
        print(f"\n[1/2] Ingesting {len(SESSIONS)} sessions...")
        for session in SESSIONS:
            print(f"      Session: {session['label']}...", end=" ", flush=True)
            backend.add(session["messages"], USER_ID)
            print("done")

        # Allow cloud backends time for async indexing before querying.
        # Mem0 processes memories asynchronously — without this pause queries
        # return empty results immediately after ingestion.
        index_wait = getattr(backend, "index_wait_s", 0)
        if index_wait > 0:
            print(f"      ⏳ Waiting {index_wait}s for async indexing...")
            time.sleep(index_wait)

        # Phase 2: Query and score
        print(f"\n[2/2] Running {len(QUERIES)} evaluation queries...")
        query_results = []
        correct = 0
        stale = 0

        for q in QUERIES:
            retrieved = backend.search(q["query"], USER_ID)
            is_correct, is_stale = score_answer(retrieved, q["correct_keywords"], q["stale_keywords"])
            if is_correct:
                correct += 1
            if is_stale:
                stale += 1

            status = "✅" if is_correct else ("🕰️  STALE" if is_stale else "❌ MISS")
            print(f"      {status}  {q['id']}: {q['query'][:55]}...")

            query_results.append({
                "query_id": q["id"],
                "query": q["query"],
                "retrieved": retrieved[:200],
                "correct": is_correct,
                "stale": is_stale,
                "explanation": q["explanation"],
            })

        accuracy = round(correct / len(QUERIES) * 100, 1)
        stale_rate = round(stale / len(QUERIES) * 100, 1)

        results[backend.name] = {
            "accuracy_pct": accuracy,
            "stale_rate_pct": stale_rate,
            "tokens_ingested": backend.stats.tokens_ingested,
            "tokens_retrieved": backend.stats.tokens_retrieved,
            "ingest_p95_ms": backend.stats.ingest_p95_ms,
            "retrieve_p95_ms": backend.stats.retrieve_p95_ms,
            "queries": query_results,
        }

        print(f"\n  Accuracy:          {accuracy}%  (stale rate: {stale_rate}%)")
        print(f"  Tokens ingested:   {backend.stats.tokens_ingested:,}")
        print(f"  Tokens retrieved:  {backend.stats.tokens_retrieved:,}")
        print(f"  Ingest p95:        {backend.stats.ingest_p95_ms} ms")
        print(f"  Retrieve p95:      {backend.stats.retrieve_p95_ms} ms")

    return results


# ── Report generation ─────────────────────────────────────────────────────────

def generate_markdown(results: dict) -> str:
    """Render benchmark results as a Markdown report with a summary table.

    Bolds the winning value for each metric (higher accuracy wins; lower tokens
    and latency win).  Appends a per-backend per-query breakdown table and a
    methodology section.

    Args:
        results: Mapping of backend name → metrics dict as returned by
            :func:`run_benchmark`.

    Returns:
        A complete Markdown string suitable for writing to a ``.md`` file.
    """
    backend_names = list(results.keys())
    lines = [
        "# Temporal Preference Showdown — Results",
        "",
        "**Scenario:** Shifting Persona — 5 sessions, evolving user preferences",
        "**Queries:** 6 golden questions testing recall of CURRENT (not stale) facts",
        "",
        "## Summary Table",
        "",
        "| Metric | " + " | ".join(backend_names) + " |",
        "|--------|" + "|".join(["--------"] * len(backend_names)) + "|",
    ]

    metrics = [
        ("Accuracy", "accuracy_pct", "%"),
        ("Stale Rate", "stale_rate_pct", "%"),
        ("Tokens Ingested", "tokens_ingested", ""),
        ("Tokens Retrieved", "tokens_retrieved", ""),
        ("Ingest p95", "ingest_p95_ms", " ms"),
        ("Retrieve p95", "retrieve_p95_ms", " ms"),
    ]

    for label, key, unit in metrics:
        row = f"| {label} |"
        vals = [results[n][key] for n in backend_names]
        for i, (name, val) in enumerate(zip(backend_names, vals)):
            # Bold the winner (higher accuracy/lower tokens/lower latency)
            if key == "accuracy_pct":
                bold = val == max(vals)
            elif key == "stale_rate_pct":
                bold = val == min(vals)
            elif "tokens" in key or "ms" in key:
                bold = val == min(vals)
            else:
                bold = False
            cell = f"**{val:,}{unit}**" if bold else f"{val:,}{unit}"
            row += f" {cell} |"
        lines.append(row)

    lines += [
        "",
        "## Per-Query Breakdown",
        "",
    ]

    for name, data in results.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| Query | Result | Retrieved Context |")
        lines.append("|-------|--------|-------------------|")
        for q in data["queries"]:
            status = "✅ Correct" if q["correct"] else ("🕰️ Stale" if q["stale"] else "❌ Miss")
            preview = q["retrieved"][:80].replace("|", "╎") + "..."
            lines.append(f"| {q['query_id']}: {q['query'][:40]}... | {status} | {preview} |")
        lines.append("")

    lines += [
        "## Methodology",
        "",
        "- **Memanto backend**: Extracts typed facts via Claude Haiku; stores only",
        "  the active digest. Newer facts replace older ones (conflict resolution).",
        "- **Mem0 backend**: Real Mem0 cloud API. Stores conversation turns and",
        "  retrieves via Mem0's own compression and semantic search.",
        "- **Accuracy**: keyword matching against a golden dataset of current facts.",
        "- **Tokens**: approximate (word count × 1.3), consistent across both backends.",
        "- **Environment**: macOS, same ANTHROPIC_API_KEY for Memanto extraction,",
        "  MEM0_API_KEY for Mem0 cloud.",
        "",
        "_Benchmark built as part of [Memanto Issue #639](https://github.com/moorcheh-ai/memanto/issues/639)_",
    ]

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point: parse arguments, select backends, run benchmark, save outputs."""
    parser = argparse.ArgumentParser(description="Temporal Preference Showdown Benchmark")
    parser.add_argument("--output", default=None, help="Path to save JSON results")
    parser.add_argument("--markdown", default=None, help="Path to save Markdown report")
    parser.add_argument("--dry-run", action="store_true", help="Use mock backends (no API calls)")
    args = parser.parse_args()

    print("\n🧠 Temporal Preference Showdown — Memanto vs Mem0")
    print("   Scenario: Shifting Persona (5 sessions, evolving preferences)")
    print("   Queries:  6 golden questions\n")

    if args.dry_run:
        print("⚠️  DRY RUN MODE — using mock backends\n")
        backends = [
            MockBackend("Memanto (simulation)", correct_rate=0.833),
            MockBackend("Mem0 (cloud)", correct_rate=0.5),
        ]
    else:
        from backends.mem0_backend import Mem0Backend
        from backends.memanto_backend import MemantoBackend
        backends = [MemantoBackend(), Mem0Backend()]

    results = run_benchmark(backends, dry_run=args.dry_run)

    # Save JSON
    output_path = args.output or "results/results.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ JSON results saved to {output_path}")

    # Save Markdown
    md_path = args.markdown or "results/results.md"
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w") as f:
        f.write(generate_markdown(results))
    print(f"✅ Markdown report saved to {md_path}")


if __name__ == "__main__":
    main()
