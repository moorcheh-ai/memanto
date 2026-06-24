"""
Memory Write Service
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.utils.errors import MemoryError, ValidationError
from memanto.app.utils.ids import generate_memory_id

if TYPE_CHECKING:
    from memanto.app.legacy.memory_validation_service import MemoryValidationService

# Defense in depth: cheap pre-upload safety check applied to every memory
# before it is forwarded to Moorcheh. Addresses bounty findings:
#   #1 DoS via oversized content (single memory or batch with many large items)
#   #2 Prompt-injection / control-character smuggling in free-form text
# The full ValidationPolicy is intentionally left disabled for speed, but
# these checks must always run because they are security-critical.
_MAX_CONTENT_CHARS = 32_000          # ~32 KB per memory, well under Moorcheh's doc limit
_MAX_TITLE_CHARS = 512                # titles should be short
_MAX_BATCH_TOTAL_CHARS = 1_000_000    # ~1 MB across the whole batch
_MAX_BATCH_SIZE = 100                 # Moorcheh hard limit, also enforced later
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Cheap prompt-injection markers; intentionally conservative. False positives
# just get logged as a warning, not blocked — operators decide.
_INJECTION_HINTS = (
    "ignore previous instructions",
    "ignore all previous",
    "system:",
    "<|im_start|>",
    "<|im_end|>",
    "### instruction",
    "assistant:",
    "you are now",
    "disregard prior",
)


def _safety_check_memory(memory: MemoryRecord) -> list[str]:
    """Return a list of human-readable warnings about suspicious content.

    The function never raises for content issues (those are warnings the caller
    may surface), only raises :class:`MemoryError` for hard size violations
    that would either break the upload or enable trivial DoS.
    """
    warnings: list[str] = []

    title = memory.title or ""
    content = memory.content or ""

    if len(title) > _MAX_TITLE_CHARS:
        raise MemoryError(
            f"title too long: {len(title)} chars (max {_MAX_TITLE_CHARS})"
        )
    if len(content) > _MAX_CONTENT_CHARS:
        raise MemoryError(
            f"content too long: {len(content)} chars (max {_MAX_CONTENT_CHARS})"
        )

    if _CONTROL_CHAR_RE.search(content):
        # Strip them silently — many real documents contain stray \x00 from
        # binary paste. Rejecting would hurt legitimate users; sanitizing is
        # safer for retrieval and embeddings downstream.
        memory.content = _CONTROL_CHAR_RE.sub("", content)
        warnings.append("stripped control characters from content")

    lowered = content.lower()
    for hint in _INJECTION_HINTS:
        if hint in lowered:
            warnings.append(f"suspicious prompt-injection marker: {hint!r}")
            break

    return warnings


class MemoryWriteService:
    """Persist memory records to Moorcheh-backed namespaces."""

    def __init__(self, moorcheh_client: "MoorchehClient"):
        """Initialize the service with a Moorcheh client."""

        self.client = moorcheh_client
        self._parser = MemoryParsingService()
        # Lazily initialized on first use — keeps import-time deps light.
        self._validation_service: "MemoryValidationService | None" = None

    @property
    def namespace_service(self):
        """Lazily create the namespace service used for memory scopes."""

        if self._namespace_service is None:
            from memanto.app.services.namespace_service import NamespaceService

            self._namespace_service = NamespaceService(self.client)
        return self._namespace_service

    @property
    def validation_service(self) -> "MemoryValidationService":
        """Lazily create the validation service that gates uploads.

        Without this layer the write path stores arbitrary user-controlled
        content directly into Moorcheh, which is later retrieved and
        injected into LLM context — a classic stored-prompt-injection
        surface. Always use ``validate_memory`` (and honor its ``action``).
        """

        if self._validation_service is None:
            from memanto.app.legacy.memory_validation_service import (
                MemoryValidationService,
            )

            self._validation_service = MemoryValidationService(self.client)
        return self._validation_service
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
            namespace = memory.namespace()

            # Defense in depth layer 1: cheap pre-upload safety check.
            # Always runs (raises on hard size violations; strips control chars
            # silently; flags prompt-injection markers as warnings).
            safety_warnings = _safety_check_memory(memory)

            # Defense in depth layer 2: full ValidationPolicy. The policy can
            # mark the memory as `provisional`, `reject`, or pass-through.
            # Stored prompt injection is a real concern because retrieved
            # memories are injected into LLM context downstream — every write
            # must pass this gate before hitting Moorcheh.
            try:
                validation_result = self.validation_service.validate_memory(
                    memory, context
                )
            except ValidationError as exc:
                raise MemoryError(f"validation rejected memory: {exc}") from exc

            # Honor the policy's action. `reject` short-circuits the upload
            # entirely; the caller gets a structured result so the API can
            # surface the reason to the user.
            if validation_result.get("action") == "reject":
                return {
                    "id": memory.id,
                    "namespace": namespace,
                    "status": "rejected",
                    "action": "reject",
                    "reason": validation_result.get(
                        "reason", "Rejected by validation policy"
                    ),
                    "warnings": safety_warnings,
                }
            if "memory" in validation_result:
                memory = validation_result["memory"]
            if safety_warnings and "warnings" not in validation_result:
                validation_result["warnings"] = safety_warnings

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

            if len(memories) > _MAX_BATCH_SIZE:
                raise MemoryError(
                    f"Batch size {len(memories)} exceeds Moorcheh's limit of {_MAX_BATCH_SIZE} documents per request"
                )

            # Pre-flight batch size cap (DoS guard) — total payload across the
            # whole batch must stay under _MAX_BATCH_TOTAL_CHARS or we reject
            # before doing any per-memory work.
            total_chars = sum(len(m.content or "") + len(m.title or "") for m in memories)
            if total_chars > _MAX_BATCH_TOTAL_CHARS:
                raise MemoryError(
                    f"Batch total content too large: {total_chars} chars "
                    f"(max {_MAX_BATCH_TOTAL_CHARS})"
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

                    # Defense in depth layer 1: cheap pre-upload safety check.
                    safety_warnings = _safety_check_memory(memory)

                    # Defense in depth layer 2: full ValidationPolicy gate.
                    # Same rationale as store_memory() — every write must pass
                    # before it lands in Moorcheh to prevent stored prompt
                    # injection from poisoning downstream LLM context.
                    try:
                        validation_result = self.validation_service.validate_memory(
                            memory, context
                        )
                    except ValidationError as exc:
                        results.append(
                            {
                                "id": memory.id,
                                "status": "failed",
                                "action": "rejected",
                                "reason": f"validation error: {exc}",
                            }
                        )
                        continue

                    # Honor reject — short-circuit the upload for this item.
                    if validation_result.get("action") == "reject":
                        results.append(
                            {
                                "id": memory.id,
                                "status": "rejected",
                                "action": "reject",
                                "reason": validation_result.get(
                                    "reason", "Rejected by validation policy"
                                ),
                                "warnings": safety_warnings,
                            }
                        )
                        continue
                    if "memory" in validation_result:
                        memory = validation_result["memory"]
                    if safety_warnings and "warnings" not in validation_result:
                        validation_result["warnings"] = safety_warnings

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

            # Defense in depth: re-run safety + validation on the post-merge
            # memory before it is re-uploaded. An attacker who can craft
            # `updates` could otherwise inject oversized content, control
            # characters, or prompt-injection payloads via the update path.
            update_warnings = _safety_check_memory(updated_memory)

            try:
                validation_result = self.validation_service.validate_memory(
                    updated_memory, None
                )
            except ValidationError as exc:
                raise MemoryError(f"validation rejected update: {exc}") from exc

            if validation_result.get("action") == "reject":
                raise MemoryError(
                    f"update rejected by validation policy: "
                    f"{validation_result.get('reason', 'no reason given')}"
                )
            if "memory" in validation_result:
                updated_memory = validation_result["memory"]
            if update_warnings and "warnings" not in validation_result:
                validation_result["warnings"] = update_warnings

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
