"""Tests for the Zep migration mapper."""
import pytest
from memanto.cli.migrate.mappers import map_zep, MAPPERS


class TestMapZepRegistration:
    """Verify the mapper is registered."""

    def test_zep_is_registered_in_mappers(self):
        assert "zep" in MAPPERS
        assert MAPPERS["zep"] is map_zep


class TestMapZepBasic:
    """Basic mapping tests."""

    def test_empty_export_returns_empty_list(self):
        assert map_zep({}) == []

    def test_empty_sessions_returns_empty_list(self):
        assert map_zep({"sessions": []}) == []

    def test_session_without_messages_or_summary(self):
        result = map_zep({"sessions": [{"id": "s1"}]})
        assert result == []

    def test_maps_summary_as_context_memory(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "user_id": "u1",
                "summary": {"content": "Discussion about Python setup.", "created_at": "2024-01-01T10:00:00Z"},
            }]
        })
        assert len(result) == 1
        assert result[0]["type"] == "context"
        assert result[0]["source"] == "zep"
        assert result[0]["confidence"] == 0.9
        assert "zep-session:s1" in result[0]["tags"]

    def test_maps_message_as_event_memory(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "messages": [
                    {"role": "user", "content": "Hello", "created_at": "2024-01-01T10:00:00Z", "id": "m1"},
                ],
            }]
        })
        assert len(result) == 1
        assert result[0]["type"] == "event"
        assert result[0]["source"] == "zep"
        assert "[user]" in result[0]["content"]
        assert "role:user" in result[0]["tags"]

    def test_maps_both_summary_and_messages(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "summary": {"content": "Summary text"},
                "messages": [
                    {"role": "user", "content": "Question", "id": "m1"},
                    {"role": "assistant", "content": "Answer", "id": "m2"},
                ],
            }]
        })
        assert len(result) == 3  # 1 summary + 2 messages
        types = [r["type"] for r in result]
        assert types == ["context", "event", "event"]

    def test_multiple_sessions(self):
        result = map_zep({
            "sessions": [
                {"id": "s1", "messages": [{"role": "user", "content": "Hi", "id": "m1"}]},
                {"id": "s2", "messages": [{"role": "user", "content": "Hello", "id": "m2"}]},
            ]
        })
        assert len(result) == 2
        tags_per_msg = [r["tags"] for r in result]
        assert "zep-session:s1" in tags_per_msg[0]
        assert "zep-session:s2" in tags_per_msg[1]


class TestMapZepEdgeCases:
    """Edge case handling."""

    def test_empty_message_content_skipped(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "messages": [
                    {"role": "user", "content": "", "id": "m1"},
                    {"role": "user", "content": "   ", "id": "m2"},
                    {"role": "user", "content": None, "id": "m3"},
                    {"role": "user", "content": "Valid", "id": "m4"},
                ],
            }]
        })
        assert len(result) == 1  # Only the valid message

    def test_empty_summary_content_skipped(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "summary": {"content": ""},
                "messages": [{"role": "user", "content": "Hi", "id": "m1"}],
            }]
        })
        assert len(result) == 1  # Only the message, not the empty summary

    def test_missing_session_id_handled(self):
        result = map_zep({
            "sessions": [{
                "messages": [{"role": "user", "content": "Hi", "id": "m1"}],
            }]
        })
        assert len(result) == 1
        # No zep-session tag when session_id is missing
        assert not any("zep-session:" in t for t in result[0]["tags"])

    def test_missing_message_id_handled(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "messages": [{"role": "user", "content": "Hi"}],
            }]
        })
        assert len(result) == 1
        assert result[0]["source_ref"] is not None  # Still has session-based ref

    def test_preserves_user_id_in_footer(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "user_id": "user-abc",
                "messages": [{"role": "user", "content": "Hi", "id": "m1"}],
            }]
        })
        assert len(result) == 1
        assert "user-abc" in result[0]["content"]

    def test_preserves_role_in_content_and_tags(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "messages": [
                    {"role": "user", "content": "Question", "id": "m1"},
                    {"role": "assistant", "content": "Answer", "id": "m2"},
                ],
            }]
        })
        assert len(result) == 2
        assert "[user]" in result[0]["content"]
        assert "[assistant]" in result[1]["content"]
        assert "role:user" in result[0]["tags"]
        assert "role:assistant" in result[1]["tags"]

    def test_preserves_timestamps(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "created_at": "2024-01-01T10:00:00Z",
                "summary": {"content": "Summary", "created_at": "2024-01-01T10:30:00Z"},
                "messages": [
                    {"role": "user", "content": "Hi", "created_at": "2024-01-01T10:00:00Z", "id": "m1"},
                ],
            }]
        })
        assert len(result) == 2
        # Summary uses summary's created_at
        assert result[0]["created_at"] is not None
        # Message uses message's created_at
        assert result[1]["created_at"] is not None

    def test_invalid_timestamp_becomes_none(self):
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "messages": [{"role": "user", "content": "Hi", "created_at": "invalid", "id": "m1"}],
            }]
        })
        assert len(result) == 1
        assert result[0]["created_at"] is None

    def test_all_fields_populated(self):
        """Every required field in the memory dict is present."""
        result = map_zep({
            "sessions": [{
                "id": "s1",
                "user_id": "u1",
                "created_at": "2024-01-01T10:00:00Z",
                "summary": {"content": "Summary"},
                "messages": [{"role": "user", "content": "Hi", "id": "m1", "created_at": "2024-01-01T10:00:00Z"}],
            }]
        })
        for mem in result:
            assert "title" in mem
            assert "content" in mem
            assert "type" in mem
            assert "tags" in mem
            assert "confidence" in mem
            assert mem["source"] == "zep"
            assert "source_ref" in mem
            assert mem["provenance"] == "imported"
            assert "created_at" in mem
            assert "updated_at" in mem
