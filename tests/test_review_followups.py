"""Regression tests for issues raised in review of the merged PR batch.

Each test fails against the pre-fix source:

* ``get_active_session`` propagated ``ValueError`` from ``validate_safe_id``
  when the active marker was empty or corrupt, instead of reporting "no active
  session" the way its ``OSError`` path already did.
* ``get_active_llm_model`` called ``.get`` on whatever ``state.json`` decoded
  to, so a valid-JSON-but-not-an-object file raised ``AttributeError`` rather
  than degrading to ``None`` (its sibling ``get_active_embedding_model``
  already guarded this).
"""

import json

import pytest

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.services.session_service import SessionService


@pytest.fixture
def service(tmp_path):
    return SessionService(secret_key="k" * 32, sessions_dir=tmp_path / "sessions")


class TestCorruptActiveMarker:
    """An unreadable active marker means "no active session", never a crash."""

    @pytest.mark.parametrize("marker", ["", "   ", "../escape", "bad/id", "a" * 300])
    def test_corrupt_marker_reports_no_active_session(self, service, marker):
        service._harden_session_storage()
        (service.sessions_dir / "active").write_text(marker, encoding="utf-8")

        assert service.get_active_session() is None

    def test_missing_marker_still_reports_none(self, service):
        service._harden_session_storage()
        assert service.get_active_session() is None

    def test_valid_marker_still_resolves(self, service):
        service.create_session(agent_id="goodagent")
        active = service.get_active_session()
        assert active is not None
        assert active.agent_id == "goodagent"


class TestMalformedOnPremState:
    """A valid-JSON-but-non-object state.json degrades to None, not AttributeError."""

    @pytest.mark.parametrize(
        "payload", [[], "a string", 42, None, [{"llm_model": "x"}]]
    )
    def test_non_object_state_returns_none(self, tmp_path, monkeypatch, payload):
        monkeypatch.setenv("MEMANTO_BACKEND", "on-prem")
        monkeypatch.setattr(
            "memanto.app.config.settings.MEMANTO_BACKEND", "on-prem", raising=False
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        state = tmp_path / ".memanto" / "on-prem" / "state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(payload), encoding="utf-8")

        assert get_active_llm_model("cloud-default") is None

    def test_well_formed_state_still_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "memanto.app.config.settings.MEMANTO_BACKEND", "on-prem", raising=False
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        state = tmp_path / ".memanto" / "on-prem" / "state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"llm_model": "llama3"}), encoding="utf-8")

        assert get_active_llm_model("cloud-default") == "llama3"
