from fastapi import HTTPException

from memanto.app.utils.errors import (
    MemoryOperationError,
    create_error_response,
    map_error_to_http_exception,
)


def test_generic_errors_redact_secrets_from_client_details():
    api_key = "mk_" + ("a" * 40)
    session_token = "eyJ" + ("b" * 20) + "." + ("c" * 20) + "." + ("d" * 20)
    error = RuntimeError(
        f"upstream failed with Authorization: Bearer {api_key} "
        f"session_token={session_token}"
    )

    http_error = map_error_to_http_exception(error)
    rendered_detail = repr(http_error.detail)

    assert http_error.status_code == 500
    assert api_key not in rendered_detail
    assert session_token not in rendered_detail
    assert "[REDACTED]" in rendered_detail


def test_memanto_errors_redact_nested_detail_values():
    github_token = "gho_" + ("e" * 36)
    openai_key = "sk-proj-" + ("f" * 40)
    session_token = "eyJ" + ("g" * 20) + "." + ("h" * 20) + "." + ("i" * 20)
    error = MemoryOperationError(
        f"backend rejected api_key={openai_key}",
        details={
            "headers": {"Authorization": f"Bearer {github_token}"},
            "records": [{"session_token": session_token}],
            "safe": "kept",
        },
    )

    http_error = map_error_to_http_exception(error)
    rendered_detail = repr(http_error.detail)

    assert http_error.status_code == 500
    assert "kept" in rendered_detail
    assert github_token not in rendered_detail
    assert openai_key not in rendered_detail
    assert session_token not in rendered_detail
    assert "[REDACTED]" in rendered_detail


def test_http_exceptions_are_sanitized_when_remapped():
    github_token = "ghp_" + ("k" * 36)
    error = HTTPException(
        status_code=403,
        detail={"error": f"Authorization: Bearer {github_token}"},
        headers={"Retry-After": "1"},
    )

    http_error = map_error_to_http_exception(error)
    rendered_detail = repr(http_error.detail)

    assert http_error.status_code == 403
    assert http_error.headers == {"Retry-After": "1"}
    assert github_token not in rendered_detail
    assert "[REDACTED]" in rendered_detail


def test_create_error_response_redacts_sensitive_fields():
    api_key = "mk_" + ("j" * 40)
    cli_key = "provider-key-value-12345"

    response = create_error_response(
        "ValidationError",
        "bad request",
        {
            "x-api-key": api_key,
            "hint": f"use api_key={api_key}",
            "command": f"['moorcheh', 'up', '--embedding-api-key', '{cli_key}']",
        },
    )
    rendered_response = repr(response)

    assert api_key not in rendered_response
    assert cli_key not in rendered_response
    assert response["details"]["x-api-key"] == "[REDACTED]"
    assert "[REDACTED]" in rendered_response
