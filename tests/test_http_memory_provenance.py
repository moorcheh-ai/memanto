"""Focused regression for HTTP memory provenance defaults."""

from memanto.app.models import BatchRememberItem, RememberRequest


def test_http_memory_provenance_defaults_follow_source_authority():
    agent_default = BatchRememberItem(content="generated preference")
    assert agent_default.source == "agent"
    assert agent_default.provenance == "inferred"

    user_default = RememberRequest(content="user stated preference", source="user")
    assert user_default.provenance == "explicit_statement"

    explicit_agent = BatchRememberItem(
        content="relayed user statement",
        source="agent",
        provenance="explicit_statement",
    )
    assert explicit_agent.provenance == "explicit_statement"
