"""The injected instruction must state the protocol its own agent can execute.

``memanto connect`` asks the model to evaluate new memory triggers on every
turn, then hides that evaluation. How it can be hidden is a property of the
agent's UI, not of Memanto. The registry declares it once per platform and the
template renders only the applicable clause.
"""

import pytest

from memanto.cli.connect.agent_registry import AGENT_REGISTRY, AgentDef
from memanto.cli.connect.templates import (
    MEMANTO_SENTINEL,
    MEMANTO_SENTINEL_END,
    MEMANTO_VERSION_TAG,
    get_instruction_content,
)

# Text that identifies each protocol's clause.
THINKING_BLOCK_MARKER = "collapses its reasoning stream"
DUMMY_TOOL_CALL_MARKER = 'echo "memory check"'

KNOWN_PROTOCOLS = {"thinking-block", "dummy-tool-call"}

# Platform names the old shared prose advertised. None of them is in the
# registry, so no instruction should mention them again.
UNSUPPORTED_PLATFORM_NAMES = ("Aider", "Anthropic Web UI")
BRANCH_HEADINGS = (
    "Native CLI & Integrated IDE Environments",
    "VS Code Agent Environments",
)


def test_every_agent_declares_a_known_memory_protocol():
    for name, agent in AGENT_REGISTRY.items():
        assert agent.memory_protocol in KNOWN_PROTOCOLS, name


def test_declaring_a_protocol_is_required():
    """A new platform must choose a protocol instead of inheriting one."""

    with pytest.raises(TypeError):
        AgentDef(name="brand-new-agent", display_name="Brand New Agent")


def test_instruction_states_only_the_agents_own_protocol():
    """Each agent gets its clause and never the other one's.

    Shipping both protocols asked the model to work out which branch applied
    to it, which is exactly the kind of ambiguity that makes a model skip the
    directive entirely.
    """

    for name, agent in AGENT_REGISTRY.items():
        content = get_instruction_content(name)

        if agent.memory_protocol == "dummy-tool-call":
            assert DUMMY_TOOL_CALL_MARKER in content, name
            assert THINKING_BLOCK_MARKER not in content, name
        else:
            assert THINKING_BLOCK_MARKER in content, name
            assert DUMMY_TOOL_CALL_MARKER not in content, name


def test_protocol_clause_names_the_agents_own_display_name():
    for name, agent in AGENT_REGISTRY.items():
        clause = get_instruction_content(name).split("**How to Execute")[1]

        assert agent.display_name in clause.split("\n", 1)[0], name


def test_instruction_no_longer_names_unsupported_platforms():
    for name in AGENT_REGISTRY:
        content = get_instruction_content(name)

        for unsupported in UNSUPPORTED_PLATFORM_NAMES:
            assert unsupported not in content, f"{name} still names {unsupported}"
        for heading in BRANCH_HEADINGS:
            assert heading not in content, f"{name} still branches on {heading}"


def test_every_instruction_carries_the_current_version_and_one_sentinel_pair():
    for name in AGENT_REGISTRY:
        content = get_instruction_content(name)

        assert MEMANTO_VERSION_TAG in content, name
        assert content.count(MEMANTO_SENTINEL) == 1, name
        assert content.count(MEMANTO_SENTINEL_END) == 1, name


def test_unregistered_agent_falls_back_to_the_native_reasoning_protocol():
    """Third-party identifiers have no declaration, so assume the common case."""

    content = get_instruction_content("some-unregistered-agent")

    assert THINKING_BLOCK_MARKER in content
    assert DUMMY_TOOL_CALL_MARKER not in content
