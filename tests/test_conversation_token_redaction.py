"""Opaque credentials must not survive conversation candidate extraction."""

import json
from types import SimpleNamespace

import pytest

from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService,
    redact_sensitive_data,
)


@pytest.mark.parametrize(
    "key",
    [
        "access_token",
        "refresh_token",
        "id_token",
        "session_token",
        "accessToken",
        "REFRESH-TOKEN",
        "IDTOKEN",
        "Session-Token",
    ],
)
@pytest.mark.parametrize("style", ["json", "single_quoted", "unquoted"])
def test_extract_redacts_opaque_tokens_in_title_and_content(key, style):
    # No provider prefix or JWT shape: the field name must classify the secret.
    token = "synthetic-opaque-credential"
    if style == "json":
        text = json.dumps({key: token, "scope": "read"})
    elif style == "single_quoted":
        text = f"{key}='{token}'; scope=read"
    else:
        text = f"{key}={token}; scope=read"
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return {
            "answer": json.dumps(
                [{"type": "fact", "title": text, "content": text, "confidence": 0.9}]
            )
        }

    service = ConversationMemoryExtractionService(
        SimpleNamespace(answer=SimpleNamespace(generate=generate))
    )
    candidates = service.extract(
        namespace="memanto_agent_test",
        messages=[{"role": "user", "content": "Remember the authentication setup."}],
        ai_model="synthetic-model",
    )

    assert len(calls) == 1
    assert len(candidates) == 1
    candidate = candidates[0]
    for field in ("title", "content"):
        assert token not in candidate[field]
        assert "[REDACTED_CREDENTIAL]" in candidate[field]
        assert "scope" in candidate[field]
        assert "read" in candidate[field]
    assert candidate["source"] == "system"
    assert candidate["provenance"] == "inferred"
    assert candidate["confidence"] == 0.9
    if style == "json":
        assert json.loads(candidate["content"]) == {
            key: "[REDACTED_CREDENTIAL]",
            "scope": "read",
        }


@pytest.mark.parametrize(
    "key", ["api_key", "password", "auth_token", "client_secret", "aws_secret_access_key"]
)
def test_existing_credential_fields_remain_redacted(key):
    token = "synthetic-existing-credential"
    assert redact_sensitive_data(json.dumps({key: token})) == json.dumps(
        {key: "[REDACTED_CREDENTIAL]"}
    )


@pytest.mark.parametrize(
    "text",
    [
        "The access token is renewed by the client.",
        "refresh_token_count=2; token_type=Bearer; expires_in=3600",
        '{"scope": "read", "token_type": "Bearer", "expires_in": 3600}',
        "token_count=42; max_tokens=200; session_id=example",
    ],
)
def test_noncredential_token_metadata_is_unchanged(text):
    assert redact_sensitive_data(text) == text


def test_extract_redacts_basic_authentication_in_title_and_content():
    token = "dXNlcjpzeW50aGV0aWMtcGFzc3dvcmQ="
    cases = [
        ("Authorization: Basic " + token, token),
        (json.dumps({"Authorization": "Basic " + token, "scope": "read"}), token),
        ("Proxy-Authorization = 'bAsIc abc-def._~+/===é'; scope=read", "abc-def._~+/===é"),
    ]
    for text, credential in cases:
        calls = []

        def generate(**kwargs):
            calls.append(kwargs)
            return {
                "answer": json.dumps(
                    [{"type": "fact", "title": text, "content": text, "confidence": 0.9}]
                )
            }

        service = ConversationMemoryExtractionService(
            SimpleNamespace(answer=SimpleNamespace(generate=generate))
        )
        candidates = service.extract(
            namespace="memanto_agent_test",
            messages=[{"role": "user", "content": "Remember the authentication setup."}],
            ai_model="synthetic-model",
        )

        assert len(calls) == 1
        assert len(candidates) == 1
        candidate = candidates[0]
        expected = text.replace(credential, "[REDACTED_CREDENTIAL]")
        assert candidate["title"] == expected
        assert candidate["content"] == expected
        assert redact_sensitive_data(expected) == expected
        assert candidate["source"] == "system"
        assert candidate["provenance"] == "inferred"
        assert candidate["confidence"] == 0.9
        if text.startswith("{"):
            assert json.loads(candidate["content"]) == {
                "Authorization": "Basic [REDACTED_CREDENTIAL]",
                "scope": "read",
            }


def test_basic_auth_redaction_preserves_noncredential_text():
    for text in (
        "WWW-Authenticate: Basic realm=\"private\"",
        "X-Authorization: Basic example",
        "Authorization: Basic\nNext-Header: value",
        "Learn the Basic principles of authorization.",
    ):
        assert redact_sensitive_data(text) == text
