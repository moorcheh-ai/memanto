"""Tests for the public ``memanto.Memanto`` client wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    InvalidSessionTokenError,
    SessionExpiredError,
)


@pytest.fixture
def sdk():
    """Patch SdkClient, key resolution, and the session store."""
    client = MagicMock()
    session_service = MagicMock()
    session_service.get_session.return_value = None
    with (
        patch("memanto.client.SdkClient", return_value=client) as cls,
        patch("memanto.client._resolve_api_key", return_value="key"),
        patch(
            "memanto.app.services.session_service.get_session_service",
            return_value=session_service,
        ),
    ):
        client.session_service = session_service
        client.cls = cls
        yield client


def test_top_level_import():
    import memanto
    from memanto.client import Memanto

    assert memanto.Memanto is Memanto
    with pytest.raises(AttributeError):
        _ = memanto.NotAThing


def test_existing_agent_without_session_activates(sdk):
    from memanto import Memanto

    Memanto("bot", session_hours=2)

    sdk.cls.assert_called_once_with(api_key="key")
    sdk.create_agent.assert_not_called()
    sdk.activate_agent.assert_called_once_with("bot", duration_hours=2)


def test_live_session_is_reused_not_reactivated(sdk):
    from memanto import Memanto

    session = MagicMock(session_token="tok")
    session.is_active.return_value = True
    sdk.session_service.get_session.return_value = session

    Memanto("bot")

    sdk.activate_agent.assert_not_called()
    assert sdk.session_token == "tok"
    assert sdk.agent_id == "bot"


def test_missing_agent_is_auto_created(sdk):
    from memanto import Memanto

    sdk.get_agent.side_effect = AgentNotFoundError("nope")
    Memanto("bot", pattern="support")

    sdk.create_agent.assert_called_once_with("bot", pattern="support")
    sdk.activate_agent.assert_called_once()


def test_concurrent_create_is_tolerated(sdk):
    from memanto import Memanto

    sdk.get_agent.side_effect = AgentNotFoundError("nope")
    sdk.create_agent.side_effect = AgentAlreadyExistsError("exists")
    Memanto("bot")

    sdk.activate_agent.assert_called_once()


def test_missing_agent_without_auto_create_raises(sdk):
    from memanto import Memanto

    sdk.get_agent.side_effect = AgentNotFoundError("nope")
    with pytest.raises(AgentNotFoundError):
        Memanto("bot", auto_create=False)
    sdk.create_agent.assert_not_called()


def test_remember_defaults_title_from_content(sdk):
    from memanto import Memanto

    m = Memanto("bot")
    m.remember("short")
    assert sdk.remember.call_args.kwargs["title"] == "short"

    long = "x" * 60
    m.remember(long, type="fact", tags=["a"])
    kwargs = sdk.remember.call_args.kwargs
    assert kwargs["title"] == "x" * 50 + "..."
    assert kwargs["memory_type"] == "fact"
    assert kwargs["tags"] == ["a"]
    assert sdk.remember.call_args.args == ("bot",)


def test_read_methods_are_scoped_to_agent(sdk):
    from memanto import Memanto

    m = Memanto("bot")
    m.recall("q", limit=3, type=["fact"])
    sdk.recall.assert_called_once_with(
        "bot", "q", limit=3, type=["fact"], tags=None, min_similarity=None
    )
    m.answer("why?", temperature=0.1)
    assert sdk.answer.call_args.args == ("bot", "why?")
    assert sdk.answer.call_args.kwargs["temperature"] == 0.1
    m.recall_recent(limit=5)
    sdk.recall_recent.assert_called_once_with("bot", limit=5, type=None, tags=None)
    m.update_memory("m1", content="new")
    sdk.update_memory.assert_called_once_with("bot", "m1", {"content": "new"})
    m.delete_memory("m1")
    sdk.delete_memory.assert_called_once_with("bot", "m1")


def test_resolve_api_key_on_prem_needs_no_key(monkeypatch):
    from memanto.app.clients.backend import Backend
    from memanto.client import _resolve_api_key

    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    with patch("memanto.cli.config.manager.ConfigManager") as cm:
        cm.return_value.get_backend.return_value = Backend.ON_PREM
        assert _resolve_api_key(None) == "on-prem"


def test_resolve_api_key_cloud(monkeypatch):
    from memanto.app.clients.backend import Backend
    from memanto.app.config import settings
    from memanto.client import _resolve_api_key

    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "")
    with patch("memanto.cli.config.manager.ConfigManager") as cm:
        cm.return_value.get_backend.return_value = Backend.CLOUD
        cm.return_value.get_api_key.return_value = None
        with pytest.raises(ValueError, match="No Moorcheh API key"):
            _resolve_api_key(None)

        monkeypatch.setenv("MOORCHEH_API_KEY", "from-env")
        assert _resolve_api_key(None) == "from-env"
        monkeypatch.delenv("MOORCHEH_API_KEY")

        cm.return_value.get_api_key.return_value = "saved"
        assert _resolve_api_key(None) == "saved"


def test_explicit_key_does_not_leak_to_other_clients(monkeypatch):
    """A wrong api_key= on one instance must not become the process-wide key."""
    import os

    from memanto.app.clients.backend import Backend
    from memanto.app.config import settings
    from memanto.client import _resolve_api_key

    monkeypatch.setenv("MOORCHEH_API_KEY", "good")
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "good")
    with patch("memanto.cli.config.manager.ConfigManager") as cm:
        cm.return_value.get_backend.return_value = Backend.CLOUD
        assert _resolve_api_key("wrong") == "wrong"
        assert os.environ["MOORCHEH_API_KEY"] == "good"
        assert settings.MOORCHEH_API_KEY == "good"
        assert _resolve_api_key(None) == "good"


def test_explicit_key_fills_unset_global_key(monkeypatch):
    """With no configured key, the explicit key backs global-key services."""
    from memanto.app.clients.backend import Backend
    from memanto.app.config import settings
    from memanto.client import _resolve_api_key

    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "")
    with patch("memanto.cli.config.manager.ConfigManager") as cm:
        cm.return_value.get_backend.return_value = Backend.CLOUD
        _resolve_api_key("explicit")
    assert settings.MOORCHEH_API_KEY == "explicit"


def _live_session(token="tok"):
    session = MagicMock(session_token=token)
    session.is_active.return_value = True
    return session


def test_unverifiable_live_session_is_replaced(sdk):
    """A session file whose token no longer verifies (rotated secret) is not adopted."""
    from memanto import Memanto

    sdk.session_service.get_session.return_value = _live_session("bad")
    sdk.session_service.validate_session.side_effect = InvalidSessionTokenError("x")

    Memanto("bot")

    sdk.activate_agent.assert_called_once_with("bot", duration_hours=None)


@pytest.mark.parametrize("error", [SessionExpiredError, InvalidSessionTokenError])
def test_lost_session_is_recovered_and_call_retried_once(sdk, error):
    """Expiry or another client's activation must not break a long-lived instance."""
    from memanto import Memanto

    m = Memanto("bot")
    sdk.activate_agent.reset_mock()
    # Another client activated meanwhile: the session file now holds its token.
    sdk.session_service.get_session.return_value = _live_session("theirs")
    sdk.recall.side_effect = [error("lost"), {"memories": []}]

    assert m.recall("q") == {"memories": []}
    assert sdk.recall.call_count == 2
    assert sdk.session_token == "theirs"
    assert sdk._cached_session is None
    sdk.activate_agent.assert_not_called()


