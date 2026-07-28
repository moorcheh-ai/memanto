"""Generate a real LangGraph checkpoint export for the OKF migration demo.

This script intentionally runs a tiny LangGraph workflow with MemorySaver
instead of hand-writing source records. The exported JSONL file is the source
artifact consumed by convert.py.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

THREAD_ID = "founder-ops-agent-demo"


class Memory(TypedDict):
    id: str
    type: str
    content: str
    confidence: float
    tags: list[str]
    evidence: str
    updated_at: str


class DemoState(TypedDict):
    messages: list[str]
    latest_turn: str
    memories: list[Memory]


STORY_TURNS = [
    {
        "at": "2026-07-01T09:00:00Z",
        "speaker": "Robin",
        "text": (
            "I prefer concise status updates with no more than three bullets. "
            "Please avoid shipping deploys after 18:00 UTC."
        ),
    },
    {
        "at": "2026-07-02T11:30:00Z",
        "speaker": "Robin",
        "text": (
            "The Alpha customer hates CSV uploads. Prioritize the Linear API "
            "importer before the spreadsheet fallback."
        ),
    },
    {
        "at": "2026-07-03T15:45:00Z",
        "speaker": "Robin",
        "text": (
            "Correction: deploys are safest on Tuesday mornings around 11:00 UTC "
            "when the support lead is online."
        ),
    },
    {
        "at": "2026-07-04T10:15:00Z",
        "speaker": "Robin",
        "text": (
            "Decision: keep the vendor lock-in escape demo focused on open "
            "markdown memory bundles, not a dashboard."
        ),
    },
    {
        "at": "2026-07-05T13:00:00Z",
        "speaker": "Robin",
        "text": (
            "I promised Nina the onboarding bugfix by Friday noon. If it slips, "
            "tell her before standup."
        ),
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(base_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _upsert(memory_rows: list[Memory], row: Memory) -> list[Memory]:
    kept = [existing for existing in memory_rows if existing["id"] != row["id"]]
    return kept + [row]


def extract_memories(state: DemoState) -> DemoState:
    """Deterministic node that extracts durable memories from the latest turn."""
    turn = state["latest_turn"]
    memories = list(state.get("memories", []))

    if "prefer concise status updates" in turn:
        memories = _upsert(
            memories,
            {
                "id": "pref-status-style",
                "type": "preference",
                "content": "Robin prefers concise status updates with at most three bullets.",
                "confidence": 0.96,
                "tags": ["communication", "status"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )
        memories = _upsert(
            memories,
            {
                "id": "deploy-window-avoid",
                "type": "instruction",
                "content": "Avoid shipping deploys after 18:00 UTC.",
                "confidence": 0.82,
                "tags": ["deploy", "superseded"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )

    if "Alpha customer hates CSV uploads" in turn:
        memories = _upsert(
            memories,
            {
                "id": "alpha-importer-priority",
                "type": "fact",
                "content": (
                    "The Alpha customer dislikes CSV uploads; prioritize the "
                    "Linear API importer before spreadsheet fallback."
                ),
                "confidence": 0.94,
                "tags": ["customer-alpha", "importer"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )

    if "deploys are safest on Tuesday mornings" in turn:
        memories = _upsert(
            memories,
            {
                "id": "deploy-window-avoid",
                "type": "instruction",
                "content": (
                    "Superseded deploy rule: the earlier blanket ban on deploys "
                    "after 18:00 UTC was replaced by the Tuesday morning rule."
                ),
                "confidence": 0.74,
                "tags": ["deploy", "superseded"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )
        memories = _upsert(
            memories,
            {
                "id": "deploy-window-best",
                "type": "preference",
                "content": (
                    "Deploys are safest on Tuesday mornings around 11:00 UTC "
                    "when the support lead is online."
                ),
                "confidence": 0.97,
                "tags": ["deploy", "schedule"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )

    if "Decision: keep the vendor lock-in escape demo" in turn:
        memories = _upsert(
            memories,
            {
                "id": "okf-demo-story-decision",
                "type": "decision",
                "content": (
                    "Keep the vendor lock-in escape demo focused on open markdown "
                    "memory bundles, not a dashboard."
                ),
                "confidence": 0.93,
                "tags": ["okf", "demo"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )

    if "promised Nina the onboarding bugfix" in turn:
        memories = _upsert(
            memories,
            {
                "id": "nina-onboarding-bugfix",
                "type": "commitment",
                "content": (
                    "Robin promised Nina the onboarding bugfix by Friday noon; "
                    "warn Nina before standup if it slips."
                ),
                "confidence": 0.95,
                "tags": ["onboarding", "nina", "deadline"],
                "evidence": turn,
                "updated_at": _now(),
            },
        )

    return {
        "messages": state["messages"],
        "latest_turn": turn,
        "memories": memories,
    }


def build_graph(checkpointer: MemorySaver):
    builder = StateGraph(DemoState)
    builder.add_node("extract_memories", extract_memories)
    builder.add_edge(START, "extract_memories")
    builder.add_edge("extract_memories", END)
    return builder.compile(checkpointer=checkpointer)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return value


def export_checkpoints(checkpointer: MemorySaver, output_path: Path) -> list[dict[str, Any]]:
    config = {"configurable": {"thread_id": THREAD_ID}}
    records = []
    for item in reversed(list(checkpointer.list(config))):
        cfg = item.config.get("configurable", {})
        parent_cfg = (item.parent_config or {}).get("configurable", {})
        checkpoint = item.checkpoint
        records.append(
            {
                "thread_id": cfg.get("thread_id", THREAD_ID),
                "checkpoint_ns": cfg.get("checkpoint_ns", ""),
                "checkpoint_id": cfg.get("checkpoint_id") or checkpoint.get("id"),
                "parent_checkpoint_id": parent_cfg.get("checkpoint_id"),
                "timestamp": checkpoint.get("ts"),
                "metadata": _jsonable(item.metadata),
                "channel_values": _jsonable(checkpoint.get("channel_values", {})),
                "pending_writes": _jsonable(item.pending_writes),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return records


def generate(base_dir: Path) -> dict[str, Any]:
    source_dir = base_dir / "data" / "source"
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)
    config = {"configurable": {"thread_id": THREAD_ID}}

    state: DemoState = {"messages": [], "latest_turn": "", "memories": []}
    for turn in STORY_TURNS:
        line = f"{turn['at']} {turn['speaker']}: {turn['text']}"
        state = {
            "messages": [*state["messages"], line],
            "latest_turn": line,
            "memories": state["memories"],
        }
        state = graph.invoke(state, config=config)

    checkpoint_path = source_dir / "langgraph_checkpoints.jsonl"
    records = export_checkpoints(checkpointer, checkpoint_path)
    transcript_path = source_dir / "source_transcript.json"
    transcript_path.write_text(
        json.dumps(STORY_TURNS, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "generated_at": _now(),
        "source": "actual LangGraph StateGraph run with MemorySaver checkpoints",
        "thread_id": THREAD_ID,
        "turn_count": len(STORY_TURNS),
        "checkpoint_count": len(records),
        "latest_memory_count": len(state["memories"]),
        "checkpoint_export": _rel(base_dir, checkpoint_path),
        "transcript": _rel(base_dir, transcript_path),
    }
    manifest_path = source_dir / "export-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    manifest = generate(args.base_dir.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
