"""
Reproducing bounty finding: Memanto /answer endpoint drops sources and
hallucinates confidence, while /{agent_id}/answer correctly extracts
sources from the same Moorcheh SDK response.

Bounty issue: #770 (Memanto Bug & Exploit Challenge)
Author: Yzgaming005
"""

import pytest
from unittest.mock import MagicMock


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


def test_generate_answer_returns_real_sources_and_confidence(mock_client_with_sources):
    """
    MemoryReadService.generate_answer() MUST return sources
    extracted from the Moorcheh response, not an empty list.
    """
    from memanto.app.services.memory_read_service import MemoryReadService

    service = MemoryReadService(mock_client_with_sources)

    # Call generate_answer (which the legacy endpoint wraps)
    # Updated to pass agent_id instead of scope_type/scope_id as per recent refactoring
    result = service.generate_answer(
        query="How does photosynthesis work?",
        agent_id="test",
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