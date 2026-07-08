from memanto.app.services.memory_read_service import MemoryReadService


class _FakeSimilaritySearch:
    def __init__(self, results=None):
        self.last_query = None
        self.results = results or [
            {
                "id": "high",
                "text": "[FACT] High confidence\n\nRelevant memory",
                "memory_type": "fact",
                "scope_type": "agent",
                "scope_id": "agent-1",
                "actor_id": "agent-1",
                "source": "user",
                "confidence": 0.91,
                "status": "active",
                "created_at": "2026-06-25T00:00:00Z",
                "updated_at": "2026-06-25T00:00:00Z",
            },
            {
                "id": "low",
                "text": "[FACT] Low confidence\n\nRelevant but weak memory",
                "memory_type": "fact",
                "scope_type": "agent",
                "scope_id": "agent-1",
                "actor_id": "agent-1",
                "source": "user",
                "confidence": 0.41,
                "status": "active",
                "created_at": "2026-06-25T00:00:00Z",
                "updated_at": "2026-06-25T00:00:00Z",
            },
        ]

    def query(self, **kwargs):
        self.last_query = kwargs["query"]
        return {
            "results": self.results,
            "execution_time": 0,
        }


class _FakeClient:
    def __init__(self, results=None):
        self.similarity_search = _FakeSimilaritySearch(results)


def test_search_memories_applies_numeric_min_confidence_after_retrieval():
    client = _FakeClient()
    service = MemoryReadService(client)

    result = service.search_memories(
        query="relevant",
        agent_id="agent-1",
        min_confidence=0.8,
        limit=10,
    )

    assert [memory["id"] for memory in result["results"]] == ["high"]
    assert "#confidence:high" not in client.similarity_search.last_query
    assert "#confidence:medium" not in client.similarity_search.last_query


def test_zero_min_confidence_preserves_results_without_confidence_field():
    client = _FakeClient(
        [
            {
                "id": "legacy",
                "text": "[FACT] Legacy memory\n\nImported before confidence existed",
                "memory_type": "fact",
                "scope_type": "agent",
                "scope_id": "agent-1",
                "actor_id": "agent-1",
                "source": "user",
                "status": "active",
                "created_at": "2026-06-25T00:00:00Z",
                "updated_at": "2026-06-25T00:00:00Z",
            }
        ]
    )
    service = MemoryReadService(client)

    result = service.search_memories(
        query="legacy",
        agent_id="agent-1",
        min_confidence=0.0,
        limit=10,
    )

    assert [memory["id"] for memory in result["results"]] == ["legacy"]
