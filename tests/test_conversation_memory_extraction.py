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
    assert text.startswith("user: ")
    assert "x" in text  # actual content was retained
    assert len(text) <= service.MAX_CONTENT_CHARS
    assert len(text) > len("user: ")  # more than just the prefix


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


@pytest.mark.parametrize("quote", ["", "'", '"'])
def test_extract_redacts_moorcheh_api_key_assignments(quote):
    """The documented provider setting must not survive candidate extraction."""
    assignment = f"MOORCHEH_API_KEY={quote}mk_your_api_key_here{quote}"
    redacted = f"MOORCHEH_API_KEY={quote}[REDACTED_CREDENTIAL]{quote}"
    client = FakeClient(
        json.dumps(
            [
                {
                    "type": "fact",
                    "title": f"Configuration: {assignment}",
                    "content": f"Configured {assignment}; keep concise release notes.",
                }
            ]
        )
    )

    candidates = ConversationMemoryExtractionService(client).extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember the configuration."}],
    )

    assert candidates[0]["title"] == f"Configuration: {redacted}"
    assert candidates[0]["content"] == (
        f"Configured {redacted}; keep concise release notes."
    )


@pytest.mark.parametrize(
    ("key", "key_quote", "value_quote", "value"),
    [
        ("MOORCHEH_API_KEY", '"', '"', "mk_json_marker"),
        ("password", '"', '"', "pw_json_marker"),
        ("password", '"', '"', r"pw_head\"pw_tail\\pw_end"),
        ("password", '"', '"', r"pw_trailing\\"),
        ("password", '"', "'", r"pw_head\'pw_tail\\pw_end"),
        ("password", "'", "'", "pw_literal_marker"),
        ("password", '"', "", "123456789"),
    ],
)
def test_extract_redacts_quoted_credential_keys(key, key_quote, value_quote, value):
    """Quoted field names and escaped values must not bypass extraction redaction."""
    assignment = f"{key_quote}{key}{key_quote}: {value_quote}{value}{value_quote}"
    redacted = (
        f"{key_quote}{key}{key_quote}: {value_quote}[REDACTED_CREDENTIAL]{value_quote}"
    )
    config = "{" + assignment + ', "mode": "safe"}'
    redacted_config = "{" + redacted + ', "mode": "safe"}'
    client = FakeClient(
        json.dumps(
            [
                {
                    "type": "fact",
                    "title": f"Config: {config}",
                    "content": f"Configured {config}; keep release notes.",
                }
            ]
        )
    )

    candidates = ConversationMemoryExtractionService(client).extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember the configuration."}],
    )

    assert candidates[0]["title"] == f"Config: {redacted_config}"
    assert candidates[0]["content"] == (
        f"Configured {redacted_config}; keep release notes."
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
    ("value", "expected"),
    [
        (
            "before -----BEGIN RSA PRIVATE KEY-----\r\nABC123\r\n"
            "-----END RSA PRIVATE KEY----- after",
            "before [REDACTED_PRIVATE_KEY] after",
        ),
        (
            "before -----BEGIN PRIVATE KEY----- ABC -----END PRIVATE KEY----- after",
            "before [REDACTED_PRIVATE_KEY] after",
        ),
        (
            "-----BEGIN PRIVATE KEY----- ABC -----END PRIVATE KEY----- "
            "-----BEGIN PRIVATE KEY----- DEF -----END PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY]",
        ),
        (
            "-----BEGIN PRIVATE KEY-----\n-----BEGIN RSA PRIVATE KEY-----\n"
            "ABC123\n-----END RSA PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY]",
        ),
        (
            "-----BEGIN PRIVATE KEY-----\nABC123\n-----END PRIVATE KEY-----\n"
            "-----BEGIN PRIVATE KEY-----\n",
            "[REDACTED_PRIVATE_KEY]\n-----BEGIN PRIVATE KEY-----\n",
        ),
        (
            "-----BEGIN rsa PRIVATE KEY-----\nABC123\n-----END rsa PRIVATE KEY-----",
            "-----BEGIN rsa PRIVATE KEY-----\nABC123\n-----END rsa PRIVATE KEY-----",
        ),
    ],
)
def test_redact_private_keys_preserves_header_boundaries(value, expected):
    from memanto.app.services.conversation_memory_extraction_service import (
        redact_sensitive_data,
    )

    assert redact_sensitive_data(value) == expected


@pytest.mark.timeout(5)
def test_extract_bounds_work_for_unclosed_private_key_headers():
    """An incomplete footer must not rescan every preceding PEM prefix."""
    content = "-----BEGIN PRIVATE KEY-----\n" * 16_000 + "-----END "
    client = FakeClient(json.dumps([{"type": "fact", "content": content}]))
    service = ConversationMemoryExtractionService(client)

    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember the supplied text."}],
    )

    assert candidates[0]["content"] == (
        content[: service.MAX_MEMORY_CONTENT_CHARS - 3].rstrip() + "..."
    )
    assert candidates[0]["source"] == "system"
    assert candidates[0]["provenance"] == "inferred"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "HTTP://alice:secret@example.test/path and ssh://bob:pw@host",
            "HTTP://alice:[REDACTED_PASSWORD]@example.test/path and "
            "ssh://bob:[REDACTED_PASSWORD]@host",
        ),
        (
            "012.+-http://alice:secret@host",
            "012.+-http://alice:[REDACTED_PASSWORD]@host",
        ),
        (
            " ".join(f"{letter}ttp://u:pw@host" for letter in "İıſK"),
            " ".join(
                f"{letter}ttp://u:[REDACTED_PASSWORD]@host" for letter in "İıſK"
            ),
        ),
        (
            "éhttp://u:pw@host _9.http://u:pw@host",
            "éhttp://u:[REDACTED_PASSWORD]@host "
            "_9.http://u:[REDACTED_PASSWORD]@host",
        ),
        (
            "http://u:bad/pass@host http://u:good@host",
            "http://u:bad/pass@host http://u:[REDACTED_PASSWORD]@host",
        ),
        (
            "123...://host barehttp://user:pass@host",
            "123...://host barehttp://user:[REDACTED_PASSWORD]@host",
        ),
    ],
)
def test_redact_url_credentials_preserves_scheme_boundaries(value, expected):
    from memanto.app.services.conversation_memory_extraction_service import (
        redact_sensitive_data,
    )

    assert redact_sensitive_data(value) == expected


@pytest.mark.timeout(5)
def test_extract_bounds_work_for_malformed_credential_url():
    """Text without URL credentials must not restart the scheme scan."""
    content = "a" * 120_000 + "://host"
    client = FakeClient(json.dumps([{"type": "fact", "content": content}]))
    service = ConversationMemoryExtractionService(client)

    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember the supplied text."}],
    )

    assert candidates[0]["content"] == (
        content[: service.MAX_MEMORY_CONTENT_CHARS - 3] + "..."
    )
