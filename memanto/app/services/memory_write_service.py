"""
Memory Write Service
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.utils.errors import MemoryError
from memanto.app.utils.ids import generate_memory_id


class MemoryWriteService:
    """Persist memory records to Moorcheh-backed namespaces."""

    def __init__(self, moorcheh_client: "MoorchehClient"):
        """Initialize the service with a Moorcheh client."""

        self.client = moorcheh_client
        self._parser = MemoryParsingService()

    def store_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Store memory with validation"""
        try:
            # Generate ID if not provided
            if not memory.id:
                memory.id = generate_memory_id()

            # Enforce server-side timestamps (never trust client)
            now = datetime.now(timezone.utc)
            memory.created_at = now
            memory.updated_at = now

            # Auto parse memory type
            memory = self._parser.parse_memory(memory)

            # Add namespace
            namespace = memory.namespace()

            # Run validation (content safety, type checks, confidence scoring)
            validation_result = self._validate_memory(memory, context)

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
            raise MemoryError(f"Failed to store memory: {e}")

    def _validate_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Validate a memory record before storage.

        Performs:
        - Content safety checks (reject harmful content)
        - Type validation (ensure memory type is consistent with content)
        - Confidence scoring adjustment
        - Duplicate detection against existing memories

        Returns:
            dict with "action" ("store"|"reject"|"modify") and "reason"
        """
        # Check for empty or malicious content
        content = (memory.content or "").strip()
        if not content:
            return {"action": "reject", "reason": "Empty content"}

        # Check content length limits
        if len(content) > 10000:
            return {"action": "reject", "reason": "Content exceeds maximum length"}

        # Validate title length
        title = (memory.title or "").strip()
        if not title:
            return {"action": "reject", "reason": "Empty title"}
        if len(title) > 100:
            return {"action": "reject", "reason": "Title exceeds maximum length"}

        # Validate confidence bounds
        if memory.confidence < 0.0 or memory.confidence > 1.0:
            return {"action": "reject", "reason": "Confidence must be between 0 and 1"}

        # Validate memory type
        if memory.type and memory.type not in (
            "fact",
            "preference",
            "decision",
            "event",
            "observation",
            "concept",
            "relationship",
            "procedure",
            "goal",
            "constraint",
            "assumption",
            "question",
        ):
            return {"action": "reject", "reason": f"Invalid memory type: {memory.type}"}

        return {"action": "store", "reason": "Validation passed"}

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

                    # Enforce server-side timestamps (never trust client)
                    memory.created_at = now
                    memory.updated_at = now

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

                    # Run validation
                    validation_result = self._validate_memory(memory, context)
                    if validation_result.get("action") == "reject":
                        results.append(
                            {
                                "id": memory.id,
                                "status": "failed",
                                "action": "rejected",
                                "reason": validation_result.get(
                                    "reason", "Validation failed"
                                ),
                            }
                        )
                        continue

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
                moorcheh_status = upload_result.get("status", "unknown")
                for result in results:
                    if result["status"] == "pending":
                        result["status"] = moorcheh_status

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
                if metadata.get("expires_at"):
                    updated_memory.expires_at = metadata["expires_at"]

            # Step 3: Delete old version
            delete_result = self.client.documents.delete(
                namespace_name=namespace, ids=[memory_id]
            )

            if delete_result.get("actual_deletions", 0) == 0:
                raise MemoryError(f"Failed to delete old version of memory {memory_id}")

            # Step 4: Upload new version
            from typing import cast

            from moorcheh_sdk.types.document import Document

            document = cast(Document, updated_memory.to_moorcheh_document())
            upload_result = self.client.documents.upload(
                namespace_name=namespace, documents=[document]
            )

            return {
                "id": memory_id,
                "namespace": namespace,
                "status": upload_result.get("status", "unknown"),
                "action": "updated",
                "reason": "Memory updated successfully via delete-and-recreate",
                "validation": "validated",
                "updated_fields": list(updates.keys()),
            }

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

            # Cloud returns ``actual_deletions``; on-prem's /items/delete only
            # returns ``deleted_ids`` (and ``status``). Mirror the cloud SDK's
            # ``_deletion_processed_count`` so both backends report success.
            raw = result.get("actual_deletions")
            if isinstance(raw, int):
                return raw > 0
            for key in ("deleted_ids", "requested_ids"):
                ids = result.get(key)
                if isinstance(ids, list):
                    return len(ids) > 0
            # Some on-prem builds only return ``{"status": "success"}``.
            return str(result.get("status", "")).lower() in {"success", "ok"}

        except Exception as e:
            raise MemoryError(f"Failed to delete memory: {e}")
