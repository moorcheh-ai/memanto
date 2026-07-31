"""
Idempotency Handling for MEMANTO
"""

import hashlib
import re
import time
import threading
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass
class IdempotencyRecord:
    """Idempotency record for duplicate prevention"""

    memory_id: str
    response: dict[str, Any]
    created_at: float
    ttl_seconds: int = 86400  # 24 hours default

    def is_expired(self) -> bool:
        """Check if record is expired"""
        return time.time() > (self.created_at + self.ttl_seconds)


class IdempotencyStore:
    """In-memory idempotency store (production should use Redis/database)"""

    def __init__(self) -> None:
        # Storage: idempotency_key -> IdempotencyRecord
        self.records: dict[str, IdempotencyRecord] = {}
        self.last_cleanup = time.time()
        self.cleanup_interval = 3600  # 1 hour
        self._lock = threading.Lock()
        # _lock guards ALL access to self.records.  The check-then-write
        # pattern in get_record / store_record is not atomic when the two
        # calls are separated — callers must use get_or_create for
        # atomicity, or hold the lock externally.

    def _cleanup_expired(self) -> None:
        """Remove expired records.  Caller MUST hold self._lock."""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return

        expired_keys = [
            key for key, record in self.records.items() if record.is_expired()
        ]

        for key in expired_keys:
            del self.records[key]

        self.last_cleanup = now

    def get_record(self, idempotency_key: str) -> IdempotencyRecord | None:
        """Get existing idempotency record (thread-safe)."""
        with self._lock:
            self._cleanup_expired()

            record = self.records.get(idempotency_key)
            if record and not record.is_expired():
                return record

            # Remove expired record
            if record:
                del self.records[idempotency_key]

            return None

    def store_record(
        self,
        idempotency_key: str,
        memory_id: str,
        response: dict[str, Any],
        ttl_seconds: int = 86400,
    ):
        """Store idempotency record (thread-safe)."""
        with self._lock:
            self._cleanup_expired()

            record = IdempotencyRecord(
                memory_id=memory_id,
                response=response,
                created_at=time.time(),
                ttl_seconds=ttl_seconds,
            )

            self.records[idempotency_key] = record

    def get_or_create(
        self,
        idempotency_key: str,
        memory_id: str,
        response: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> IdempotencyRecord | None:
        """Atomically check for an existing record and create one if absent.

        Returns the *existing* record (without modifying it) when a
        non-expired record is already present, so callers can return the
        cached response.  Returns ``None`` after creating a *new* record,
        signalling that the caller should proceed with the real operation.

        This is the atomic replacement for the previous
        check_idempotency → store_idempotent_response two-call pattern.
        """
        with self._lock:
            self._cleanup_expired()

            existing = self.records.get(idempotency_key)
            if existing and not existing.is_expired():
                return existing

            record = IdempotencyRecord(
                memory_id=memory_id,
                response=response,
                created_at=time.time(),
                ttl_seconds=ttl_seconds,
            )
            self.records[idempotency_key] = record
            return None

    def get_stats(self) -> dict[str, Any]:
        """Get idempotency store statistics (thread-safe)."""
        with self._lock:
            self._cleanup_expired()

            return {
                "total_records": len(self.records),
                "oldest_record_age": min(
                    (time.time() - record.created_at for record in self.records.values()),
                    default=0,
                ),
                "memory_usage_estimate": len(str(self.records)),
            }





# Global idempotency store
idempotency_store = IdempotencyStore()


class IdempotencyHandler:
    """Idempotency handling utilities"""

    @staticmethod
    def check_idempotency(idempotency_key: str | None) -> dict[str, Any] | None:
        """Check if request is duplicate based on idempotency key"""
        if not idempotency_key:
            return None

        record = idempotency_store.get_record(idempotency_key)
        if record:
            # Return cached response
            return record.response

        return None

    @staticmethod
    def store_idempotent_response(
        idempotency_key: str | None,
        memory_id: str,
        response: dict[str, Any],
        ttl_seconds: int = 86400,
    ):
        """Store response for idempotency"""
        if not idempotency_key:
            return

        idempotency_store.store_record(
            idempotency_key=idempotency_key,
            memory_id=memory_id,
            response=response,
            ttl_seconds=ttl_seconds,
        )

    @staticmethod
    def generate_idempotency_key(scope_id: str, content_hash: str) -> str:
        """Generate deterministic idempotency key"""

        key_data = f"{scope_id}:{content_hash}"
        return f"idem_{hashlib.sha256(key_data.encode()).hexdigest()[:16]}"

    @staticmethod
    def validate_idempotency_key(idempotency_key: str) -> bool:
        """Validate idempotency key format"""
        if not idempotency_key:
            return False

        # Must be reasonable length and format
        if len(idempotency_key) < 8 or len(idempotency_key) > 128:
            return False

        # Should contain only safe characters

        if not re.match(r"^[a-zA-Z0-9_-]+$", idempotency_key):
            return False

        return True


def handle_write_idempotency(idempotency_key: str | None) -> dict[str, Any] | None:
    """Handle idempotency for write operations

    Uses the atomic get_or_create so that the check and the initial store
    happen under a single lock acquisition — no other request can insert
    a record for the same key between the check and the write.
    """
    if not idempotency_key:
        return None

    if not IdempotencyHandler.validate_idempotency_key(idempotency_key):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_idempotency_key",
                "message": "Idempotency key must be 8-128 characters, alphanumeric with _ and - allowed",
            },
        )

    # Atomically check + reserve.  Returns existing record if already
    # present (idempotent replay), or None after creating a placeholder.
    existing = idempotency_store.get_or_create(
        idempotency_key=idempotency_key,
        memory_id="pending",
        response={"status": "pending"},
    )
    if existing:
        return existing.response

    return None


def store_write_idempotency(
    idempotency_key: str | None, memory_id: str, response: dict[str, Any]
):
    """Store write operation for idempotency"""
    if idempotency_key:
        IdempotencyHandler.store_idempotent_response(
            idempotency_key=idempotency_key, memory_id=memory_id, response=response
        )
