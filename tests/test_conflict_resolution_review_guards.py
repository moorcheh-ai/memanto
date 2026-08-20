from pathlib import Path


def test_conflict_resolution_requires_validated_agent_session():
    source = Path("memanto/cli/client/direct_client.py").read_text(encoding="utf-8")
    start = source.index("    def resolve_conflict(")
    end = source.index("    def ", start + 8)
    body = source[start:end]
    assert "self._get_validated_session_for_agent(agent_id)" in body
    assert "namespace = session.namespace" in body


def test_unverified_conflicts_disable_destructive_ui_actions():
    cli = Path("memanto/cli/commands/memory.py").read_text(encoding="utf-8")
    ui = Path("memanto/app/ui/static/index.html").read_text(encoding="utf-8")
    assert "Destructive resolution disabled for this unverified conflict" in cli
    assert "binding.status === 'blocked'" in ui
    assert "btn.disabled = true" in ui
