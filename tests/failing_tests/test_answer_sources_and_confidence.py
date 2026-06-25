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
    from memanto.app.services.memory_read_service import MemoryReadService
    
    service = MemoryReadService(mock_client_with_sources)
    
    # Call generate_answer (which the legacy endpoint wraps)
    result = service.generate_answer(
        query="How does photosynthesis work?",
        scope_type="agent",
        scope_id="test",
    )
    
    # Assert sources are forwarded from SDK response
    assert "sources" in result, "generate_answer() must return 'sources'"
    assert len(result["sources"]) == 3, f"Expected 3 sources, got {len(result['sources'])}"
    assert result["sources"][0]["id"] == "mem_001"
    assert result["sources"][0]["score"] == 0.92
    
    # Assert confidence is computed from sources, not hardcoded
    assert "confidence" in result
    expected_confidence = round((0.92 + 0.85 + 0.71) / 3, 3)
    assert result["confidence"] == expected_confidence, f"Expected {expected_confidence}, got {result['confidence']}"
    assert result["confidence"] != 0.8, "confidence must not be hardcoded to 0.8"


def test_generate_answer_propagates_sources_from_sdk(mock_client_with_sources):
    """
    MemoryReadService.generate_answer() must include 'sources' in its
    return dict so downstream endpoints can surface them.
    """
    from memanto.app.services.memory_read_service import MemoryReadService

    service = MemoryReadService(mock_client_with_sources)

    # When scope_type="agent" and scope_id are provided, the service uses
    # create_memory_scope() directly and never touches namespace_service,
    # so no PropertyMock is needed here.
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
    confidence must reflect them (average relevance score, etc.)
    """
    from memanto.app.services.memory_read_service import MemoryReadService
    
    # Mock client with sources that produce avg != 0.8
    client = MagicMock()
    client.answer.generate.return_value = {
        "answer": "Test answer",
        "sources": [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.7},
            {"id": "c", "score": 0.5},
        ],
    }
    
    service = MemoryReadService(client)
    
    # Stub namespace_service
    with patch.object(type(service), "namespace_service", new_callable=PropertyMock) as mock_prop:
        mock_ns = MagicMock()
        mock_ns.list_namespaces.return_value = ["agent_test"]
        mock_prop.return_value = mock_ns
        
        result = service.generate_answer(
            query="test query",
            scope_type="agent",
            scope_id="test",
        )
    
    # Expected confidence from real sources
    expected_avg = round((0.9 + 0.7 + 0.5) / 3, 3)  # 0.7
    assert expected_avg != 0.8  # sanity check
    
    # Assert production code computes confidence from sources
    assert result["confidence"] == expected_avg, f"Expected {expected_avg}, got {result['confidence']}"
    assert result["confidence"] != 0.8, "confidence must not be hardcoded to 0.8"