def test_persistent_session_error_is_raised_not_looped(sdk):
    from memanto import Memanto

    m = Memanto("bot")
    sdk.remember.side_effect = SessionExpiredError("still lost")

    with pytest.raises(SessionExpiredError):
        m.remember("x")
    assert sdk.remember.call_count == 2


def test_non_session_errors_are_not_retried(sdk):
    from memanto import Memanto

    m = Memanto("bot")
    sdk.remember.side_effect = ValueError("bad type")

    with pytest.raises(ValueError):
        m.remember("x", type="nonsense")
    assert sdk.remember.call_count == 1


def test_single_filter_values_are_wrapped_in_lists(sdk):
    from memanto import Memanto

    m = Memanto("bot")
    m.recall("q", type="fact", tags="diet")
    assert sdk.recall.call_args.kwargs["type"] == ["fact"]
    assert sdk.recall.call_args.kwargs["tags"] == ["diet"]
    m.recall_recent(type=["fact", "goal"])
    assert sdk.recall_recent.call_args.kwargs["type"] == ["fact", "goal"]
    m.remember("x", tags="diet")
    assert sdk.remember.call_args.kwargs["tags"] == ["diet"]


@pytest.mark.parametrize("delete_memories", [False, True])
def test_delete_agent_passes_memory_choice(sdk, delete_memories):
    from memanto import Memanto

    m = Memanto("bot")
    m.delete_agent(delete_memories=delete_memories)
    sdk.delete_agent.assert_called_once_with("bot", delete_memories=delete_memories)
