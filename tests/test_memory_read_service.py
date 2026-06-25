from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import MemoryReadService


def test_search_multi_scope_builds_namespaces_and_queries_backend():
    client = MagicMock()
    client.similarity_search.query.return_value = {
        "results": [
            {
                "id": "mem-1",
                "text": "[FACT] Favorite language\n\nThe user prefers Python.",
                "memory_type": "fact",
                "scope_type": "agent",
                "scope_id": "alpha",
                "status": "active",
            }
        ],
        "execution_time": 0.01,
    }

    result = MemoryReadService(client).search_multi_scope(
        query="favorite language",
        scopes=[
            {"scope_type": "agent", "scope_id": "alpha"},
            {"scope_type": "project", "scope_id": "roadmap"},
        ],
        limit=5,
    )

    client.similarity_search.query.assert_called_once_with(
        query="favorite language",
        namespaces=["memanto_agent_alpha", "memanto_project_roadmap"],
        top_k=5,
        threshold=None,
        kiosk_mode=False,
    )
    assert result["total_found"] == 1
    assert result["searched_namespaces"] == [
        "memanto_agent_alpha",
        "memanto_project_roadmap",
    ]
    assert result["results"][0]["id"] == "mem-1"
