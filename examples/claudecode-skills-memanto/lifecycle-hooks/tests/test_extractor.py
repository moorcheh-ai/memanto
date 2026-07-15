"""Tests for LLM-answer parsing and the heuristic fallback."""

from __future__ import annotations

from memanto_skills import extractor


class TestParseLlmMemories:
    def test_parses_clean_json_array(self, llm_answer_json: str) -> None:
        mems = extractor.parse_llm_memories(llm_answer_json)
        assert len(mems) == 2
        assert mems[0]["type"] == "decision"
        assert mems[1]["title"] == "Cart != Order"

    def test_strips_code_fences_and_prose(self) -> None:
        text = (
            "Here are the memories:\n```json\n"
            '[{"type":"fact","title":"Py","content":"Project uses Python 3.12."}]'
            "\n```\nHope that helps!"
        )
        mems = extractor.parse_llm_memories(text)
        assert len(mems) == 1
        assert mems[0]["type"] == "fact"

    def test_invalid_type_coerced_to_learning(self) -> None:
        mems = extractor.parse_llm_memories(
            '[{"type":"nonsense","content":"something durable"}]'
        )
        assert mems[0]["type"] == "learning"

    def test_drops_items_without_content(self) -> None:
        mems = extractor.parse_llm_memories(
            '[{"type":"fact","title":"x"},{"type":"fact","content":"keep me"}]'
        )
        assert len(mems) == 1
        assert mems[0]["content"] == "keep me"

    def test_confidence_clamped_and_defaulted(self) -> None:
        mems = extractor.parse_llm_memories(
            '[{"content":"a","confidence":5},{"content":"b","confidence":"bad"}]'
        )
        assert mems[0]["confidence"] == 1.0
        assert mems[1]["confidence"] == 0.85

    def test_empty_or_garbage_returns_empty(self) -> None:
        assert extractor.parse_llm_memories("") == []
        assert extractor.parse_llm_memories("no json here") == []
        assert extractor.parse_llm_memories("[]") == []

    def test_title_truncated_to_80(self) -> None:
        long = "x" * 200
        mems = extractor.parse_llm_memories(f'[{{"content":"{long}"}}]')
        assert len(mems[0]["title"]) <= 80


class TestHeuristicFallback:
    def test_classifies_instruction(self) -> None:
        mems = extractor.heuristic_memories("Always use type hints in this repo.")
        assert any(m["type"] == "instruction" for m in mems)

    def test_classifies_decision(self) -> None:
        mems = extractor.heuristic_memories("We decided to use Postgres for storage.")
        assert any(m["type"] == "decision" for m in mems)

    def test_ignores_short_and_neutral_sentences(self) -> None:
        assert extractor.heuristic_memories("ok. hi. done.") == []

    def test_dedupes(self) -> None:
        text = "We chose React. We chose React. We chose React."
        mems = extractor.heuristic_memories(text)
        assert len(mems) == 1

    def test_strips_dialogue_role_prefixes(self) -> None:
        # Role-label lines with no durable signal should produce nothing.
        garbage = extractor.heuristic_memories(
            "assistant: Understood, let me summarise that for you."
        )
        assert garbage == []

        # Real signal after a role prefix must still be extracted, and the
        # stored content must not include the "user:" prefix itself.
        signal = extractor.heuristic_memories(
            "user: We always use TypeScript, never plain JavaScript."
        )
        assert any(m["type"] == "instruction" for m in signal)
        for m in signal:
            assert not m["content"].lower().startswith("user:")


class TestExtractionQuestion:
    def test_includes_skill_and_summary(self) -> None:
        q = extractor.build_extraction_question("tdd", "Decided to use Vitest.")
        assert "/tdd" in q
        assert "Vitest" in q

    def test_truncates_long_summary(self) -> None:
        q = extractor.build_extraction_question(None, "x" * 99999)
        assert len(q) < 99999
