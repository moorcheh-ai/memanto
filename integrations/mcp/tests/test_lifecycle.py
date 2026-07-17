"""MCP agent/session lifecycle behavior."""

from unittest.mock import MagicMock

import pytest
from memanto.app.utils.errors import AgentNotFoundError

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.lifecycle import MemantoLifecycle


def _lifecycle_with_missing_agents(settings: MCPServerSettings):
    lifecycle = MemantoLifecycle(settings)
    client = MagicMock()
    client.get_agent.side_effect = AgentNotFoundError("missing")
    lifecycle._client = client
    return lifecycle, client


def test_arbitrary_agent_id_cannot_bypass_hidden_admin_tools(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-create is limited to the configured default agent."""
    monkeypatch.setenv("MEMANTO_DEFAULT_AGENT_ID", "project-agent")
    settings = MCPServerSettings()  # type: ignore[call-arg]
    lifecycle, client = _lifecycle_with_missing_agents(settings)

    with pytest.raises(AgentNotFoundError, match="Only the configured default agent"):
        lifecycle.ensure_ready("attacker-chosen-agent")

    client.create_agent.assert_not_called()
    client.activate_agent.assert_not_called()


def test_configured_default_agent_is_still_auto_created(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented default-agent convenience remains available."""
    monkeypatch.setenv("MEMANTO_DEFAULT_AGENT_ID", "project-agent")
    settings = MCPServerSettings()  # type: ignore[call-arg]
    lifecycle, client = _lifecycle_with_missing_agents(settings)

    assert lifecycle.ensure_ready("project-agent") == "project-agent"

    client.create_agent.assert_called_once_with(
        agent_id="project-agent",
        pattern="tool",
        description="Auto-created by memanto-mcp",
    )
    client.activate_agent.assert_called_once_with(
        agent_id="project-agent",
        duration_hours=None,
    )
