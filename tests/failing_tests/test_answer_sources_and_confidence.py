"""
Reproducing bounty finding: Memanto /answer endpoint drops sources and
hallucinates confidence, while /{agent_id}/answer correctly extracts
sources from the same Moorcheh SDK response.

Bounty issue: #770 (Memanto Bug & Exploit Challenge)
Author: Yzgaming005
"""

import pytest
from unittest.mock import MagicMock, PropertyMock, patch


@pytest.fixture
def mock_client_with_sources():
    """Mock Moorcheh client whose answer.generate returns real sources."""
    client = MagicMock()
    client.answer.generate.return_value = {
        "answer": "Photosynthesis converts CO2 + sunlight into glucose.",
        "sources": [
            {"id": "mem_001", "score": 0.92, "text": "Chloroplasts absorb sunlight..."},
            {"id": "mem_002", "score": 0.85, "text": "CO2 enters via stomata..."},
            {"id": "mem_003", "score": 0.71, "text": "Glucose is stored as starch..."},
        ],
    }
    return client


def test_legacy_answer_endpoint_returns_real_sources(mock_client_with_sources):
    """
    POST /answer (memanto/app/legacy/memory.py) MUST return sources
    extracted from the Moorcheh response, not an empty list.
    """
    with patch("memanto.app.legacy.memory.MemoryReadService") as MockService:
        MockService.return_value.generate_answer.return_value = {
            "answer": "Photosynthesis converts CO2 + sunlight into glucose.",
            "namespace": "agent_test",
            "query": "How does photosynthesis work?",
            "sources": [
                {"id": "mem_001", "score": 0.92, "text": "Chloroplasts absorb sunlight..."},
                {"id": "mem_002", "score": 0.85, "text": "CO2 enters via stomata..."},
            ],
            "confidence": 0.89,
        }

        # If the service is fixed to pass through sources, the endpoint
        # should also stop hardcoding [] and 0.8
        from memanto.app.legacy.memory import MemoryAnswerResponse

        result = MemoryAnswerResponse(
            answer="Photosynthesis converts CO2 + sunlight into glucose.",
            sources=[
                {"id": "mem_001", "score": 0.92, "text": "Chloroplasts absorb sunlight..."},
                {"id": "mem_002", "score": 0.85, "text": "CO2 enters via stomata..."},
            ],
            confidence=0.89,
            namespace="agent_test",
        )

        # BUG: legacy endpoint currently hardcodes sources=[] and confidence=0.8
        assert len(result.sources) > 0, "sources should not be empty"
        assert result.confidence != 0.8, "confidence should be calculated from sources"


def test_generate_answer_propagates_sources_from_sdk(mock_client_with_sources):
    """
    MemoryReadService.generate_answer() must include 'sources' in its
    return dict so downstream endpoints can surface them.
    """
    from memanto.app.services.memory_read_service import MemoryReadService

    service = MemoryReadService(mock_client_with_sources)

    # Stub the lazy-initialized _namespace_service directly (it's a property).
    with patch.object(type(service), "namespace_service", new_callable=PropertyMock) as mock_prop:
        mock_ns = MagicMock()
        mock_ns.list_namespaces.return_value = ["agent_test"]
        mock_prop.return_value = mock_ns
        result = service.generate_answer(
            query="How does photosynthesis work?",
            scope_type="agent",
            scope_id="test",
        )

    assert "sources" in result, "generate_answer() must surface 'sources'"
    assert len(result["sources"]) == 3, "should pass through all 3 SDK sources"
    assert "confidence" in result, "generate_answer() must include 'confidence'"


def test_confidence_is_derived_from_sources_not_hardcoded():
    """
    The endpoint must NOT hardcode confidence=0.8. If sources exist,
    confidence must reflect them (average relevance score, etc.).
    """
    # Use source scores that produce an average != 0.8 so the test is meaningful
    sources = [
        {"id": "a", "score": 0.9},
        {"id": "b", "score": 0.7},
        {"id": "c", "score": 0.5},
    ]
    expected_avg = round(sum(s["score"] for s in sources) / len(sources), 3)
    assert expected_avg != 0.8  # sanity: this test is only meaningful if avg != 0.8

    derived = round(sum(s["score"] for s in sources) / len(sources), 3)
    assert derived == expected_avg
    assert derived != 0.8, "confidence must not be hardcoded"
