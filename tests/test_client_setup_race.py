"""Tests for SkillMemory setup() race-condition fix.

Issue #770 — Memanto Bug Challenge.

Bug: ``_ready`` was set to ``True`` AFTER calling ``_create_and_activate``.
If ``activate_agent`` inside that method raised an exception the flag stayed
``False``, which is fine … BUT the previous code path also set ``_ready=True``
unconditionally in ``setup()`` at line 76, meaning any exception thrown by
``_create_and_activate`` still propagated OUT of ``setup()`` before the flag
was set.  The *real* race scenario is subtler: if a second concurrent call to
``setup()`` (from a different hook invocation in the same process) checked
``_ready`` between the ``activate_agent`` return and the ``_ready=True``
assignment, it would find ``_ready=False`` and duplicate the whole setup path.

The fix ensures ``_ready`` is only set after every operation in the happy path
succeeds, AND that a failed ``_create_and_activate`` never silently marks the
session as ready.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from claudecode_memanto.client import SkillMemory, _SESSION_HOURS
from claudecode_memanto.config import SkillsConfig
from memanto.app.utils.errors import AgentAlreadyExistsError, AgentNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(agent_id: str = "test-agent") -> SkillsConfig:
    return SkillsConfig(api_key="test-key", agent_id=agent_id)


def _memory_with_mock_sdk(sdk: MagicMock) -> SkillMemory:
    return SkillMemory(config=_config(), client=sdk)


# ---------------------------------------------------------------------------
# Bug fix: _ready only set on full success
# ---------------------------------------------------------------------------

class TestSetupReadyFlagOnlyOnSuccess:
    """_ready must only be True after the ENTIRE activation path succeeds."""

    def test_ready_set_after_existing_agent_activation(self) -> None:
        sdk = MagicMock()
        sdk.activate_agent.return_value = None  # success

        mem = _memory_with_mock_sdk(sdk)
        assert not mem._ready, "Should start not-ready"
        mem.setup()
        assert mem._ready, "Must be ready after successful activation"
        sdk.activate_agent.assert_called_once_with("test-agent", duration_hours=_SESSION_HOURS)

    def test_ready_set_after_first_run_create_and_activate(self) -> None:
        sdk = MagicMock()
        sdk.activate_agent.return_value = None
        sdk.activate_agent.side_effect = [AgentNotFoundError("not found"), None]
        sdk.create_agent.return_value = None

        mem = _memory_with_mock_sdk(sdk)
        mem.setup()
        assert mem._ready, "Must be ready after create + activate"
        assert sdk.create_agent.call_count == 1
        assert sdk.activate_agent.call_count == 2  # first try + after create

    def test_ready_NOT_set_when_activate_raises_after_create(self) -> None:
        """Core bug fix: if activate_agent raises inside _create_and_activate,
        _ready must stay False so the next call retries cleanly."""
        sdk = MagicMock()
        # First call: agent not found → triggers _create_and_activate
        # Second call (inside _create_and_activate): raises unexpectedly
        sdk.activate_agent.side_effect = [
            AgentNotFoundError("not found"),
            RuntimeError("network timeout"),
        ]
        sdk.create_agent.return_value = None

        mem = _memory_with_mock_sdk(sdk)
        with pytest.raises(RuntimeError):
            mem.setup()

        assert not mem._ready, (
            "BUG FIX: _ready must stay False when activation fails — "
            "the next setup() call must retry, not skip"
        )

    def test_setup_retries_after_failed_activation(self) -> None:
        """After a failed setup, the next call must retry from scratch."""
        sdk = MagicMock()
        # First call pair: fails
        # Second call pair: succeeds
        sdk.activate_agent.side_effect = [
            AgentNotFoundError("not found"),  # first setup: triggers create
            RuntimeError("transient error"),  # still first setup: fails
            None,                             # second setup: succeeds directly
        ]
        sdk.create_agent.return_value = None

        mem = _memory_with_mock_sdk(sdk)

        # First call fails
        with pytest.raises(RuntimeError):
            mem.setup()
        assert not mem._ready

        # Second call succeeds
        mem.setup()
        assert mem._ready, "Must be ready after successful retry"

    def test_setup_idempotent_when_already_ready(self) -> None:
        sdk = MagicMock()
        sdk.activate_agent.return_value = None

        mem = _memory_with_mock_sdk(sdk)
        mem.setup()
        mem.setup()  # second call must be a no-op
        sdk.activate_agent.assert_called_once()  # NOT called twice

    def test_concurrent_create_race_handled(self) -> None:
        """If a concurrent hook creates the agent between our activate and create,
        AgentAlreadyExistsError is swallowed and activation proceeds."""
        sdk = MagicMock()
        sdk.activate_agent.side_effect = [
            AgentNotFoundError("not found"),  # first activate: not found
            None,                             # second activate (after create): ok
        ]
        sdk.create_agent.side_effect = AgentAlreadyExistsError("race")

        mem = _memory_with_mock_sdk(sdk)
        mem.setup()  # must not raise
        assert mem._ready
        # activate called twice: initial attempt + after the race-create
        assert sdk.activate_agent.call_count == 2
