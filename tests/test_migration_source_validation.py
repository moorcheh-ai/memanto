"""Regression coverage for migration rows crossing the MemoryRecord boundary."""

import pytest

from memanto.app.core import MemoryRecord
from memanto.cli.migrate.mappers import (
    map_letta,
    map_mem0,
    map_okf,
    map_supermemory,
)


def _as_memory_record(row):
    """Mirror the batch clients, which omit absent optional timestamp fields."""
    kwargs = {
        key: value for key, value in row.items() if value is not None or key == "type"
    }
    return MemoryRecord(**kwargs, agent_id="agent-1", actor_id="agent-1")


@pytest.mark.parametrize(
    ("mapper", "export"),
    [
        (map_mem0, {"memories": [{"id": "m1", "memory": "Prefers tea"}]}),
        (map_letta, {"passages": [{"id": "l1", "text": "Prefers tea"}]}),
        (
            map_supermemory,
            {"memories": [{"id": "s1", "content": "Prefers tea"}]},
        ),
        (
            map_supermemory,
            {
                "documents": [
                    {
                        "id": "d1",
                        "chunks": [{"id": "c1", "content": "Prefers tea"}],
                    }
                ]
            },
        ),
        (
            map_okf,
            {"memories": [{"title": "Preference", "body": "Prefers tea"}]},
        ),
        (
            map_okf,
            {
                "memories": [
                    {
                        "title": "Preference",
                        "body": "Prefers tea",
                        "x_memanto": {"source": "okf"},
                    }
                ]
            },
        ),
    ],
)
def test_provider_rows_are_valid_memory_records(mapper, export):
    """Every shipped provider must produce rows the batch clients can store."""
    row = mapper(export)[0]

    record = _as_memory_record(row)

    assert record.source == "tool"
    assert record.provenance == "imported"


def test_okf_round_trip_preserves_valid_memanto_source():
    """A Memanto-authored OKF bundle keeps a valid original source."""
    row = map_okf(
        {
            "memories": [
                {
                    "title": "Preference",
                    "body": "Prefers tea",
                    "x_memanto": {"source": "user"},
                }
            ]
        }
    )[0]

    record = _as_memory_record(row)

    assert record.source == "user"
