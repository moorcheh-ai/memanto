#!/usr/bin/env python3
"""Generate a privacy-safe Holo SQLite fixture through Hermes' real MemoryStore API."""

from __future__ import annotations

import argparse
import importlib
import json
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_EPISODES = [
    (
        "Atlas",
        "portable knowledge migration",
        "OKF-first interchange",
        "avoid silently serializing derived vector indexes",
        "a two-stage verification gate",
        "retain the previous readable bundle until the replacement validates",
        "a fresh destination reproduced the canonical facts",
    ),
    (
        "Beacon",
        "offline incident handoff",
        "append-only Markdown evidence packets",
        "work without a network connection",
        "hash and schema validation before handoff",
        "preserve the last signed packet",
        "the next operator reproduced the incident state without hidden context",
    ),
    (
        "Cinder",
        "deterministic release packaging",
        "content-addressed artifact manifests",
        "never publish an artifact whose inputs are unknown",
        "manifest, archive, and checksum verification",
        "keep the previous release candidate available",
        "two clean-room rebuilds produced matching manifests",
    ),
    (
        "Drift",
        "agent context-budget control",
        "retrieval caps plus explicit relevance thresholds",
        "background memory must not dominate the active task",
        "token-count and relevance regression checks",
        "fall back to an empty optional context block",
        "median injected context dropped while golden recall remained stable",
    ),
    (
        "Harbor",
        "safe configuration migration",
        "versioned configuration with explicit defaults",
        "old configuration files must remain readable",
        "forward and backward fixture tests",
        "restore the pre-migration configuration file",
        "all supported fixtures loaded without implicit field loss",
    ),
    (
        "Kestrel",
        "contributor attribution tracking",
        "a per-change source and lineage ledger",
        "do not obscure prior contributors behind a squash of unrelated work",
        "diff-level provenance review",
        "split the unowned change from the candidate patch",
        "reviewers could identify the new delta and its prior art independently",
    ),
    (
        "Meridian",
        "cross-platform bundle portability",
        "normalized filenames with collision checks",
        "case-insensitive filesystems must not overwrite distinct records",
        "Linux and case-folded filename simulations",
        "emit a collision report instead of overwriting",
        "the same bundle inventory survived both filesystem models",
    ),
    (
        "Northstar",
        "acceptance-evidence automation",
        "machine-readable reports beside human-readable documentation",
        "a green narrative cannot replace a failing invariant",
        "structural, operational, and portability evidence",
        "stop publication when any required evidence layer fails",
        "release decisions became reproducible from committed evidence alone",
    ),
]

PREFERENCES = [
    "The operator prefers warm work lights after sunset.",
    "The operator prefers narrow pull requests with explicit attribution over kitchen-sink changes.",
    "The operator prefers reproducible one-command demos over screenshots without executable evidence.",
    "The operator prefers UTC timestamps in portable artifacts and local time only in presentation layers.",
    "The operator prefers deterministic fixtures over network-dependent fixtures for regression tests.",
    "The operator prefers explicit stop conditions when a bounty seam is already owned by another contributor.",
    "The operator prefers plain Markdown evidence that can be reviewed without a proprietary dashboard.",
    "The operator prefers a small public interface with complex migration logic hidden behind it.",
    "The operator prefers source-derived expected values over tests that recompute the implementation result.",
    "The operator prefers preserving raw source metadata whenever a semantic mapping is lossy.",
    "The operator prefers clean-room verification before calling a migration portable.",
    "The operator prefers privacy-scrubbed public fixtures rather than redacted copies of a live memory database.",
]

TOOL_FACTS = [
    "Hermes Holographic memory treats fact text and metadata as source truth, not HRR vectors.",
    "The local Holographic memory database stores retrieval and helpful feedback counters for each fact.",
    "Holographic entity associations are represented by fact_entities rather than a first-class relationship-edge table.",
    "Holographic contradiction detection is query-time behavior in the audited public schema, not a durable contradiction ledger.",
    "The Holographic full-text index is derived from canonical fact content and tags.",
    "Holographic HRR vectors can be rebuilt from canonical content and linked entities.",
    "Holographic memory-bank vectors are aggregate retrieval structures rather than independent source facts.",
    "Memanto OKF import accepts Markdown with YAML frontmatter and preserves memory content through the migration path.",
    "Memanto uses a fixed memory-type vocabulary while OKF permits free-form domain vocabulary.",
    "Unknown OKF fields should not be treated as a substitute for preserving source truth in a bounded readable form.",
    "A migration result is not accepted until a fresh destination passes the same recall probes.",
    "The final OKF bundle should remain human-inspectable plain Markdown after leaving Memanto.",
]


