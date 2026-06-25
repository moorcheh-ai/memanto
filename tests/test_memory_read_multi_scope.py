from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import MemoryReadService


def test_search_multi_scope_builds_namespaces_from_scope_defs():
    client = MagicMock()
    client.similarity_search.query.return_value = {
        "results": [],
        "execution_time": 0.01,
    }
    service = MemoryReadService(client)

    result = service.search_multi_scope(
        query="deployment preference",
        scopes=[
            {"scope_type": "agent", "scope_id": "support-agent"},
            {"scope_type": "project", "scope_id": "alpha"},
        ],
        limit=5,
    )

    client.similarity_search.query.assert_called_once_with(
        query="deployment preference",
        namespaces=["memanto_agent_support-agent", "memanto_project_alpha"],
        top_k=5,
        threshold=None,
        kiosk_mode=False,
    )
    assert result["searched_namespaces"] == [
        "memanto_agent_support-agent",
        "memanto_project_alpha",
    ]
    assert result["total_found"] == 0
