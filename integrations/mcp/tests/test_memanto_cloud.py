"""memanto-mcp on the Memanto Cloud backend (``memanto login``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from memanto.cli.client.hosted_client import HostedClient

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.lifecycle import MemantoLifecycle


@pytest.fixture
def memanto_cloud_home(tmp_path: Path) -> Path:
    """A ~/.memanto signed in to Memanto Cloud, with no Moorcheh key."""
    config_dir = tmp_path / ".memanto"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("memanto:\n  backend: memanto-cloud\n")
    (config_dir / ".env").write_text("MEMANTO_API_KEY=mk_test_fake_key\n")
    return config_dir


def test_settings_valid_without_moorcheh_key_on_memanto_cloud(
    memanto_cloud_home: Path,
) -> None:
    settings = MCPServerSettings()  # type: ignore[call-arg]
    assert settings.api_key_value() == ""


def test_lifecycle_uses_hosted_client_on_memanto_cloud(
    memanto_cloud_home: Path,
) -> None:
    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]
    assert isinstance(lifecycle.client, HostedClient)
    assert lifecycle.client.api_key == "mk_test_fake_key"
