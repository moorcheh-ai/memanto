"""
Move memories from a local backend (Moorcheh key or on-prem) to Memanto Cloud.

Used by ``memanto login`` ("Move memories") and ``memanto migrate to-cloud``.
For each local agent: create a Memanto Cloud agent (``<id>-local`` when the id is
taken), read its memories from the local store (active only, or also expired
ones when asked), and send them in batches of 100 with ``import: true`` so each
keeps its type, tags, confidence, provenance, source, ``created_at`` and, for an
expired memory, its expiry. Local data is never changed or deleted.

Progress is saved after every batch to ``~/.memanto/migrate/cloud-state.json``:

    {
      "version": 1,
      "source_backend": "on-prem",
      "agents": {
        "<local agent id>": {
          "cloud_agent_id": "<id on Memanto Cloud>",
          "moved_ids": ["<local memory id>", ...],
          "complete": true
        }
      }
    }

so an interrupted move picks up where it stopped without sending duplicates.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AuthorizationError,
    MemoryOperationError,
)

STATE_VERSION = 1
BATCH_SIZE = 100
CLASH_SUFFIX = "-local"

# Fields a Memanto Cloud import accepts per memory.
_IMPORT_FIELDS = ("type", "title", "confidence", "tags", "source", "provenance")


def state_path(config_dir: Path) -> Path:
    return config_dir / "migrate" / "cloud-state.json"


def load_state(path: Path) -> dict[str, Any]:
    """Saved progress, or an empty state when there is none."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": STATE_VERSION, "agents": {}}
    if not isinstance(data, dict) or not isinstance(data.get("agents"), dict):
        raise ValueError(f"Unreadable move progress file: {path}")
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def default_source(config_manager: Any) -> str | None:
    """The local backend to move from when none is named, or None.

    An unfinished move's source first, then the backend used before signing
    in to Memanto Cloud, then the current backend if it is a local one.
    """
    saved = load_state(state_path(config_manager.config_dir)).get("source_backend")
    for candidate in (
        saved,
        config_manager.get("previous_backend"),
        config_manager.get_backend().value,
    ):
        if candidate and candidate != "memanto-cloud":
            return str(candidate)
    return None


@contextmanager
def reading_from(source_backend: str) -> Iterator[None]:
    """Point this process's storage client at *source_backend* for the block.

    The local client follows the process-wide backend setting, which says
    memanto-cloud once signed in; moving reads from the old local store.
    """
    from memanto.app.clients.moorcheh import moorcheh_client
    from memanto.app.config import settings

    saved = settings.MEMANTO_BACKEND
    settings.MEMANTO_BACKEND = source_backend
    moorcheh_client.reset_client()
    try:
        yield
    finally:
        settings.MEMANTO_BACKEND = saved
        moorcheh_client.reset_client()


@dataclass
class AgentMove:
    """What happened to one local agent."""

    local_id: str
    cloud_id: str | None = None
    moved: int = 0
    already_moved: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (memory id, reason)


@dataclass
class MoveReport:
    agents: list[AgentMove] = field(default_factory=list)
    # Local agents with nothing to move in this store: no cloud agent created.
    # (The local agent registry is shared by all backends.)
    empty: list[str] = field(default_factory=list)
    # Expired memories left behind because only active ones were moved.
    expired_skipped: int = 0
    # Local agents not moved because the plan's agent limit was reached.
    not_moved: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def to_import_item(memory: dict[str, Any]) -> dict[str, Any] | None:
    """One local memory as a Memanto Cloud import item; None when it has no text."""
    content = (memory.get("content") or "").strip() or (
        memory.get("title") or ""
    ).strip()
    if not content:
        return None
    item: dict[str, Any] = {"content": content}
    for key in _IMPORT_FIELDS:
        value = memory.get(key)
        if value not in (None, "", []):
            item[key] = value
    if memory.get("created_at"):
        item["created_at"] = memory["created_at"]
    if memory.get("status") == "expired":
        item["status"] = "expired"
        for key in ("expired_at", "expired_by"):
            if memory.get(key):
                item[key] = memory[key]
    return item


def read_local_memories(local_client: Any, agent_id: str) -> list[dict[str, Any]]:
    """Every memory of a local agent, active and expired, oldest first (no session needed)."""
    result = local_client._get_read_service().search_recent(
        agent_id=agent_id, limit=None, status="all"
    )
    memories: list[dict[str, Any]] = list(result.get("results", []))
    memories.reverse()
    return memories


