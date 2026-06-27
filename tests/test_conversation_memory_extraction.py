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


def test_impossible_calendar_date_is_rejected():
    """Dates that pass YYYY-MM-DD regex but aren't real (e.g. 2026-99-99) must be dropped."""
    client = FakeClient(
        """
        [
          {
            "type": "event",
            "title": "Impossible event",
            "content": "Something happened.",
            "confidence": 0.8,
            "date": "2026-99-99"
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)
    results = service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": "Something happened."},
            {"role": "assistant", "content": "OK."},
        ],
    )
    assert len(results) == 1
    assert "date" not in results[0], (
        "Impossible date '2026-99-99' passed regex validation but must be "
        "rejected by calendar-aware parsing."
    )


def test_non_dashed_iso_date_is_rejected():
    """Dates like 20260625 or 2026-W26-4 pass fromisoformat() but must be rejected."""
    for bad_date in ["20260625", "2026-W26-4", "2026-06-25T10:00:00"]:
        client = FakeClient(
            f"""
            [
              {{
                "type": "event",
                "title": "Some event",
                "content": "Something happened.",
                "confidence": 0.8,
                "date": "{bad_date}"
              }}
            ]
            """
        )
        service = ConversationMemoryExtractionService(client)
        results = service.extract(
            namespace="memanto_agent_test",
            messages=[
                {"role": "user", "content": "Something happened."},
                {"role": "assistant", "content": "OK."},
            ],
        )
        assert "date" not in results[0], (
            f"Non-dashed ISO form '{bad_date}' should be rejected — "
            "only strict YYYY-MM-DD is accepted."
        )


def test_same_event_different_dates_are_not_deduplicated():
    """Identical content on different dates must yield two distinct memories."""
    client = FakeClient(
        """
        [
          {
            "type": "event",
            "title": "Morning run",
            "content": "User went for a morning run.",
            "confidence": 0.9,
            "date": "2026-06-25"
          },
          {
            "type": "event",
            "title": "Morning run",
            "content": "User went for a morning run.",
            "confidence": 0.9,
            "date": "2026-06-26"
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)
    results = service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": "I went for a run yesterday and today."},
            {"role": "assistant", "content": "Great habit!"},
        ],
        max_memories=5,
    )
    assert len(results) == 2, (
        "Same event on different dates was incorrectly deduplicated — "
        "the date must be part of the dedup key."
    )
    dates = {r["date"] for r in results}
    assert dates == {"2026-06-25", "2026-06-26"}


def test_footer_prompt_anchors_relative_dates_to_today():
    """_footer_prompt must include today's date so relative expressions resolve correctly."""
    from datetime import date

    # Capture the date window before and after the call to avoid a midnight-rollover
    # flake where the date advances between the _footer_prompt() call and date.today().
    date_before = date.today().isoformat()
    service = ConversationMemoryExtractionService(client=None)
    footer = service._footer_prompt()
    date_after = date.today().isoformat()

    assert date_before in footer or date_after in footer, (
        f"_footer_prompt does not include today's date (expected {date_before} or {date_after}) — "
        "the LLM cannot reliably resolve relative expressions like 'yesterday' "
        "without a reference point (nondeterministic inference)."
    )
