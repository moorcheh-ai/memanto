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
from typing import Any

from memanto.cli.migrate.langfuse_state import (
    Reconciliation,
    reconcile,
    record_updated,
    record_written,
)
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


@dataclass
class LangfuseSyncSummary:
    """Outcome of one Langfuse sync.

    Distinct from :class:`MigrationSummary` because a Langfuse sync is
    repeatable: rows are reconciled against a ledger, so the interesting
    numbers are new/changed/unchanged, not imported/skipped.
    """

    provider: str = "langfuse"
    observation_count: int = 0
    signature_count: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    imported: int = 0
    updated: int = 0
    failed: int = 0
    batches: int = 0
    matched_count: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "observation_count": self.observation_count,
            "signature_count": self.signature_count,
            "matched_count": self.matched_count,
            "new": self.new,
            "changed": self.changed,
            "unchanged": self.unchanged,
            "imported": self.imported,
            "updated": self.updated,
            "failed": self.failed,
            "batches": self.batches,
            "type_counts": self.type_counts,
            "errors": self.errors[:20],
            "warnings": self.warnings,
        }


def langfuse_warnings(
    export: dict[str, Any],
    rows: list[dict[str, Any]],
    matched: int,
    config: Any,
) -> list[str]:
    """Non-fatal problems the user should see before trusting the numbers.

    A mode that is switched on but has no rule or budget captures nothing;
    saying so is the difference between "no problems found" and "never
    actually looked".
    """
    from memanto.cli.migrate.langfuse_rules import cardinality_warning, has_cost_data

    warnings: list[str] = []

    for mode, reason in config.unconfigured_modes().items():
        warnings.append(f"'{mode.replace('_', '-')}' captured nothing: {reason}")
    if "costly" in config.modes and not has_cost_data(export.get("observations") or []):
        warnings.append(
            "'costly' captured nothing: no observation in this window carries "
            "cost data. Self-hosted Langfuse needs model pricing configured."
        )

    cardinality = cardinality_warning(matched, len(rows))
    if cardinality:
        warnings.append(cardinality)
    return warnings


