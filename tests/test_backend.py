"""Tests for the backend abstraction (cloud vs on-prem dispatcher)."""

from types import SimpleNamespace
from unittest.mock import patch

from memanto.app.clients.backend import (
    Backend,
    get_active_llm_model,
    parse_backend,
)


class TestBackendParse:
    def test_default_is_cloud(self):
        assert parse_backend("") == Backend.CLOUD
        assert parse_backend(None) == Backend.CLOUD

    def test_cloud(self):
        assert parse_backend("cloud") == Backend.CLOUD
        assert parse_backend("Cloud") == Backend.CLOUD

    def test_on_prem(self):
        assert parse_backend("on-prem") == Backend.ON_PREM
        assert parse_backend("ON-PREM") == Backend.ON_PREM

    def test_unknown_falls_back_to_cloud(self):
        assert parse_backend("hybrid") == Backend.CLOUD


class TestActiveLlmModel:
    """``get_active_llm_model`` is the single source of truth for which model
    ID gets sent to ``answer.generate``. Cloud returns the configured cloud
    default; on-prem reads ``llm_model`` from the on-prem state.json without
    any fallback to cloud values.
    """

    def test_cloud_returns_cloud_default(self, monkeypatch):
        from memanto.app.config import settings

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
        assert get_active_llm_model("anthropic.claude-sonnet-4-6") == (
            "anthropic.claude-sonnet-4-6"
        )

    def test_on_prem_reads_state_llm_model(self, tmp_path, monkeypatch):
        import json

        from memanto.app.config import settings

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
        # Redirect Path.home() so we don't depend on developer's real state.
        monkeypatch.setattr(
            "memanto.app.clients.backend.Path",
            type(
                "P",
                (),
                {"home": classmethod(lambda cls: tmp_path)},
            ),
        )
        state_dir = tmp_path / ".memanto" / "on-prem"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text(json.dumps({"llm_model": "qwen2.5"}))
        # On-prem must NOT fall back to the cloud default.
        assert get_active_llm_model("anthropic.claude-sonnet-4-6") == "qwen2.5"

    def test_on_prem_missing_state_returns_none(self, tmp_path, monkeypatch):
        from memanto.app.config import settings

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
        monkeypatch.setattr(
            "memanto.app.clients.backend.Path",
            type("P", (), {"home": classmethod(lambda cls: tmp_path)}),
        )
        # No state.json → return None so callers omit ai_model and let the
        # server use its own configured LLM (no silent cloud fallback).
        assert get_active_llm_model("anthropic.claude-sonnet-4-6") is None


class TestOnPremClient:
    def test_answer_generate_delegates_to_raw_client(self):
        """OnPremClient.answer.generate must pass through to the on-prem
        ``moorcheh.MoorchehClient`` — answer is supported on-prem since
        moorcheh-client v0.1.3."""
        from memanto.app.clients import onprem

        class _FakeAnswer:
            def __init__(self):
                self.called_with = None

            def generate(self, **kwargs):
                self.called_with = kwargs
                return {"answer": "ok", "namespace": kwargs.get("namespace")}

        class _FakeRaw:
            def __init__(self, base_url, timeout=None):
                self.base_url = base_url
                self.timeout = timeout
                self.namespaces = object()
                self.documents = object()
                self.similarity_search = object()
                self.answer = _FakeAnswer()
                self.vectors = object()
                self.files = object()

        with patch.object(onprem, "_import_raw_client", return_value=_FakeRaw):
            client = onprem.OnPremClient(base_url="http://localhost:8080")
            result = client.answer.generate(namespace="x", query="y")
            assert result == {"answer": "ok", "namespace": "x"}


class _FakeAnswerConfig:
    """ConfigManager stub that returns no explicit answer model."""

    def get_answer_config(self):
        """Return answer settings that exercise backend-default model handling."""
        return {
            "answer_limit": 10,
            "temperature": 0.7,
            "model": None,
            "kiosk_mode": False,
            "threshold": 0.15,
        }


