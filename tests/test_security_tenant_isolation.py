"""
Security Verification: Tenant Isolation and Tag Input Validation
Tests for Issue #1852 (The Memanto Security Challenge)
"""

import pytest
from pydantic import ValidationError

from memanto.app.core import MemoryRecord, MemoryTag


def test_tag_rejects_null_byte_and_path_traversal():
    """Ensure tags reject directory traversal sequences, null bytes, and path delimiters."""
    invalid_tags = [
        "../../tenant_b",
        "default/admin",
        "\x00injected",
        "tag with spaces",
        "tag;DROP TABLE;",
        "<script>alert(1)</script>",
        "tag#fragment",
    ]
    for tag in invalid_tags:
        with pytest.raises((ValidationError, ValueError)):
            # MemoryRecord uses BoundedTags which wraps MemoryTag
            MemoryRecord(
                agent_id="agent_123",
                content="test content",
                type="fact",
                tags=[tag],
            )


def test_tag_accepts_valid_slugs():
    """Ensure alphanumeric and standard slug tags remain fully valid."""
    valid_tags = ["prod_v1", "finance-dept", "project.core", "agent123"]
    record = MemoryRecord(
        agent_id="agent_123",
        content="valid record content",
        type="fact",
        tags=valid_tags,
    )
    assert record.tags == valid_tags
