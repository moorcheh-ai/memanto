"""
Migration Runner - Orchestrates memory migration from various sources to Memanto.

Supports OKF (Open Knowledge Format) and direct source migrations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Orchestrates the migration of memory records into Memanto."""

    def __init__(self, client: Any = None, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run
        self._results: dict[str, Any] = {
            "imported": 0,
            "skipped": 0,
            "errors": [],
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_from_okf(self, okf_path: str | Path) -> dict[str, Any]:
        """Import memories from an OKF-format JSON file.

        Parameters
        ----------
        okf_path:
            Path to the OKF JSON file produced by :mod:`memanto.cli.migrate.okf_loader`.

        Returns
        -------
        dict
            Summary with keys ``imported``, ``skipped``, and ``errors``.
        """
        from memanto.cli.migrate.okf_loader import OKFLoader
        from memanto.cli.migrate.mappers import okf_record_to_memory

        path = Path(okf_path)
        if not path.exists():
            raise FileNotFoundError(f"OKF file not found: {path}")

        loader = OKFLoader(path)
        records = loader.load()

        logger.info("Loaded %d OKF records from %s", len(records), path)

        for record in records:
            try:
                memory = okf_record_to_memory(record)
                if self.dry_run:
                    logger.debug("[dry-run] Would import: %s", memory.get("content", "")[:80])
                    self._results["imported"] += 1
                    continue

                if self.client is not None:
                    self.client.store(memory)
                self._results["imported"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to import record %s: %s", record.get("id", "?"), exc)
                self._results["errors"].append({"record_id": record.get("id"), "error": str(exc)})
                self._results["skipped"] += 1

        return dict(self._results)

    def run_from_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Import an already-loaded list of normalised memory dicts.

        Each dict must have at least a ``content`` key.  Additional keys
        (``agent_id``, ``created_at``, ``metadata``) are passed through.
        """
        for record in records:
            try:
                if not record.get("content"):
                    self._results["skipped"] += 1
                    continue

                if self.dry_run:
                    logger.debug("[dry-run] Would import: %s", str(record.get("content", ""))[:80])
                    self._results["imported"] += 1
                    continue

                if self.client is not None:
                    self.client.store(record)
                self._results["imported"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to import record: %s", exc)
                self._results["errors"].append({"error": str(exc)})
                self._results["skipped"] += 1

        return dict(self._results)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset internal counters (useful when reusing the same runner)."""
        self._results = {"imported": 0, "skipped": 0, "errors": []}