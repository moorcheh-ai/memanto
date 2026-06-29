"""Tests for the MemoryProfile context-block renderer."""

from __future__ import annotations

from typing import Any

from claudecode_memanto.profile import MemoryProfile


class TestFromRecall:
    def test_empty_result(self) -> None:
        assert not MemoryProfile.from_recall(None)
        assert not MemoryProfile.from_recall({})
        assert len(MemoryProfile.from_recall({"memories": []})) == 0

    def test_malformed_recall_shape_is_ignored(self) -> None:
        assert not MemoryProfile.from_recall("backend timeout")  # type: ignore[arg-type]
        assert not MemoryProfile.from_recall({"memories": "not-a-list"})

    def test_malformed_recall_entries_are_skipped_before_filtering(self) -> None:
        profile = MemoryProfile.from_recall(
            {
                "memories": [
                    "truncated row",
                    None,
                    {"type": "fact", "content": "Keep valid hits", "score": 0.9},
                ]
            },
            min_similarity=0.5,
        )
        assert len(profile) == 1
        assert profile.memories[0]["content"] == "Keep valid hits"

    def test_similarity_floor_filters(
        self, sample_memories: list[dict[str, Any]]
    ) -> None:
        profile = MemoryProfile.from_recall(
            {"memories": sample_memories}, min_similarity=0.85
        )
        # Only the 0.9-scored instruction clears a 0.85 floor.
        assert len(profile) == 1
        assert profile.memories[0]["type"] == "instruction"

    def test_no_floor_keeps_all(self, sample_memories: list[dict[str, Any]]) -> None:
        profile = MemoryProfile.from_recall({"memories": sample_memories})
        assert len(profile) == 3


class TestFormatContextBlock:
    def test_empty_profile_renders_empty_string(self) -> None:
        assert MemoryProfile([]).format_context_block() == ""

    def test_block_wraps_in_engineering_profile_tag(
        self, sample_memories: list[dict[str, Any]]
    ) -> None:
        block = MemoryProfile(sample_memories).format_context_block(skill_name="tdd")
        assert block.startswith('<engineering-profile source="memanto"')
        assert 'skill="tdd"' in block
        assert block.rstrip().endswith("</engineering-profile>")

    def test_instructions_render_before_preferences(
        self, sample_memories: list[dict[str, Any]]
    ) -> None:
        block = MemoryProfile(sample_memories).format_context_block()
        assert block.index("Rules") < block.index("Preferences")

    def test_low_confidence_marked_tentative(self) -> None:
        block = MemoryProfile(
            [{"type": "fact", "content": "maybe true", "confidence": 0.3}]
        ).format_context_block()
        assert "(tentative)" in block

    def test_unusual_scalar_fields_render_without_crashing(self) -> None:
        block = MemoryProfile(
            [{"type": 123, "content": 456, "confidence": "high"}]
        ).format_context_block()
        assert "456" in block

    def test_falsy_scalar_content_values_are_preserved(self) -> None:
        block = MemoryProfile(
            [
                {"type": "fact", "content": 0, "title": "fallback"},
                {"type": "fact", "content": False, "title": "fallback"},
                {"type": "fact", "content": 0.0, "title": "fallback"},
            ]
        ).format_context_block()

        assert "  - 0\n" in block
        assert "  - False\n" in block
        assert "  - 0.0\n" in block
        assert "fallback" not in block

    def test_missing_content_falls_back_to_title(self) -> None:
        block = MemoryProfile(
            [{"type": "fact", "title": "fallback title"}]
        ).format_context_block()

        assert "fallback title" in block

    def test_content_present(self, sample_memories: list[dict[str, Any]]) -> None:
        block = MemoryProfile(sample_memories).format_context_block()
        assert "Always use Vitest" in block
        assert "CQRS" in block

    def test_skill_name_is_html_escaped_in_attribute(
        self, sample_memories: list[dict[str, Any]]
    ) -> None:
        # A crafted skill name must NOT break the attribute boundary or close
        # the wrapper early. The raw injected payload must not appear verbatim.
        evil = 'tdd"><script>alert(1)</script><x foo="'
        block = MemoryProfile(sample_memories).format_context_block(skill_name=evil)
        assert "<script>" not in block
        assert "</engineering-profile>" in block
        # Wrapper must still close exactly once at the end.
        assert block.count("<engineering-profile") == 1
        assert block.count("</engineering-profile>") == 1
        # The escaped form must be what was rendered.
        assert "&quot;" in block or "&gt;" in block
