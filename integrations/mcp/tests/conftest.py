"""Shared fixtures for memanto-mcp tests.

These tests never hit the network: ``SdkClient.__init__`` only stores the key
and lazy-loads the real Moorcheh client on first call. Tests that exercise the
server therefore only need a non-empty key to satisfy validation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Wipe env vars AND switch cwd so a developer's local ``.env`` cannot
    bleed into settings construction (pydantic-settings reads ``./.env``)."""
    for var in list(os.environ):
        if var.startswith(("MOORCHEH_", "MEMANTO_")):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def fake_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "mch_test_fake_key_for_unit_tests"
    monkeypatch.setenv("MOORCHEH_API_KEY", key)
    return key