def _cloud_agent_id(local_id: str, taken: set[str]) -> str:
    if local_id not in taken:
        return local_id
    candidate = f"{local_id}{CLASH_SUFFIX}"
    n = 2
    while candidate in taken:
        candidate = f"{local_id}{CLASH_SUFFIX}-{n}"
        n += 1
    return candidate


def _is_plan_limit(error: Exception) -> bool:
    return isinstance(error, AuthorizationError) or "limit" in str(error).lower()


def move_to_cloud(
    local_client: Any,
    hosted_client: Any,
    state_file: Path,
    source_backend: str,
    on_progress: Callable[[str, int, int], None] | None = None,
    include_expired: bool = False,
) -> MoveReport:
    """Move every local agent's memories to Memanto Cloud; resumable.

    Args:
        local_client: ``SdkClient`` for the local backend (read only).
        hosted_client: ``HostedClient`` for Memanto Cloud.
        state_file: Progress file; reused when it belongs to the same source.
        source_backend: The local backend's config value, stored in the state.
        on_progress: Called as ``(local agent id, sent so far, total)`` when
            an agent starts and after each batch.
        include_expired: Also move expired memories (default: active only).

    Returns:
        What was moved, what failed, and agents left behind by the plan limit.
    """
    state = load_state(state_file)
    if state.get("source_backend") not in (None, source_backend):
        # Progress from moving another backend does not apply here.
        state = {"version": STATE_VERSION, "agents": {}}
    state["source_backend"] = source_backend

    local_ids = [a["agent_id"] for a in local_client.list_agents().get("agents", [])]
    taken = {a["agent_id"] for a in hosted_client.list_agents().get("agents", [])}
    report = MoveReport()

    for local_id in local_ids:
        memories = read_local_memories(local_client, local_id)
        if not include_expired:
            active = [m for m in memories if m.get("status") != "expired"]
            report.expired_skipped += len(memories) - len(active)
            memories = active
        entry = state["agents"].get(local_id)
        if entry is None:
            if not memories:
                report.empty.append(local_id)
                continue
            if report.stop_reason:
                # Agent limit reached: agents already on Cloud still finish.
                report.not_moved.append(local_id)
                continue
            cloud_id = _cloud_agent_id(local_id, taken)
            try:
                hosted_client.create_agent(cloud_id)
            except AgentAlreadyExistsError:
                pass  # Appeared since list_agents (e.g. created in the console).
            except (AuthorizationError, MemoryOperationError) as e:
                if not _is_plan_limit(e):
                    raise
                report.stop_reason = str(e)
                report.not_moved.append(local_id)
                continue
            taken.add(cloud_id)
            entry = {"cloud_agent_id": cloud_id, "moved_ids": [], "complete": False}
            state["agents"][local_id] = entry
            save_state(state_file, state)

        move = AgentMove(local_id=local_id, cloud_id=entry["cloud_agent_id"])
        report.agents.append(move)
        moved_ids = set(entry["moved_ids"])

        pending: list[tuple[str, dict[str, Any]]] = []
        for memory in memories:
            mid = str(memory.get("id") or "")
            if mid in moved_ids:
                move.already_moved += 1
                continue
            item = to_import_item(memory)
            if item is None:
                move.failed.append((mid, "no content"))
                continue
            pending.append((mid, item))

        total = move.already_moved + len(pending)
        if on_progress:
            on_progress(local_id, move.already_moved, total)
        for start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[start : start + BATCH_SIZE]
            result = hosted_client.import_memories(
                entry["cloud_agent_id"], [item for _, item in chunk]
            )
            outcomes = result.get("results", [])
            for i, (mid, _) in enumerate(chunk):
                # Results are in input order; a missing one counts as failed.
                outcome = outcomes[i] if i < len(outcomes) else {}
                if outcome.get("id"):
                    entry["moved_ids"].append(mid)
                    move.moved += 1
                else:
                    move.failed.append((mid, str(outcome.get("reason") or "failed")))
            save_state(state_file, state)
            if on_progress:
                on_progress(local_id, move.already_moved + move.moved, total)

        entry["complete"] = not move.failed
        save_state(state_file, state)

    return report
