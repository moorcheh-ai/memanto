"""Populate a LangMem store from the scripted history in conversation.py.

The store is a real ``langgraph.store.memory.InMemoryStore`` and every write
goes through LangMem's own ``create_manage_memory_tool`` -- the same tool a
LangMem agent would call at runtime.

Two extraction backends:

* ``replay`` (default, offline, deterministic):
  Replays the ``MemoryOp`` list in ``conversation.py`` through the
  ``manage_memory`` tool. No LLM, no API key -- this is how the committed
  sample artifacts are produced, so they reproduce byte-for-byte.

* ``live`` (``--extract live``, needs an LLM key):
  Feeds the raw transcript to LangMem's ``create_memory_store_manager`` and
  lets the model extract/consolidate memories on its own. Requires
  ``OPENAI_API_KEY`` (or another provider) and an embedding model.

After writing, per-session dates from the transcript are stamped onto each
item's ``created_at``/``updated_at`` so the three-week timeline carries
through into the OKF export -- this is the one part of the source data that's
simulated rather than produced live, done transparently here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from langgraph.store.memory import InMemoryStore
from langmem import create_manage_memory_tool

from .conversation import SESSIONS, USER_ID, MemoryOp, raw_transcript


def _namespace() -> tuple[str, str]:
    return ("memories", USER_ID)


def _session_dt(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


def build_store_replay() -> InMemoryStore:
    """Populate a store by replaying the scripted tool operations."""
    store = InMemoryStore()
    ns = _namespace()
    tool = create_manage_memory_tool(namespace=ns, store=store)

    # Map our stable local refs -> the UUIDs LangMem assigns on create, so
    # later update/delete operations target the right memory.
    ref_to_id: dict[str, str] = {}
    # Track which session date each surviving memory should be stamped with.
    ref_to_date: dict[str, str] = {}

    for session in SESSIONS:
        for op in session.ops:
            _apply_op(tool, op, ref_to_id, ref_to_date, session.date)

    _stamp_dates(store, ns, ref_to_id, ref_to_date)
    return store


def _apply_op(
    tool,
    op: MemoryOp,
    ref_to_id: dict[str, str],
    ref_to_date: dict[str, str],
    session_date: str,
) -> None:
    if op.action == "create":
        result = tool.invoke({"content": op.content, "action": "create"})
        ref_to_id[op.ref] = _extract_id(result)
        ref_to_date[op.ref] = session_date
    elif op.action == "update":
        mem_id = ref_to_id.get(op.ref)
        if mem_id is None:
            raise KeyError(f"update before create for ref {op.ref!r}")
        tool.invoke({"content": op.content, "action": "update", "id": mem_id})
        # A correction refreshes the "last touched" date but keeps the memory.
        ref_to_date[op.ref] = session_date
    elif op.action == "delete":
        mem_id = ref_to_id.get(op.ref)
        if mem_id is None:
            raise KeyError(f"delete before create for ref {op.ref!r}")
        tool.invoke({"content": None, "action": "delete", "id": mem_id})
        ref_to_id.pop(op.ref, None)
        ref_to_date.pop(op.ref, None)
    else:  # pragma: no cover - guarded by the dataclass authoring
        raise ValueError(f"unknown action {op.action!r}")


def _extract_id(tool_result: str) -> str:
    """LangMem's manage_memory returns e.g. 'created memory <uuid>'."""
    return str(tool_result).strip().split()[-1]


def _stamp_dates(
    store: InMemoryStore,
    ns: tuple[str, str],
    ref_to_id: dict[str, str],
    ref_to_date: dict[str, str],
) -> None:
    """Backdate surviving items to their session date for temporal fidelity.

    ``store.search`` returns *copies*, so we write through the canonical Item
    objects held in the store's backing map. The access is defensive: if a
    future LangGraph release changes the internal shape, the dates simply stay
    at "now" rather than raising -- the migration itself is unaffected.
    """
    backing = getattr(store, "_data", None)
    if backing is None:  # pragma: no cover - defensive
        return
    ns_items = backing.get(ns, {})
    id_to_date = {ref_to_id[ref]: date for ref, date in ref_to_date.items()}
    for key, item in ns_items.items():
        date_str = id_to_date.get(key)
        if not date_str:
            continue
        stamp = _session_dt(date_str).isoformat()
        for attr in ("created_at", "updated_at"):
            try:
                setattr(item, attr, stamp)
            except (AttributeError, TypeError):  # pragma: no cover - defensive
                pass


def build_store_live(model: str) -> InMemoryStore:
    """Populate a store by letting an LLM extract memories from the transcript.

    Requires a provider key (e.g. ``OPENAI_API_KEY``) and an embeddings model.
    Same downstream pipeline, but the memories come from model extraction
    instead of the scripted replay.
    """
    from langmem import create_memory_store_manager

    store = InMemoryStore(
        index={"dims": 1536, "embed": "openai:text-embedding-3-small"}
    )
    manager = create_memory_store_manager(
        model,
        namespace=("memories", USER_ID),
        store=store,
    )
    # Feed the whole conversation; the manager extracts + consolidates.
    manager.invoke({"messages": [{"role": "user", "content": raw_transcript()}]})
    return store


def build_store(extract: str = "replay", model: str = "openai:gpt-4o-mini"):
    if extract == "replay":
        return build_store_replay()
    if extract == "live":
        return build_store_live(model)
    raise ValueError("extract must be 'replay' or 'live'")


def _summarize(store: InMemoryStore) -> None:
    items = store.search(_namespace())
    print(f"LangMem store populated: {len(items)} live memories under {_namespace()}")
    for it in sorted(items, key=lambda i: i.created_at or datetime.min):
        when = (it.created_at or "").isoformat()[:10] if it.created_at else "?"
        print(f"  [{when}] {it.value.get('content', '')[:70]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate a LangMem store.")
    parser.add_argument(
        "--extract",
        choices=["replay", "live"],
        default="replay",
        help="replay = deterministic offline tool replay; live = LLM extraction.",
    )
    parser.add_argument(
        "--model",
        default="openai:gpt-4o-mini",
        help="LLM for --extract live (provider:model).",
    )
    args = parser.parse_args()
    store = build_store(extract=args.extract, model=args.model)
    _summarize(store)


if __name__ == "__main__":
    main()
