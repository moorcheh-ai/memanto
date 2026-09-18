#!/usr/bin/env python3
"""
Connect to a running ChromaDB instance and migrate a collection into Memanto.

Requires:
    CHROMA_COLLECTION env var  — collection name to migrate
    chromadb package           — pip install chromadb

Optional:
    CHROMA_HOST env var        — ChromaDB host (default: localhost)
    CHROMA_PORT env var        — ChromaDB port (default: 8000)

Run:
    python scripts/migrate_chroma.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_HERE, _MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)


def _fetch_chroma_collection(collection: str, host: str, port: int) -> dict | None:
    try:
        import chromadb
    except ImportError:
        print("chromadb is required: pip install chromadb", file=sys.stderr)
        return None

    try:
        client = chromadb.HttpClient(host=host, port=port)
        col = client.get_collection(collection)
        result = col.get(include=["documents", "metadatas"])
    except Exception as exc:
        print(f"ChromaDB error: {exc}", file=sys.stderr)
        return None

    memories = []
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    for i, doc_id in enumerate(ids):
        doc = documents[i] if i < len(documents) else ""
        meta = metadatas[i] if i < len(metadatas) else {}
        if doc:
            memories.append({"id": doc_id, "document": doc, "metadata": meta or {}})

    return {"memories": memories}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a Chroma collection to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--collection", default=None, help="Collection name (overrides CHROMA_COLLECTION)")
    parser.add_argument("--host", default=None, help="ChromaDB host (overrides CHROMA_HOST)")
    parser.add_argument("--port", default=None, type=int, help="ChromaDB port (overrides CHROMA_PORT)")
    args = parser.parse_args()

    collection = args.collection or os.environ.get("CHROMA_COLLECTION", "")
    if not collection:
        print("CHROMA_COLLECTION is not set. Export it or pass --collection.", file=sys.stderr)
        return 1

    host = args.host or os.environ.get("CHROMA_HOST", "localhost")
    port = args.port or int(os.environ.get("CHROMA_PORT", "8000"))

    from _shared import print_summary, require_agent
    from runner import run_migration

    print(f"Fetching collection '{collection}' from {host}:{port}...")
    export = _fetch_chroma_collection(collection, host, port)
    if export is None:
        return 1
    if not export["memories"]:
        print("No documents found in collection.", file=sys.stderr)
        return 1

    if not args.dry_run:
        agent = require_agent(args.agent, "migrate_chroma.py")
        if agent is None:
            return 1
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            print("MOORCHEH_API_KEY is not set.", file=sys.stderr)
            return 1
        from memanto.cli.client.sdk_client import SdkClient
        client = SdkClient(api_key=api_key)
        client.activate_agent(agent, duration_hours=2)
    else:
        agent = args.agent
        client = None

    try:
        summary, _ = run_migration(
            provider="chroma",
            export=export,
            client=client,
            agent_id=agent or "",
            dry_run=args.dry_run,
            on_progress=lambda msg: print(f"  {msg}"),
        )
    finally:
        if client is not None:
            client.deactivate_agent(agent)

    print_summary(summary, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
