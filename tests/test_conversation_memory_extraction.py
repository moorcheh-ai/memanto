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


def test_extract_keeps_context_when_first_message_exceeds_limit():
    client = FakeClient(
        """
        [
          {
            "type": "fact",
            "title": "Large transcript",
            "content": "The user pasted a large support transcript.",
            "confidence": 0.8
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)

    service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "A" * 20_000}],
    )

    query = client.answer.call_kwargs["query"]
    assert query.startswith("user: ")
    assert len(query) == service.MAX_CONTENT_CHARS
    assert "A" in query


def test_extract_counts_newline_separator_in_content_limit():
    client = FakeClient(
        """
        [
          {
            "type": "fact",
            "title": "Bounded transcript",
            "content": "The transcript was truncated to the configured limit.",
            "confidence": 0.8
          }
        ]
        """
    )
    service = ConversationMemoryExtractionService(client)
    first_content = "A" * (service.MAX_CONTENT_CHARS - len("user: ") - 5)

    service.extract(
        namespace="memanto_agent_test",
        messages=[
            {"role": "user", "content": first_content},
            {"role": "assistant", "content": "BCDEFG"},
        ],
    )

    query = client.answer.call_kwargs["query"]
    assert len(query) == service.MAX_CONTENT_CHARS
    assert query.endswith("\nassi")


def test_extract_requires_messages():
    service = ConversationMemoryExtractionService(FakeClient("[]"))

    with pytest.raises(ValueError, match="at least one message"):
        service.extract(namespace="memanto_agent_test", messages=[])
