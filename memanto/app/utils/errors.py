"""
Error Handling and Mapping
"""

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


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
        return error

    if isinstance(error, ValidationError):
        return HTTPException(
            status_code=400,
            detail={
                "error": "ValidationError",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, MemoryOperationError):
        # Backend exceptions can contain hostnames, request bodies, vector
        # metadata, or provider error payloads. They are useful internally but
        # must never become part of a public 500 response.
        logger.error("Memory operation failed: %s", type(error).__name__)
        return HTTPException(
            status_code=500,
            detail={
                "error": "MemoryOperationError",
                "message": "A memory operation failed.",
            },
        )

    elif isinstance(error, NamespaceError):
        return HTTPException(
            status_code=400,
            detail={
                "error": "NamespaceError",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, AuthenticationError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "AuthenticationError",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, AuthorizationError):
        return HTTPException(
            status_code=403,
            detail={
                "error": "AuthorizationError",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, SessionExpiredError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "SessionExpired",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, SessionNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "error": "SessionNotFound",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, InvalidSessionTokenError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "InvalidSessionToken",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, AgentNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "error": "AgentNotFound",
                "message": error.message,
                "details": error.details,
            },
        )

    elif isinstance(error, AgentAlreadyExistsError):
        return HTTPException(
            status_code=409,
            detail={
                "error": "AgentAlreadyExists",
                "message": error.message,
                "details": error.details,
            },
        )

    else:
        # Generic server error
        logger.error("Unhandled internal error: %s", type(error).__name__)
        return HTTPException(
            status_code=500,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
            },
        )


def create_error_response(
    error_type: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create standardized error response"""
    return {"error": error_type, "message": message, "details": details or {}}
