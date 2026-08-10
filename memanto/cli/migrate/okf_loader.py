"""
OKF Loader - Loads Open Knowledge Format (OKF) memory export files.

OKF is the canonical interchange format for the Great Memory Migration
feature (issue #1609).  An OKF file is a JSON document whose top-level
value is either:

- a list of memory records, or
- an object with a ``memories`` or ``records`` key containing a list.

Each record must have at least a ``content`` or ``text`` field.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OKFLoader:
    """Load and validate an OKF export file.

    Parameters
    ----------
    path:
        Filesystem path to the ``.json`` OKF export file.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[dict[str, Any]]:
        """Parse the OKF file and return a list of raw record dicts.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the file cannot be parsed as valid OKF JSON.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"OKF file not found: {self.path}")

        raw = self.path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in OKF file {self.path}: {exc}") from exc

        records = self._extract_records(data)
        logger.debug("OKFLoader: extracted %d records from %s", len(records), self.path)
        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_records(self, data: Any) -> list[dict[str, Any]]:
        """Normalise the top-level JSON structure to a flat list of dicts."""
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]

        if isinstance(data, dict):
            for key in ("memories", "records", "data", "items"):
                if key in data and isinstance(data[key], list):
                    return [r for r in data[key] if isinstance(r, dict)]

            # Single record wrapped in an object
            if "content" in data or "text" in data:
                return [data]

        raise ValueError(
            f"Unrecognised OKF structure in {self.path}. "
            "Expected a JSON array or an object with a 'memories' / 'records' key."
        )