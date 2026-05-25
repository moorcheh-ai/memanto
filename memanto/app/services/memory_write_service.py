"""
Memory Write Service
"""

from datetime import datetime
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
        self._namespace_service = None
        self._parser = MemoryParsingService()

    @property
    def namespace_service(self):
        """Lazily create the namespace service used for memory scopes."""

        if self._namespace_service is None:
            from memanto.app.services.namespace_service import NamespaceService

            self._namespace_service = NamespaceService(self.client)
        return self._namespace_service

    def store_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Store memory with validation"""
        try:
            # Generate ID if not provided
            if not memory.id:
                memory.id = generate_memory_id()

            # Enforce server-side timestamps (never trust client)
            now = datetime.utcnow()
            memory.created_at = now
            memory.updated_at = now

            # Auto parse memory type
            memory = self._parser.parse_memory(memory)

            # Add namespace
            namespace = memory.get_scope().to_namespace()

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
            now = datetime.utcnow()

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
                    namespace = memory.get_scope().to_namespace()

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

            # Build updated memory record
            updated_memory = MemoryRecord(
                id=memory_id,  # Keep same ID
                type=updates.get("type", metadata.get("type", "fact")),
                title=updates.get(
                    "title", existing_memory_data.get("title", "Updated Memory")
                ),
                content=updates.get("content", existing_memory_data.get("content", "")),
                scope_type=metadata.get("scope_type", "agent"),
                scope_id=metadata.get("scope_id", "unknown"),
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
            updated_memory.updated_at = datetime.utcnow()

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

            validation_result = {"action": "store", "reason": "MVP direct store"}

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
                "validation": validation_result.get("action", "validated"),
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

            actual_deletions = result.get("actual_deletions", 0)
            if not isinstance(actual_deletions, int):
                actual_deletions = 0
            return actual_deletions > 0

        except Exception as e:
            raise MemoryError(f"Failed to delete memory: {e}")

    def _ensure_namespace(self, memory: MemoryRecord) -> str:
        """Ensure namespace exists for memory"""
        from typing import cast

        namespace = self.namespace_service.create_namespace(
            cast(Any, memory.scope_type), memory.scope_id
        )
        return cast(str, namespace)
