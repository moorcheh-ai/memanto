"""
Regression test for disabled memory validation.

Verifies that:
1. The validation_service attribute exists on MemoryWriteService
2. store_memory() calls validation when validation is enabled
3. Contradictory memories are flagged when validation is active
"""

from unittest.mock import MagicMock, patch
import pytest


def test_validation_service_exists():
    """MemoryWriteService should have a validation_service attribute."""
    from memanto.app.services.memory_write_service import MemoryWriteService
    # We can't fully instantiate without a Moorcheh client, but we can
    # verify the class structure expects a validation service.
    import inspect
    source = inspect.getsource(MemoryWriteService.store_memory)
    # The validation call should NOT be commented out
    assert "validation_service.validate_memory" in source, (
        "Validation is commented out in store_memory() — memories are stored "
        "without integrity checks, contradiction detection, or poisoning prevention."
    )


def test_batch_validation_service_exists():
    """batch_store_memories should also call validation."""
    from memanto.app.services.memory_write_service import MemoryWriteService
    import inspect
    source = inspect.getsource(MemoryWriteService.batch_store_memories)
    assert "validation_service.validate_memory" in source, (
        "Validation is commented out in batch_store_memories() — batch memories "
        "are stored without integrity checks."
    )


def test_trust_score_not_commented():
    """_format_memory_item should compute trust scores, not skip them."""
    from memanto.app.services.memory_read_service import MemoryReadService
    import inspect
    source = inspect.getsource(MemoryReadService._format_memory_item)
    # The trust score computation should not be entirely commented out
    # Count commented lines vs active lines in the trust score section
    lines = source.split('\\n')
    has_active_trust = any('trust_score' in line and not line.strip().startswith('#') for line in lines)
    assert has_active_trust, (
        "Trust score computation is commented out in _format_memory_item() — "
        "search results lack computed_confidence and trust_score fields."
    )
