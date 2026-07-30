from adversarial_memory.adapters import MemantoAdapter
from adversarial_memory.dataset import Event, Probe


class FakeClient:
    def __init__(self, result: str) -> None:
        self.result = result
        self.remembered: list[dict] = []
        self.recalled: list[dict] = []

    def remember(self, **kwargs) -> None:
        self.remembered.append(kwargs)

    def recall(self, **kwargs) -> dict:
        self.recalled.append(kwargs)
        return {"memories": [{"content": self.result}]}


def test_memanto_routes_each_tenant_through_its_own_session_client() -> None:
    adapter = MemantoAdapter.__new__(MemantoAdapter)
    first = FakeClient("first-result")
    second = FakeClient("second-result")
    adapter._clients = {"tenant-0": first, "tenant-1": second}
    adapter._agents = {"tenant-0": "agent-0", "tenant-1": "agent-1"}

    event = Event(
        event_id="event-1",
        tenant="tenant-1",
        session=0,
        content="memory",
        marker="STATE_TENANT-1_00_V0",
        kind="state",
    )
    adapter.add(event)

    probe = Probe(
        probe_id="probe-1",
        tenant="tenant-0",
        session=0,
        query="current state",
        expected_marker="STATE_TENANT-0_00_V0",
        stale_markers=(),
        poison_markers=(),
        foreign_markers=(),
    )
    assert adapter.search(probe, limit=3) == ["first-result"]

    assert first.remembered == []
    assert second.remembered[0]["agent_id"] == "agent-1"
    assert first.recalled == [
        {"agent_id": "agent-0", "query": "current state", "limit": 3}
    ]
    assert second.recalled == []
