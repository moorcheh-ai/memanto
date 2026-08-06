"""Shared paths and .env loading for the scripts."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OKF_BUNDLE_DIR = DATA_DIR / "graphiti_okf_bundle"
RAW_EXPORT_PATH = DATA_DIR / "graphiti_raw_export.json"
PROVIDER_JSON_PATH = DATA_DIR / "memanto_provider_import.json"
VALIDATION_DIR = DATA_DIR / "validation"
EXPORTED_BUNDLE_DIR = PROJECT_ROOT / "okf_bundle_sample"


def load_env() -> None:
    """Load ``.env`` from the example directory if python-dotenv is available.

    Real environment variables always win, so CI can inject secrets without a
    file on disk.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def ensure_importable() -> None:
    """Put the example root on ``sys.path`` so ``scripts/*.py`` run standalone."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str) -> None:
    """Exit non-zero with a message on stderr, so ``run_all.sh`` halts."""
    print(f"ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)
