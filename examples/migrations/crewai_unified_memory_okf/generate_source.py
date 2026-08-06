#!/usr/bin/env python3
"""Generate a real CrewAI unified-memory LanceDB store without paid APIs.

The script calls CrewAI's public ``Memory.remember`` and ``Memory.recall``
APIs.  A deterministic local embedding function keeps the run reproducible
and avoids sending the sample's memory content to an external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

EMBEDDING_DIMENSIONS = 384


def deterministic_embedder(texts: list[str]) -> list[list[float]]:
    """Create stable token-hash embeddings suitable for an offline demo."""

    embeddings: list[list[float]] = []
    for text in texts:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        embeddings.append([value / norm for value in vector])
    return embeddings


SOURCE_MEMORIES: tuple[dict[str, Any], ...] = (
    {
        "key": "database-decision-old",
        "agent_role": "Platform Architect",
        "content": (
            "The Aurora pilot originally selected SQLite for the order ledger "
            "because the prototype ran on one node."
        ),
        "scope": "/decisions/platform",
        "categories": ["decision", "database", "superseded"],
        "importance": 0.45,
        "source": "platform_architect",
        "metadata": {
            "title": "Original SQLite decision",
            "memory_type": "decision",
            "lifecycle_status": "superseded",
            "superseded_by": "database-decision-current",
            "task": "Choose the pilot order-ledger database",
        },
    },
    {
        "key": "database-decision-current",
        "agent_role": "Platform Architect",
        "content": (
            "The Aurora order ledger must use PostgreSQL 16, replacing SQLite, "
            "because concurrent writers and point-in-time recovery are required."
        ),
        "scope": "/decisions/platform",
        "categories": ["decision", "database", "current"],
        "importance": 0.96,
        "source": "platform_architect",
        "metadata": {
            "title": "PostgreSQL 16 is the current ledger decision",
            "memory_type": "decision",
            "lifecycle_status": "active",
            "supersedes": "database-decision-old",
            "task": "Re-evaluate the ledger after the concurrency review",
        },
    },
    {
        "key": "privacy-instruction",
        "agent_role": "Security Auditor",
        "content": (
            "Never persist raw customer email addresses in analytics events; "
            "store a salted irreversible hash and keep the salt in the secret manager."
        ),
        "scope": "/instructions/security",
        "categories": ["instruction", "privacy", "pii"],
        "importance": 1.0,
        "source": "security_auditor",
        "metadata": {
            "title": "Analytics email privacy rule",
            "memory_type": "instruction",
            "policy": "SEC-14",
            "task": "Review analytics event collection",
        },
    },
    {
        "key": "stakeholder-preference",
        "agent_role": "Product Researcher",
        "content": (
            "The pilot sponsor prefers concise evidence tables with raw numbers "
            "and confidence bounds; avoid hype and decorative dashboards."
        ),
        "scope": "/preferences/stakeholders",
        "categories": ["preference", "reporting", "stakeholder"],
        "importance": 0.84,
        "source": "product_researcher",
        "metadata": {
            "title": "Sponsor reporting preference",
            "memory_type": "preference",
            "stakeholder": "pilot-sponsor",
            "task": "Synthesize the discovery interviews",
        },
    },
    {
        "key": "incident-learning",
        "agent_role": "Reliability Engineer",
        "content": (
            "Invoice retry incident AUR-218 duplicated three invoices because the "
            "worker retried after a timeout without an idempotency key."
        ),
        "scope": "/errors/billing",
        "categories": ["error", "incident", "billing"],
        "importance": 0.94,
        "source": "reliability_engineer",
        "metadata": {
            "title": "AUR-218 duplicate invoice root cause",
            "memory_type": "error",
            "incident_id": "AUR-218",
            "affected_records": 3,
            "task": "Complete the invoice incident review",
        },
    },
    {
        "key": "incident-remediation",
        "agent_role": "Reliability Engineer",
        "content": (
            "All invoice creation calls now require the event UUID as an "
            "idempotency key, and the database enforces a unique constraint on it."
        ),
        "scope": "/learnings/billing",
        "categories": ["learning", "remediation", "billing"],
        "importance": 0.93,
        "source": "reliability_engineer",
        "metadata": {
            "title": "AUR-218 idempotency remediation",
            "memory_type": "learning",
            "incident_id": "AUR-218",
            "task": "Prevent recurrence of duplicate invoices",
        },
    },
    {
        "key": "pilot-goal",
        "agent_role": "Delivery Manager",
        "content": (
            "Ship the Aurora EU pilot by 2026-08-28 with checkout p95 below "
            "350 milliseconds and zero unresolved severity-one defects."
        ),
        "scope": "/goals/delivery",
        "categories": ["goal", "deadline", "slo"],
        "importance": 0.98,
        "source": "delivery_manager",
        "metadata": {
            "title": "Aurora EU pilot exit goal",
            "memory_type": "goal",
            "deadline": "2026-08-28",
            "checkout_p95_ms": 350,
            "task": "Define the pilot release gate",
        },
    },
    {
        "key": "ownership-relationship",
        "agent_role": "Delivery Manager",
        "content": (
            "Maya owns the Aurora checkout workstream, and Rafael is the security "
            "approver required before the EU pilot can launch."
        ),
        "scope": "/relationships/aurora",
        "categories": ["relationship", "ownership", "approval"],
        "importance": 0.82,
        "source": "delivery_manager",
        "metadata": {
            "title": "Aurora checkout ownership",
            "memory_type": "relationship",
            "owner": "Maya",
            "approver": "Rafael",
            "task": "Record workstream accountability",
        },
    },
)


GOLDEN_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "question": (
            "Which database was selected for concurrent writers and point-in-time "
            "recovery?"
        ),
        "expected_key": "database-decision-current",
    },
    {
        "question": "What is the analytics email privacy rule?",
        "expected_key": "privacy-instruction",
    },
    {
        "question": "What caused incident AUR-218 duplicate invoices?",
        "expected_key": "incident-learning",
    },
    {
        "question": "What idempotency remediation prevents duplicate invoices?",
        "expected_key": "incident-remediation",
    },
    {
        "question": "What is the Aurora EU pilot deadline and checkout p95 goal?",
        "expected_key": "pilot-goal",
    },
    {
        "question": "Who owns Aurora checkout and who approves security?",
        "expected_key": "ownership-relationship",
    },
)


def _safe_generated_target(path: Path) -> Path:
    target = path.resolve()
    forbidden = {
        Path(target.anchor).resolve(),
        Path.home().resolve(),
        Path.cwd().resolve(),
    }
    if target in forbidden or len(target.parts) < 3:
        raise ValueError(f"Refusing unsafe generated-data target: {target}")
    return target


def generate(
    database: Path, evidence_dir: Path, *, force: bool = False
) -> dict[str, Any]:
    """Populate and query a real CrewAI memory store."""

    database = _safe_generated_target(database)
    evidence_dir = _safe_generated_target(evidence_dir)
    for target in (database, evidence_dir):
        if target.exists():
            if not force:
                raise FileExistsError(
                    f"Generated target exists (use --force): {target}"
                )
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)

    from crewai.memory import Memory

    offline_llm = MagicMock(name="offline_llm_not_called")
    memory = Memory(
        storage=str(database),
        llm=offline_llm,
        embedder=deterministic_embedder,
        consolidation_threshold=1.0,
        exploration_budget=0,
    )
    ids_by_key: dict[str, str] = {}
    for item in SOURCE_MEMORIES:
        record = memory.remember(
            item["content"],
            scope=item["scope"],
            categories=item["categories"],
            metadata=item["metadata"],
            importance=item["importance"],
            source=item["source"],
            agent_role=item["agent_role"],
        )
        if record is None:
            raise RuntimeError(f"CrewAI did not persist {item['key']}")
        ids_by_key[item["key"]] = record.id

    records = memory.list_records(scope="/", limit=100)
    if len(records) != len(SOURCE_MEMORIES):
        raise RuntimeError(
            f"CrewAI stored {len(records)} records, expected {len(SOURCE_MEMORIES)}"
        )

    recall_results: list[dict[str, Any]] = []
    for item in GOLDEN_QUESTIONS:
        matches = memory.recall(item["question"], depth="shallow", limit=3)
        expected_id = ids_by_key[item["expected_key"]]
        rank = next(
            (
                index
                for index, match in enumerate(matches, start=1)
                if match.record.id == expected_id
            ),
            None,
        )
        recall_results.append(
            {
                "question": item["question"],
                "expected_key": item["expected_key"],
                "expected_id": expected_id,
                "expected_rank": rank,
                "top_ids": [match.record.id for match in matches],
                "top_contents": [match.record.content for match in matches],
            }
        )

    memory.close()
    if offline_llm.call.call_count:
        raise RuntimeError("Offline generation unexpectedly called an LLM")

    evidence_dir.mkdir(parents=True)
    evidence = {
        "source_tool": "CrewAI",
        "crewai_version": version("crewai"),
        "storage": "LanceDB unified memory",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "public_api_calls": ["Memory.remember", "Memory.list_records", "Memory.recall"],
        "external_llm_calls": 0,
        "embedding": {
            "provider": "deterministic local token hash",
            "dimensions": EMBEDDING_DIMENSIONS,
        },
        "record_count": len(records),
        "ids_by_key": ids_by_key,
        "golden_recall": recall_results,
    }
    (evidence_dir / "source-run.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"CrewAI {evidence['crewai_version']} source run: "
        f"{len(records)} real records, {len(recall_results)} recall queries, 0 LLM calls"
    )
    print(f"LanceDB: {database}")
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="LanceDB output directory")
    parser.add_argument("evidence_dir", type=Path, help="Evidence output directory")
    parser.add_argument(
        "--force", action="store_true", help="Replace generated outputs"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    generate(args.database, args.evidence_dir, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
