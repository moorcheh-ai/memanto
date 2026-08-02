"""LangGraph checkpoint store -> OKF bundle migration adapter.

Reads a real LangGraph SqliteSaver checkpoint database using LangGraph's own
reader API and transforms every accumulated agent memory into a valid OKF
(Open Knowledge Format) bundle — plain markdown + YAML frontmatter — directly
consumable by Memanto's shipped tooling:

    memanto migrate okf out/okf-bundle

Mapping (LangGraph concept -> OKF field):
    thread_id                    -> resource, tags, extra.thread_id
    channel_values["memories"]   -> one OKF document per memory record
    record.kind                  -> type (OKF free-form) + x_memanto.type when
                                    it matches a Memanto memory type
    record.ts                    -> timestamp
    checkpoint id / step         -> extra.checkpoint_id / extra.step (+ body)
    record.rule                  -> extra.extraction_rule
    record.turn                  -> extra.turn

Everything Memanto's OKF loader doesn't have a schema slot for is preserved
losslessly as frontmatter "extra" fields — nothing is dropped.

Run:  python adapter.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
from seed_agent import DB_PATH

OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
BUNDLE_DIR = os.path.join(OUT_DIR, "okf-bundle")
SUMMARY_PATH = os.path.join(OUT_DIR, "migration_summary.json")

# source "kind" -> Memanto memory type (only when it exists in their schema;
# otherwise we omit x_memanto.type and let Memanto auto-classify).
KIND_TO_MEMANTO_TYPE = {
    "fact": "fact",
    "preference": "preference",
    "decision": "decision",
    "commitment": "commitment",
    "goal": "goal",
    "event": "event",
    "relationship": "relationship",
    "observation": "observation",
}


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "memory"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_thread_ids(db_path: str | None = None) -> list[str]:
    """Enumerate every thread persisted in the checkpoint store.

    The adapter must migrate ALL stored threads — not just the ones the demo
    seeder knows about — so thread IDs are discovered from the store itself.
    """
    db_path = db_path or DB_PATH  # resolved at call time, not def time
    if not os.path.exists(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()
    return sorted(r[0] for r in rows if r[0])


def read_thread_memories(thread_ids: list[str] | None = None) -> dict[str, dict]:
    """Read the latest checkpoint per thread via LangGraph's official API.

    Defaults to every thread discovered in the store; an explicit list may be
    passed to migrate a subset (validated against stored threads).
    """
    stored = discover_thread_ids()
    if thread_ids is None:
        thread_ids = stored
    else:
        unknown = [t for t in thread_ids if t not in stored]
        if unknown:
            raise ValueError(f"thread(s) not present in checkpoint store: {unknown}")

    result: dict[str, dict] = {}
    with SqliteSaver.from_conn_string(DB_PATH) as saver:
        for thread_id in thread_ids:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoints = list(saver.list(config))
            if not checkpoints:
                continue
            latest = max(checkpoints, key=lambda t: t.checkpoint.get("ts", ""))
            values = latest.checkpoint.get("channel_values", {})
            result[thread_id] = {
                "memories": values.get("memories", []),
                "checkpoint_id": latest.checkpoint.get("id"),
                "checkpoint_ts": latest.checkpoint.get("ts"),
                "step": (latest.metadata or {}).get("step"),
                "n_checkpoints": len(checkpoints),
            }
    return result


def memory_to_okf_doc(thread_id: str, mem: dict, prov: dict) -> str:
    """Render one memory record as an OKF markdown document."""
    kind = mem.get("kind", "fact")
    text = mem["text"].strip()
    memanto_type = KIND_TO_MEMANTO_TYPE.get(kind)

    frontmatter: dict = {
        "type": kind,  # OKF type is free-form domain vocabulary
        "title": text if len(text) <= 90 else text[:87] + "...",
        "description": (
            f"Agent memory migrated from a LangGraph SqliteSaver checkpoint "
            f"(thread '{thread_id}', turn {mem.get('turn')})."
        ),
        "resource": f"langgraph-checkpoint://{thread_id}",
        "tags": ["langgraph", "checkpoint-migration", thread_id, kind],
        "timestamp": mem.get("ts"),
        "x_memanto": {
            **({"type": memanto_type} if memanto_type else {}),
            "confidence": 0.85,
            "source": "langgraph-checkpoints",
        },
        # extras — preserved losslessly by memanto's OKF loader
        "thread_id": thread_id,
        "turn": mem.get("turn"),
        "checkpoint_id": prov.get("checkpoint_id"),
        "checkpoint_step": prov.get("step"),
        "extraction_rule": mem.get("rule"),
    }
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()

    body = f"""{text}

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `{thread_id}` · Turn: {mem.get("turn")} · Checkpoint: `{prov.get("checkpoint_id")}` (step {prov.get("step")})
- Extraction rule: `{mem.get("rule")}`
- Migrated: {_now()}

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
"""
    return f"---\n{fm}\n---\n\n{body}"


def run() -> dict:
    threads = read_thread_memories()
    memories_dir = os.path.join(BUNDLE_DIR, "memories")
    os.makedirs(memories_dir, exist_ok=True)

    # clean previous bundle contents for idempotent reruns
    for f in os.listdir(memories_dir):
        if f.endswith(".md"):
            os.remove(os.path.join(memories_dir, f))

    files: list[str] = []
    per_type: dict[str, int] = {}
    per_thread: dict[str, int] = {}
    idx = 0
    for thread_id, data in threads.items():
        for mem in data["memories"]:
            idx += 1
            doc = memory_to_okf_doc(thread_id, mem, data)
            fname = f"{idx:03d}-{_slug(mem['text'])}.md"
            with open(os.path.join(memories_dir, fname), "w", encoding="utf-8") as f:
                f.write(doc)
            files.append(fname)
            per_type[mem.get("kind", "fact")] = (
                per_type.get(mem.get("kind", "fact"), 0) + 1
            )
            per_thread[thread_id] = per_thread.get(thread_id, 0) + 1

    summary = {
        "generated_at": _now(),
        "source": "langgraph SqliteSaver checkpoints",
        "source_db": os.path.basename(DB_PATH),
        "threads": {
            t: {"checkpoint_id": d["checkpoint_id"], "checkpoints": d["n_checkpoints"]}
            for t, d in threads.items()
        },
        "total_memories": idx,
        "per_type": per_type,
        "per_thread": per_thread,
        "files": files,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Read {len(threads)} threads from {os.path.basename(DB_PATH)}")
    print(f"Wrote {idx} OKF documents -> {os.path.relpath(memories_dir)}")
    print(f"Per-type breakdown: {per_type}")
    print(f"Summary -> {os.path.relpath(SUMMARY_PATH)}")
    return summary


if __name__ == "__main__":
    run()
