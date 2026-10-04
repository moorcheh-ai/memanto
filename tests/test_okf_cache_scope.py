"""Automatic OKF fallback must use only a previous sync for this backend identity."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memanto.app.config import settings
from memanto.app.utils.errors import SessionExpiredError
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.migrate.okf_loader import load_okf_bundle


@pytest.fixture(params=[DirectClient, SdkClient])
def client_factory(request, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    monkeypatch.delenv("MOORCHEH_BASE_URL", raising=False)

    def build(api_key="synthetic-tenant-a"):
        client = request.param(api_key=api_key)
        monkeypatch.setattr(client, "_get_validated_session_for_agent", lambda _: None)
        return client

    return build


def _memories(client, monkeypatch, marker="tenant-a-private-marker"):
    def recall(*, agent_id, query, limit, type):
        return {
            "memories": [{"id": "fact-1", "title": "Private fact", "content": marker}]
            if type == ["fact"]
            else []
        }

    monkeypatch.setattr(client, "recall", MagicMock(side_effect=recall))


def _offline(client, monkeypatch):
    monkeypatch.setattr(
        client, "recall", MagicMock(side_effect=ConnectionError("offline"))
    )


def _seed(client, monkeypatch, tmp_path):
    _memories(client, monkeypatch)
    result = client.sync_okf_to_project("shared-agent", str(tmp_path / "seed"))
    assert result["source"] == "fresh"
    assert result["total_memories"] == 1


def _existing_project(tmp_path):
    project = tmp_path / "destination"
    bundle = project / "okf"
    bundle.mkdir(parents=True)
    sentinel = bundle / "keep.txt"
    sentinel.write_text("keep existing project context", encoding="utf-8")
    return project, sentinel


def test_rejects_another_credentials_bundle(client_factory, monkeypatch, tmp_path):
    _seed(client_factory(), monkeypatch, tmp_path)
    other = client_factory("synthetic-tenant-b")
    _offline(other, monkeypatch)
    project, sentinel = _existing_project(tmp_path)

    with pytest.raises(ConnectionError):
        other.sync_okf_to_project("shared-agent", str(project))
    assert sentinel.read_text(encoding="utf-8") == "keep existing project context"


@pytest.mark.parametrize("backend", ["cloud", "on-prem"])
def test_same_credentials_reuse_last_successful_sync(
    client_factory, monkeypatch, tmp_path, backend
):
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", backend)
    _seed(client_factory(), monkeypatch, tmp_path)
    restarted = client_factory()
    _offline(restarted, monkeypatch)

    result = restarted.sync_okf_to_project(
        "shared-agent", str(tmp_path / "destination")
    )
    assert result["source"] == "stale-cache"
    assert result["total_memories"] == 1
    memories = load_okf_bundle(Path(result["output_path"]))["memories"]
    assert any("tenant-a-private-marker" in str(memory) for memory in memories)


@pytest.mark.parametrize("backend", ["cloud", "on-prem"])
def test_rejects_another_backend_endpoint(
    client_factory, monkeypatch, tmp_path, backend
):
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", backend)
    if backend == "cloud":
        monkeypatch.setenv("MOORCHEH_BASE_URL", "https://tenant-a.invalid/v1")
    else:
        monkeypatch.setattr(settings, "MOORCHEH_ONPREM_URL", "http://tenant-a.invalid")
    _seed(client_factory(), monkeypatch, tmp_path)
    if backend == "cloud":
        monkeypatch.setenv("MOORCHEH_BASE_URL", "https://tenant-b.invalid/v1")
    else:
        monkeypatch.setattr(settings, "MOORCHEH_ONPREM_URL", "http://tenant-b.invalid")
    other = client_factory()
    _offline(other, monkeypatch)
    project, sentinel = _existing_project(tmp_path)

    with pytest.raises(ConnectionError):
        other.sync_okf_to_project("shared-agent", str(project))
    assert sentinel.read_text(encoding="utf-8") == "keep existing project context"


def test_manual_exports_keep_paths_but_are_not_fallbacks(
    client_factory, monkeypatch, tmp_path
):
    client = client_factory()
    _memories(client, monkeypatch)
    default = client.export_okf_bundle("shared-agent")
    explicit_dir = tmp_path / ".memanto" / "chosen-export"
    explicit = client.export_okf_bundle("shared-agent", output_dir=str(explicit_dir))
    assert (
        Path(default["output_path"])
        == tmp_path / ".memanto" / "exports" / "shared-agent_okf"
    )
    assert Path(explicit["output_path"]) == explicit_dir
    assert default["total_memories"] == explicit["total_memories"] == 1
    _offline(client, monkeypatch)

    with pytest.raises(ConnectionError):
        client.sync_okf_to_project("shared-agent", str(tmp_path / "destination"))
    assert len(load_okf_bundle(explicit_dir)["memories"]) == 1


def test_authorization_denial_is_not_an_offline_fallback(
    client_factory, monkeypatch, tmp_path
):
    client = client_factory()
    _seed(client, monkeypatch, tmp_path)
    validation = MagicMock(side_effect=SessionExpiredError("authorization revoked"))
    monkeypatch.setattr(client, "_get_validated_session_for_agent", validation)
    project, sentinel = _existing_project(tmp_path)

    with pytest.raises(SessionExpiredError, match="authorization revoked"):
        client.sync_okf_to_project("shared-agent", str(project))
    assert sentinel.read_text(encoding="utf-8") == "keep existing project context"
