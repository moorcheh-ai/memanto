"""
Error Handling and Mapping
"""

from typing import Any

from fastapi import HTTPException


class MemantoError(Exception):
    """Base MEMANTO exception"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(MemantoError):
    """Memory validation error"""



class MemoryError(MemantoError):
    """Memory operation error"""



class NamespaceError(MemantoError):
    """Namespace operation error"""



class AuthenticationError(MemantoError):
    """Authentication error"""



class AuthorizationError(MemantoError):
    """Authorization error"""



class SessionError(MemantoError):
    """Session operation error"""



class SessionExpiredError(SessionError):
    """Session has expired"""



class SessionNotFoundError(SessionError):
    """Session not found"""



class InvalidSessionTokenError(SessionError):
    """Invalid session token"""



class AgentError(MemantoError):
    """Agent operation error"""



class AgentNotFoundError(AgentError):
    """Agent not found"""



class AgentAlreadyExistsError(AgentError):
    """Agent already exists"""



def map_error_to_http_exception(error: Exception) -> HTTPException:
    """Map internal errors to HTTP exceptions"""

    if isinstance(error, ValidationError):
        return HTTPException(
            status_code=400,
            detail={
                "error": "ValidationError",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, MemoryError):
        return HTTPException(
            status_code=500,
            detail={
                "error": "MemoryError",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, NamespaceError):
        return HTTPException(
            status_code=400,
            detail={
                "error": "NamespaceError",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, AuthenticationError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "AuthenticationError",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, AuthorizationError):
        return HTTPException(
            status_code=403,
            detail={
                "error": "AuthorizationError",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, SessionExpiredError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "SessionExpired",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, SessionNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "error": "SessionNotFound",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, InvalidSessionTokenError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "InvalidSessionToken",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, AgentNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "error": "AgentNotFound",
                "message": error.message,
                "details": error.details,
            },
        )

    if isinstance(error, AgentAlreadyExistsError):
        return HTTPException(
            status_code=409,
            detail={
                "error": "AgentAlreadyExists",
                "message": error.message,
                "details": error.details,
            },
        )

    # Generic server error
    return HTTPException(
        status_code=500,
        detail={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": {"original_error": str(error)},
        },
    )


def create_error_response(
    error_type: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create standardized error response"""
    return {"error": error_type, "message": message, "details": details or {}}
