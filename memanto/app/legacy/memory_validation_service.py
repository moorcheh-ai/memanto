"""
Memory Validation Service

Write-time contradiction detection and resolution for memory records.
(Retained in legacy during upstream refactor; restored for PR #1610 compatibility.)
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.core import MemoryRecord, ValidationPolicy
from memanto.app.utils.errors import ValidationError

_MISSING = object()
_MAX_VALIDATION_WORKERS = 8


class MemoryValidationService:
    """Detect and resolve direct contradictions before persisting a memory.

    A stored memory contradicts an incoming one when it is active, shares the
    same memory type and title (case-insensitive), but carries different
    content. Resolution follows the keep_new convention used by the conflict
    report pipeline: the old record is preserved with status "superseded"
    (annotated with superseded_by/superseded_at, matching search_as_of's
    timeline fields) and the new record is stored as active.

    Detection is deterministic — no LLM calls — so the write path stays cheap.
    Deeper semantic conflicts remain the job of the offline conflict report.
    """

    # How many candidates to inspect after server-side type/status filtering.
    CANDIDATE_LIMIT = 100

    def __init__(self, moorcheh_client: "MoorchehClient"):
        self.client = moorcheh_client
        self.policy = ValidationPolicy()

    def validate_memory(
        self,
        memory: MemoryRecord,
        context: dict[str, Any] | None = None,
        *,
        prefetched_conflicts: list[dict[str, Any]] | None | object = _MISSING,
    ) -> dict[str, Any]:
        """Validate a memory against existing records, resolving contradictions.

        Returns a dict with at least ``action`` and ``reason``; when
        contradictions were resolved it also carries ``superseded_ids``.
        """
        context = context or {}
        memory_type = memory.type or "fact"
        if memory_type not in settings.REQUIRE_VALIDATION_FOR:
            return {
                "action": "store",
                "reason": f"stored: type '{memory_type}' exempt from conflict validation",
            }

        if prefetched_conflicts is _MISSING:
            try:
                conflicts = self._find_contradictions(memory)
            except Exception:
                return {
                    "action": "store",
                    "reason": "stored: conflict check unavailable",
                }
        elif prefetched_conflicts is None:
            return {
                "action": "store",
                "reason": "stored: conflict check unavailable",
            }
        else:
            conflicts = cast(list[dict[str, Any]], prefetched_conflicts)

        if not conflicts:
            # Run policy validation for non-conflicting memories, but preserve
            # the deterministic contradiction-free reason text that callers expect.
            context["repetition_count"] = 0
            validation_result = self.policy.validate_memory(memory, context)
            if validation_result.get("action") == "store_provisional":
                memory = self.policy.make_provisional(memory)
                validation_result["memory"] = memory
            # Ensure a known reason key so store_memory/batch_store_memories
            # do not fall back to "Stored successfully".
            if "reason" not in validation_result:
                validation_result["reason"] = "validated: no contradicting memories found"
            return validation_result

        superseded: list[str] = []
        failed: list[str] = []
        for old_item in conflicts:
            old_id = str(old_item.get("id"))
            if self._supersede(old_item, memory):
                superseded.append(old_id)
            else:
                failed.append(old_id)

        reason_parts = []
        if superseded:
            reason_parts.append(
                f"contradiction resolved: superseded {', '.join(superseded)}"
            )
        if failed:
            reason_parts.append(
                f"contradiction detected but failed to supersede {', '.join(failed)}"
            )

        return {
            "action": "store",
            "reason": "; ".join(reason_parts) if reason_parts else "validated: no contradicting memories found",
            "superseded_ids": superseded,
        }

    def resolve_batch_contradictions(
        self, memories: list[MemoryRecord],
    ) -> dict[str, str]:
        """Resolve contradictions between memories submitted in one batch.

        For memories sharing a type and title but differing in content, the
        last submission wins; earlier ones are downgraded to
        status="superseded" in place. Returns a mapping of superseded memory
        id -> winning memory id.
        """
        superseded: dict[str, str] = {}
        latest_by_key: dict[tuple[str, str], MemoryRecord] = {}

        for memory in memories:
            memory_type = memory.type or "fact"
            if memory_type not in settings.REQUIRE_VALIDATION_FOR:
                continue
            key = (memory_type, memory.title.strip().lower())
            previous = latest_by_key.get(key)
            if (
                previous is not None
                and previous.content.strip() != memory.content.strip()
            ):
                previous.status = "superseded"
                superseded[str(previous.id)] = str(memory.id)
            latest_by_key[key] = memory

        return superseded

    def prefetch_contradictions(
        self, memories: list[MemoryRecord],
    ) -> dict[str, list[dict[str, Any]] | None]:
        """Run contradiction lookups in parallel for batch writes."""
        from concurrent.futures import ThreadPoolExecutor

        targets = [
            memory
            for memory in memories
            if (memory.type or "fact") in settings.REQUIRE_VALIDATION_FOR
        ]
        if not targets:
            return {}

        def lookup(
            memory: MemoryRecord,
        ) -> tuple[str, list[dict[str, Any]] | None]:
            try:
                return memory.id, self._find_contradictions(memory)
            except Exception:
                return memory.id, None

        workers = min(len(targets), _MAX_VALIDATION_WORKERS)
        prefetched: dict[str, list[dict[str, Any]] | None] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for memory_id, conflicts in executor.map(lookup, targets):
                prefetched[memory_id] = conflicts
        return prefetched

    def _find_contradictions(self, memory: MemoryRecord) -> list[dict[str, Any]]:
        """Find active memories of the same type/title with different content."""
        from memanto.app.services.memory_read_service import MemoryReadService

        memory_type = memory.type or "fact"
        title = memory.title.strip()
        title_key = title.lower()
        content = memory.content.strip()

        read_service = MemoryReadService(self.client)
        search = read_service.search_memories(
            query=title,
            agent_id=memory.agent_id,
            type=[memory_type],
            status_filter=["active"],
            limit=self.CANDIDATE_LIMIT,
        )

        conflicts = []
        for item in search.get("results", []):
            if not item.get("id") or item.get("id") == memory.id:
                continue
            if (item.get("status") or "active") != "active":
                continue
            if (item.get("title") or "").strip().lower() != title_key:
                continue
            if (item.get("content") or "").strip() == content:
                continue
            conflicts.append(item)
        return conflicts

    def _supersede(self, old_item: dict[str, Any], new_memory: MemoryRecord) -> bool:
        """Mark an existing memory as superseded by the new one.

        Moorcheh supports overwriting documents by ID, so no explicit delete
        is needed — a re-upload with status="superseded" is sufficient.
        Returns False when the upload response indicates failure.
        """
        try:
            old_id = str(old_item.get("id"))
            namespace = new_memory.namespace()

            now_iso = datetime.now(timezone.utc).isoformat()
            document: dict[str, Any] = {
                "id": old_id,
                "text": old_item.get("text") or "",
                "memory_type": old_item.get("type") or "fact",
                "agent_id": new_memory.agent_id,
                "actor_id": old_item.get("actor_id") or "unknown",
                "source": old_item.get("source") or "system",
                "confidence": old_item.get("confidence", 0.8),
                "status": "superseded",
                "provenance": old_item.get("provenance") or "explicit_statement",
                "created_at": old_item.get("created_at") or now_iso,
                "updated_at": now_iso,
                "superseded_by": new_memory.id,
                "superseded_at": now_iso,
            }
            tags = old_item.get("tags")
            if tags:
                document["tags"] = ",".join(tags) if isinstance(tags, list) else tags

            from moorcheh_sdk.types.document import Document

            upload_result = self.client.documents.upload(
                namespace_name=namespace,
                documents=[cast(Document, document)],
            )
            # Check upload response — a non-success status means the supersede
            # did not actually take effect.
            status = str(upload_result.get("status", "")).lower()
            if status in ("error", "failed"):
                return False
            return True

        except Exception:
            return False

    def _check_repetition(self, memory: MemoryRecord) -> int:
        """Check how many times similar content has been seen"""
        try:
            namespace = memory.get_scope().to_namespace()
            search_results = self.client.similarity_search.query(
                query=memory.content, namespaces=[namespace],
            )
            similar_count = 0
            for result in search_results.get("results", []):
                if result.get("score", 0) > 0.8:
                    similar_count += 1
            return similar_count
        except Exception:
            return 0

    def is_critical_memory_type(self, memory_type: str) -> bool:
        """Check if memory type requires validation"""
        return memory_type in settings.REQUIRE_VALIDATION_FOR

    def get_validation_requirements(self, memory_type: str) -> dict[str, Any]:
        """Get validation requirements for memory type"""
        if self.is_critical_memory_type(memory_type):
            return {
                "requires_validation": True,
                "validation_options": [
                    "user_confirmation",
                    "repetition_threshold_2",
                    "tool_grounded_source",
                    "high_confidence_system_source",
                ],
            }
        else:
            return {"requires_validation": False, "validation_options": []}
