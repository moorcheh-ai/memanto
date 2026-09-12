"""
Security: tenant isolation of the Moorcheh client dispatch.

MEMANTO is single-tenant per server instance: sessions are created under the
configured server key, so memory operations must stay bound to it. A
caller-presented ``X-Api-Key`` must not silently redirect memory operations
to a different tenant's namespace — the server never verifies that the
presented key owns the agent's namespace, so a mismatched key is ignored and
the server key is used instead.
"""

from unittest.mock import patch

from memanto.app.clients import moorcheh as mclients
from memanto.app.config import settings


class _RecordingClient:
    """Fake MoorchehClient that records the api_key it was constructed with."""

    def __init__(self, api_key: str):
        self.api_key = api_key


class TestTenantIsolation:
    def test_mismatched_caller_key_does_not_redirect_tenant(self):
        """A caller-presented X-Api-Key that differs from the server key must
        not switch the tenant the server operates in. The dependency resolves
        it back to the server key, so memory ops stay in the tenant that owns
        the agent's namespace."""
        original_key = settings.MOORCHEH_API_KEY
        settings.MOORCHEH_API_KEY = "server-key-A"
        mclients.moorcheh_client.reset_client()
        try:
            with patch.object(mclients, "MoorchehClient", _RecordingClient):
                # Server-side client (no header) is bound to the server key.
                server_client = mclients.get_moorcheh_client(api_key=None)
                assert server_client.api_key == "server-key-A"

                # A caller presenting a *different* tenant's key must resolve
                # back to the server key — not a client bound to tenant B.
                caller_client = mclients.get_moorcheh_client(api_key="tenant-key-B")
                assert caller_client.api_key == "server-key-A"
                assert caller_client is server_client
        finally:
            settings.MOORCHEH_API_KEY = original_key
            mclients.moorcheh_client.reset_client()

    def test_matching_caller_key_is_honored(self):
        """A caller presenting the server's own key is honored (no behavior
        change for legitimate callers)."""
        original_key = settings.MOORCHEH_API_KEY
        settings.MOORCHEH_API_KEY = "server-key-A"
        mclients.moorcheh_client.reset_client()
        try:
            with patch.object(mclients, "MoorchehClient", _RecordingClient):
                client = mclients.get_moorcheh_client(api_key="server-key-A")
                assert client.api_key == "server-key-A"
        finally:
            settings.MOORCHEH_API_KEY = original_key
            mclients.moorcheh_client.reset_client()

    def test_session_token_is_not_tenant_bound(self):
        """Session tokens carry agent_id/namespace but no tenant binding, so
        the server key (not a caller header) is what keeps memory ops in the
        owning tenant."""
        from memanto.app.services.session_service import SessionService

        svc = SessionService(secret_key="x" * 32)
        session = svc.create_session(agent_id="agent-x", duration_hours=1)
        token = svc.validate_session(session.session_token)
        assert token.agent_id == "agent-x"
        assert token.namespace == "memanto_agent_agent-x"
        assert not hasattr(token, "tenant_id")

    def test_route_dependency_forwards_resolved_key(self):
        """The FastAPI dependency reads X-Api-Key from the request and passes
        the *resolved* key to the dispatcher — a mismatched header resolves to
        None (server key) before it can switch tenants."""
        dep = mclients.get_moorcheh_client
        metadata = dep.__annotations__["api_key"].__metadata__
        assert any(getattr(m, "alias", None) == "X-Api-Key" for m in metadata)

        with patch.object(
            mclients.moorcheh_client, "get_client", return_value=object()
        ) as dispatcher:
            mclients.get_moorcheh_client(api_key="tenant-key-B")
            dispatcher.assert_called_once_with(api_key=None)
