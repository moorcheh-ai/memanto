import pytest
from unittest.mock import AsyncMock, MagicMock

from memanto.models import Session
from memanto.services import DailyAnalysisService, EmbeddingService

@pytest.mark.asyncio
async def test_generate_summary_with_large_content():
    # Setup
    embedding_service = MagicMock(spec=EmbeddingService)
    embedding_service.generate = AsyncMock(return_value="Summary for chunk")

    service = DailyAnalysisService(embedding_service)

    # Create a large session text
    large_text = " ".join(["This is a test sentence."] * 1000)  # ~10,000 characters

    sessions = [Session(summary=large_text)]
    header_prompt = "Summarize the following text:"
    footer_prompt = "## Summary"

    # Execute
    summary = await service.generate_summary(sessions, header_prompt, footer_prompt)

    # Verify
    assert summary == "Summary for chunk"
    assert embedding_service.generate.call_count == 2  # Should split into 2 chunks

@pytest.mark.asyncio
async def test_generate_summary_with_small_content():
    # Setup
    embedding_service = MagicMock(spec=EmbeddingService)
    embedding_service.generate = AsyncMock(return_value="Summary for small content")

    service = DailyAnalysisService(embedding_service)

    sessions = [Session(summary="This is a small test.")]
    header_prompt = "Summarize the following text:"
    footer_prompt = "## Summary"

    # Execute
    summary = await service.generate_summary(sessions, header_prompt, footer_prompt)

    # Verify
    assert summary == "Summary for small content"
    assert embedding_service.generate.call_count == 1  # Should not split

def test_split_text():
    # Setup
    service = DailyAnalysisService(MagicMock())

    text = " ".join(["This is a test sentence."] * 10)  # ~100 characters
    max_chunk_size = 50  # Split into chunks of ~50 characters

    # Execute
    chunks = service._split_text(text, max_chunk_size)

    # Verify
    assert len(chunks) == 2  # Should split into 2 chunks
    assert all(len(chunk) <= max_chunk_size for chunk in chunks)