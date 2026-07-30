"""
Memory Write Service
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.core import MemoryRecord
from memanto.app.legacy.memory_validation_service import MemoryValidationService
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.utils.errors import MemoryError
from memanto.app.utils.ids import generate_memory_id
from memanto.app.utils.temporal_helpers import as_utc_aware

SUCCESSFUL_UPLOAD_STATUSES = {"queued", "success", "ok"}

# Trust fields removed from the active schema on 2026-06-29 (see
# memanto/app/legacy/REMOVED.md). Old on-prem data_store.json records may still
# carry them; they must never be copied forward on update or we resurrect dead
# schema that no live read/write flow populates.
_REMOVED_TRUST_FIELDS = frozenset(
    {
        "superseded_by",
        "supersedes",
        "validated_at",
        "validation_count",
        "contradiction_detected",
    }
)

_SUCCESSFUL_UPLOAD_STATUSES = {"queued", "success", "ok"}


class MemoryWriteService:
    """Persist memory records to Moorcheh-backed namespaces."""

    def __init__(self, moorcheh_client: "MoorchehClient"):
        """Initialize the service with a Moorcheh client."""

        self.client = moorcheh_client
        self._parser = MemoryParsingService()
        self.validation_service = MemoryValidationService(moorcheh_client)
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

            # Validate memory (write-time contradiction resolution)
            validation_result = self.validation_service.validate_memory(memory, context)
            # Use validated memory if modified
            if "memory" in validation_result:
                memory = validation_result["memory"]

            from typing import cast

            from moorcheh_sdk.types.document import Document

            # Convert to Moorcheh document
            document = cast(Document, memory.to_moorcheh_document())

            # Store in Moorcheh
            result = self.client.documents.upload(
                namespace_name=namespace, documents=[document]
            )

            response = {
                "id": memory.id,
                "namespace": namespace,
                "status": result.get("status", "unknown"),
                "action": validation_result.get("action", "store"),
                "reason": validation_result.get("reason", "Stored successfully"),
                "confidence": memory.confidence,
                "memory_status": memory.status,
                "type": memory.type,
            }
            if validation_result.get("superseded_ids"):
                response["superseded_ids"] = validation_result["superseded_ids"]
            return response

        except Exception as e:
            raise MemoryError(f"Failed to store memory: {e}")

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
                raise MemoryError("No memories provided for batch operation")

            if len(memories) > 100:
                raise MemoryError(
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

                    # Validate memory (write-time contradiction resolution)
                    validation_result = self.validation_service.validate_memory(memory, context)
                    # Use validated memory if modified
                    if "memory" in validation_result:
                        memory = validation_result["memory"]

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

            # Resolve contradictions between memories in the same batch
            # BEFORE building documents, so superseded status is captured
            # in the uploaded documents.
            superseded_by = self.validation_service.resolve_batch_contradictions(memories)

            # Now build validated documents — superseded memories will have
            # status="superseded" from resolve_batch_contradictions.
            for idx, memory in enumerate(memories):
                # Skip memories that were already rejected (cross-namespace)
                result_id = str(memory.id) if hasattr(memory, 'id') and memory.id else ""
                # Find the corresponding result entry
                for result_entry in results:
                    if str(result_entry.get("id") or "") == result_id:
                        if str(memory.status).lower() == "superseded":
                            winner_id = superseded_by.get(result_id)
                            result_entry["action"] = "store_superseded"
                            result_entry["reason"] = (
                                f"superseded within batch by {winner_id}"
                            )
                        break

            # Upload all validated documents in single batch to Moorcheh
            if validated_documents and first_namespace:
                from typing import cast

                upload_result = self.client.documents.upload(
                    namespace_name=cast(str, first_namespace),
                    documents=validated_documents,
                )

                # Per-document status verification (fixes #770)
                moorcheh_status = str(upload_result.get("status", "unknown")).lower()
                per_doc = upload_result.get("results") or upload_result.get("documents") or []

                # Build a lookup by document id so we don't rely on index
                # alignment between results (all docs) and validated_documents
                # (only valid docs).
                doc_status_by_id: dict[str, str] = {}
                for doc in per_doc:
                    if isinstance(doc, dict):
                        doc_id = str(doc.get("id") or "")
                        if doc_id:
                            doc_status_by_id[doc_id] = str(doc.get("status", "")).lower()

                for result in results:
                    if result["status"] != "pending":
                        continue
                    result_id = str(result.get("id") or "")
                    explicit = doc_status_by_id.get(result_id)

                    if explicit is not None:
                        # Per-document status available — use it directly.
                        if explicit in _SUCCESSFUL_UPLOAD_STATUSES:
                            result["status"] = "success"
                        elif explicit == "failed":
                            result["status"] = "failed"
                            result["error"] = (
                                f"Document upload failed with status '{explicit}'"
                            )
                        else:
                            result["status"] = "unconfirmed"
                            if not result.get("error"):
                                result["error"] = (
                                    f"Per-document status '{explicit}' could not be confirmed"
                                )
                    elif moorcheh_status not in _SUCCESSFUL_UPLOAD_STATUSES:
                        result["status"] = "failed"
                        result["error"] = f"Upload returned status '{moorcheh_status}'"
                    elif not per_doc:
                        # No per-doc data at all, but aggregate succeeded —
                        # genuinely unconfirmed for all documents.
                        result["status"] = "unconfirmed"
                        if not result.get("error"):
                            result["error"] = (
                                "Upstream provider returned aggregate success"
                                " without per-document confirmation payload"
                            )
                    else:
                        # Batch succeeded but this specific document was not
                        # found in per-doc results — genuinely unconfirmed.
                        result["status"] = "unconfirmed"
                        if not result.get("error"):
                            result["error"] = (
                                "Batch uploaded but per-document status unavailable"
                            )

            # Count successes, failures, unconfirmed, and namespace-rejected
            # items separately so that
            # successful + failed + unconfirmed + rejected == total_submitted
            # always.
            _known = set(SUCCESSFUL_UPLOAD_STATUSES) | {"failed", "rejected", "unconfirmed"}
            successful = sum(
                1
                for r in results
                if str(r["status"]).lower() in SUCCESSFUL_UPLOAD_STATUSES
            )
            failed = sum(1 for r in results if str(r["status"]).lower() == "failed")
            unconfirmed = sum(
                1 for r in results if str(r["status"]).lower() == "unconfirmed"
            )
            rejected = sum(1 for r in results if str(r["status"]).lower() == "rejected")
            # Absorb any non-standard upload statuses into failed so the
            # invariant holds (does not touch the known four categories).
            for r in results:
                if str(r["status"]).lower() not in _known:
                    r["status"] = "failed"
            # Recompute failed so it catches the re-mapped unknowns.
            failed = sum(1 for r in results if str(r["status"]).lower() == "failed")

            return {
                "total_submitted": len(memories),
                "successful": successful,
                "failed": failed,
                "unconfirmed": unconfirmed,
                "rejected": rejected,
                "namespace": first_namespace,
                "results": results,
            }

        except Exception as e:
            raise MemoryError(f"Failed to batch store memories: {e}")

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
        # Validate inputs before the try block so ValueError propagates as-is.
        if not memory_id or not memory_id.strip():
            raise ValueError("memory_id must be a non-empty string")
        if not namespace or not namespace.strip():
            raise ValueError("namespace must be a non-empty string")

        try:
            from memanto.app.services.memory_read_service import MemoryReadService

            # Step 1: Retrieve existing memory
            read_service = MemoryReadService(self.client)
            existing_memory_data = read_service.get_memory(memory_id, namespace)

            if not existing_memory_data:
                raise MemoryError(
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
                raise MemoryError(
                    f"Cannot determine agent_id for memory {memory_id} "
                    f"in namespace {namespace}"
                )

            # Normalize legacy source values
            source_val = updates.get("source", metadata.get("source", "system"))
            if source_val not in {"user", "agent", "tool", "system"}:
                source_val = "system"

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
                status=updates.get("status", metadata.get("status", "active")),
                tags=updates.get("tags", metadata.get("tags", [])),
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

            # Handle TTL
            if "ttl_seconds" in updates:
                updated_memory.set_ttl(updates["ttl_seconds"])
            elif metadata.get("ttl_seconds"):
                updated_memory.ttl_seconds = metadata["ttl_seconds"]
                raw_expires_at = metadata.get("expires_at")
                if raw_expires_at:
                    if isinstance(raw_expires_at, str):
                        try:
                            updated_memory.expires_at = datetime.fromisoformat(
                                raw_expires_at.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass  # Keep the default if the stored timestamp is invalid
                    else:
                        updated_memory.expires_at = raw_expires_at

            # Step 3: Upload new version (overwrites existing document with same ID)
            from typing import Any, cast

            from moorcheh_sdk.types.document import Document

            validation_result = self.validation_service.validate_memory(updated_memory, context)

            document = cast(Document, updated_memory.to_moorcheh_document())

            # Preserve extra metadata fields from the existing record (e.g. original_id
            # in on-prem data_store.json) that aren't part of the MemoryRecord schema.
            existing_meta = existing_memory_data.get("metadata", existing_memory_data)
            if isinstance(existing_meta, dict):
                # ``document`` is a TypedDict; cast to a plain dict to attach
                # extra schema-external keys (e.g. original_id) dynamically.
                extra_document = cast(dict[str, Any], document)
                for key in existing_meta:
                    if (
                        key not in document
                        and key != "text"
                        and key not in _REMOVED_TRUST_FIELDS
                    ):
                        extra_document[key] = existing_meta[key]

            try:
                upload_result = self.client.documents.upload(
                    namespace_name=namespace, documents=[document]
                )
            except Exception as e:
                raise MemoryError(f"Upload failed. Error: {e}")

            return {
                "id": memory_id,
                "namespace": namespace,
                "status": upload_result.get("status", "unknown"),
                "action": "updated",
                "reason": "Memory updated successfully via overwrite",
                "validation": validation_result.get("action", "validated"),
                "updated_fields": list(updates.keys()),
            }

        except Exception as e:
            raise MemoryError(f"Failed to update memory: {e}")

    def delete_memory(self, memory_id: str, namespace: str) -> bool:
        """Delete memory by ID"""
        if not memory_id or not memory_id.strip():
            raise ValueError("memory_id must be a non-empty string")
        if not namespace or not namespace.strip():
            raise ValueError("namespace must be a non-empty string")
        try:
            from typing import Any, cast

            result = cast(
                dict[str, Any],
                self.client.documents.delete(namespace_name=namespace, ids=[memory_id]),
            )

            return self._deletion_succeeded(result)

        except Exception as e:
            raise MemoryError(f"Failed to delete memory: {e}")

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
