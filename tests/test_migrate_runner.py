from __future__ import annotations

from typing import Any

from memanto.cli.migrate.runner import run_migration


class RecordingClient:
    def __init__(self, fail_calls: set[int] | None = None) -> None:
        self.fail_calls = fail_calls or set()
        self.calls: list[list[dict[str, Any]]] = []

    def batch_remember(
        self, agent_id: str, memories: list[dict[str, Any]]
    ) -> dict[str, Any]:
        call_number = len(self.calls) + 1
        self.calls.append([dict(memory) for memory in memories])
        if call_number in self.fail_calls:
            raise RuntimeError("transient import failure")
        return {
            "successful": len(memories),
            "failed": 0,
            "results": [{"id": memory.get("id")} for memory in memories],
        }


def _mem0_export(count: int) -> dict[str, Any]:
    return {
        "memories": [
            {
                "id": f"mem-{idx}",
                "memory": f"Imported memory {idx}",
                "categories": ["work"],
            }
            for idx in range(count)
        ]
    }


def test_migration_retry_reuses_stable_import_ids_after_partial_failure():
    export = _mem0_export(101)
    first_client = RecordingClient(fail_calls={2})

    first_summary, _ = run_migration(
        provider="mem0",
        export=export,
        client=first_client,
        agent_id="agent-a",
        dry_run=False,
    )

    assert first_summary.imported == 100
    assert first_summary.failed == 1

    retry_client = RecordingClient()
    retry_summary, _ = run_migration(
        provider="mem0",
        export=export,
        client=retry_client,
        agent_id="agent-a",
        dry_run=False,
    )

    assert retry_summary.imported == 101
    first_batch_ids = [memory.get("id") for memory in first_client.calls[0]]
    retry_batch_ids = [memory.get("id") for memory in retry_client.calls[0]]
    assert first_batch_ids == retry_batch_ids
    assert all(first_batch_ids)


def test_migration_import_ids_are_scoped_to_agent():
    export = _mem0_export(1)
    agent_a = RecordingClient()
    agent_b = RecordingClient()

    run_migration(
        provider="mem0",
        export=export,
        client=agent_a,
        agent_id="agent-a",
        dry_run=False,
    )
    run_migration(
        provider="mem0",
        export=export,
        client=agent_b,
        agent_id="agent-b",
        dry_run=False,
    )

    agent_a_id = agent_a.calls[0][0].get("id")
    agent_b_id = agent_b.calls[0][0].get("id")

    assert agent_a_id != agent_b_id
