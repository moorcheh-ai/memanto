"""
Export Letta agent archival memory to JSON.

Used by ``memanto analyze letta``.

Analyze mode (default): list every agent in the account and export archival
passages from each.

Single-agent export (``agent_id`` / ``agent_name`` kwargs) and optional
``.af`` agent files (``include_agent_file``) are kept for future migration
workflows — not exposed on the analyze CLI today.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_AGENT_NAME = "lette"
PASSAGE_PAGE_SIZE = 100
AGENT_PAGE_SIZE = 50

PASSAGE_EMBED_KEYS = ("embedding", "embedding_config")


def model_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: model_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [model_to_dict(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)


def passage_to_dict(passage: Any) -> dict[str, Any]:
    data = model_to_dict(passage)
    if isinstance(data, dict):
        for key in PASSAGE_EMBED_KEYS:
            data.pop(key, None)
    return data if isinstance(data, dict) else {"value": data}


def dedupe_agents(agents: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for agent in agents:
        agent_id = getattr(agent, "id", None)
        if agent_id:
            if agent_id in seen:
                continue
            seen.add(agent_id)
        unique.append(agent)
    return unique


def list_all_agents(
    client: Any,
    *,
    page_size: int = AGENT_PAGE_SIZE,
) -> tuple[list[Any], dict[str, Any]]:
    start = time.perf_counter()
    all_items: list[Any] = []
    cursor: str | None = None
    pages = 0

    while True:
        kwargs: dict[str, Any] = {"limit": page_size}
        if cursor:
            kwargs["after"] = cursor
        page = list(client.agents.list(**kwargs))
        pages += 1
        if not page:
            break
        all_items.extend(page)
        if len(page) < page_size:
            break
        last_id = getattr(page[-1], "id", None)
        if not last_id or last_id == cursor:
            break
        cursor = last_id

    agents = dedupe_agents(all_items)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return agents, {
        "pages": pages,
        "count": len(agents),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def find_agent_by_name(client: Any, name: str) -> Any | None:
    agents = list(client.agents.list(name=name, limit=50))
    if not agents:
        agents = list(client.agents.list(query_text=name, limit=50))
    for agent in agents:
        if getattr(agent, "name", None) == name:
            return agent
    return agents[0] if agents else None


def resolve_agent(
    client: Any,
    *,
    agent_id: str | None,
    agent_name: str,
) -> Any:
    if agent_id:
        return client.agents.retrieve(agent_id)
    agent = find_agent_by_name(client, agent_name)
    if agent is None:
        raise ValueError(
            f"Letta agent not found: name={agent_name!r}. "
            "Create the agent in Letta ADE first."
        )
    return agent


def list_all_passages(
    client: Any,
    agent_id: str,
    *,
    page_size: int,
) -> tuple[list[Any], dict[str, Any]]:
    start = time.perf_counter()
    all_items: list[Any] = []
    cursor: str | None = None
    pages = 0

    while True:
        kwargs: dict[str, Any] = {"agent_id": agent_id, "limit": page_size}
        if cursor:
            kwargs["after"] = cursor
        page = client.agents.passages.list(**kwargs)
        pages += 1
        if not page:
            break
        all_items.extend(page)
        if len(page) < page_size:
            break
        last_id = page[-1].id
        if not last_id or last_id == cursor:
            break
        cursor = last_id

    elapsed_ms = (time.perf_counter() - start) * 1000
    return all_items, {
        "pages": pages,
        "count": len(all_items),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def fetch_agent_file(client: Any, agent_id: str) -> str | dict[str, Any] | None:
    raw = client.agents.export_file(agent_id)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return str(raw)
    if isinstance(parsed, dict):
        return parsed
    return str(parsed)


def _tag_passages(
    passages: list[dict[str, Any]],
    *,
    agent_id: str,
    agent_name: str | None,
) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for passage in passages:
        row = dict(passage)
        row["export_agent_id"] = agent_id
        if agent_name:
            row["export_agent_name"] = agent_name
        tagged.append(row)
    return tagged


def _export_single_agent(
    client: Any,
    *,
    agent_id: str | None,
    agent_name: str,
    include_agent_file: bool,
    page_size: int,
    on_progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    if on_progress:
        on_progress("Resolving Letta agent...")
    agent = resolve_agent(client, agent_id=agent_id, agent_name=agent_name)
    resolved_agent_id = agent.id
    resolved_agent_name = getattr(agent, "name", None)

    if on_progress:
        on_progress(
            f"Agent: {resolved_agent_name or resolved_agent_id} ({resolved_agent_id})"
        )

    if on_progress:
        on_progress("Fetching archival passages (paginated)...")
    passages, passage_meta = list_all_passages(
        client,
        resolved_agent_id,
        page_size=page_size,
    )
    if on_progress:
        on_progress(
            f"Passages: {passage_meta['count']} "
            f"({passage_meta['pages']} pages, {passage_meta['elapsed_ms']}ms)"
        )

    agent_file: str | dict[str, Any] | None = None
    if include_agent_file:
        if on_progress:
            on_progress("Fetching agent export file (.af schema)...")
        agent_file = fetch_agent_file(client, resolved_agent_id)

    passage_dicts = _tag_passages(
        [passage_to_dict(p) for p in passages],
        agent_id=resolved_agent_id,
        agent_name=resolved_agent_name,
    )

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "export_mode": "single_agent",
        "agent_id": resolved_agent_id,
        "agent_name": resolved_agent_name,
        "summary": {
            "agent_count": 1,
            "passage_count": len(passage_dicts),
            "include_agent_file": include_agent_file,
            "passage_page_size": page_size,
            "passage_pages": passage_meta["pages"],
        },
        "agents": [model_to_dict(agent)],
        "passages": passage_dicts,
        "passages_by_agent": {resolved_agent_id: passage_dicts},
        "agent_file": agent_file,
        "meta": {"passages": passage_meta},
    }


def _export_all_agents(
    client: Any,
    *,
    include_agent_file: bool,
    page_size: int,
    on_progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    if on_progress:
        on_progress("Listing all Letta agents...")
    agents, agent_meta = list_all_agents(client)
    if on_progress:
        on_progress(
            f"Found {agent_meta['count']} agents "
            f"({agent_meta['pages']} pages, {agent_meta['elapsed_ms']}ms)"
        )

    if not agents:
        raise ValueError(
            "No Letta agents found in this account. Create one in Letta ADE first."
        )

    all_passages: list[dict[str, Any]] = []
    passages_by_agent: dict[str, list[dict[str, Any]]] = {}
    per_agent_meta: dict[str, dict[str, Any]] = {}
    agent_files: dict[str, str | dict[str, Any] | None] = {}
    total_pages = 0

    for i, agent in enumerate(agents, 1):
        resolved_agent_id = agent.id
        resolved_agent_name = getattr(agent, "name", None)
        label = resolved_agent_name or resolved_agent_id

        if on_progress:
            on_progress(f"Fetching passages [{i}/{len(agents)}] {label}...")

        passages, passage_meta = list_all_passages(
            client,
            resolved_agent_id,
            page_size=page_size,
        )
        passage_dicts = _tag_passages(
            [passage_to_dict(p) for p in passages],
            agent_id=resolved_agent_id,
            agent_name=resolved_agent_name,
        )

        passages_by_agent[resolved_agent_id] = passage_dicts
        all_passages.extend(passage_dicts)
        per_agent_meta[resolved_agent_id] = passage_meta
        total_pages += passage_meta["pages"]

        if on_progress:
            on_progress(
                f"  {label}: {passage_meta['count']} passages "
                f"({passage_meta['pages']} pages)"
            )

        if include_agent_file:
            agent_files[resolved_agent_id] = fetch_agent_file(client, resolved_agent_id)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "export_mode": "all_agents",
        "summary": {
            "agent_count": len(agents),
            "passage_count": len(all_passages),
            "include_agent_file": include_agent_file,
            "passage_page_size": page_size,
            "passage_pages": total_pages,
        },
        "agents": [model_to_dict(agent) for agent in agents],
        "passages": all_passages,
        "passages_by_agent": passages_by_agent,
        "agent_files": agent_files if include_agent_file else None,
        "meta": {
            "agents": agent_meta,
            "passages_by_agent": per_agent_meta,
        },
        "notes": {
            "export": "All agents listed via client.agents.list() and exported "
            "automatically — no manual agent ID config required for analyze.",
        },
    }


def run_letta_export(
    api_key: str,
    dest_dir: Path,
    *,
    agent_id: str | None = None,
    agent_name: str | None = None,
    include_agent_file: bool = False,
    page_size: int = PASSAGE_PAGE_SIZE,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """
    Export Letta archival memory and write JSON into *dest_dir*.

    When neither *agent_id* nor *agent_name* is set, lists every agent in the
    account and exports passages from each (analyze default).

    Returns the written file path and the full export dict.
    """
    try:
        from letta_client import Letta
    except ImportError as exc:
        raise ImportError(
            "Letta SDK is required. Install with: pip install letta-client"
        ) from exc

    page_size = max(1, min(page_size, 200))
    client = Letta(api_key=api_key)

    if agent_id or agent_name:
        export = _export_single_agent(
            client,
            agent_id=agent_id,
            agent_name=agent_name or DEFAULT_AGENT_NAME,
            include_agent_file=include_agent_file,
            page_size=page_size,
            on_progress=on_progress,
        )
    else:
        export = _export_all_agents(
            client,
            include_agent_file=include_agent_file,
            page_size=page_size,
            on_progress=on_progress,
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "letta_export.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
