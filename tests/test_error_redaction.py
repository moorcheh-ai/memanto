"""Regression tests for public API error redaction."""

from memanto.app.utils.errors import MemoryOperationError, map_error_to_http_exception


def test_unexpected_error_does_not_expose_internal_exception_text():
    response = map_error_to_http_exception(
        RuntimeError("postgres://internal-db:5432/memories password=secret")
    )

    assert response.status_code == 500
    assert "postgres" not in str(response.detail).lower()
    assert "secret" not in str(response.detail).lower()


def test_memory_operation_error_does_not_expose_backend_response_details():
    response = map_error_to_http_exception(
        MemoryOperationError(
            "Moorcheh request to https://internal.example/vectors failed",
            details={"item_preview": "private vector metadata"},
        )
    )

    assert response.status_code == 500
    assert "internal.example" not in str(response.detail)
    assert "private vector" not in str(response.detail)
