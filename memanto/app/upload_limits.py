"""Shared upload size limits."""

MAX_UPLOAD_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
UPLOAD_CHUNK_SIZE = 1024 * 1024
MULTIPART_FORM_OVERHEAD_SIZE = 100_000
MAX_REQUEST_BODY_SIZE = MAX_UPLOAD_FILE_SIZE + MULTIPART_FORM_OVERHEAD_SIZE


def file_too_large_detail(
    actual_size: int,
    max_size: int = MAX_UPLOAD_FILE_SIZE,
) -> dict[str, int | str]:
    """Return the API detail payload for oversized uploads."""
    return {
        "error": "file_too_large",
        "message": f"File exceeds maximum size of {max_size} bytes",
        "actual_size": actual_size,
        "max_size": max_size,
    }
