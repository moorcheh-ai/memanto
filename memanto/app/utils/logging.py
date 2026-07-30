"""
Structured Logging for MEMANTO Observability
"""

import hashlib
import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any

# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class MemantoLogger:
    """Structured JSON logger for MEMANTO"""

    @staticmethod
    def generate_request_id() -> str:
        """Generate unique request ID"""
        return f"req_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def redact_text(text: str, max_preview: int = 80) -> dict[str, Any]:
        """Redact sensitive text, return length + hash + preview"""
        if not text:
            return {"length": 0, "hash": "", "preview": ""}

        return {
            "length": len(text),
            "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "preview": text[:max_preview] if len(text) > max_preview else text,
        }

    @staticmethod
    def log_request(
        request_id: str,
        route: str,
        method: str,
        status_code: int,
        latency_ms: float,
        tenant_id: str | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
        endpoint_family: str | None = None,
        idempotency_key: str | None = None,
        errors: list[str] | None = None,
        **kwargs,
    ):
        """Log core request information"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "logger": "memanto.request",
            "request_id": request_id,
            "trace_id": trace_id_var.get(),
            "route": route,
            "method": method,
            "status_code": status_code,
            "latency_ms_total": round(latency_ms, 2),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "endpoint_family": endpoint_family,
            "idempotency_key": idempotency_key,
            "errors": errors or [],
        }

        # Add extra fields
        log_entry.update(kwargs)

        # Remove None values
        log_entry = {k: v for k, v in log_entry.items() if v is not None}

        print(json.dumps(log_entry))

    @staticmethod
    def log_memory_write(
        request_id: str,
        memory_type: str,
        provisional: bool,
        confidence_in: float,
        confidence_stored: float,
        ttl_seconds: int | None,
        text_len_chars: int,
        metadata_size_bytes: int,
        validation_outcome: str,
        validation_warnings: list[str],
        document_count: int,
        moorcheh_upload_status: str,
        latency_ms: float,
    ):
        """Log memory write operation"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "logger": "memanto.memory.write",
            "request_id": request_id,
            "memory_type": memory_type,
            "provisional": provisional,
            "confidence_in": confidence_in,
            "confidence_stored": confidence_stored,
            "ttl_seconds": ttl_seconds,
            "text_len_chars": text_len_chars,
            "metadata_size_bytes": metadata_size_bytes,
            "validation_outcome": validation_outcome,
            "validation_warnings": validation_warnings,
            "document_count": document_count,
            "moorcheh_upload_status": moorcheh_upload_status,
            "latency_ms": round(latency_ms, 2),
        }

        print(json.dumps(log_entry))

    @staticmethod
    def log_memory_read(
        request_id: str,
        query_len_chars: int,
        k_requested: int,
        k_returned: int,
        filters_applied: dict[str, Any],
        score_stats: dict[str, float] | None,
        namespace_fanout_count: int,
        latency_ms: float,
    ):
        """Log memory read operation"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "logger": "memanto.memory.read",
            "request_id": request_id,
            "query_len_chars": query_len_chars,
            "k_requested": k_requested,
            "k_returned": k_returned,
            "filters_applied": filters_applied,
            "score_stats": score_stats,
            "namespace_fanout_count": namespace_fanout_count,
            "latency_ms": round(latency_ms, 2),
        }

        print(json.dumps(log_entry))

    @staticmethod
    def log_memory_delete(
        request_id: str,
        delete_count_requested: int,
        delete_count_success: int,
        latency_ms: float,
    ):
        """Log memory delete operation"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "logger": "memanto.memory.delete",
            "request_id": request_id,
            "delete_count_requested": delete_count_requested,
            "delete_count_success": delete_count_success,
            "latency_ms": round(latency_ms, 2),
        }

        print(json.dumps(log_entry))

    @staticmethod
    def log_moorcheh_call(
        request_id: str,
        method: str,
        success: bool,
        latency_ms: float,
        error_code: str | None = None,
    ):
        """Log Moorcheh SDK calls"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO" if success else "ERROR",
            "logger": "memanto.moorcheh",
            "request_id": request_id,
            "method": method,
            "success": success,
            "latency_ms": round(latency_ms, 2),
            "error_code": error_code,
        }

        print(json.dumps(log_entry))


def track_moorcheh_call(method_name: str):
    """Decorator to track Moorcheh SDK calls"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request_id = request_id_var.get()
            start_time = time.time()
            success = True
            error_code = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_code = type(e).__name__
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                MemantoLogger.log_moorcheh_call(
                    request_id=request_id,
                    method=method_name,
                    success=success,
                    latency_ms=latency_ms,
                    error_code=error_code,
                )

        return wrapper

    return decorator


def get_logger(name: str) -> logging.Logger:
    """Compatibility helper for modules using stdlib-style named loggers."""
    return logging.getLogger(name)
