"""
Memory Validation Service

Write-time contradiction detection and resolution for memory records.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.core import MemoryRecord

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
    # Must align with MemoryReadService's post-filter pool so same-title records
    # are not dropped by default pagination before title matching runs.
    CANDIDATE_LIMIT = 100

    def __init__(self, moorcheh_client: "MoorchehClient"):
        self.client = moorcheh_client

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

        When ``prefetched_conflicts`` is supplied by batch prefetch, the
        lookup is skipped. ``None`` means the prefetch lookup failed.
        """
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
                # A failed lookup must never block a write, but say the check did
                # not run rather than pretending it passed.
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
            return {
                "action": "store",
                "reason": "validated: no contradicting memories found",
            }

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
            "reason": "; ".join(reason_parts),
            "superseded_ids": superseded,
        }

    def resolve_batch_contradictions(
        self, memories: list[MemoryRecord]
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
        self, memories: list[MemoryRecord]
    ) -> dict[str, list[dict[str, Any]] | None]:
        """Run contradiction lookups in parallel for batch writes.

        Returns a mapping of memory id -> conflicts list, or ``None`` when
        that memory's lookup failed. Exempt types are omitted.
        """
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
        # Title is embedded in Moorcheh document text (`[TYPE] title\\n\\ncontent`).
        # Query by title (not incoming content) so same-title records are ranked
        # in even when content diverges sharply.
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
                # Identical content is a duplicate, not a contradiction.
                continue
            conflicts.append(item)
        return conflicts

    def _supersede(self, old_item: dict[str, Any], new_memory: MemoryRecord) -> bool:
        """Mark an existing memory as superseded by the new one.

        Upload the superseded document first (same ID overwrites in Moorcheh).
        Returns False instead of raising so one bad record cannot block the new
        write; a failed upload leaves the original document untouched.
        """
        try:
            old_id = str(old_item.get("id"))
            namespace = new_memory.namespace()

            now_iso = datetime.utcnow().isoformat()
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
            upload_status = str(upload_result.get("status", "unknown")).lower()
            if upload_status not in {"queued", "success", "ok"}:
                return False
            return True

        except Exception:
            return False
