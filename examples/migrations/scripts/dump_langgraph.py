"""
Dump LangGraph InMemoryStore to a JSON file for use with `memanto migrate langgraph`.

Usage:
    python scripts/dump_langgraph.py --output dump.json

Reads from an in-memory store seeded with sample data when run standalone.
For a real Postgres-backed store, set LANGGRAPH_POSTGRES_URI and the script
will connect to it instead.

Exit 1 when LANGGRAPH_POSTGRES_URI is set but invalid (connection fails).
"""

import argparse
import asyncio
import json
import os
import sys


def _get_store():
    """
    Create the configured LangGraph store.
    
    Returns:
        tuple: The store instance and a boolean indicating whether Postgres mode is enabled.
    
    Raises:
        SystemExit: If the Postgres dependency is unavailable or the configured store cannot be initialized.
    """
    uri = os.environ.get("LANGGRAPH_POSTGRES_URI")
    if uri:
        try:
            from langgraph.store.postgres import AsyncPostgresStore
            return AsyncPostgresStore.from_conn_string(uri), True
        except ImportError:
            print("langgraph[postgres] not installed. Run: pip install 'langgraph[postgres]'", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Failed to initialize Postgres store: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        from langgraph.store.memory import InMemoryStore
        return InMemoryStore(), False


async def _dump(store, postgres: bool) -> list[dict]:
    """
    Export all items from a LangGraph store.
    
    Parameters:
    	store: Store providing namespace listing and item search operations.
    	postgres (bool): Whether the store uses the Postgres backend.
    
    Returns:
    	list[dict]: Exported items with namespace, key, value, and timestamp fields.
    """
    items = []
    seen: set[tuple] = set()
    ns_list: list = []
    offset = 0
    limit = 100
    while True:
        try:
            batch = await store.alist_namespaces(limit=limit, offset=offset)
        except TypeError:
            batch = await store.alist_namespaces()
            ns_list.extend(batch)
            break
        if not batch:
            break
        ns_list.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    for ns in ns_list:
        offset = 0
        limit = 100
        while True:
            try:
                results = await store.asearch(ns, limit=limit, offset=offset)
                paginated = True
            except TypeError:
                results = await store.asearch(ns)
                paginated = False
            if not results:
                break
            for item in results:
                key = (tuple(item.namespace), item.key)
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "namespace": list(item.namespace),
                    "key": item.key,
                    "value": item.value,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                })
            if not paginated or len(results) < limit:
                break
            offset += limit
    return items


async def _seed_demo(store) -> None:
    """
    Populate the store with sample user and project entries for export demonstrations.
    
    Parameters:
    	store: Storage backend that accepts asynchronous item insertion.
    """
    await store.aput(("user", "alice", "memories"), "pref-editor", {"content": "Alice uses VSCode with dark mode as her primary editor."})
    await store.aput(("user", "alice", "memories"), "pref-lang", {"content": "Alice prefers Python and FastAPI over JavaScript."})
    await store.aput(("user", "alice", "facts"), "location", {"content": "Alice is based in Berlin, Germany."})
    await store.aput(("project", "example-project"), "goal-1", {"content": "Build an open-source agentic memory layer.", "priority": "high"})


async def main(output: str) -> None:
    """
    Export store contents to a JSON file.
    
    Parameters:
        output (str): Path to the output JSON file.
    """
    store, postgres = _get_store()

    if not postgres:
        print("No LANGGRAPH_POSTGRES_URI set — using InMemoryStore with demo data.", file=sys.stderr)
        await _seed_demo(store)
        items = await _dump(store, postgres)
    else:
        try:
            async with store as s:
                try:
                    await s.setup()
                except Exception as e:
                    print(f"Failed to set up Postgres store: {e}", file=sys.stderr)
                    sys.exit(1)
                items = await _dump(s, postgres)
        except Exception as e:
            print(f"Failed to connect to Postgres store: {e}", file=sys.stderr)
            sys.exit(1)

    export = {"items": items}
    with open(output, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    print(f"Exported {len(items)} items to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dump LangGraph store to JSON")
    parser.add_argument("--output", default="langgraph_dump.json", help="Output file path")
    args = parser.parse_args()
    asyncio.run(main(args.output))
