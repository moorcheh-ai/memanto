"""
Tests for client-level session authorization enforcement.

Verifies that SdkClient and DirectClient enforce session validation across all
memory lifecycle operations, policy management, conflict resolution, daily
summaries, and project sync methods. Calls without an active session or targeting
a different agent must raise SessionError.
"""

from unittest.mock import MagicMock
import pytest

from memanto.app.utils.errors import SessionError
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


@pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
class TestClientSessionAuthorizationUnauthenticated:
    """Ensure all critical client methods require active agent session validation."""

    def test_get_policy_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.get_policy(agent_id="victim-agent")

    def test_set_policy_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.set_policy(agent_id="victim-agent", policy={"rules": []})

    def test_apply_policy_preset_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.apply_policy_preset(agent_id="victim-agent", name="assistant")

    def test_apply_policy_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.apply_policy(agent_id="victim-agent")

    def test_purge_expired_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.purge_expired(agent_id="victim-agent")

    def test_generate_daily_summary_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.generate_daily_summary(agent_id="victim-agent", date="2026-08-25")

    def test_generate_conflict_report_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.generate_conflict_report(agent_id="victim-agent", date="2026-08-25")

    def test_list_conflicts_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.list_conflicts(agent_id="victim-agent")

    def test_resolve_conflict_unauthorized_raises(self, client_cls):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.resolve_conflict(
                agent_id="victim-agent",
                date="2026-08-25",
                conflict_index=0,
                action="keep_newer",
            )

    def test_sync_memory_to_project_unauthorized_raises(self, client_cls, tmp_path):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.sync_memory_to_project(
                agent_id="victim-agent",
                project_dir=str(tmp_path),
            )

    def test_sync_okf_to_project_unauthorized_raises(self, client_cls, tmp_path):
        client = client_cls(api_key="test-api-key")
        with pytest.raises(SessionError, match="No active session|Session.*expired|activate_agent"):
            client.sync_okf_to_project(
                agent_id="victim-agent",
                project_dir=str(tmp_path),
            )


@pytest.mark.parametrize("client_cls", [SdkClient, DirectClient])
class TestClientSessionAuthorizationCrossAgentMismatch:
    """Ensure an active session for Agent A cannot be used to operate on Agent B."""

    def test_cross_agent_operations_rejected(self, client_cls, monkeypatch, tmp_path):
        client = client_cls(api_key="test-api-key")
        client.agent_id = "agent-a"
        client.session_token = "token-for-agent-a"

        def mock_validate(target_agent_id):
            if target_agent_id != client.agent_id:
                raise SessionError(
                    f"Active session is for agent '{client.agent_id}', not '{target_agent_id}'"
                )
            return MagicMock()

        monkeypatch.setattr(client, "_get_validated_session_for_agent", mock_validate)

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.get_policy(agent_id="agent-b")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.set_policy(agent_id="agent-b", policy={"rules": []})

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.apply_policy_preset(agent_id="agent-b", name="assistant")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.apply_policy(agent_id="agent-b")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.purge_expired(agent_id="agent-b")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.generate_daily_summary(agent_id="agent-b", date="2026-08-25")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.generate_conflict_report(agent_id="agent-b", date="2026-08-25")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.list_conflicts(agent_id="agent-b")

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.resolve_conflict(
                agent_id="agent-b",
                date="2026-08-25",
                conflict_index=0,
                action="keep_newer",
            )

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.sync_memory_to_project(
                agent_id="agent-b",
                project_dir=str(tmp_path),
            )

        with pytest.raises(SessionError, match="Active session is for agent 'agent-a', not 'agent-b'"):
            client.sync_okf_to_project(
                agent_id="agent-b",
                project_dir=str(tmp_path),
            )
