"""
Error Handling and Mapping
"""

import re
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

_REDACTED = "[REDACTED]"

_AUTH_HEADER_PATTERN = re.compile(
    r"\b(Authorization\s*:\s*(?:Bearer|Basic|Token)\s+)([^\s,'\"}]+)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b(api[_-]?key|session[_-]?token|access[_-]?token|refresh[_-]?token|"
    r"password|secret)\b(\s*[:=]\s*)([^\s,'\"}]+)",
    re.IGNORECASE,
)
_CLI_SECRET_ARG_PATTERN = re.compile(
    r"((?:--|/)[A-Za-z0-9_-]*(?:api[-_]?key|token|secret|password)"
    r"[A-Za-z0-9_-]*(?:['\"]?,\s*['\"]|\s+))([^'\"\s,]+)",
    re.IGNORECASE,
)
_BARE_SECRET_PATTERN = re.compile(
    r"\b(?:mk_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|"
    r"gh[opsru]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|"
    r"hf_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,})\b"
)
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)
_SENSITIVE_DETAIL_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "session_token",
    "token",
    "x_api_key",
    "access_token",
    "refresh_token",
}


def redact_sensitive_text(text: str) -> str:
    """Redact secrets from text before exposing it to API callers."""
    redacted = _AUTH_HEADER_PATTERN.sub(rf"\1{_REDACTED}", text)
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(rf"\1\2{_REDACTED}", redacted)
    redacted = _CLI_SECRET_ARG_PATTERN.sub(rf"\1{_REDACTED}", redacted)
    redacted = _JWT_PATTERN.sub(_REDACTED, redacted)
    return _BARE_SECRET_PATTERN.sub(_REDACTED, redacted)


def _is_sensitive_detail_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in _SENSITIVE_DETAIL_KEYS or normalized.endswith(
        ("_api_key", "_password", "_secret", "_token")
    )


def sanitize_error_details(value: Any) -> Any:
    """Recursively redact secrets from details included in client errors."""
    if isinstance(value, str):
        return redact_sensitive_text(value)

    if isinstance(value, bytes):
        return redact_sensitive_text(value.decode(errors="replace"))

    if isinstance(value, Mapping):
        return {
            key: _REDACTED
            if _is_sensitive_detail_key(key)
            else sanitize_error_details(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [sanitize_error_details(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_error_details(item) for item in value)

    return value


def _http_error(
    status_code: int,
    error_type: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=create_error_response(error_type, message, details),
    )


class MemantoError(Exception):
    """Base MEMANTO exception"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(MemantoError):
    """Memory validation error"""

    pass


class MemoryOperationError(MemantoError):
    """Memory operation error"""

    pass


# Deprecated alias to maintain compatibility with external integrations like MCP.
MemoryError = MemoryOperationError


class NamespaceError(MemantoError):
    """Namespace operation error"""

    pass


class AuthenticationError(MemantoError):
    """Authentication error"""

    pass


class AuthorizationError(MemantoError):
    """Authorization error"""

    pass


class SessionError(MemantoError):
    """Session operation error"""

    pass


class SessionExpiredError(SessionError):
    """Session has expired"""

    pass


class SessionNotFoundError(SessionError):
    """Session not found"""

    pass


class InvalidSessionTokenError(SessionError):
    """Invalid session token"""

    pass


class AgentError(MemantoError):
    """Agent operation error"""

    pass


class AgentNotFoundError(AgentError):
    """Agent not found"""

    pass


class AgentAlreadyExistsError(AgentError):
    """Agent already exists"""

    pass


def map_error_to_http_exception(error: Exception) -> HTTPException:
    """Map internal errors to HTTP exceptions"""

    if isinstance(error, HTTPException):
        return HTTPException(
            status_code=error.status_code,
            detail=sanitize_error_details(error.detail),
            headers=error.headers,
        )

    if isinstance(error, ValidationError):
        return _http_error(400, "ValidationError", error.message, error.details)

    elif isinstance(error, MemoryOperationError):
        return _http_error(500, "MemoryOperationError", error.message, error.details)

    elif isinstance(error, NamespaceError):
        return _http_error(400, "NamespaceError", error.message, error.details)

    elif isinstance(error, AuthenticationError):
        return _http_error(401, "AuthenticationError", error.message, error.details)

    elif isinstance(error, AuthorizationError):
        return _http_error(403, "AuthorizationError", error.message, error.details)

    elif isinstance(error, SessionExpiredError):
        return _http_error(401, "SessionExpired", error.message, error.details)

    elif isinstance(error, SessionNotFoundError):
        return _http_error(404, "SessionNotFound", error.message, error.details)

    elif isinstance(error, InvalidSessionTokenError):
        return _http_error(401, "InvalidSessionToken", error.message, error.details)

    elif isinstance(error, AgentNotFoundError):
        return _http_error(404, "AgentNotFound", error.message, error.details)

    elif isinstance(error, AgentAlreadyExistsError):
        return _http_error(409, "AgentAlreadyExists", error.message, error.details)

    else:
        # Generic server error
        return _http_error(
            500,
            "InternalServerError",
            "An unexpected error occurred",
            {"original_error": str(error)},
        )


def create_error_response(
    error_type: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create standardized error response"""
    return {
        "error": error_type,
        "message": redact_sensitive_text(message),
        "details": sanitize_error_details(details or {}),
    }
