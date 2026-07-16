from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import MemoryReadService


def _memory(memory_id: str, expires_at: str) -> dict:
    return {
        "id": memory_id,
        "text": "[FACT] Historical fact\n\nThis was true at the requested time.",
        "metadata": {
            "memory_type": "fact",
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2020-01-01T00:00:00Z",
            "expires_at": expires_at,
        },
    }


def test_search_as_of_evaluates_ttl_at_requested_time():
    client = MagicMock()
    client.documents.fetch_text_data.return_value = {
        "items": [
            _memory("valid-then", "2020-12-31T23:59:59Z"),
            _memory("expired-then", "2020-05-31T23:59:59Z"),
        ],
        "pagination": {"has_more": False},
    }

    result = MemoryReadService(client).search_as_of(
        as_of_date="2020-06-01T00:00:00Z",
        agent_id="test-agent",
    )

    assert [memory["id"] for memory in result["results"]] == ["valid-then"]
