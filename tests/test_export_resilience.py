"""Regression coverage: ``export_memory_md`` must not silently write an
empty export when every ``recall`` call fails (e.g. the on-prem backend is
unreachable), and ``sync_memory_to_project`` must fall back to a
previous good export instead of overwriting a project's ``MEMORY.md`` with
nothing.

Before this fix, a total-outage export produced an all-empty
``memories_by_type`` (each per-type ``recall`` exception was swallowed) and
still wrote it out — every call to ``memanto memory sync`` during a brief
backend outage silently wiped the agent's exported context and the
project's ``MEMORY.md``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import memanto.cli.client.direct_client as direct_mod
import memanto.cli.client.sdk_client as sdk_mod
from memanto.app.services.memory_export_service import MEMORY_TYPE_ORDER

DirectClient = direct_mod.DirectClient
SdkClient = sdk_mod.SdkClient


def _build_client(client_cls, monkeypatch, tmp_path, api_key="test-key"):
    """Construct *client_cls* with session validation stubbed out and
    ``Path.home()`` redirected to *tmp_path*. ``Path`` is the same class
    object everywhere it's imported, so this one patch also covers
    ``MemoryExportService`` and the scoped sync cache. Only the session and
    recall service boundaries are controlled; export and sync use real files.
    """
    module = direct_mod if client_cls is DirectClient else sdk_mod
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    client = client_cls(api_key=api_key)
    monkeypatch.setattr(
        client, "_get_validated_session_for_agent", lambda agent_id: None
    )
    return client


def _seed_sync_cache(client, monkeypatch, tmp_path, content="good content"):
    def recall(agent_id, query, limit, type):
        return {
            "memories": [{"title": "Saved memory", "content": content}]
            if type == ["fact"]
            else []
        }

    monkeypatch.setattr(client, "recall", MagicMock(side_effect=recall))
    result = client.sync_memory_to_project("test-agent", str(tmp_path / "seed"))
    assert result["source"] == "fresh"
    assert result["total_memories"] == 1


class TestExportMemoryMdRefusesEmptyOnTotalFailure:
    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_raises_when_every_recall_fails(self, client_cls, monkeypatch, tmp_path):
        client = _build_client(client_cls, monkeypatch, tmp_path)
        monkeypatch.setattr(
            client, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        with pytest.raises(ConnectionError, match="unreachable"):
            client.export_memory_md(agent_id="test-agent")

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_partial_failure_refuses_incomplete_export(
        self, client_cls, monkeypatch, tmp_path
    ):
        """One failed type must not be represented as a genuinely empty type."""
        client = _build_client(client_cls, monkeypatch, tmp_path)

        def fake_recall(agent_id, query, limit, type):
            if type == [MEMORY_TYPE_ORDER[0]]:
                raise ConnectionError("flaky")
            return {"memories": [{"content": "ok"}]}

        monkeypatch.setattr(client, "recall", MagicMock(side_effect=fake_recall))

        with pytest.raises(
            ConnectionError,
            match=f"incomplete.*{MEMORY_TYPE_ORDER[0]}|{MEMORY_TYPE_ORDER[0]}.*incomplete",
        ):
            client.export_memory_md(agent_id="test-agent")


class TestSyncFallsBackToCache:
    """Sync refreshes first, so a cached export is only reused when the
    refresh fails — never in place of memories written this session."""

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_cache_used_when_backend_down(self, client_cls, monkeypatch, tmp_path):
        client = _build_client(client_cls, monkeypatch, tmp_path)
        _seed_sync_cache(client, monkeypatch, tmp_path)
        # A new client with the same credential can reuse the previous sync.
        client = _build_client(client_cls, monkeypatch, tmp_path)

        monkeypatch.setattr(
            client, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        project_dir = tmp_path / "project"
        result = client.sync_memory_to_project(
            agent_id="test-agent", project_dir=str(project_dir)
        )

        client.recall.assert_called()
        assert result["source"] == "stale-cache"
        assert result["total_memories"] == 1
        written = (project_dir / "MEMORY.md").read_text(encoding="utf-8")
        assert "good content" in written

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_fresh_export_replaces_stale_cache(self, client_cls, monkeypatch, tmp_path):
        """A cache written before this session must not shadow new memories."""
        client = _build_client(client_cls, monkeypatch, tmp_path)
        _seed_sync_cache(client, monkeypatch, tmp_path, "stale content")

        monkeypatch.setattr(
            client,
            "recall",
            MagicMock(return_value={"memories": [{"content": "fresh content"}]}),
        )

        project_dir = tmp_path / "project"
        result = client.sync_memory_to_project(
            agent_id="test-agent", project_dir=str(project_dir)
        )

        assert result["source"] == "fresh"
        written = (project_dir / "MEMORY.md").read_text(encoding="utf-8")
        assert "stale content" not in written
        assert "fresh content" in written

    def test_raises_when_no_cache_and_backend_down(self, monkeypatch, tmp_path):
        client = _build_client(SdkClient, monkeypatch, tmp_path)
        monkeypatch.setattr(
            client, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        with pytest.raises(ConnectionError):
            client.sync_memory_to_project(
                agent_id="test-agent", project_dir=str(tmp_path / "project")
            )

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_cache_is_not_reused_across_credentials(
        self, client_cls, monkeypatch, tmp_path
    ):
        account_a = _build_client(client_cls, monkeypatch, tmp_path, "account-a-key")
        _seed_sync_cache(account_a, monkeypatch, tmp_path, "account A private marker")
        account_b = _build_client(client_cls, monkeypatch, tmp_path, "account-b-key")
        monkeypatch.setattr(
            account_b, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )
        project = tmp_path / "account-b-project"
        project.mkdir()
        target = project / "MEMORY.md"
        target.write_text("account B existing memory", encoding="utf-8")

        with pytest.raises(ConnectionError):
            account_b.sync_memory_to_project("test-agent", str(project))

        assert target.read_text(encoding="utf-8") == "account B existing memory"
        cache_paths = list((tmp_path / ".memanto" / "exports").rglob("*.md"))
        assert len(cache_paths) == 1
        assert all("account-a-key" not in str(path) for path in cache_paths)

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    @pytest.mark.parametrize("backend", ["cloud", "on-prem"])
    def test_cache_is_not_reused_after_endpoint_switch(
        self, client_cls, backend, monkeypatch, tmp_path
    ):
        from memanto.app.config import settings

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", backend)
        if backend == "cloud":
            monkeypatch.setenv("MOORCHEH_BASE_URL", "https://deployment-a.invalid/v1")
        else:
            monkeypatch.setattr(
                settings, "MOORCHEH_ONPREM_URL", "http://deployment-a.invalid:8080"
            )
        first = _build_client(client_cls, monkeypatch, tmp_path)
        _seed_sync_cache(first, monkeypatch, tmp_path, "deployment A private marker")

        if backend == "cloud":
            monkeypatch.setenv("MOORCHEH_BASE_URL", "https://deployment-b.invalid/v1")
        else:
            monkeypatch.setattr(
                settings, "MOORCHEH_ONPREM_URL", "http://deployment-b.invalid:8080"
            )
        second = _build_client(client_cls, monkeypatch, tmp_path)
        monkeypatch.setattr(
            second, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        with pytest.raises(ConnectionError):
            second.sync_memory_to_project("test-agent", str(tmp_path / "second"))
        assert not (tmp_path / "second" / "MEMORY.md").exists()

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_on_prem_cache_ignores_unused_api_key(
        self, client_cls, monkeypatch, tmp_path
    ):
        from memanto.app.config import settings

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
        first = _build_client(client_cls, monkeypatch, tmp_path, "unused-key-a")
        _seed_sync_cache(first, monkeypatch, tmp_path)
        second = _build_client(client_cls, monkeypatch, tmp_path, "unused-key-b")
        monkeypatch.setattr(
            second, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        result = second.sync_memory_to_project("test-agent", str(tmp_path / "second"))
        assert result["source"] == "stale-cache"
        assert "good content" in (tmp_path / "second" / "MEMORY.md").read_text()

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_cache_uses_existing_transport_identity(
        self, client_cls, monkeypatch, tmp_path
    ):
        client = _build_client(client_cls, monkeypatch, tmp_path)
        client._moorcheh = SimpleNamespace(
            api_key="transport-key", base_url="https://transport.invalid/v1"
        )
        _seed_sync_cache(client, monkeypatch, tmp_path)
        monkeypatch.setenv("MOORCHEH_BASE_URL", "https://changed-env.invalid/v1")
        monkeypatch.setattr(client, "api_key", "changed-client-key")
        monkeypatch.setattr(
            client, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        result = client.sync_memory_to_project("test-agent", str(tmp_path / "second"))
        assert result["source"] == "stale-cache"
        assert "good content" in (tmp_path / "second" / "MEMORY.md").read_text()

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_explicit_export_keeps_path_but_is_not_adopted_as_sync_cache(
        self, client_cls, monkeypatch, tmp_path
    ):
        client = _build_client(client_cls, monkeypatch, tmp_path)
        monkeypatch.setattr(
            client,
            "recall",
            MagicMock(return_value={"memories": [{"content": "manual export"}]}),
        )
        exported = client.export_memory_md("test-agent")
        export_path = tmp_path / ".memanto" / "exports" / "test-agent_memory.md"
        assert exported["output_path"] == str(export_path)
        original = export_path.read_bytes()
        monkeypatch.setattr(
            client, "recall", MagicMock(side_effect=ConnectionError("backend down"))
        )

        with pytest.raises(ConnectionError):
            client.sync_memory_to_project("test-agent", str(tmp_path / "project"))
        assert export_path.read_bytes() == original
        assert not (tmp_path / "project" / "MEMORY.md").exists()

    @pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
    def test_rejects_path_traversal_before_cache_lookup(
        self, client_cls, monkeypatch, tmp_path
    ):
        client = _build_client(client_cls, monkeypatch, tmp_path)

        # Invalid identifiers must be rejected before the shared cache reads state.
        mock_get_data_dir = MagicMock()
        monkeypatch.setattr(
            "memanto.cli.client.memory_cache.get_data_dir", mock_get_data_dir
        )

        with pytest.raises(ValueError, match="invalid characters"):
            client.sync_memory_to_project(
                agent_id="../outside", project_dir=str(tmp_path / "project")
            )

        mock_get_data_dir.assert_not_called()
