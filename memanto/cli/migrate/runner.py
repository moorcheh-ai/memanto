"""
Shared migration orchestrator.

Pipeline:
    1. Load an export — either from disk (``--file``) or by running the
       provider's existing exporter live (reusing ``cli/analyze/*_export``).
    2. Map source rows → Memanto memory payloads via ``mappers.MAPPERS``.
    3. On ``--dry-run``: emit the mapped preview JSON + always render the
       savings report (no writes).
    4. On a real run: chunk into batches of ≤100 and call
       ``SdkClient.batch_remember``. Roll up successful/failed counts. Write
       the optional savings report when requested.

The savings report code is the same one the old ``analyze`` command used —
``compute_metrics`` + ``build_report_markdown`` from
``cli/analyze/<provider>_compare.py``. Kept as helpers so the migrate flow
can surface them as the "what migrating saves you" preview.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from memanto.cli.migrate.mappers import MAPPERS, type_breakdown

BATCH_LIMIT = 100


@dataclass
class MigrationSummary:
    provider: str
    source_count: int = 0
    mapped_count: int = 0
    imported: int = 0
    failed: int = 0
    skipped: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    batches: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "source_count": self.source_count,
            "mapped_count": self.mapped_count,
            "imported": self.imported,
            "failed": self.failed,
            "skipped": self.skipped,
            "type_counts": self.type_counts,
            "batches": self.batches,
            "errors": self.errors[:20],  # cap so a bad batch doesn't flood
        }


def load_export(file_path: Path) -> dict[str, Any]:
    """Load a previously-produced provider export JSON, Markdown, or JSONL from disk."""
    if not file_path.exists():
        raise FileNotFoundError(f"Export file not found: {file_path}")

    suffix = file_path.suffix.lower()
    raw_text = file_path.read_text(encoding="utf-8")

    if suffix in (".md", ".markdown"):
        return {"content": raw_text, "format": "okf", "source_file": str(file_path)}

    if suffix == ".jsonl":
        items: list[dict[str, Any]] = []
        for line in raw_text.splitlines():
            line_str = line.strip()
            if line_str:
                try:
                    items.append(json.loads(line_str))
                except json.JSONDecodeError:
                    pass
        return {"memories": items, "format": "jsonl", "source_file": str(file_path)}

    try:
        data = json.loads(raw_text)
        if isinstance(data, list):
            return {"memories": data, "format": "json_list", "source_file": str(file_path)}
        return cast(dict[str, Any], data)
    except json.JSONDecodeError:
        return {"content": raw_text, "format": "text", "source_file": str(file_path)}


def map_export(provider: str, export: dict[str, Any]) -> list[dict[str, Any]]:
    mapper = MAPPERS.get(provider)
    if mapper is None:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {sorted(MAPPERS)}")
    return mapper(export)


def chunked(items: list[dict[str, Any]], size: int = BATCH_LIMIT):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def write_preview(rows: list[dict[str, Any]], dest: Path) -> Path:
    """Write the mapped Memanto payloads so a dry-run is fully inspectable."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return dest


def source_count(provider: str, export: dict[str, Any]) -> int:
    """Best-effort count of source records (for the summary header)."""
    if provider == "letta":
        return len(export.get("passages", []) or [])
    if provider in ("okf", "markdown"):
        raw = export.get("content") or export.get("markdown") or ""
        count = sum(1 for line in raw.splitlines() if line.strip().startswith("### "))
        return count if count > 0 else (1 if raw.strip() else 0)
    if provider in ("langchain", "langgraph"):
        msgs = len(export.get("messages") or export.get("chat_history") or export.get("history") or [])
        entities = len(export.get("entities") or export.get("entity_store") or {})
        summary = 1 if (export.get("summary") or export.get("conversation_summary")) else 0
        return msgs + entities + summary
    if provider in ("generic", "jsonl"):
        items = export.get("memories") or export.get("items") or export.get("data") or export.get("records") or []
        return len(items) if items else (1 if ("content" in export or "text" in export) else 0)
    memories = export.get("memories", []) or []
    if provider == "supermemory" and not memories:
        # Mirror map_supermemory's fallback: when no extracted memories exist
        # we harvest document chunks, so the summary should reflect that.
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
    """Map + (optionally) batch-import.

    Returns the summary and the mapped rows so the caller can write a
    preview file and/or render an analyze-style savings report.
    """
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
            on_progress(
                f"Importing batch {idx}/{len(batches)} ({len(batch)} memories)..."
            )
        try:
            result = client.batch_remember(agent_id=agent_id, memories=batch)
        except Exception as exc:  # noqa: BLE001 — surface any client failure
            summary.failed += len(batch)
            summary.errors.append(f"batch {idx}: {exc}")
            continue

        successful = int(result.get("successful") or 0)
        failed = int(result.get("failed") or 0)
        summary.imported += successful
        summary.failed += failed

        # batch_remember reports per-item errors in results[]; surface a few.
        for item in (result.get("results") or [])[:5]:
            err = item.get("error")
            if err:
                summary.errors.append(f"batch {idx}: {err}")

    return summary, rows