def run_langfuse_sync(
    *,
    export: dict[str, Any],
    client: Any,
    agent_id: str,
    state: dict[str, Any],
    dry_run: bool,
    config: Any,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[LangfuseSyncSummary, list[dict[str, Any]], Reconciliation]:
    """Group, reconcile, and (optionally) write one Langfuse sync.

    Shared by ``memanto migrate langfuse`` and the UI's migrate tile so both
    honour the ledger — writing through ``run_migration`` instead would
    duplicate every signature on the second run.

    *config* is the caller's ``CaptureConfig``; it is required so that a
    ``--file`` replay maps with the user's current settings rather than
    whatever the saved export happened to be pulled with. Mutates *state* in
    place; the caller persists it with ``save_state``.
    """
    from memanto.cli.migrate.langfuse_rules import build_rows

    rows = build_rows(export, config)
    plan = reconcile(rows, state)

    matched = sum(int(row.get("occurrences") or 0) for row in rows)
    summary = LangfuseSyncSummary(
        observation_count=len(export.get("observations") or []),
        signature_count=len(rows),
        matched_count=matched,
        new=len(plan.new_rows),
        changed=len(plan.updates),
        unchanged=plan.unchanged,
        type_counts=type_breakdown(rows),
        warnings=langfuse_warnings(export, rows, matched, config),
    )

    if dry_run:
        return summary, rows, plan

    batches = list(chunked(plan.new_rows, BATCH_LIMIT))
    summary.batches = len(batches)
    for idx, batch in enumerate(batches, 1):
        if on_progress:
            on_progress(
                f"Writing batch {idx}/{len(batches)} ({len(batch)} new signatures)..."
            )
        try:
            result = client.batch_remember(agent_id=agent_id, memories=batch)
        except Exception as exc:
            summary.failed += len(batch)
            summary.errors.append(f"batch {idx}: {exc}")
            continue

        summary.imported += int(result.get("successful") or 0)
        summary.failed += int(result.get("failed") or 0)
        record_written(state, batch, result.get("results") or [])
        for item in result.get("results") or []:
            if isinstance(item, dict) and item.get("error"):
                summary.errors.append(f"batch {idx}: {item['error']}")

    if plan.updates and on_progress:
        on_progress(f"Updating {len(plan.updates)} recurring signatures...")
    for update in plan.updates:
        try:
            client.update_memory(
                agent_id=agent_id,
                memory_id=update["memory_id"],
                updates=update["updates"],
            )
        except Exception as exc:
            summary.failed += 1
            summary.errors.append(f"update {update['signature']}: {exc}")
            continue
        record_updated(state, update)
        summary.updated += 1

    return summary, rows, plan


def load_export(file_path: Path) -> dict[str, Any]:
    """Load a previously-produced provider export JSON from disk."""
    if not file_path.exists():
        raise FileNotFoundError(f"Export file not found: {file_path}")
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Export file must be a JSON object: {file_path}")
    return data


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
    if provider == "chatgpt":
        return len(export.get("memories", []) or [])
    if provider == "langfuse":
        # Observations, not memories — many collapse into one signature.
        return len(export.get("observations", []) or [])
    memories = export.get("memories", []) or []
    if provider == "supermemory":
        mapped_memory_ids: set[str] = set()
        represented_document_ids: set[str] = set()
        for memory in memories:
            content = (
                memory.get("content")
                or memory.get("memory")
                or memory.get("text")
                or ""
            ).strip()
            if not content:
                continue
            if memory.get("id"):
                mapped_memory_ids.add(str(memory["id"]))
            document_id = memory.get("documentId") or memory.get("document_id")
            if document_id:
                represented_document_ids.add(str(document_id))

        uncovered_chunks = 0
        for doc in export.get("documents", []) or []:
            doc_id = doc.get("id")
            doc_memory_ids = {
                str(memory_id)
                for memory_id in (doc.get("memory_ids") or [])
                if memory_id
            }
            if (doc_id and str(doc_id) in represented_document_ids) or (
                doc_memory_ids & mapped_memory_ids
            ):
                continue
            uncovered_chunks += len(doc.get("chunks", []) or [])
        return len(memories) + uncovered_chunks
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

    from memanto.app.utils.errors import MemoryOperationError

    for idx, batch in enumerate(batches, 1):
        if on_progress:
            on_progress(
                f"Importing batch {idx}/{len(batches)} ({len(batch)} memories)..."
            )
        try:
            result = client.batch_remember(agent_id=agent_id, memories=batch)
        except MemoryOperationError:
            raise
        except Exception as exc:
            summary.failed += len(batch)
            summary.errors.append(f"batch {idx}: {exc}")
            continue

        if not isinstance(result, dict):
            raise MemoryOperationError(
                message="Data corruption detected: Received malformed batch response envelope during migration.",
                details={"result_preview": str(result)[:100]},
            )

        batch_results = result.get("results")
        if not isinstance(batch_results, list):
            raise MemoryOperationError(
                message="Data corruption detected: Received malformed batch result array during migration.",
                details={"results_preview": str(batch_results)[:100]},
            )

        total_submitted = int(result.get("total_submitted") or 0)
        successful = int(result.get("successful") or 0)
        failed = int(result.get("failed") or 0)
        rejected = int(result.get("rejected") or 0)

        if (
            total_submitted < 0
            or successful < 0
            or failed < 0
            or rejected < 0
            or total_submitted != len(batch)
            or len(batch_results) != len(batch)
            or successful + failed + rejected != len(batch)
        ):
            raise MemoryOperationError(
                message="Data corruption detected: Inconsistent batch counters during migration.",
                details={"result_preview": str(result)[:100]},
            )

        summary.imported += successful
        summary.failed += failed + rejected

        # batch_remember reports per-item errors in results[]; surface all errors.
        for item in batch_results:
            if not isinstance(item, dict) or not item:
                raise MemoryOperationError(
                    message="Data corruption detected: Received malformed batch result from storage layer during migration.",
                    details={"item_preview": str(item)[:100]},
                )
            err = item.get("error")
            if err:
                summary.errors.append(f"batch {idx}: {err}")

    return summary, rows
