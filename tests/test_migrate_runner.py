from unittest.mock import MagicMock

from memanto.cli.migrate.runner import run_migration


def test_run_migration_ignores_malformed_batch_result_rows():
    """Malformed per-item batch rows must not hide a successful migration."""
    export = {
        "memories": [
            {"id": "m1", "memory": "User prefers dark mode"},
            {"id": "m2", "memory": "Timezone is PST"},
        ]
    }
    client = MagicMock()
    client.batch_remember.return_value = {
        "successful": 2,
        "failed": 0,
        "results": ["stored", {"id": "m2"}],
    }

    summary, rows = run_migration(
        provider="mem0",
        export=export,
        client=client,
        agent_id="test-agent",
        dry_run=False,
    )

    assert len(rows) == 2
    assert summary.imported == 2
    assert summary.failed == 0
    assert summary.errors == []
