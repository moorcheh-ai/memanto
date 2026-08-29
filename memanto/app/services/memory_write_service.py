"""
Memory Write Service
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.constants import VALID_STATUS_TYPES
from memanto.app.core import MemoryRecord, is_valid_expired_by, is_valid_source
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.utils.errors import MemoryOperationError
from memanto.app.utils.ids import generate_memory_id
from memanto.app.utils.temporal_helpers import as_utc_aware

SUCCESSFUL_UPLOAD_STATUSES = {"queued", "success", "ok"}

# Fields owned by the current MemoryRecord/document schema. They must not be
# copied from the old document after an update because an omitted optional field
# (for example, tags=[] or source_ref=None) represents an intentional clear.
_MEMORY_SCHEMA_FIELDS = frozenset(
    {
        "id",
        "text",
        "memory_type",
        "type",
        "title",
        "content",
        "agent_id",
        "actor_id",
        "source",
        "source_ref",
        "confidence",
        "status",
        "tags",
        "provenance",
        "created_at",
        "updated_at",
        "expired_at",
        "expired_by",
        "score",
        "metadata",
        "scope_type",
        "scope_id",
    }
)

# Fields removed from the active schema. Old on-prem data_store.json records
# may still carry them; they must never be copied forward on update or we
# resurrect dead schema that no live read/write flow populates.
#
# The first group is the 2026-06-29 "trust" machinery. The second is the TTL
# pair, replaced by the stamped `status` / `expired_at` / `expired_by`
# lifecycle: a future-dated deadline no longer has any meaning, and leaving one
# on a record would make it look expiry-bound to any external reader.
_REMOVED_SCHEMA_FIELDS = frozenset(
    {
        "superseded_by",
        "supersedes",
        "validated_at",
        "validation_count",
        "contradiction_detected",
        "expires_at",
        "ttl_seconds",
    }
)

# The stamp that travels with `status`. Owned by lifecycle transitions, never
# carried forward blindly from a prior version of the record.
_LIFECYCLE_STAMP_FIELDS = frozenset({"expired_at", "expired_by"})


class MemoryWriteService:
    """Persist memory records to Moorcheh-backed namespaces."""

    def __init__(self, moorcheh_client: "MoorchehClient"):
        """Initialize the service with a Moorcheh client."""

        self.client = moorcheh_client
        self._parser = MemoryParsingService()
        self._namespace_service = None

    @property
    def namespace_service(self):
        """Lazily create the namespace service used for memory scopes."""

        if self._namespace_service is None:
            from memanto.app.services.namespace_service import NamespaceService

            self._namespace_service = NamespaceService(self.client)
        return self._namespace_service

    def _apply_timestamps(self, memory: MemoryRecord, now: datetime) -> None:
        """Apply server timestamps while preserving imported source chronology."""
        if memory.provenance == "imported":
            memory.created_at = as_utc_aware(memory.created_at)
            memory.updated_at = as_utc_aware(memory.updated_at)

            # Clamp to current time if in the future
            if memory.created_at > now:
                memory.created_at = now
            if memory.updated_at > now:
                memory.updated_at = now

            # Enforce created_at <= updated_at invariant
            if memory.created_at > memory.updated_at:
                memory.created_at = memory.updated_at
            return
        memory.created_at = now
        memory.updated_at = now

    def store_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Store memory with validation"""
        try:
            # Generate ID if not provided
            if not memory.id:
                memory.id = generate_memory_id()

            now = datetime.now(timezone.utc)
            self._apply_timestamps(memory, now)

            # Auto parse memory type
            memory = self._parser.parse_memory(memory)

            # Add namespace
            namespace = memory.namespace()

            # skip validation for speed
            ## Validate memory
            # validation_result = self.validation_service.validate_memory(memory, context)
            ## Use validated memory if modified
            # if "memory" in validation_result:
            #     memory = validation_result["memory"]
            validation_result = {"action": "store", "reason": "MVP direct store"}

            from typing import cast

            from moorcheh_sdk.types.document import Document

            # Convert to Moorcheh document
            document = cast(Document, memory.to_moorcheh_document())

            # Store in Moorcheh
            result = self.client.documents.upload(
                namespace_name=namespace, documents=[document]
            )

            return {
                "id": memory.id,
                "namespace": namespace,
                "status": result.get("status", "unknown"),
                "action": validation_result.get("action", "store"),
                "reason": validation_result.get("reason", "Stored successfully"),
                "confidence": memory.confidence,
                "memory_status": memory.status,
                "type": memory.type,
            }

        except Exception as e:
            raise MemoryOperationError(f"Failed to store memory: {e}")

    def batch_store_memories(
        self, memories: list[MemoryRecord], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Store multiple memories in batch leveraging Moorcheh's 100 docs/request capability

        Args:
            memories: List of MemoryRecord objects to store (max 100)
            context: Optional context dict with validation info

        Returns:
            Dict with batch operation results including success/failure counts
        """
        try:
            if not memories:
                raise MemoryOperationError("No memories provided for batch operation")

            if len(memories) > 100:
                raise MemoryOperationError(
                    f"Batch size {len(memories)} exceeds Moorcheh's limit of 100 documents per request"
                )

            # Ensure all memories are in same namespace
            first_namespace = None
            results = []
            validated_documents = []

            # Enforce server-side timestamps for batch (single timestamp for all)
            now = datetime.now(timezone.utc)

            for memory in memories:
                try:
                    # Generate ID if not provided
                    if not memory.id:
                        memory.id = generate_memory_id()

                    self._apply_timestamps(memory, now)

                    memory = self._parser.parse_memory(memory)

                    # Add namespace
                    namespace = memory.namespace()

                    if first_namespace is None:
                        first_namespace = namespace
                    elif namespace != first_namespace:
                        # Different namespaces - reject this memory
                        results.append(
                            {
                                "id": memory.id,
                                "status": "failed",
                                "action": "rejected",
                                "reason": "All memories in batch must be in same namespace",
                                "error": f"Expected namespace {first_namespace}, got {namespace}",
                            }
                        )
                        continue

                    # skip validation for speed
                    ## Validate memory
                    # validation_result = self.validation_service.validate_memory(memory, context)
                    ## Use validated memory if modified
                    # if "memory" in validation_result:
                    #     memory = validation_result["memory"]
                    validation_result = {
                        "action": "store",
                        "reason": "MVP direct store",
                    }

                    from typing import cast

                    from moorcheh_sdk.types.document import Document

                    # Convert to Moorcheh document
                    document = cast(Document, memory.to_moorcheh_document())
                    validated_documents.append(document)

                    # Store validation result for later
                    results.append(
                        {
                            "id": memory.id,
                            "status": "pending",
                            "action": validation_result.get("action", "store"),
                            "reason": validation_result.get(
                                "reason", "Validated successfully"
                            ),
                            "type": memory.type,
                        }
                    )

                except Exception as e:
                    results.append(
                        {
                            "id": memory.id
                            if hasattr(memory, "id") and memory.id
                            else "unknown",
                            "status": "failed",
                            "action": "rejected",
                            "error": str(e),
                        }
                    )

            # Upload all validated documents in single batch to Moorcheh
            if validated_documents and first_namespace:
                from typing import cast

                upload_result = self.client.documents.upload(
                    namespace_name=cast(str, first_namespace),
                    documents=validated_documents,
                )

                # Update results with upload status
                moorcheh_status = str(upload_result.get("status", "unknown")).lower()
                for result in results:
                    if result["status"] == "pending":
                        if moorcheh_status in SUCCESSFUL_UPLOAD_STATUSES:
                            result["status"] = moorcheh_status
                        else:
                            result["status"] = "failed"
                            result["error"] = (
                                f"Batch upload returned status '{moorcheh_status}'"
                            )

            # Count successes, failures, and namespace-rejected items separately
            # so that successful + failed + rejected == total_submitted always.
            successful = 0
            failed = 0
            rejected = 0
            for r in results:
                status = str(r["status"]).lower()
                if status in SUCCESSFUL_UPLOAD_STATUSES:
                    successful += 1
                elif status == "rejected":
                    rejected += 1
                else:
                    # Validation failures carry status="failed"/action="rejected"
                    # and must stay in `failed`: the batch endpoints return only
                    # successful/failed (see routes/memory.py), so counting them
                    # as `rejected` would drop them from the response entirely.
                    # Non-standard upload statuses are absorbed here too.
                    failed += 1
                    r["status"] = "failed"

            return {
                "total_submitted": len(results),
                "successful": successful,
                "failed": failed,
                "rejected": rejected,
                "namespace": first_namespace,
                "results": results,
            }

        except Exception as e:
            raise MemoryOperationError(f"Failed to batch store memories: {e}")

    def update_memory(
        self,
        memory_id: str,
        namespace: str,
        updates: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update existing memory.

        Moorcheh supports overwriting documents by ID, so we:
        1. Retrieve the existing memory
        2. Apply updates to create new version
        3. Upload new version with same ID (overwrites)

        Args:
            memory_id: ID of memory to update
            namespace: Namespace containing the memory
            updates: Dict of fields to update
            context: Optional validation context

        Returns:
            Dict with update result
        """
        try:
            from memanto.app.services.memory_read_service import MemoryReadService

            # Step 1: Retrieve existing memory
            read_service = MemoryReadService(self.client)
            existing_memory_data = read_service.get_memory(memory_id, namespace)

            if not existing_memory_data:
                raise MemoryOperationError(
                    f"Memory {memory_id} not found in namespace {namespace}"
                )

            # Step 2: Create updated MemoryRecord
            metadata = (
                existing_memory_data.get("metadata", {})
                if "metadata" in existing_memory_data
                else existing_memory_data
            )

            # The namespace (memanto_agent_{agent_id}) is authoritative for the
            # agent_id; fall back to it when stored metadata predates the flat
            # agent_id field so the rewritten record keeps correct metadata.
            agent_id = metadata.get("agent_id")
            if not agent_id and namespace.startswith("memanto_agent_"):
                agent_id = namespace.removeprefix("memanto_agent_")
            if not agent_id:
                raise MemoryOperationError(
                    f"Cannot determine agent_id for memory {memory_id} "
                    f"in namespace {namespace}"
                )

            # Sources are open labels (the writer's name), so keep whatever the
            # record carries. Only a value MemoryRecord would reject — blank, or
            # one holding characters that break `#source:` filters — falls back,
            # so an edit cannot fail on data written before the label was bounded.
            source_val = updates.get("source", metadata.get("source", "system"))
            if not is_valid_source(source_val):
                source_val = "system"

            # Records predating the two-state lifecycle can carry a retired
            # status ("superseded", "provisional", "deleted"). Those are not
            # valid StatusType values any more, so treat anything unrecognised
            # as active rather than failing the edit outright.
            status_val = updates.get("status", metadata.get("status", "active"))
            if status_val not in VALID_STATUS_TYPES:
                status_val = "active"

            # Build updated memory record
            updated_memory = MemoryRecord(
                id=memory_id,  # Keep same ID
                type=updates.get("type", metadata.get("type", "fact")),
                title=updates.get(
                    "title", existing_memory_data.get("title", "Updated Memory")
                ),
                content=updates.get("content", existing_memory_data.get("content", "")),
                agent_id=agent_id,
                actor_id=updates.get("actor_id", metadata.get("actor_id", "unknown")),
                source=source_val,
                source_ref=updates.get("source_ref", metadata.get("source_ref")),
                confidence=updates.get("confidence", metadata.get("confidence", 0.8)),
                status=status_val,
                tags=updates.get("tags", metadata.get("tags", [])),
                provenance=updates.get(
                    "provenance", metadata.get("provenance") or "explicit_statement"
                ),
            )

            # Update timestamps (preserve created_at, set updated_at to now)
            raw_created = metadata.get("created_at")
            if raw_created:
                if isinstance(raw_created, str):
                    try:
                        updated_memory.created_at = datetime.fromisoformat(
                            raw_created.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pass  # Keep default
                else:
                    updated_memory.created_at = raw_created
            updated_memory.updated_at = datetime.now(timezone.utc)

            # Expiry stamp. An explicit lifecycle transition passes the stamp in
            # `updates` and owns it outright; any other edit preserves whatever
            # the stored record carries, so editing the text of an expired
            # memory cannot silently revive it. Restoring leaves both fields
            # None, which clears the stamp.
            if _LIFECYCLE_STAMP_FIELDS & set(updates):
                updated_memory.expired_at = updates.get("expired_at")
                updated_memory.expired_by = updates.get("expired_by")
            elif updated_memory.status == "expired":
                raw_expired_at = metadata.get("expired_at")
                if raw_expired_at:
                    if isinstance(raw_expired_at, str):
                        try:
                            updated_memory.expired_at = datetime.fromisoformat(
                                raw_expired_at.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass  # Keep the default if the stored timestamp is invalid
                    else:
                        updated_memory.expired_at = raw_expired_at
                expired_by = metadata.get("expired_by")
                if is_valid_expired_by(expired_by):
                    updated_memory.expired_by = expired_by

            # Step 3: Upload new version (overwrites existing document with same ID).
            # Uploading with the same ID is safe — Moorcheh treats it as an upsert,
            # so the original is never lost if the upload call fails.
            from typing import Any, cast

            from moorcheh_sdk.types.document import Document

            validation_result = {"action": "store", "reason": "MVP direct store"}

            document = cast(Document, updated_memory.to_moorcheh_document())

            # Preserve extra metadata fields from the existing record (e.g. original_id
            # in on-prem data_store.json) that aren't part of the MemoryRecord schema.
            #
            # The lifecycle stamp is deliberately excluded: `to_moorcheh_document`
            # omits both fields when a memory is active, so copying them back
            # from the old record would resurrect the previous expiry stamp on
            # every restore.
            existing_meta = existing_memory_data.get("metadata", existing_memory_data)
            if isinstance(existing_meta, dict):
                extra_document = cast(dict[str, Any], document)
                for key in existing_meta:
                    if (
                        key not in _MEMORY_SCHEMA_FIELDS
                        and key not in _REMOVED_SCHEMA_FIELDS
                        and key not in _LIFECYCLE_STAMP_FIELDS
                    ):
                        extra_document[key] = existing_meta[key]

            try:
                upload_result = self.client.documents.upload(
                    namespace_name=namespace, documents=[document]
                )
            except Exception as e:
                raise MemoryOperationError(f"Upload failed. Error: {e}")

            status = upload_result.get("status", "unknown")
            if str(status).lower() not in SUCCESSFUL_UPLOAD_STATUSES:
                raise MemoryOperationError(
                    f"Failed to upload updated memory {memory_id}: {status}"
                )

            return {
                "id": memory_id,
                "namespace": namespace,
                "status": status,
                "action": "updated",
                "reason": "Memory updated successfully via overwrite",
                "validation": validation_result.get("action", "validated"),
                "updated_fields": list(updates.keys()),
            }

        except MemoryOperationError:
            raise
        except Exception as e:
            raise MemoryOperationError(f"Failed to update memory: {e}")

    def set_lifecycle(
        self,
        memory_id: str,
        namespace: str,
        *,
        expired: bool,
        reason: str | None = None,
        when: datetime | None = None,
    ) -> dict[str, Any]:
        """Move one memory between the active and expired states.

        Expiring stamps ``status``, ``expired_at`` and ``expired_by`` together;
        restoring clears all three. This is a metadata-only rewrite — the
        memory's text, tags, confidence and timestamps are untouched, and no
        content is destroyed either way.

        Args:
            memory_id: ID of the memory to transition
            namespace: Namespace containing the memory
            expired: True to expire, False to restore
            reason: Why it expired (policy rule name, ``manual``,
                ``conflict-resolution``). Required when expiring.
            when: Expiry timestamp; defaults to now. Lets a sweep stamp a whole
                batch with one consistent time.

        Returns:
            Dict describing the transition that was applied.
        """
        if expired:
            if not reason:
                raise MemoryOperationError(
                    "A reason is required when expiring a memory"
                )
            if not is_valid_expired_by(reason):
                raise MemoryOperationError(
                    f"Invalid expiry reason '{reason}': only letters, digits, "
                    "'.', '_' and '-' are allowed"
                )
            stamped_at = when or datetime.now(timezone.utc)
            updates: dict[str, Any] = {
                "status": "expired",
                "expired_at": stamped_at,
                "expired_by": reason,
            }
        else:
            stamped_at = None
            updates = {"status": "active", "expired_at": None, "expired_by": None}

        result = self.update_memory(memory_id, namespace, updates)

        return {
            **result,
            "action": "expired" if expired else "restored",
            "memory_id": memory_id,
            "memory_status": updates["status"],
            "expired_at": stamped_at.isoformat() if stamped_at else None,
            "expired_by": reason if expired else None,
        }

    def delete_memory(self, memory_id: str, namespace: str) -> bool:
        """Permanently delete a memory by ID. Not reversible — prefer
        ``set_lifecycle(expired=True)`` when the intent is to retire a memory."""
        try:
            from typing import Any, cast

            result = cast(
                dict[str, Any],
                self.client.documents.delete(namespace_name=namespace, ids=[memory_id]),
            )

            return self._deletion_succeeded(result)

        except Exception as e:
            raise MemoryOperationError(f"Failed to delete memory: {e}")

    @staticmethod
    def _deletion_succeeded(result: dict[str, Any]) -> bool:
        """Return True for cloud and on-prem successful deletion shapes."""
        raw = result.get("actual_deletions")
        if isinstance(raw, int):
            return raw > 0
        ids = result.get("deleted_ids")
        if isinstance(ids, list):
            return len(ids) > 0
        return str(result.get("status", "")).lower() in {"success", "ok"}
