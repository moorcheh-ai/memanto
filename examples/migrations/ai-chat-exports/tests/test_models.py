import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.models import MemoryEntity, MemoryType


class TestMemoryType:
    def test_all_types_exist(self):
        expected = [
            "fact",
            "user_preference",
            "context",
            "event",
            "decision",
            "learning",
            "observation",
            "instruction",
            "relationship",
            "commitment",
            "goal",
            "artifact",
            "error",
        ]
        actual = [t.value for t in MemoryType]
        assert sorted(actual) == sorted(expected)

    def test_type_count(self):
        assert len(MemoryType) == 13


class TestMemoryEntity:
    def test_create_minimal(self):
        e = MemoryEntity(
            source_type=MemoryType.FACT,
            title="Test",
            content="Content",
        )
        assert e.source_type == MemoryType.FACT
        assert e.title == "Test"
        assert e.content == "Content"
        assert e.tags == []
        assert e.timestamp is None
        assert e.confidence == 0.8
        assert e.source == ""

    def test_create_full(self):
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        e = MemoryEntity(
            source_type=MemoryType.PREFERENCE,
            title="Prefers dark mode",
            content="User prefers dark mode in all apps",
            tags=["ui", "theme"],
            timestamp=ts,
            confidence=0.95,
            provenance="explicit_statement",
            source="chatgpt",
            source_ref="chatgpt://conv/123",
            metadata={"chat_id": "123"},
        )
        assert e.source_type == MemoryType.PREFERENCE
        assert e.tags == ["ui", "theme"]
        assert e.confidence == 0.95
        assert e.metadata["chat_id"] == "123"

    def test_escape_yaml_basic(self):
        result = MemoryEntity._escape_yaml('Hello "World"')
        assert result == 'Hello \\"World\\"'

    def test_escape_yaml_newline(self):
        result = MemoryEntity._escape_yaml("Line1\nLine2")
        assert result == "Line1 Line2"

    def test_escape_yaml_backslash(self):
        result = MemoryEntity._escape_yaml("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_to_okf_frontmatter(self):
        e = MemoryEntity(
            source_type=MemoryType.FACT,
            title="Postgres is primary",
            content="Uses PostgreSQL 16 on port 5432",
            tags=["db", "infra"],
            timestamp=datetime(2026, 5, 28, 14, 30, 0, tzinfo=timezone.utc),
            confidence=0.9,
            source="chatgpt",
            source_ref="https://example.com",
        )
        fm = e.to_okf_frontmatter()
        assert "type: fact" in fm
        assert 'title: "Postgres is primary"' in fm
        assert "tags: [db, infra]" in fm
        assert "timestamp: 2026-05-28T14:30:00Z" in fm
        assert "resource: https://example.com" in fm
        assert "x_memanto:" in fm
        assert "confidence: 0.9" in fm
        assert "source: chatgpt" in fm
        assert fm.startswith("---")
        assert fm.endswith("---")
