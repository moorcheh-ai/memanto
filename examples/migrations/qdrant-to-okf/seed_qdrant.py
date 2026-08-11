"""
Seed a lived-in Qdrant memory collection.

Builds a realistic agent-memory store in an embedded (in-memory) Qdrant
instance: ~80 memories accumulated over 6 weeks — preferences, facts,
relationships, goals, decisions, events, commitments — stored the way real
memory backends do it:

- Mem0-on-Qdrant shape: ``text`` + ``metadata`` dict (created_at as ms
  epoch, memory_type, user/agent scope, score, hash)
- LangChain vectorstore shape: ``page_content`` + ``metadata``
- A few raw attribute payloads (no text key) to prove the fallback path

Run::

    python seed_qdrant.py            # prints the shared-state path
    python seed_qdrant.py --out export.json   # seed + immediate dump

The seeded store is ephemeral (in-memory) — the point is the *pipeline*:
seed -> export -> migrate -> OKF, all reproducible with zero infrastructure.
For a server-backed run: start Qdrant (``docker run -p 6333:6333 qdrant/qdrant``)
and use ``--url http://localhost:6333`` instead.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ImportError:  # pragma: no cover
    print("qdrant-client is required: pip install qdrant-client", file=sys.stderr)
    raise SystemExit(2)

# ---------------------------------------------------------------------------
# The lived-in memory corpus (as a real agent would accumulate it)
# ---------------------------------------------------------------------------

# (kind, text, memory_type, created_days_ago, tags)
_MEMORIES: list[tuple[str, str, str, int, list[str]]] = [
    ("pref", "Prefers deep work blocks before noon; meetings after 14:00 only.", "preference", 41, ["schedule"]),
    ("pref", "Strong preference for Python over TypeScript for backend services.", "preference", 39, ["language"]),
    ("pref", "Dislikes auto-generated commit messages — writes manual, detailed commit bodies.", "preference", 35, ["git"]),
    ("pref", "Prefers weekly planning on Monday mornings over daily standups.", "preference", 33, ["process"]),
    ("pref", "Wants test suites to fail loudly on missing AI answers rather than degrade silently.", "preference", 21, ["testing"]),
    ("pref", "Prefers Postgres over MySQL for new projects.", "preference", 18, ["database"]),
    ("pref", "Prefers RFC-style design docs before large refactors.", "preference", 14, ["process"]),
    ("pref", "Enjoys dark-mode UIs with purple accents.", "preference", 12, ["design"]),
    ("pref", "Avoids meetings on Fridays; uses them for deep work.", "preference", 9, ["schedule"]),
    ("pref", "Prefers small, focused PRs under 300 lines.", "preference", 6, ["code-review"]),
    ("pref", "Wants dependency upgrades reviewed separately from feature work.", "preference", 4, ["dependencies"]),
    ("pref", "Prefers async communication over real-time chat for non-urgent items.", "preference", 2, ["communication"]),
    ("pref", "Likes LLM output to be concise; hates corporate boilerplate.", "preference", 1, ["writing"]),
    ("fact", "Works at Moorcheh as a backend engineer on the memory platform.", "fact", 40, ["work"]),
    ("fact", "Team uses mem0 for long-term agent memory in production.", "fact", 38, ["work", "stack"]),
    ("fact", "The memory service stores embeddings in a Qdrant collection named 'memories'.", "fact", 37, ["work", "infra"]),
    ("fact", "Deploys to Kubernetes on AWS EKS.", "fact", 30, ["work", "infra"]),
    ("fact", "Uses VS Code with the Vim extension as the primary editor.", "fact", 28, ["tools"]),
    ("fact", "Runs a homelab with a NAS and two mini-PCs for self-hosted services.", "fact", 26, ["personal"]),
    ("fact", "Has a cat named Pixel.", "fact", 25, ["personal"]),
    ("fact", "Maintains an open-source memory migration tool used by ~2k developers.", "fact", 22, ["work", "oss"]),
    ("fact", "Lives in Lisbon, Portugal.", "fact", 20, ["personal"]),
    ("fact", "The OKF format is a Google Cloud spec for portable knowledge as markdown.", "fact", 19, ["work", "standards"]),
    ("fact", "Attends the Lisbon AI meetup monthly.", "fact", 15, ["personal", "events"]),
    ("fact", "Coffee order is a flat white with oat milk.", "fact", 11, ["personal"]),
    ("fact", "Team ships a nightly release train with a canary stage.", "fact", 8, ["work"]),
    ("fact", "The agent memory store hit 1M embeddings last quarter.", "fact", 5, ["work", "metrics"]),
    ("fact", "Uses Notion for personal notes and docs.", "fact", 3, ["tools"]),
    ("rel", "Works closely with Ana (ML engineer) on the retrieval pipeline.", "relationship", 36, ["work"]),
    ("rel", "Mentors a junior engineer named Rui on the migration tooling.", "relationship", 24, ["work"]),
    ("rel", "Reports to the CTO, Marta.", "relationship", 17, ["work"]),
    ("rel", "Collaborates with the design team lead, Sofia, on UX for the CLI.", "relationship", 10, ["work"]),
    ("rel", "Pixel the cat is 4 years old and answers to 'Pixel' only when food is involved.", "relationship", 7, ["personal"]),
    ("goal", "Migrate all legacy memory stores to OKF by end of quarter.", "goal", 34, ["work"]),
    ("goal", "Ship v2 of the migration CLI with dry-run previews.", "goal", 23, ["work"]),
    ("goal", "Publish the OKF adapter showcase to the community.", "goal", 16, ["work", "oss"]),
    ("goal", "Run a 10k in October.", "goal", 13, ["personal"]),
    ("goal", "Reduce p95 retrieval latency under 120ms.", "goal", 3, ["work", "metrics"]),
    ("goal", "Write monthly OSS blog posts documenting the migration journeys.", "goal", 1, ["work", "writing"]),
    ("event", "Sprint planning on Monday — Q3 memory roadmap.", "event", 31, ["work"]),
    ("event", "Lisbon AI meetup talk: 'Portable agent memory with OKF'.", "event", 15, ["events"]),
    ("event", "Team offsite in Porto next month.", "event", 12, ["work"]),
    ("event", "Migrated the analytics service to the new retrieval stack.", "event", 9, ["work"]),
    ("event", "Upgraded Qdrant to 1.12 across all environments.", "event", 7, ["work", "infra"]),
    ("event", "Gave a brown-bag on memory migration best practices.", "event", 5, ["work"]),
    ("decision", "Chose Qdrant over Pinecone for the embedding store (self-hosted, OSS).", "decision", 39, ["work", "infra"]),
    ("decision", "Adopted OKF as the canonical export format for all memory exports.", "decision", 33, ["work", "standards"]),
    ("decision", "Standardized on uv for Python dependency management.", "decision", 27, ["tools"]),
    ("decision", "Decided the migration CLI must never silently drop unmapped fields.", "decision", 20, ["work"]),
    ("decision", "Picked ruff + mypy as the lint/type gate.", "decision", 16, ["tools"]),
    ("decision", "Moved CI to GitHub Actions with a 5-min warm cache.", "decision", 8, ["work", "ci"]),
    ("commit", "Draft the OKF migration adapter PR by Friday.", "commitment", 6, ["work"]),
    ("commit", "Review Ana's retrieval pipeline PR before Wednesday.", "commitment", 5, ["work"]),
    ("commit", "Book flights for the Porto offsite.", "commitment", 4, ["personal"]),
    ("commit", "Fix the p95 latency regression in the recall service.", "commitment", 2, ["work"]),
    ("commit", "Record the demo video for the migration showcase.", "commitment", 1, ["work", "oss"]),
    ("obs", "Retrieval latency spiked after the 1.12 upgrade — likely cold segments.", "observation", 7, ["work", "metrics"]),
    ("obs", "Users of the migration CLI often ask for a Qdrant source adapter.", "observation", 6, ["work", "oss"]),
    ("obs", "Daily summaries are more useful when they include token savings numbers.", "observation", 4, ["work"]),
    ("obs", "The canary caught a regression in export timestamps last night.", "observation", 2, ["work"]),
    ("obs", "Community PRs for adapters tend to arrive in bursts after release notes.", "observation", 1, ["work", "oss"]),
]


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _mem0_payload(mem: tuple) -> dict:
    """The payload shape Mem0 persists into Qdrant (text + metadata)."""
    _, text, mem_type, days_ago, tags = mem
    created = int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp() * 1000)
    return {
        "text": text,
        "metadata": {
            "created_at": created,
            "memory_type": mem_type,
            "user_id": "tim@moorcheh.ai",
            "agent_id": "assistant-v1",
            "run_id": f"run-{random.randint(1000, 9999)}",
        },
        "score": round(random.uniform(0.55, 0.98), 3),
        "hash": _hash(text),
        "categories": tags,
    }


def _langchain_payload(mem: tuple) -> dict:
    """LangChain-on-Qdrant shape (page_content + metadata)."""
    _, text, mem_type, days_ago, tags = mem
    created = int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp())
    return {
        "page_content": text,
        "metadata": {
            "source": "agent-memory.log",
            "created_at": created,
            "type": mem_type,
            "tags": tags,
        },
    }


def _raw_payload(mem: tuple) -> dict:
    """No text key at all — forces the attribute-rendering fallback."""
    _, text, mem_type, days_ago, tags = mem
    created = int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp() * 1000)
    return {
        "note": text,
        "kind": mem_type,
        "created_at": created,
        "tags": tags,
    }


def _pseudo_vector(text: str, dim: int = 32) -> list[float]:
    """Deterministic pseudo-embedding so points carry real vectors."""
    seed = sum(ord(c) * (i + 7) for i, c in enumerate(text[:64])) % (2**31)
    rng = random.Random(seed)
    vec = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def seed(client: QdrantClient, collection: str = "memories") -> int:
    """Seed the collection; returns the number of points written."""
    if collection in [c.name for c in client.get_collections().collections]:
        client.delete_collection(collection)
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=32, distance=Distance.COSINE),
    )
    points: list[PointStruct] = []
    for idx, mem in enumerate(_MEMORIES):
        style = idx % 3
        if style == 0:
            payload = _mem0_payload(mem)
        elif style == 1:
            payload = _langchain_payload(mem)
        else:
            payload = _raw_payload(mem)
        points.append(
            PointStruct(
                id=idx + 1,
                vector=_pseudo_vector(mem[1]),
                payload=payload,
            )
        )
    client.upsert(collection_name=collection, points=points)
    return len(points)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="Qdrant server URL (default: embedded in-memory)")
    parser.add_argument("--collection", default="memories")
    parser.add_argument("--out", default=None, help="Also dump export JSON here")
    args = parser.parse_args(argv)

    client = QdrantClient(":memory:") if args.url is None else QdrantClient(url=args.url)
    n = seed(client, args.collection)
    print(f"Seeded {n} memories into Qdrant collection '{args.collection}'")

    if args.out:
        # Reuse the exporter with the shared in-memory client handle.
        from memanto.cli.analyze.qdrant_export import dump_collection
        from datetime import timezone as _tz

        memories = dump_collection(client, args.collection)
        export = {
            "provider": "qdrant",
            "collection": args.collection,
            "exported_at": datetime.now(_tz.utc).isoformat(),
            "memories": memories,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Dumped {len(memories)} memories -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
