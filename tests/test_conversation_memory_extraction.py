import pytest

from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService,
    NothingToExtractError,
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
    assert client.answer.call_kwargs["namespace"] == ""
    assert client.answer.call_kwargs["temperature"] == 0
    assert "user:" in client.answer.call_kwargs["query"]


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


def test_extract_rejects_non_json_answers_as_unusable_not_empty():
    service = ConversationMemoryExtractionService(FakeClient("not json"))

    with pytest.raises(ValueError) as exc_info:
        service.extract(
            namespace="memanto_agent_test",
            messages=[{"role": "user", "content": "Remember that I like Python."}],
        )
    assert not isinstance(exc_info.value, NothingToExtractError)


@pytest.mark.parametrize("answer", ["[]", "Nothing to store: []", "```json\n[]\n```"])
def test_extract_empty_array_raises_nothing_to_extract(answer):
    service = ConversationMemoryExtractionService(FakeClient(answer))

    with pytest.raises(NothingToExtractError, match="nothing worth remembering"):
        service.extract(
            namespace="memanto_agent_test",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_nothing_to_extract_is_a_value_error():
    """Existing callers catch a failed extraction as ValueError."""
    assert issubclass(NothingToExtractError, ValueError)


def test_extract_with_only_unusable_candidates_returns_empty_list():
    """Unchanged: a non-empty array whose items are all dropped returns []."""
    service = ConversationMemoryExtractionService(
        FakeClient('[{"type": "fact", "title": "t", "content": ""}]')
    )

    assert (
        service.extract(
            namespace="memanto_agent_test",
            messages=[{"role": "user", "content": "hi"}],
        )
        == []
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
    # The text must include the role prefix and truncated content, not just "user:"
    assert "user: x" in text
    assert len(text) <= service.MAX_CONTENT_CHARS
    assert len(text) > len(
        "<conversation_content>\nuser: \n</conversation_content>"
    )  # more than just the prefix


def test_conversation_text_truncates_after_budget():
    """When the second message pushes total over the budget, only the
    first message should appear."""
    service = ConversationMemoryExtractionService(FakeClient("[]"))
    # 47 is the wrapper length
    half = (service.MAX_CONTENT_CHARS - 47) // 2 + 100
    text = service._conversation_text(
        [
            {"role": "user", "content": "a" * half},
            {"role": "assistant", "content": "b" * half},
        ]
    )
    # First message must be complete with its content
    expected = f"<conversation_content>\nuser: {'a' * half}\n</conversation_content>"
    assert text == expected
    assert len(text) <= service.MAX_CONTENT_CHARS


def test_conversation_text_exact_budget_boundary_with_separator():
    """Verify that when line lengths plus the newline separator exactly reach
    MAX_CONTENT_CHARS, the second message is included, but if it exceeds by 1,
    it is excluded."""
    service = ConversationMemoryExtractionService(FakeClient("[]"))

    prefix1 = "user: "
    prefix2 = "assistant: "

    wrapper_len = 47
    avail = service.MAX_CONTENT_CHARS - wrapper_len - len(prefix1) - 1 - len(prefix2)
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
    assert len(text_exceeds) == wrapper_len + len(prefix1) + len1


def test_extract_redacts_sensitive_credentials():
    """Secrets, API keys, passwords, and tokens must be redacted from extracted memories."""
    client = FakeClient(
        """
        [
          {
            "type": "fact",
            "title": "Config with token ghp_123456789012345678901234567890123456",
            "content": "User configured openai key sk-proj-1234567890123456789012345 and password: secretpassword123",
            "confidence": 0.95
          },
          {
            "type": "fact",
            "title": "DB URL",
            "content": "Database url is postgresql://usr:mypassword99@db.internal:5432/prod",
            "confidence": 0.88
          }
        ]
        """
    )

    service = ConversationMemoryExtractionService(client)
    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Here are my credentials"}],
    )

    assert len(candidates) == 2
    # Ensure sensitive credentials are sanitized
    assert "sk-proj-1234567890123456789012345" not in candidates[0]["content"]
    assert "[REDACTED_API_KEY]" in candidates[0]["content"]
    assert "secretpassword123" not in candidates[0]["content"]
    assert "[REDACTED_CREDENTIAL]" in candidates[0]["content"]
    assert "ghp_123456789012345678901234567890123456" not in candidates[0]["title"]
    assert "[REDACTED_API_KEY]" in candidates[0]["title"]

    assert "mypassword99" not in candidates[1]["content"]
    assert (
        "Database url is postgresql://usr:[REDACTED_PASSWORD]@db.internal:5432/prod"
        == candidates[1]["content"]
    )


def test_redact_sensitive_data_helper():
    from memanto.app.services.conversation_memory_extraction_service import (
        redact_sensitive_data,
    )

    privkey = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
    assert redact_sensitive_data(privkey) == "[REDACTED_PRIVATE_KEY]"

    bearer = "Bearer ya29.a0AfH6SMBxyz1234567890"
    assert redact_sensitive_data(bearer) == "Bearer [REDACTED_TOKEN]"

    bearer_token68 = "Bearer aBc12+34/56~test=="
    assert redact_sensitive_data(bearer_token68) == "Bearer [REDACTED_TOKEN]"

    aws = "AWS credentials: AKIAIOSFODNN7EXAMPLE"
    assert redact_sensitive_data(aws) == "AWS credentials: [REDACTED_API_KEY]"

    aws_secret = 'aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
    assert (
        redact_sensitive_data(aws_secret)
        == 'aws_secret_access_key="[REDACTED_CREDENTIAL]"'
    )

    aws_secret_unquoted = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG"
    assert (
        redact_sensitive_data(aws_secret_unquoted)
        == "AWS_SECRET_ACCESS_KEY=[REDACTED_CREDENTIAL]"
    )


@pytest.mark.parametrize(
    "client_path", ["direct_client.DirectClient", "sdk_client.SdkClient"]
)
@pytest.mark.parametrize(
    "answer", ["[]", '[{"type": "fact", "title": "t", "content": ""}]']
)
def test_client_extract_with_nothing_to_store_raises_without_writing(
    client_path, answer
):
    from importlib import import_module
    from types import SimpleNamespace
    from unittest.mock import patch

    module_name, class_name = client_path.split(".")
    client_cls = getattr(import_module(f"memanto.cli.client.{module_name}"), class_name)
    session = SimpleNamespace(namespace="memanto_agent_bot", session_id="s1")

    with (
        patch.object(
            client_cls, "_get_validated_session_for_agent", return_value=session
        ),
        patch.object(client_cls, "_get_moorcheh", return_value=FakeClient(answer)),
        patch.object(client_cls, "batch_remember") as batch_remember,
    ):
        client = client_cls.__new__(client_cls)
        with pytest.raises(NothingToExtractError):
            client.extract_memories_from_conversation(
                agent_id="bot", messages=[{"role": "user", "content": "hi"}]
            )
        # A dry run of the same conversation still previews zero candidates.
        if answer != "[]":
            preview = client.extract_memories_from_conversation(
                agent_id="bot",
                messages=[{"role": "user", "content": "hi"}],
                dry_run=True,
            )
            assert preview["candidates"] == [] and preview["count"] == 0

    batch_remember.assert_not_called()
