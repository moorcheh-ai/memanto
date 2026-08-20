"""Regression guards for conflict-resolution authorization and fail-closed UI behavior."""

from pathlib import Path


def test_conflict_resolution_requires_validated_agent_session():
    """Resolver must authorize the requested agent and use the validated namespace."""
    source = Path("memanto/cli/client/direct_client.py").read_text(encoding="utf-8")
    start = source.index("    def resolve_conflict(")
    end = source.index("    def ", start + 8)
    body = source[start:end]
    assert "self._get_validated_session_for_agent(agent_id)" in body
    assert "namespace = session.namespace" in body


def test_api_route_propagates_validated_session_to_direct_client():
    """FastAPI route must pass its validated session into DirectClient before resolution."""
    route = Path("memanto/app/routes/memory.py").read_text(encoding="utf-8")
    assert "direct_client.agent_id = agent_id" in route
    assert "direct_client.session_token = session.session_token" in route
    assert "direct_client._cached_session = session" in route
    assert "direct_client.resolve_conflict" in route


def test_unverified_conflicts_disable_destructive_ui_actions():
    """Any binding state other than bound must be presented as unverified."""
    cli = Path("memanto/cli/commands/memory.py").read_text(encoding="utf-8")
    ui = Path("memanto/app/ui/static/index.html").read_text(encoding="utf-8")
    assert 'binding.get("status") != "bound"' in cli
    assert "Destructive resolution is disabled for this unverified conflict" in cli
    assert "binding.status !== 'bound'" in ui
    assert "btn.disabled = true" in ui


def test_unverified_cli_keeps_only_non_destructive_resolution_available():
    """Unverified conflicts must still offer Keep Both, Skip, and Quit."""
    cli = Path("memanto/cli/commands/memory.py").read_text(encoding="utf-8")
    assert "Keep Both, Skip, and Quit remain available" in cli
    assert 'action_map = {"3": "keep_both"}' in cli
    assert '_opt("3", "Keep both", None)' in cli
