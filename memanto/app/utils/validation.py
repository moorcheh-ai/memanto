"""
Input Validation and Cost Guards for MEMANTO
"""

import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, validator


class InputLimits:
    """Input size and cost limits"""

    # Text limits
    MAX_TEXT_LENGTH = 10000  # characters
    MAX_METADATA_SIZE = 5000  # bytes

    # Query limits
    MAX_K = 100  # maximum results
    MAX_NAMESPACES_FANOUT = 10  # future multi-namespace support

    # Answer limits
    MAX_ANSWER_TOKENS = 4000  # token budget for AI answers
    MAX_QUERY_LENGTH = 1000  # characters


class CostGuard:
    """Cost and abuse protection"""

    @staticmethod
    def validate_text_length(text: str, field_name: str = "text") -> str:
        """Validate text length"""
        if len(text) > InputLimits.MAX_TEXT_LENGTH:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "text_too_long",
                    "message": f"{field_name} exceeds maximum length of {InputLimits.MAX_TEXT_LENGTH} characters",
                    "actual_length": len(text),
                    "max_length": InputLimits.MAX_TEXT_LENGTH,
                },
            )
        return text

    @staticmethod
    def validate_metadata_size(metadata: dict[str, Any]) -> dict[str, Any]:
        """Validate metadata size"""
        metadata_bytes = len(str(metadata).encode("utf-8"))
        if metadata_bytes > InputLimits.MAX_METADATA_SIZE:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "metadata_too_large",
                    "message": f"Metadata exceeds maximum size of {InputLimits.MAX_METADATA_SIZE} bytes",
                    "actual_size": metadata_bytes,
                    "max_size": InputLimits.MAX_METADATA_SIZE,
                },
            )
        return metadata

    @staticmethod
    def validate_k_limit(k: int) -> int:
        """Validate k (result count) limit"""
        if k > InputLimits.MAX_K:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "k_too_large",
                    "message": f"k exceeds maximum of {InputLimits.MAX_K}",
                    "actual_k": k,
                    "max_k": InputLimits.MAX_K,
                },
            )
        return k

    @staticmethod
    def validate_query_length(query: str) -> str:
        """Validate query length"""
        if len(query) > InputLimits.MAX_QUERY_LENGTH:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "query_too_long",
                    "message": f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters",
                    "actual_length": len(query),
                    "max_length": InputLimits.MAX_QUERY_LENGTH,
                },
            )
        return query

    @staticmethod
    def validate_namespaces_fanout(namespaces: list[str]) -> list[str]:
        """Validate namespace fanout limit"""
        if len(namespaces) > InputLimits.MAX_NAMESPACES_FANOUT:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "too_many_namespaces",
                    "message": f"Too many namespaces, maximum is {InputLimits.MAX_NAMESPACES_FANOUT}",
                    "actual_count": len(namespaces),
                    "max_count": InputLimits.MAX_NAMESPACES_FANOUT,
                },
            )
        return namespaces


# Enhanced Pydantic models with validation
class ValidatedMemoryWriteRequest(BaseModel):
    """Memory write request with input validation"""

    text: str = Field(..., description="Memory text content")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @validator("text")
    def validate_text(cls, v):
        return CostGuard.validate_text_length(v, "text")

    @validator("metadata")
    def validate_metadata(cls, v):
        return CostGuard.validate_metadata_size(v)


class ValidatedMemoryReadRequest(BaseModel):
    """Memory read request with input validation"""

    query: str = Field(..., description="Search query")
    k: int = Field(default=10, ge=1, description="Number of results")

    @validator("query")
    def validate_query(cls, v):
        return CostGuard.validate_query_length(v)

    @validator("k")
    def validate_k(cls, v):
        return CostGuard.validate_k_limit(v)


class ValidatedMemoryAnswerRequest(BaseModel):
    """Memory answer request with input validation"""

    question: str = Field(..., description="Question to answer")

    @validator("question")
    def validate_question(cls, v):
        return CostGuard.validate_query_length(v)


def validate_request_size(
    request_body: bytes, max_size: int = 1024 * 1024
):  # 1MB default
    """Validate total request size"""
    if len(request_body) > max_size:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "request_too_large",
                "message": f"Request body exceeds maximum size of {max_size} bytes",
                "actual_size": len(request_body),
                "max_size": max_size,
            },
        )


def validate_safe_id(value: str, field_name: str = "id") -> str:
    """
    Reject agent_id / session_id values that would escape the storage directory.

    Path traversal via f-strings such as
        sessions_dir / f"{agent_id}.json"
    allows a caller to write files outside the intended directory when
    agent_id contains '..' or OS-level path separators.

    Only alphanumeric characters, hyphens, and underscores are allowed.
    """
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    # fullmatch (not match+$) so a trailing newline can't sneak through: `$`
    # matches before a final "\n" even without re.MULTILINE.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(
            f"{field_name} '{value}' contains invalid characters. "
            "Only letters, digits, hyphens, and underscores are allowed."
        )
    return value


def validate_output_path(
    output_path: str | None, base_dir: Path | None = None
) -> Path | None:
    """Restrict *output_path* to a safe base directory to prevent path traversal writes.

    An authenticated caller who supplies ``output_path="/etc/cron.d/evil"`` could
    overwrite arbitrary files on the server.  This guard resolves the requested path
    and ensures it remains inside *base_dir* (defaults to ``~/.memanto/``).

    Args:
        output_path: Raw path string from the API request, or ``None``.
        base_dir: Allowed parent directory.  Defaults to ``~/.memanto``.

    Returns:
        Resolved ``Path`` when *output_path* is provided, ``None`` otherwise.

    Raises:
        HTTPException(400): When the resolved path escapes *base_dir*.
    """
    if output_path is None:
        return None

    safe_base = (base_dir or Path.home() / ".memanto").resolve()
    try:
        candidate = Path(output_path)
        if not candidate.is_absolute():
            candidate = safe_base / candidate
        resolved = candidate.resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid output_path")

    try:
        resolved.relative_to(safe_base)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "output_path must be inside the agent data directory. "
                "Absolute paths that escape it are not allowed."
            ),
        )
    return resolved
