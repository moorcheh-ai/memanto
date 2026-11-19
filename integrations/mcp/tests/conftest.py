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
    # Credentials validation reads the backend from ~/.memanto/config.yaml;
    # point home at an empty dir so the developer's real config is ignored.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


@pytest.fixture
def fake_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "mch_test_fake_key_for_unit_tests"
    monkeypatch.setenv("MOORCHEH_API_KEY", key)
    return key


@pytest.fixture(autouse=True)
def session_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Sessions in a temp dir, so the developer's active agent never leaks in.

    ``resolve_agent_id`` follows the agent active on this computer, read from
    the process-wide ``SessionService`` singleton.
    """
    from memanto.app.services.session_service import SessionService

    import memanto_mcp.lifecycle as lifecycle_module

    service = SessionService(secret_key="k" * 32, sessions_dir=tmp_path / "sessions")
    monkeypatch.setattr(lifecycle_module, "get_session_service", lambda: service)
    return service
