from typing import Any, cast

from memanto.app.config import settings
from memanto.app.constants import MemoryType
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_parsing_service import MemoryParsingService


def make_memory(content: str, memory_type: MemoryType | None = None) -> MemoryRecord:
    memory = MemoryRecord(
        content=content,
        type=memory_type or "fact",
        title="test",
        actor_id="user",
        source="test",
        scope_type="agent",
        scope_id="test",
    )
    if memory_type is None:
        cast(Any, memory).type = None
    return memory


# 1 Rule-based detection
def test_detect_preference():
    parser = MemoryParsingService()

    memory = make_memory("I like Python")

    parser.parse_memory(memory)

    assert memory.type == "preference"


# 2 Do NOT override existing type
def test_no_override_existing_type():
    parser = MemoryParsingService()

    memory = make_memory("I like Python", "fact")

    parser.parse_memory(memory)

    assert memory.type == "fact"


# 3. Config disabled
def test_auto_parse_disabled_uses_default_type(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_PARSE_ENABLED", False)

    parser = MemoryParsingService()

    memory = make_memory("I like Python")

    parser.parse_memory(memory)

    assert memory.type == "fact"

    monkeypatch.setattr(settings, "AUTO_PARSE_ENABLED", True)


# 4. Fallback to fact
def test_fallback_to_fact():
    parser = MemoryParsingService()

    memory = make_memory("The API endpoint is https://example.com")

    parser.parse_memory(memory)

    assert memory.type == "fact"


def test_boundary_matching_avoids_substring_false_positive():
    parser = MemoryParsingService()

    memory = make_memory("The team selected mustard yellow for the warning badge")

    parser.parse_memory(memory)

    assert memory.type == "decision"


def test_mixed_context_prioritizes_stronger_preference_signal():
    parser = MemoryParsingService()

    memory = make_memory("Alex mentioned he prefers dark mode for long coding sessions")

    parser.parse_memory(memory)

    assert memory.type == "preference"


def test_mixed_context_prioritizes_instruction_over_weak_event_signal():
    parser = MemoryParsingService()

    memory = make_memory(
        "I prefer the new approach because we decided it must be implemented before the next client meeting."
    )

    parser.parse_memory(memory)

    assert memory.type == "instruction"


def test_richer_lexical_coverage_for_common_scenarios():
    parser = MemoryParsingService()

    cases = {
        "The action item is to follow up with the client by EOD": "commitment",
        "I realized the root cause was a timeout in the export job": "learning",
        "The app keeps crashing with a traceback during upload": "error",
        "Saved the output to exports/session_report.md": "artifact",
        "Alex reports to Jordan on the platform team": "relationship",
        "Currently the project is blocked waiting on API access": "context",
        "The client usually asks for CSV exports": "observation",
    }

    for content, expected_type in cases.items():
        memory = make_memory(content)

        parser.parse_memory(memory)

        assert memory.type == expected_type


def test_unrelated_text_falls_back_to_default_fact():
    parser = MemoryParsingService()

    memory = make_memory("random unrelated words here")

    parser.parse_memory(memory)

    assert memory.type == "fact"


def test_detect_error_with_inflected_and_camelcase_signals():
    parser = MemoryParsingService()

    memory = make_memory("The app crashed with a NullPointerException during upload")

    parser.parse_memory(memory)

    assert memory.type == "error"


def test_learning_intent_beats_topical_error_terms():
    parser = MemoryParsingService()

    memory = make_memory("I learned that caching fixed the timeout issue")

    parser.parse_memory(memory)

    assert memory.type == "learning"


def test_reminder_intent_beats_artifact_mention():
    parser = MemoryParsingService()

    memory = make_memory("Remind me to email the report.pdf to the manager tomorrow")

    parser.parse_memory(memory)

    assert memory.type == "commitment"
