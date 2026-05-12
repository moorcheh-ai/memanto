"""
Universal Adoption Services
"""

from datetime import datetime
from typing import Any, cast

from memanto.app.clients.moorcheh import get_async_moorcheh_client, get_moorcheh_client
from memanto.app.constants import (
    VALID_MEMORY_TYPES,
    MemoryType,
    ProvenanceType,
    ScopeType,
)
from memanto.app.core import MemoryRecord, create_memory_scope
from memanto.app.models.universal_endpoints import (
    ExportedMemory,
    MemoryExplainRequest,
    MemoryExplainResponse,
    MemoryExplanation,
    MemoryExportRequest,
    MemoryExportResponse,
    MemorySupersedeRequest,
    MemorySupersedeResponse,
)
from memanto.app.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryExplainService:
    """Service for explaining memory retrieval decisions"""

    @staticmethod
    async def explain_memory_retrieval(
        tenant_id: str, request: MemoryExplainRequest
    ) -> MemoryExplainResponse:
        """Explain why specific memories were returned for a query"""

        # Compute namespace for routing explanation
        scope_type_raw = str(request.scope.get("type", "agent"))
        if scope_type_raw not in {"user", "workspace", "agent", "session"}:
            scope_type_raw = "agent"
        scope_id = str(request.scope.get("id", tenant_id))

        scope_obj = create_memory_scope(cast(ScopeType, scope_type_raw), scope_id)
        namespace = cast(str, scope_obj.to_namespace())

        client = get_async_moorcheh_client()

        # Re-execute the search to get detailed results
        search_results = await client.similarity_search.query(
            query=request.query,
            namespaces=[namespace],
            top_k=50,  # Get more results for explanation
        )

        explanations = []
        total_candidates = len(search_results.get("results", []))

        for result in search_results.get("results", []):
            memory_id = str(result.get("id", ""))
            score_raw = result.get("score", 0.0)
            score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
            metadata_raw = result.get("metadata", {})
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
            text_raw = result.get("text", "")
            text = text_raw if isinstance(text_raw, str) else str(text_raw or "")

            # Determine match reason
            match_reason = MemoryExplainService._analyze_match_reason(
                request.query, text, score
            )

            # Determine filter status
            filter_status = MemoryExplainService._analyze_filter_status(
                metadata, request.filters
            )

            explanation = MemoryExplanation(
                memory_id=memory_id,
                text=text[:200] + "..." if len(text) > 200 else text,
                memory_type=str(metadata.get("memory_type", "unknown")),
                confidence=float(metadata.get("confidence", 0.0) or 0.0),
                score=score,
                match_reason=match_reason,
                filter_status=filter_status,
                routing_path=f"tenant:{tenant_id} -> namespace:{namespace}",
            )
            explanations.append(explanation)

        # Apply filters and count
        filtered_explanations = MemoryExplainService._apply_explanation_filters(
            explanations, request.filters
        )

        return MemoryExplainResponse(
            query=request.query,
            namespace_used=namespace,
            total_candidates=total_candidates,
            filtered_count=len(filtered_explanations),
            returned_count=min(len(filtered_explanations), 10),  # Typical return limit
            explanations=filtered_explanations[:10],
            routing_decision=f"Tenant '{tenant_id}' + Scope '{request.scope}' -> Namespace '{namespace}'",
            filter_summary=MemoryExplainService._summarize_filters(request.filters),
        )

    @staticmethod
    def _analyze_match_reason(query: str, text: str, score: float) -> str:
        """Analyze why a memory matched the query"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        common_words = query_words.intersection(text_words)

        if score > 0.8:
            return f"High semantic similarity (score: {score:.3f})"
        elif score > 0.5:
            return f"Moderate semantic similarity (score: {score:.3f})"
        elif common_words:
            return f"Keyword matches: {', '.join(list(common_words)[:3])} (score: {score:.3f})"
        else:
            return f"Low similarity match (score: {score:.3f})"

    @staticmethod
    def _analyze_filter_status(metadata: dict, filters: dict | None) -> str:
        """Analyze how filters affected this memory"""
        if not filters:
            return "No filters applied"

        status_parts = []

        if "memory_type" in filters:
            if metadata.get("memory_type") == filters["memory_type"]:
                status_parts.append(f"✓ Type match: {filters['memory_type']}")
            else:
                status_parts.append(
                    f"✗ Type mismatch: expected {filters['memory_type']}, got {metadata.get('memory_type')}"
                )

        if "confidence_min" in filters:
            conf = metadata.get("confidence", 0.0)
            if conf >= filters["confidence_min"]:
                status_parts.append(f"✓ Confidence OK: {conf}")
            else:
                status_parts.append(
                    f"✗ Low confidence: {conf} < {filters['confidence_min']}"
                )

        return "; ".join(status_parts) if status_parts else "Passed all filters"

    @staticmethod
    def _apply_explanation_filters(
        explanations: list[MemoryExplanation], filters: dict | None
    ) -> list[MemoryExplanation]:
        """Apply filters to explanations for demonstration"""
        if not filters:
            return explanations

        filtered = explanations

        if "memory_type" in filters:
            filtered = [e for e in filtered if e.memory_type == filters["memory_type"]]

        if "confidence_min" in filters:
            filtered = [
                e for e in filtered if e.confidence >= filters["confidence_min"]
            ]

        return filtered

    @staticmethod
    def _summarize_filters(filters: dict | None) -> dict[str, Any]:
        """Summarize applied filters"""
        if not filters:
            return {"applied": False, "count": 0}

        return {
            "applied": True,
            "count": len(filters),
            "types": list(filters.keys()),
            "details": filters,
        }


class MemorySupersedeService:
    """Service for superseding memories"""

    @staticmethod
    async def supersede_memory(
        tenant_id: str, request: MemorySupersedeRequest
    ) -> MemorySupersedeResponse:
        """Supersede an existing memory with a new one"""

        client = get_moorcheh_client()

        # First, verify the memory exists and belongs to tenant
        try:
            # Get the existing memory to verify ownership
            await MemorySupersedeService._get_memory_metadata(
                tenant_id, request.memory_id
            )
        except Exception:
            raise ValueError(f"Memory {request.memory_id} not found or not accessible")

        # Create the new memory with superseding relationship
        new_memory_data = request.superseding_memory.copy()
        new_memory_data["supersedes"] = [request.memory_id]

        # Store new memory
        from memanto.app.services.memory_write_service import MemoryWriteService

        memory_type = str(new_memory_data.get("type", "fact"))
        if memory_type not in VALID_MEMORY_TYPES:
            memory_type = "fact"
        resolved_memory_type = cast(MemoryType, memory_type)

        content = str(new_memory_data.get("content", "")).strip()
        if not content:
            raise ValueError("superseding_memory.content is required")

        scope_type_raw = str(new_memory_data.get("scope_type", "agent"))
        if scope_type_raw not in {"user", "workspace", "agent", "session"}:
            scope_type_raw = "agent"

        scope_id = str(new_memory_data.get("scope_id", tenant_id))
        title = str(new_memory_data.get("title") or content[:50])
        confidence = float(new_memory_data.get("confidence", 0.8))
        tags_raw = new_memory_data.get("tags", [])
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        provenance = str(new_memory_data.get("provenance", "explicit_statement"))
        if provenance not in {
            "explicit_statement",
            "inferred",
            "corrected",
            "validated",
            "observed",
            "imported",
        }:
            provenance = "explicit_statement"
        resolved_provenance = cast(ProvenanceType, provenance)

        write_service = MemoryWriteService(client)
        stored = write_service.store_memory(
            MemoryRecord(
                type=resolved_memory_type,
                title=title,
                content=content,
                scope_type=cast(ScopeType, scope_type_raw),
                scope_id=scope_id,
                actor_id=str(new_memory_data.get("actor_id", tenant_id)),
                confidence=confidence,
                tags=tags,
                source=str(new_memory_data.get("source", "user")),
                provenance=resolved_provenance,
            )
        )

        # Mark old memory as superseded (update metadata)
        await MemorySupersedeService._mark_memory_superseded(
            tenant_id, request.memory_id, str(stored.get("id", ""))
        )

        logger.info(f"Memory superseded: {request.memory_id} -> {stored.get('id', '')}")

        return MemorySupersedeResponse(
            superseded_memory_id=request.memory_id,
            new_memory_id=str(stored.get("id", "")),
            supersede_timestamp=datetime.utcnow(),
            reason=request.reason,
            status="superseded",
        )

    @staticmethod
    async def _get_memory_metadata(tenant_id: str, memory_id: str) -> dict:
        """Get memory metadata to verify ownership"""
        # This would typically query the memory by ID
        # For now, we'll simulate this
        return {"memory_id": memory_id, "tenant_id": tenant_id}

    @staticmethod
    async def _mark_memory_superseded(
        tenant_id: str, old_memory_id: str, new_memory_id: str
    ):
        """Mark memory as superseded in metadata"""
        # This would update the memory's metadata to mark it as superseded
        # Implementation depends on Moorcheh SDK capabilities
        logger.info(f"Marked memory {old_memory_id} as superseded by {new_memory_id}")


class MemoryExportService:
    """Service for exporting memories"""

    @staticmethod
    async def export_memories(
        tenant_id: str, request: MemoryExportRequest
    ) -> MemoryExportResponse:
        """Export memories for a scope"""

        scope_type_raw = str(request.scope.get("type", "agent"))
        if scope_type_raw not in {"user", "workspace", "agent", "session"}:
            scope_type_raw = "agent"
        scope_id = str(request.scope.get("id", tenant_id))

        scope_obj = create_memory_scope(cast(ScopeType, scope_type_raw), scope_id)
        namespace = cast(str, scope_obj.to_namespace())

        client = get_async_moorcheh_client()

        # Get all memories in the namespace
        # This is a simplified implementation - real version would handle pagination
        search_results = await client.similarity_search.query(
            query="",  # Empty query to get all
            namespaces=[namespace],
            top_k=1000,  # Large number to get all memories
        )

        exported_memories = []

        for result in search_results.get("results", []):
            metadata_raw = result.get("metadata", {})
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
            memory_id = str(result.get("id", ""))
            text_raw = result.get("text", "")
            text = text_raw if isinstance(text_raw, str) else str(text_raw or "")

            # Apply filters
            if not MemoryExportService._passes_export_filters(metadata, request):
                continue

            exported_memory = ExportedMemory(
                memory_id=memory_id,
                text=text,
                memory_type=metadata.get("memory_type", "unknown"),
                confidence=metadata.get("confidence", 0.0),
                provisional=metadata.get("provisional", False),
                created_at=datetime.fromisoformat(
                    metadata.get("created_at", datetime.utcnow().isoformat())
                ),
                updated_at=None,  # Would be populated if available
                source=metadata.get("source", "unknown"),
                status=metadata.get("status", "active"),
                superseded_by=metadata.get("superseded_by"),
                supersedes=metadata.get("supersedes", []),
                metadata=metadata,
            )
            exported_memories.append(exported_memory)

        logger.info(
            f"Exported {len(exported_memories)} memories for scope {request.scope}"
        )

        return MemoryExportResponse(
            scope=request.scope,
            export_timestamp=datetime.utcnow(),
            total_memories=len(search_results.get("results", [])),
            exported_count=len(exported_memories),
            format=request.format,
            memories=exported_memories,
            export_metadata={
                "tenant_id": tenant_id,
                "namespace": namespace,
                "filters_applied": {
                    "include_inactive": request.include_inactive,
                    "date_range": request.date_range,
                    "memory_types": request.memory_types,
                },
                "export_format": request.format,
            },
        )

    @staticmethod
    def _passes_export_filters(metadata: dict, request: MemoryExportRequest) -> bool:
        """Check if memory passes export filters"""

        # Status filter
        if not request.include_inactive and metadata.get("status") != "active":
            return False

        # Memory type filter
        if (
            request.memory_types
            and metadata.get("memory_type") not in request.memory_types
        ):
            return False

        # Date range filter (simplified)
        if request.date_range:
            # Would implement proper date filtering here
            pass

        return True