def _build_demo_facts() -> list[tuple[str, str, str]]:
    facts: list[tuple[str, str, str]] = []
    for (
        name,
        purpose,
        approach,
        constraint,
        verification,
        rollback,
        outcome,
    ) in PROJECT_EPISODES:
        tag = f"Project {name},project"
        facts.extend(
            [
                (
                    f"Project {name} exists to deliver {purpose}.",
                    "project",
                    f"{tag},purpose",
                ),
                (
                    f"Project {name} chose {approach} as its working approach.",
                    "project",
                    f"{tag},decision",
                ),
                (
                    f"Project {name} has this constraint: {constraint}.",
                    "project",
                    f"{tag},constraint",
                ),
                (
                    f"Project {name} uses {verification} before publication.",
                    "project",
                    f"{tag},verification",
                ),
                (
                    f"Project {name}'s rollback rule is to {rollback}.",
                    "project",
                    f"{tag},rollback",
                ),
                (
                    f"Project {name}'s latest verified outcome is that {outcome}.",
                    "project",
                    f"{tag},outcome",
                ),
            ]
        )
    facts.extend((text, "user_pref", "preference,operator") for text in PREFERENCES)
    facts.extend((text, "tool", "Hermes,Holographic,tool") for text in TOOL_FACTS)
    return facts


DEMO_FACTS = _build_demo_facts()


def _load_store(hermes_repo: Path):
    repo = hermes_repo.resolve()
    if not (repo / "plugins" / "memory" / "holographic" / "store.py").is_file():
        raise FileNotFoundError(
            "Hermes Holographic store.py not found under "
            f"{repo}/plugins/memory/holographic"
        )
    repo_text = str(repo)
    if repo_text not in sys.path:
        # Keep the repo importable for the lifetime of this process. Holo loads
        # some Hermes helpers lazily from MemoryStore.__init__ and later methods.
        sys.path.insert(0, repo_text)
    module = importlib.import_module("plugins.memory.holographic.store")
    return module.MemoryStore


def generate_demo_source(hermes_repo: Path, output: Path) -> dict[str, Any]:
    """Populate ``output`` using public Holo add/update/search/feedback operations."""
    MemoryStore = _load_store(hermes_repo)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    Path(f"{output}-wal").unlink(missing_ok=True)
    Path(f"{output}-shm").unlink(missing_ok=True)

    store = MemoryStore(db_path=output, default_trust=0.6)
    ids: list[int] = []
    try:
        for content, category, tags in DEMO_FACTS:
            ids.append(store.add_fact(content, category=category, tags=tags))

        # Evolve the corpus through the real source operations rather than
        # materializing a static database dump. Feedback is deliberately mixed.
        feedback_plan = [
            (0, True),
            (0, True),
            (5, False),
            (11, True),
            (23, True),
            (31, False),
            (47, True),
            (52, True),
            (63, True),
            (70, False),
        ]
        for index, helpful in feedback_plan:
            store.record_feedback(ids[index], helpful=helpful)

        atlas_verification_index = next(
            i
            for i, (content, _, _) in enumerate(DEMO_FACTS)
            if content.startswith("Project Atlas uses a two-stage verification gate")
        )
        store.update_fact(
            ids[atlas_verification_index],
            content=(
                "Project Atlas uses a three-stage verification gate before publication: "
                "structural, operational, and portability evidence."
            ),
            tags="Project Atlas,project,verification,portability",
        )

        # Retrieval is an operational source field in Holo. Exercise the public
        # search path so the public fixture carries genuine retrieval counters.
        probes = [
            "warm work lights",
            "Project Atlas verification",
            "Project Beacon incident handoff",
            "Project Drift context budget",
            "entity associations",
            "HRR vectors",
            "fresh destination recall",
            "portable Markdown",
        ]
        search = getattr(store, "search_facts", None)
        search_latencies_ms: list[float] = []
        search_runs = 0
        if callable(search):
            for query in probes:
                started = time.perf_counter()
                search(query, min_trust=0.0, limit=5)
                search_latencies_ms.append((time.perf_counter() - started) * 1000.0)
                search_runs += 1

        facts = store.list_facts(min_trust=0.0, limit=1000)
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    # Make the committed fixture self-contained even when Hermes used WAL.
    conn = sqlite3.connect(output)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        stored_count = int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
        entity_count = int(conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
        association_count = int(
            conn.execute("SELECT COUNT(*) FROM fact_entities").fetchone()[0]
        )
    finally:
        conn.close()

    try:
        hermes_commit = subprocess.run(
            ["git", "-C", str(hermes_repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        hermes_commit = None

    return {
        "source_tool": "Hermes Holographic MemoryStore",
        "hermes_commit": hermes_commit,
        "source_operations": {
            "add_fact": len(DEMO_FACTS),
            "record_feedback": 10,
            "update_fact": 1,
            "search_facts": search_runs,
        },
        "source_search_latency_ms": [round(v, 3) for v in search_latencies_ms],
        "source_search_latency_median_ms": (
            round(statistics.median(search_latencies_ms), 3)
            if search_latencies_ms
            else None
        ),
        "fact_count": len(facts),
        "stored_fact_count": stored_count,
        "entity_count": entity_count,
        "fact_entity_association_count": association_count,
        "sqlite_integrity_check": integrity,
        "database": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-repo", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("fixtures/memory_store.db"))
    parser.add_argument(
        "--report", type=Path, default=Path("reports/source-generation.json")
    )
    args = parser.parse_args()
    report = generate_demo_source(args.hermes_repo, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
