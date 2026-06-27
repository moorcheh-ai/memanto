import pytest

from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService,
)


class FakeAnswer:
    def __init__(self, answer):
        self._answer = answer
        self.call_kwargs = None

    def generate(self, **kwargs):
        self.call_kwargs = kwargs
        return {"answer": self._answer}


class FakeClient:
    def __init__(self, answer):
        self.answer = FakeAnswer(answer)


def test_extract_conversation_memories_normalizes_candidates():
    client = FakeClient(
        """
        ```json
        [
          {
            "type": "preference",
            "title": "Editor preference",
            "content": "The user prefers concise pull request summaries.",
            "confidence": 0.91
          },
          {
            "type": "made-up",
            "title": "Fallback type",
            "content": "The project uses pytest for unit tests.",
            "confidence": 2
          },
          {
            "type": "preference",
            "title": "Duplicate",
            "content": "The user prefers concise pull request summaries.",
            "confidence": 0.5
          }
        ]
        ```
        """
    )

    service = ConversationMemoryExtractionService(client)
    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": "Please keep PR summaries concise."},
            {"role": "assistant", "content": "I will use pytest for checks."},
        ],
    )

    assert candidates == [
        {
            "type": "preference",
            "title": "Editor preference",
            "content": "The user prefers concise pull request summaries.",
            "confidence": 0.91,
            "source": "conversation",
            "provenance": "inferred",
        },
        {
            "type": None,
            "title": "Fallback type",
            "content": "The project uses pytest for unit tests.",
            "confidence": 1.0,
            "source": "conversation",
            "provenance": "inferred",
        },
    ]
    assert client.answer.call_kwargs["namespace"] == "memanto_agent_test"
    assert client.answer.call_kwargs["temperature"] == 0
    assert "user:" in client.answer.call_kwargs["query"]


def test_extract_rejects_non_json_answers():
    service = ConversationMemoryExtractionService(FakeClient("not json"))

    with pytest.raises(ValueError, match="valid JSON"):
        service.extract(
            namespace="memanto_agent_test",
            messages=[{"role": "user", "content": "Remember that I like Python."}],
        )


def test_extract_requires_messages():
    service = ConversationMemoryExtractionService(FakeClient("[]"))

    with pytest.raises(ValueError, match="at least one message"):
        service.extract(namespace="memanto_agent_test", messages=[])


# ── Timeline Amnesia regression tests ─────────────────────────────────────────
# Bug: _footer_prompt did not ask for a "date" field, so temporal context from
# relative expressions ("yesterday", "last Tuesday") was silently discarded.
# The extracted memory stored WHAT happened but never WHEN.

def test_temporal_context_preserved_when_date_provided():
    """Extracted memory must carry the date when the LLM infers one."""
    client = FakeClient(
        """
        [
          {
            "type": "event",
            "title": "Doctor appointment",
            "content": "User had a doctor appointment.",
            "confidence": 0.95,
            "date": "2026-06-26"
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)
    results = service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": "I had a doctor appointment yesterday."},
            {"role": "assistant", "content": "I hope it went well!"},
        ],
    )
    assert len(results) == 1
    # Without the fix this key would be absent — timeline amnesia.
    assert results[0].get("date") == "2026-06-26", (
        "Temporal context lost: 'yesterday' was in the conversation but the "
        "extracted memory carries no date field (timeline amnesia)."
    )


def test_temporal_context_absent_when_no_date():
    """When the LLM returns no date the candidate must not grow a spurious key."""
    client = FakeClient(
        """
        [
          {
            "type": "preference",
            "title": "Dark mode preference",
            "content": "User prefers dark mode.",
            "confidence": 0.9
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)
    results = service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": "I always use dark mode."},
            {"role": "assistant", "content": "Got it, I will remember that."},
        ],
    )
    assert len(results) == 1
    assert "date" not in results[0], "Spurious date key added when no date was present."


def test_malformed_date_is_rejected():
    """Non-ISO-8601 date strings must be silently ignored rather than stored."""
    client = FakeClient(
        """
        [
          {
            "type": "event",
            "title": "Team lunch",
            "content": "User had a team lunch.",
            "confidence": 0.8,
            "date": "last Tuesday"
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)
    results = service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": "We had a team lunch last Tuesday."},
            {"role": "assistant", "content": "Sounds fun!"},
        ],
    )
    assert len(results) == 1
    assert "date" not in results[0], (
        "Raw relative string 'last Tuesday' must not be stored as date — "
        "only resolved ISO-8601 dates are valid."
    )


def test_footer_prompt_requests_date_field():
    """_footer_prompt must instruct the LLM to extract a date field."""
    service = ConversationMemoryExtractionService(client=None)
    footer = service._footer_prompt()
    assert "date" in footer, (
        "_footer_prompt does not mention 'date' — the LLM will never produce "
        "temporal context, causing systematic timeline amnesia."
    )