class _CaptureAnswer:
    """Capture answer.generate kwargs while returning a canned response."""

    def __init__(self, answer="ok"):
        """Initialize the fake answer endpoint with a canned answer."""
        self.answer = answer
        self.call_kwargs = None

    def generate(self, **kwargs):
        """Record kwargs and return a Moorcheh-like answer payload."""
        self.call_kwargs = kwargs
        return {"answer": self.answer, "sources": []}


class _CaptureMoorcheh:
    """Small Moorcheh client stub with answer and documents surfaces."""

    def __init__(self, answer="ok"):
        """Initialize fake Moorcheh surfaces used by answer-generation tests."""
        self.answer = _CaptureAnswer(answer)
        self.documents = SimpleNamespace(get=lambda **kwargs: {"items": []})


def _stub_answer_client(client, moorcheh):
    """Patch a CLI client to bypass session validation and use the fake client."""
    client._get_validated_session_for_agent = lambda agent_id: SimpleNamespace(
        namespace=f"memanto_agent_{agent_id}"
    )
    client._get_moorcheh = lambda: moorcheh


class TestAnswerGenerateKwargs:
    """Regression tests for omitting unsupported answer.generate kwargs."""

    def test_direct_client_omits_none_ai_model_and_threshold(self, monkeypatch):
        """DirectClient should omit optional kwargs when config resolves to None."""
        from memanto.cli.client import direct_client as direct_mod

        monkeypatch.setattr(direct_mod, "ConfigManager", lambda: _FakeAnswerConfig())
        client = direct_mod.DirectClient(api_key="test-key")
        moorcheh = _CaptureMoorcheh()
        _stub_answer_client(client, moorcheh)

        client.answer("agent-1", "What changed?")

        assert moorcheh.answer.call_kwargs is not None
        assert "ai_model" not in moorcheh.answer.call_kwargs
        assert "threshold" not in moorcheh.answer.call_kwargs

    def test_sdk_client_omits_none_ai_model_and_threshold(self, monkeypatch):
        """SdkClient should omit optional kwargs when config resolves to None."""
        from memanto.cli.client import sdk_client as sdk_mod

        monkeypatch.setattr(sdk_mod, "ConfigManager", lambda: _FakeAnswerConfig())
        client = sdk_mod.SdkClient(api_key="test-key")
        moorcheh = _CaptureMoorcheh()
        _stub_answer_client(client, moorcheh)

        client.answer("agent-1", "What changed?")

        assert moorcheh.answer.call_kwargs is not None
        assert "ai_model" not in moorcheh.answer.call_kwargs
        assert "threshold" not in moorcheh.answer.call_kwargs

    def test_daily_summary_omits_none_ai_model(self, monkeypatch, tmp_path):
        """Daily summaries should let on-prem use the backend default model."""
        from memanto.app.config import settings
        from memanto.app.services import daily_analysis_service as daily_mod

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
        monkeypatch.setattr(
            "memanto.app.clients.backend.Path",
            type("P", (), {"home": classmethod(lambda cls: tmp_path)}),
        )

        sessions_dir = tmp_path / "sessions"
        summaries_dir = tmp_path / "summaries"
        sessions_dir.mkdir()
        (sessions_dir / "agent-1_2026-06-25_sess-1_summary.md").write_text(
            "# Session Summary\n\n- Local on-prem answer test\n"
        )
        moorcheh = _CaptureMoorcheh(answer="# Daily Summary\n\nok")
        monkeypatch.setattr(daily_mod, "get_moorcheh_client", lambda: moorcheh)

        service = daily_mod.DailyAnalysisService(
            sessions_dir=sessions_dir,
            summaries_dir=summaries_dir,
        )
        result = service.generate_summary("agent-1", "2026-06-25")

        assert result["status"] == "success"
        assert moorcheh.answer.call_kwargs is not None
        assert "ai_model" not in moorcheh.answer.call_kwargs

    def test_conflict_report_omits_none_ai_model(self, monkeypatch, tmp_path):
        """Conflict reports should let on-prem use the backend default model."""
        from memanto.app.config import settings
        from memanto.app.services import daily_analysis_service as daily_mod

        monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
        monkeypatch.setattr(
            "memanto.app.clients.backend.Path",
            type("P", (), {"home": classmethod(lambda cls: tmp_path)}),
        )
        monkeypatch.setattr(
            daily_mod.Path,
            "home",
            classmethod(lambda cls: tmp_path),
        )

        sessions_dir = tmp_path / "sessions"
        summaries_dir = tmp_path / "summaries"
        sessions_dir.mkdir()
        (sessions_dir / "agent-1_2026-06-25_sess-1_summary.md").write_text(
            "# Session Summary\n\n- Local on-prem conflict test\n"
        )
        moorcheh = _CaptureMoorcheh(answer="[]")
        monkeypatch.setattr(daily_mod, "get_moorcheh_client", lambda: moorcheh)

        service = daily_mod.DailyAnalysisService(
            sessions_dir=sessions_dir,
            summaries_dir=summaries_dir,
        )
        result = service.generate_conflict_report("agent-1", "2026-06-25")

        assert result["status"] == "success"
        assert moorcheh.answer.call_kwargs is not None
        assert "ai_model" not in moorcheh.answer.call_kwargs


