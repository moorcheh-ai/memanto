"""Regression tests for crash-safe configuration persistence."""

import os
from unittest.mock import patch

import pytest

from memanto.cli.config.manager import ConfigManager


def test_onprem_state_survives_interrupted_replace(tmp_path):
    """An interrupted state replacement must preserve the previous file."""
    manager = ConfigManager(tmp_path)
    manager.set_onprem_state(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    state_path = manager._onprem_state_path()
    original = state_path.read_text(encoding="utf-8")

    with (
        patch(
            "memanto.cli.config.manager.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        manager.set_onprem_state(llm_model="qwen3:8b")

    assert state_path.read_text(encoding="utf-8") == original
    assert manager.get_onprem_state() == {
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
    }
    assert list(state_path.parent.glob(f".{state_path.name}.*.tmp")) == []


def test_yaml_config_survives_interrupted_replace(tmp_path):
    """An interrupted YAML replacement must preserve the previous config."""
    manager = ConfigManager(tmp_path)
    manager.set("backend", "cloud")
    original = manager.config_file.read_text(encoding="utf-8")

    with (
        patch(
            "memanto.cli.config.manager.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        manager.set("backend", "on-prem")

    assert manager.config_file.read_text(encoding="utf-8") == original
    assert manager.get("backend") == "cloud"
    assert list(tmp_path.glob(f".{manager.config_file.name}.*.tmp")) == []


def test_cleanup_error_does_not_mask_replace_failure(tmp_path):
    """Cleanup failures must not replace the original persistence error."""
    manager = ConfigManager(tmp_path)
    state_path = manager._onprem_state_path()

    with (
        patch(
            "memanto.cli.config.manager.os.replace",
            side_effect=OSError("replace failed"),
        ),
        patch(
            "memanto.cli.config.manager.Path.unlink",
            side_effect=PermissionError("temporary file is locked"),
        ),
        pytest.raises(OSError, match="replace failed"),
    ):
        manager.set_onprem_state(llm_model="qwen3:8b")

    leftovers = list(state_path.parent.glob(f".{state_path.name}.*.tmp"))
    assert len(leftovers) == 1
    leftovers[0].unlink()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable")
def test_atomic_config_files_are_owner_only(tmp_path):
    """Atomically persisted configuration files must be owner-readable only."""
    manager = ConfigManager(tmp_path)

    manager.set("backend", "cloud")
    manager.set_onprem_state(llm_model="qwen3:8b")
    manager._save_connections({"claude": {"projects": [], "installed_global": True}})

    for path in (
        manager.config_file,
        manager._onprem_state_path(),
        manager.connections_file,
    ):
        assert path.stat().st_mode & 0o777 == 0o600
