import json

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
            "source": "system",
            "provenance": "inferred",
        },
        {
            "type": None,
            "title": "Fallback type",
            "content": "The project uses pytest for unit tests.",
            "confidence": 1.0,
            "source": "system",
            "provenance": "inferred",
        },
    ]
    assert client.answer.call_kwargs["namespace"] == "memanto_agent_test"
    assert client.answer.call_kwargs["temperature"] == 0
    assert "user:" in client.answer.call_kwargs["query"]


def test_extract_ignores_non_json_brackets_before_memory_array():
    client = FakeClient(
        "I checked the transcript [notes] and extracted this:\n"
        '[{"type":"learning","title":"Regression tests","content":"Run focused '
        'regression tests before pushing memory extraction fixes.","confidence":0.88}]'
    )

    service = ConversationMemoryExtractionService(client)
    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember to test extraction fixes."}],
    )

    assert candidates == [
        {
            "type": "learning",
            "title": "Regression tests",
            "content": "Run focused regression tests before pushing memory extraction fixes.",
            "confidence": 0.88,
            "source": "system",
            "provenance": "inferred",
        }
    ]


def test_extract_skips_invalid_json_arrays():
    client = FakeClient(
        "Dummy array first: [1, 2]\n"
        "Real array second:\n"
        '[{"type":"fact","title":"Validation","content":"Iterate arrays.","confidence":0.95}]'
    )

    service = ConversationMemoryExtractionService(client)
    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Iterate arrays."}],
    )

    assert candidates == [
        {
            "type": "fact",
            "title": "Validation",
            "content": "Iterate arrays.",
            "confidence": 0.95,
            "source": "system",
            "provenance": "inferred",
        }
    ]


def test_extract_ignores_brackets_in_strings():
    client = FakeClient(
        '[{"type":"fact","title":"Nested brackets","content":"Like this [1, 2].","confidence":0.95}]'
    )

    service = ConversationMemoryExtractionService(client)
    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Like this [1, 2]."}],
    )

    assert candidates == [
        {
            "type": "fact",
            "title": "Nested brackets",
            "content": "Like this [1, 2].",
            "confidence": 0.95,
            "source": "system",
            "provenance": "inferred",
        }
    ]


def test_extract_omits_unset_active_ai_model(monkeypatch):
    """On-prem fallback should let answer.generate use its configured model."""
    from memanto.app.services import conversation_memory_extraction_service as module

    monkeypatch.setattr(module, "get_active_llm_model", lambda _: None)
    client = FakeClient(
        '[{"type":"fact","title":"Test","content":"Use pytest.","confidence":0.9}]'
    )

    service = ConversationMemoryExtractionService(client)
    service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "The project uses pytest."}],
    )

    assert "ai_model" not in client.answer.call_kwargs


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


def test_conversation_text_includes_first_message_when_oversized():
    """A single message longer than MAX_CONTENT_CHARS must still appear
    (truncated) so the query is never empty."""
    service = ConversationMemoryExtractionService(FakeClient("[]"))
    long_content = "x" * (service.MAX_CONTENT_CHARS + 500)
    text = service._conversation_text([{"role": "user", "content": long_content}])
    expected_text = f"user: {long_content}"[:service.MAX_CONTENT_CHARS]
    assert text == expected_text
    assert len(text) == service.MAX_CONTENT_CHARS


def test_conversation_text_truncates_after_budget():
    """When the second message pushes total over the budget, only the
    first message should appear."""
    service = ConversationMemoryExtractionService(FakeClient("[]"))
    half = service.MAX_CONTENT_CHARS // 2 + 100
    text = service._conversation_text(
        [
            {"role": "user", "content": "a" * half},
            {"role": "assistant", "content": "b" * half},
        ]
    )
    # First message must be complete with its content
    expected = f"user: {'a' * half}"
    assert text == expected
    assert len(text) <= service.MAX_CONTENT_CHARS

def test_conversation_text_exact_budget_boundary_with_separator():
    """Verify that when line lengths plus the newline separator exactly reach
    MAX_CONTENT_CHARS, the second message is included, but if it exceeds by 1,
    it is excluded."""
    service = ConversationMemoryExtractionService(FakeClient("[]"))
    
    prefix1 = "user: "
    prefix2 = "assistant: "
    
    avail = service.MAX_CONTENT_CHARS - len(prefix1) - 1 - len(prefix2)
    len1 = avail // 2
    len2 = avail - len1
    
    text_exact = service._conversation_text(
        [
            {"role": "user", "content": "a" * len1},
            {"role": "assistant", "content": "b" * len2},
        ]
    )
    
    assert "assistant: b" in text_exact
    assert len(text_exact) == service.MAX_CONTENT_CHARS
    
    text_exceeds = service._conversation_text(
        [
            {"role": "user", "content": "a" * len1},
            {"role": "assistant", "content": "b" * (len2 + 1)},
        ]
    )
    assert "assistant:" not in text_exceeds
    assert len(text_exceeds) == len(prefix1) + len1

def test_extract_caps_candidate_content_to_memory_record_limit():
    oversized = "x" * 10_001
    service = ConversationMemoryExtractionService(
        FakeClient(
            json.dumps(
                [
                    {
                        "type": "fact",
                        "title": "Large memory",
                        "content": oversized,
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )

    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember the supplied document."}],
    )

    assert len(candidates[0]["content"]) == 10_000
    assert candidates[0]["content"].endswith("...")
