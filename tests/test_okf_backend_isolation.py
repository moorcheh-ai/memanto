"""Regression coverage for backend-isolated OKF exports and sync caches."""

from unittest.mock import MagicMock

import pytest

import memanto.app.config as app_config
import memanto.cli.client.direct_client as direct_mod
import memanto.cli.client.sdk_client as sdk_mod
from memanto.app.services.okf_export_service import OkfExportService


def _memory(title: str, content: str) -> dict:
    return {
        "id": title.lower().replace(" ", "-"),
        "title": title,
        "content": content,
        "confidence": 0.9,
        "provenance": "explicit_statement",
        "source": "user",
        "status": "active",
    }


def _write_cached_bundle(exports_dir, agent_id: str, title: str, content: str):
    return OkfExportService(exports_dir=exports_dir).write_okf_bundle(
        agent_id=agent_id,
        memories_by_type={"fact": [_memory(title, content)]},
        split="file",
    )


def test_default_okf_export_uses_active_backend_data_dir(tmp_path, monkeypatch):
    """On-prem exports must not overwrite the same agent's cloud bundle."""
    monkeypatch.setattr(app_config.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(app_config.settings, "MEMANTO_BACKEND", "on-prem")

    result = OkfExportService().write_okf_bundle(
        agent_id="shared-agent",
        memories_by_type={"fact": [_memory("On-prem fact", "local-only")]},
        split="file",
    )

    expected = tmp_path / ".memanto" / "on-prem" / "exports" / "shared-agent_okf"
    assert result["output_path"] == str(expected.resolve())
    assert expected.exists()
    assert not (tmp_path / ".memanto" / "exports" / "shared-agent_okf").exists()


@pytest.mark.parametrize(
    ("client_cls", "client_module"),
    [
        (direct_mod.DirectClient, direct_mod),
        (sdk_mod.SdkClient, sdk_mod),
    ],
)
def test_okf_sync_fallback_reads_only_active_backend_cache(
    client_cls, client_module, tmp_path, monkeypatch
):
    """An on-prem outage must never copy a cloud OKF cache into a project."""
    monkeypatch.setattr(app_config.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(client_module.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(app_config.settings, "MEMANTO_BACKEND", "on-prem")

    cloud_exports = tmp_path / ".memanto" / "exports"
    onprem_exports = tmp_path / ".memanto" / "on-prem" / "exports"
    _write_cached_bundle(cloud_exports, "shared-agent", "Cloud fact", "cloud-secret")
    _write_cached_bundle(onprem_exports, "shared-agent", "On-prem fact", "local-only")

    client = client_cls(api_key="test-key")
    monkeypatch.setattr(
        client,
        "export_okf_bundle",
        MagicMock(side_effect=ConnectionError("backend down")),
    )

    project = tmp_path / f"project-{client_cls.__name__}"
    result = client.sync_okf_to_project(
        agent_id="shared-agent", project_dir=str(project)
    )

    rendered = "\n".join(
        path.read_text(encoding="utf-8") for path in (project / "okf").rglob("*.md")
    )
    assert result["source"] == "stale-cache"
    assert result["total_memories"] == 1
    assert "local-only" in rendered
    assert "cloud-secret" not in rendered
