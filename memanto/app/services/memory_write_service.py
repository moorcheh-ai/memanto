"""
Memory Write Service
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.core import MemoryRecord
from memanto.app.services.conflict_resolution_service import ConflictResolutionService
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.services.memory_validation_service import MemoryValidationService
from memanto.app.utils.errors import MemoryError
from memanto.app.utils.ids import generate_memory_id
from memanto.app.utils.temporal_helpers import as_utc_naive


class MemoryWriteService:
    """Persist memory records to Moorcheh-backed namespaces."""

    def __init__(self, moorcheh_client: "MoorchehClient"):
        """Initialize the service with a Moorcheh client."""

        self.client = moorcheh_client
        self._parser = MemoryParsingService()
        self._validation_service = MemoryValidationService(moorcheh_client)
        self._conflict_service = ConflictResolutionService(moorcheh_client)
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
            memory.created_at = as_utc_naive(memory.created_at)
            memory.updated_at = as_utc_naive(memory.updated_at)
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

            now = datetime.utcnow()
            self._apply_timestamps(memory, now)

            # Auto parse memory type
            memory = self._parser.parse_memory(memory)

            # Add namespace
            namespace = memory.namespace()

            # Validate memory (may downgrade it to provisional in-place)
            validation_result = self._validation_service.validate_memory(
                memory, context
            )
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

            # Check whether this memory contradicts/replaces an existing
            # active one, and if so, mark the older one superseded. Skip
            # this for memories that were just stored provisionally -
            # unconfirmed information shouldn't be allowed to bump
            # something that was already trusted.
            superseded_ids: list[str] = []
            if validation_result.get("action") != "store_provisional":
                conflicts = self._conflict_service.find_conflicts(memory)
                if conflicts:
                    superseded_ids = self._conflict_service.supersede(
                        conflicts, memory.id, namespace, self
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
                "superseded_ids": superseded_ids,
            }

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
            stored_memories: list[tuple[MemoryRecord, dict[str, Any]]] = []

            # Enforce server-side timestamps for batch (single timestamp for all)
            now = datetime.utcnow()

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

                    validation_result = self._validation_service.validate_memory(
                        memory, context
                    )
                    if "memory" in validation_result:
                        memory = validation_result["memory"]

                    from typing import cast

                    from moorcheh_sdk.types.document import Document

                    # Convert to Moorcheh document
                    document = cast(Document, memory.to_moorcheh_document())
                    validated_documents.append(document)
                    stored_memories.append((memory, validation_result))

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
                moorcheh_status = upload_result.get("status", "unknown")
                for result in results:
                    if result["status"] == "pending":
                        result["status"] = moorcheh_status

                # Now that everything's durably written, check each stored
                # memory against existing memories for conflicts. Skipped for
                # provisional memories - unconfirmed info shouldn't supersede
                # something already trusted. Same namespace for the whole
                # batch, so this only needs first_namespace.
                for memory, validation_result in stored_memories:
                    if validation_result.get("action") == "store_provisional":
                        continue
                    conflicts = self._conflict_service.find_conflicts(memory)
                    if conflicts:
                        self._conflict_service.supersede(
                            conflicts, memory.id, cast(str, first_namespace), self
                        )

            # Count successes and failures
            successful = sum(1 for r in results if r["status"] in ["queued", "success"])
            failed = sum(1 for r in results if r["status"] == "failed")

            return {
                "total_submitted": len(memories),
                "successful": successful,
                "failed": failed,
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
        Update existing memory using delete-and-recreate pattern

        Since Moorcheh doesn't support in-place updates, we:
        1. Retrieve the existing memory
        2. Apply updates to create new version
        3. Delete old version
        4. Upload new version with same ID

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
                source=updates.get("source", metadata.get("source", "system")),
                source_ref=updates.get("source_ref", metadata.get("source_ref")),
                confidence=updates.get("confidence", metadata.get("confidence", 0.8)),
                status=updates.get("status", metadata.get("status", "active")),
                tags=updates.get("tags", metadata.get("tags", [])),
                superseded_by=updates.get(
                    "superseded_by", metadata.get("superseded_by")
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
            updated_memory.updated_at = datetime.utcnow()

            # Handle TTL
            if "ttl_seconds" in updates:
                updated_memory.set_ttl(updates["ttl_seconds"])
            elif metadata.get("ttl_seconds"):
                updated_memory.ttl_seconds = metadata["ttl_seconds"]
                if metadata.get("expires_at"):
                    updated_memory.expires_at = metadata["expires_at"]

            # Moorcheh doesn't support in-place updates, so a rewrite still
            # needs a delete + re-upload under the same id somewhere in the
            # process. The previous version of this method deleted the old
            # doc *first*, which meant a failure on the re-upload (timeout,
            # backend error, whatever) silently destroyed the memory with no
            # way back. Instead:
            #   1. upload the new content under a temporary id (old doc is
            #      untouched the whole time - if this fails, nothing changed)
            #   2. only once that's confirmed, delete the old doc
            #   3. re-upload the new content under the real id
            #   4. clean up the temporary copy
            # If step 3 fails after step 2 succeeded, the original id is
            # briefly gone, but the content isn't lost - it's sitting under
            # the staging id, and the error says so.
            from typing import Any, cast

            from moorcheh_sdk.types.document import Document

            document = cast(Document, updated_memory.to_moorcheh_document())
            staging_id = f"{memory_id}__staging_{uuid.uuid4().hex[:8]}"
            staged_document = cast(Document, dict(document))
            staged_document["id"] = staging_id

            self.client.documents.upload(
                namespace_name=namespace, documents=[staged_document]
            )

            delete_result = cast(
                dict[str, Any],
                self.client.documents.delete(namespace_name=namespace, ids=[memory_id]),
            )
            if not self._deletion_succeeded(delete_result):
                # Old doc is still there - just clean up the stray staged
                # copy and bail, nothing lost either way.
                try:
                    self.client.documents.delete(
                        namespace_name=namespace, ids=[staging_id]
                    )
                except Exception:
                    pass
                raise MemoryError(f"Failed to delete old version of memory {memory_id}")

            try:
                upload_result = self.client.documents.upload(
                    namespace_name=namespace, documents=[document]
                )
            except Exception as promote_error:
                raise MemoryError(
                    f"Failed to finalize update for memory {memory_id}: "
                    f"{promote_error}. The updated content was not lost - it's "
                    f"stored under temporary id '{staging_id}' in namespace "
                    f"'{namespace}'. Retry the update, or restore it manually."
                )

            try:
                self.client.documents.delete(namespace_name=namespace, ids=[staging_id])
            except Exception:
                # A leftover staging doc is clutter, not a correctness problem.
                pass

            return {
                "id": memory_id,
                "namespace": namespace,
                "status": upload_result.get("status", "unknown"),
                "action": "updated",
                "reason": "Memory updated successfully via stage-then-swap",
                "updated_fields": list(updates.keys()),
            }

        except MemoryError:
            raise
        except Exception as e:
            raise MemoryError(f"Failed to update memory: {e}")

    def delete_memory(self, memory_id: str, namespace: str) -> bool:
        """Delete memory by ID"""
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