class TestSingletonDispatch:
    def test_cloud_returns_cloud_client(self):
        """On cloud, the dispatcher must not return an OnPremClient."""
        from memanto.app.clients import moorcheh as mclients
        from memanto.app.clients import onprem
        from memanto.app.config import settings

        original = settings.MEMANTO_BACKEND
        settings.MEMANTO_BACKEND = "cloud"
        mclients.moorcheh_client.reset_client()
        try:
            client = mclients.moorcheh_client.get_client()
            assert not isinstance(client, onprem.OnPremClient)
        finally:
            settings.MEMANTO_BACKEND = original
            mclients.moorcheh_client.reset_client()

    def test_on_prem_returns_on_prem_client(self):
        from memanto.app.clients import moorcheh as mclients
        from memanto.app.clients import onprem
        from memanto.app.config import settings

        original = settings.MEMANTO_BACKEND
        settings.MEMANTO_BACKEND = "on-prem"
        mclients.moorcheh_client.reset_client()

        class _FakeRaw:
            def __init__(self, base_url, timeout=None):
                self.base_url = base_url
                self.timeout = timeout
                # OnPremClient binds these from the raw client; stub them so
                # construction succeeds without a real on-prem server.
                self.namespaces = object()
                self.documents = object()
                self.similarity_search = object()
                self.answer = object()
                self.vectors = object()
                self.files = object()

        try:
            with patch.object(onprem, "_import_raw_client", return_value=_FakeRaw):
                client = mclients.moorcheh_client.get_client()
                assert isinstance(client, onprem.OnPremClient)
        finally:
            settings.MEMANTO_BACKEND = original
            mclients.moorcheh_client.reset_client()


class TestDataDirRouting:
    def test_cloud_uses_default(self, tmp_path, monkeypatch):
        from memanto.app import config as app_config

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(app_config.settings, "MEMANTO_BACKEND", "cloud")
        # Path.home() is cached via os.path.expanduser in some envs; force it
        monkeypatch.setattr(app_config.Path, "home", classmethod(lambda cls: tmp_path))
        assert app_config.get_data_dir() == tmp_path / ".memanto"

    def test_on_prem_uses_subdir(self, tmp_path, monkeypatch):
        from memanto.app import config as app_config

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(app_config.settings, "MEMANTO_BACKEND", "on-prem")
        monkeypatch.setattr(app_config.Path, "home", classmethod(lambda cls: tmp_path))
        result = app_config.get_data_dir()
        assert result == tmp_path / ".memanto" / "on-prem"
        assert result.exists()
