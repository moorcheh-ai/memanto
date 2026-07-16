"""
Safer Deletion with Audit Logging for MEMANTO
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException


@dataclass
class DeletionAuditRecord:
    """Audit record for deletion operations"""

    timestamp: str
    scope_type: str
    scope_id: str
    actor_id: str
    deleted_ids: list[str]
    deletion_method: str  # "by_ids", "by_selector" (future)
    request_id: str
    success: bool
    error: str | None = None


class DeletionAuditor:
    """Audit logger for deletion operations"""

    def __init__(self) -> None:
        # In production, this should write to secure audit log storage
        self.audit_log: list[DeletionAuditRecord] = []

    def log_deletion(
        self,
        scope_type: str,
        scope_id: str,
        actor_id: str,
        deleted_ids: list[str],
        deletion_method: str,
        request_id: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Log deletion operation"""
        record = DeletionAuditRecord(
            timestamp=datetime.utcnow().isoformat(),
            scope_type=scope_type,
            scope_id=scope_id,
            actor_id=actor_id,
            deleted_ids=deleted_ids.copy(),
            deletion_method=deletion_method,
            request_id=request_id,
            success=success,
            error=error,
        )

        self.audit_log.append(record)

        # Also log to structured logging

        log_data = {
            "audit_event": "memory_deletion",
            "scope_type": scope_type,
            "scope_id": scope_id,
            "actor_id": actor_id,
            "deleted_count": len(deleted_ids),
            "deletion_method": deletion_method,
            "success": success,
            "error": error,
        }

        print(
            json.dumps(
                {
                    "timestamp": record.timestamp,
                    "level": "INFO" if success else "ERROR",
                    "logger": "memanto.audit.deletion",
                    "request_id": request_id,
                    **log_data,
                }
            )
        )

    def get_audit_records(
        self, scope_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get audit records (for admin/compliance)"""
        records = self.audit_log

        if scope_id:
            records = [r for r in records if r.scope_id == scope_id]

        # Return most recent first
        records = sorted(records, key=lambda x: x.timestamp, reverse=True)

        return [asdict(record) for record in records[:limit]]


# Global deletion auditor
deletion_auditor = DeletionAuditor()


class SafeDeletion:
    """Safe deletion utilities with validation and audit"""

    @staticmethod
    def validate_deletion_request(
        scope_type: str, scope_id: str, ids: list[str], authenticated_scope_id: str
    ):
        """Validate deletion request"""

        # 1. Require correct scope
        if scope_id != authenticated_scope_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "scope_mismatch",
                    "message": f"Cannot delete from scope {scope_id} when authenticated as {authenticated_scope_id}",
                },
            )

        # 2. Validate IDs format
        if not ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no_ids_provided",
                    "message": "At least one memory ID must be provided for deletion",
                },
            )

        # 3. Limit batch size
        if len(ids) > 100:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "too_many_ids",
                    "message": "Cannot delete more than 100 memories at once",
                    "provided_count": len(ids),
                    "max_count": 100,
                },
            )

        # 4. Validate ID format
        invalid_ids = [id for id in ids if not SafeDeletion._is_valid_memory_id(id)]
        if invalid_ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_memory_ids",
                    "message": "Some memory IDs have invalid format",
                    "invalid_ids": invalid_ids[:10],  # Limit error response size
                },
            )

    @staticmethod
    def _is_valid_memory_id(memory_id: str) -> bool:
        """Validate memory ID format"""
        if not memory_id or len(memory_id) < 4:
            return False

        # Should match our ID generation pattern

        return bool(re.match(r"^[a-zA-Z0-9_-]+$", memory_id))

    @staticmethod
    def perform_safe_deletion(
        scope_type: str,
        scope_id: str,
        ids: list[str],
        actor_id: str,
        request_id: str,
        moorcheh_client,
    ) -> dict[str, Any]:
        """Perform deletion with audit logging"""
        from typing import cast

        from memanto.app.constants import ScopeType
        from memanto.app.core import create_memory_scope

        try:
            # Compute namespace
            scope = create_memory_scope(cast(ScopeType, scope_type), scope_id)
            namespace = scope.to_namespace()

            # Perform deletion
            delete_result = moorcheh_client.documents.delete(
                namespace_name=namespace, ids=ids
            )

            deleted_count = delete_result.get("actual_deletions", 0)
            success = True
            error = None

            # Log successful deletion
            deletion_auditor.log_deletion(
                scope_type=scope_type,
                scope_id=scope_id,
                actor_id=actor_id,
                deleted_ids=ids,
                deletion_method="by_ids",
                request_id=request_id,
                success=success,
                error=error,
            )

            return {
                "status": "success",
                "deleted_count": deleted_count,
                "requested_count": len(ids),
                "namespace": namespace,
                "audit_logged": True,
            }

        except Exception as e:
            error = str(e)
            success = False

            # Log failed deletion
            deletion_auditor.log_deletion(
                scope_type=scope_type,
                scope_id=scope_id,
                actor_id=actor_id,
                deleted_ids=ids,
                deletion_method="by_ids",
                request_id=request_id,
                success=success,
                error=error,
            )

            raise


def validate_and_delete_memories(
    scope_type: str,
    scope_id: str,
    ids: list[str],
    authenticated_scope_id: str,
    actor_id: str,
    request_id: str,
    moorcheh_client,
) -> dict[str, Any]:
    """Main function for safe memory deletion"""

    # Validate request
    SafeDeletion.validate_deletion_request(
        scope_type=scope_type,
        scope_id=scope_id,
        ids=ids,
        authenticated_scope_id=authenticated_scope_id,
    )

    # Perform deletion with audit
    return SafeDeletion.perform_safe_deletion(
        scope_type=scope_type,
        scope_id=scope_id,
        ids=ids,
        actor_id=actor_id,
        request_id=request_id,
        moorcheh_client=moorcheh_client,
    )
