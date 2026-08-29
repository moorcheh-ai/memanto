"""
Migration runner for examples/migrations.

Imports core types and helpers from memanto.cli.migrate.runner directly.
Extends source_count and run_migration to cover the custom providers added
in this example (chatgpt, claude, gemini, zep, hindsight, langgraph, notion,
obsidian, chroma) that are not part of the core package.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from memanto.cli.migrate.runner import (
    BATCH_LIMIT,
    MigrationSummary,
    load_export,
    chunked,
)
from memanto.cli.migrate.mappers import type_breakdown

try:
    from .mappers import MAPPERS
except ImportError:
    from mappers import MAPPERS  # type: ignore[no-redef]


def map_export(provider: str, export: dict[str, Any]) -> list[dict[str, Any]]:
    mapper = MAPPERS.get(provider)
    if mapper is None:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {sorted(MAPPERS)}")
    return mapper(export)


def source_count(provider: str, export: dict[str, Any]) -> int:
    if provider == "letta":
        return len(export.get("passages", []) or [])
    if provider == "langgraph":
        return len(export.get("items", []) or [])
    if provider == "chatgpt":
        count = 0
        for conv in (export.get("memories", []) or []):
            if not isinstance(conv, dict):
                continue
            mapping = conv.get("mapping") or {}
            if not isinstance(mapping, dict):
                continue
            current_node = conv.get("current_node")
            if current_node:
                seen: set[str] = set()
                node_id = current_node
                while node_id and node_id not in seen:
                    seen.add(node_id)
                    node = mapping.get(node_id)
                    if not isinstance(node, dict):
                        break
                    msg = node.get("message")
                    if isinstance(msg, dict):
                        author = msg.get("author") or {}
                        content_obj = msg.get("content") or {}
                        if (
                            author.get("role") == "user"
                            and content_obj.get("content_type", "text") != "user_editable_context"
                        ):
                            parts = content_obj.get("parts") or []
                            if any(isinstance(p, str) and p.strip() for p in parts):
                                count += 1
                    node_id = node.get("parent")
            else:
                for node in mapping.values():
                    if not isinstance(node, dict):
                        continue
                    msg = node.get("message")
                    if not isinstance(msg, dict):
                        continue
                    if (msg.get("author") or {}).get("role") == "user":
                        count += 1
        return count
    if provider in ("claude", "gemini"):
        role_key = "sender" if provider == "claude" else "role"
        role_val = "human" if provider == "claude" else "user"
        msg_key = "chat_messages" if provider == "claude" else "messages"
        return sum(
            1
            for conv in (export.get("memories", []) or [])
            if isinstance(conv, dict)
            for msg in (conv.get(msg_key) or [])
            if isinstance(msg, dict) and msg.get(role_key) == role_val
        )
    memories = export.get("memories", []) or []
    if provider == "supermemory" and not memories:
        return sum(
            len(doc.get("chunks", []) or [])
            for doc in (export.get("documents", []) or [])
        )
    return len(memories)


def run_migration(
    *,
    provider: str,
    export: dict[str, Any],
    client: Any,
    agent_id: str,
    dry_run: bool,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[MigrationSummary, list[dict[str, Any]]]:
    summary = MigrationSummary(provider=provider)
    summary.source_count = source_count(provider, export)

    rows = map_export(provider, export)
    summary.mapped_count = len(rows)
    summary.skipped = max(0, summary.source_count - summary.mapped_count)
    summary.type_counts = type_breakdown(rows)

    if dry_run or not rows:
        return summary, rows

    batches = list(chunked(rows, BATCH_LIMIT))
    summary.batches = len(batches)

    for idx, batch in enumerate(batches, 1):
        if on_progress:
            on_progress(f"Importing batch {idx}/{len(batches)} ({len(batch)} memories)...")
        try:
            result = client.batch_remember(agent_id=agent_id, memories=batch)
        except Exception as exc:
            summary.failed += len(batch)
            summary.errors.append(f"batch {idx}: {exc}")
            continue

        successful = int(result.get("successful") or 0)
        failed = int(result.get("failed") or 0)
        summary.imported += successful
        summary.failed += failed

        for item in (result.get("results") or [])[:5]:
            err = item.get("error")
            if err:
                summary.errors.append(f"batch {idx}: {err}")

    return summary, rows
