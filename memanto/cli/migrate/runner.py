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

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from memanto.cli.migrate.mappers import MAPPERS, type_breakdown

BATCH_LIMIT = 100
MIGRATION_ID_NAMESPACE = uuid.UUID("c96c2be1-42c1-4db0-a4b3-55a040f7b74c")


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
    """Load a previously-produced provider export JSON from disk."""
    if not file_path.exists():
        raise FileNotFoundError(f"Export file not found: {file_path}")
    return cast(dict[str, Any], json.loads(file_path.read_text(encoding="utf-8")))


def map_export(provider: str, export: dict[str, Any]) -> list[dict[str, Any]]:
    mapper = MAPPERS.get(provider)
    if mapper is None:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {sorted(MAPPERS)}")
    return mapper(export)


def chunked(items: list[dict[str, Any]], size: int = BATCH_LIMIT):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _content_fingerprint(row: dict[str, Any]) -> str:
    payload = {
        "title": row.get("title"),
        "content": row.get("content"),
        "source": row.get("source"),
        "tags": row.get("tags") or [],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _stable_import_id(provider: str, agent_id: str, row: dict[str, Any]) -> str:
    """Build a retry-stable memory id for one migrated source row."""
    source_ref = row.get("source_ref")
    if source_ref:
        source_identity = f"source_ref:{source_ref}"
    else:
        source_identity = f"content:{_content_fingerprint(row)}"

    return str(
        uuid.uuid5(
            MIGRATION_ID_NAMESPACE,
            f"agent:{agent_id}:provider:{provider}:{source_identity}",
        )
    )


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

    for row in rows:
        row.setdefault("id", _stable_import_id(provider, agent_id, row))

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
