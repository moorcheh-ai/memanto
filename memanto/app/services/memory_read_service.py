"""
Memory Read Service
"""

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.core import create_memory_scope
from memanto.app.utils.errors import MemoryError


class MemoryReadService:
    def __init__(self, moorcheh_client: "MoorchehClient"):
        self.client = moorcheh_client
        self._namespace_service = None

    @property
    def namespace_service(self):
        if self._namespace_service is None:
            from memanto.app.services.namespace_service import NamespaceService

            self._namespace_service = NamespaceService(self.client)
        return self._namespace_service

    def get_memory(self, memory_id: str, namespace: str) -> dict[str, Any] | None:
        """Retrieve specific memory by ID with TTL enforcement"""
        try:
            result = self.client.documents.get(
                namespace_name=namespace, ids=[memory_id]
            )

            from typing import Any, cast

            if not isinstance(result, dict):
                return None

            items: list[Any] = cast(list[Any], result.get("items", []))
            if items and isinstance(items, list) and len(items) > 0:
                memory = self._format_memory_item(items[0])

                # Apply TTL enforcement
                filtered = self._filter_expired_memories([memory])
                if filtered:
                    return filtered[0]
                else:
                    return None  # Memory has expired

            return None

        except Exception as e:
            raise MemoryError(f"Failed to retrieve memory: {e}")

    def search_memories(
        self,
        query: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        status_filter: list[str] | None = None,
        limit: int = 10,
        offset: int = 0,
        min_similarity_score: float | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Search memories with filters leveraging Moorcheh's native metadata filtering

        Uses Moorcheh's #key:value syntax for efficient server-side filtering
        and kiosk_mode for score-based filtering.

        Supports pagination via limit/offset parameters.
        """
        try:
            # Determine namespaces to search
            namespaces = self._get_search_namespaces(scope_type, scope_id)

            if not namespaces:
                return {"results": [], "total_found": 0, "execution_time": 0}

            # Build enhanced query with Moorcheh metadata filters
            enhanced_query = self._build_filtered_query(
                query=query,
                type=type,
                tags=tags,
                min_confidence=min_confidence,
                status_filter=status_filter,
                created_after=created_after,
                created_before=created_before,
                metadata_filters=metadata_filters,
            )

            # Build query parameters
            # Request extra results to handle offset (Moorcheh doesn't have native offset support)
            requested_limit = limit + offset
            top_k = min(requested_limit, 100)  # Moorcheh max is 100

            # Perform search with server-side filtering
            search_result = self.client.similarity_search.query(
                query=enhanced_query,
                namespaces=namespaces,
                top_k=top_k,
                threshold=min_similarity_score,
                kiosk_mode=min_similarity_score is not None,
            )

            search_items = search_result.get("results", [])

            # Format results
            all_results = [self._format_memory_item(item) for item in search_items]

            # Apply temporal filtering (post-processing since Moorcheh metadata filters are string-based)
            if created_after or created_before:
                all_results = self._apply_temporal_filter(
                    all_results,
                    created_after=created_after,
                    created_before=created_before,
                )

            # Apply TTL enforcement - filter out expired memories
            all_results = self._filter_expired_memories(all_results)

            # Apply pagination (offset + limit)
            paginated_results = all_results[offset : offset + limit]
            has_more = len(all_results) > offset + limit

            return {
                "results": paginated_results,
                "total_found": len(paginated_results),
                "total_available": len(all_results),
                "offset": offset,
                "limit": limit,
                "has_more": has_more,
                "query": query,
                "enhanced_query": enhanced_query,
                "execution_time": search_result.get("execution_time", 0),
            }

        except Exception as e:
            raise MemoryError(f"Failed to search memories: {e}")

    def search_multi_scope(
        self,
        query: str,
        scopes: list[dict[str, str]],
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        status_filter: list[str] | None = None,
        limit: int = 10,
        min_similarity_score: float | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Search across multiple scopes simultaneously

        Leverages Moorcheh's multi-namespace search capability
        with optional threshold filtering via kiosk_mode
        """
        try:
            # Build namespaces from scopes
            namespaces = []
            from typing import cast

            from memanto.memanto.app.constants import ScopeType

            for scope_def in scopes:
                scope = create_memory_scope(
                    scope_type=cast(ScopeType, scope_def["scope_type"]),
                    scope_id=scope_def["scope_id"],
                )
                namespaces.append(scope.to_namespace())

            if not namespaces:
                return {"results": [], "total_found": 0, "execution_time": 0}

            # Build enhanced query with filters
            enhanced_query = self._build_filtered_query(
                query=query,
                type=type,
                tags=tags,
                min_confidence=min_confidence,
                status_filter=status_filter,
                metadata_filters=metadata_filters,
            )

            # Build query parameters
            top_k = limit

            # Perform cross-namespace search
            search_result = self.client.similarity_search.query(
                query=enhanced_query,
                namespaces=namespaces,
                top_k=top_k,
                threshold=min_similarity_score,
                kiosk_mode=min_similarity_score is not None,
            )

            # Format results
            formatted_results = [
                self._format_memory_item(item)
                for item in search_result.get("results", [])
            ]

            return {
                "results": formatted_results,
                "total_found": len(formatted_results),
                "query": query,
                "enhanced_query": enhanced_query,
                "searched_namespaces": namespaces,
                "execution_time": search_result.get("execution_time", 0),
            }

        except Exception as e:
            raise MemoryError(f"Failed to search across multiple scopes: {e}")

    def search_as_of(
        self,
        as_of_date: str,
        agent_id: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Point-in-time query: "What was true at this point in time?"

        Returns memories that were:
        1. Created before or at as_of_date
        2. NOT superseded before as_of_date
        3. NOT expired at as_of_date

        Args:
            as_of_date: ISO timestamp for point-in-time (e.g., "2025-11-01T00:00:00Z")
            agent_id: Agent whose memories to search
            type: Optional memory type filters
            tags: Optional tag filters
            limit: Max results
        """
        try:
            from memanto.app.utils.temporal_helpers import parse_iso_timestamp

            as_of_dt = parse_iso_timestamp(as_of_date)

            namespaces = self._get_search_namespaces("agent", agent_id)
            if not namespaces:
                return {
                    "results": [],
                    "total_found": 0,
                    "as_of_date": as_of_date,
                    "temporal_mode": "as_of",
                }

            all_memories = self._fetch_all_memories(namespaces, type=type, tags=tags)
            all_memories = self._apply_temporal_filter(
                all_memories, created_before=as_of_date
            )

            # Filter to only include memories valid at as_of_date
            valid_memories = []
            for memory in all_memories:
                # Skip if expired before as_of_date
                expires_at = memory.get("expires_at")
                if expires_at:
                    try:
                        expires_dt = parse_iso_timestamp(expires_at)
                        if expires_dt <= as_of_dt:
                            continue  # Already expired at as_of_date
                    except (ValueError, AttributeError):
                        pass

                # Skip if superseded before as_of_date
                if memory.get("superseded_by"):
                    # Memory was superseded - check if supersession happened before as_of_date
                    updated_at = memory.get("updated_at")
                    if updated_at:
                        try:
                            updated_dt = parse_iso_timestamp(updated_at)
                            if updated_dt <= as_of_dt:
                                continue  # Already superseded at as_of_date
                        except (ValueError, AttributeError):
                            pass

                valid_memories.append(memory)

            # Apply limit
            valid_memories = valid_memories[:limit]

            return {
                "results": valid_memories,
                "total_found": len(valid_memories),
                "as_of_date": as_of_date,
                "temporal_mode": "as_of",
            }

        except Exception as e:
            raise MemoryError(f"Failed to perform as-of query: {e}")

    def search_changed_since(
        self,
        since_date: str,
        agent_id: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Differential retrieval: "What changed recently?"

        Returns memories created or updated after since_date.

        Args:
            since_date: ISO timestamp for change boundary (e.g., "2025-12-01T00:00:00Z")
            agent_id: Agent whose memories to search
            type: Optional memory type filters
            tags: Optional tag filters
            limit: Max results
        """
        try:
            from memanto.app.utils.temporal_helpers import parse_iso_timestamp

            since_dt = parse_iso_timestamp(since_date)

            namespaces = self._get_search_namespaces("agent", agent_id)
            if not namespaces:
                return {"results": [], "total_found": 0, "since_date": since_date}

            all_memories = self._fetch_all_memories(namespaces, type=type, tags=tags)

            # Filter to only changed memories
            changed_memories = []
            seen_ids = set()

            for memory in all_memories:
                mem_id = memory.get("id")
                if mem_id in seen_ids:
                    continue
                seen_ids.add(mem_id)

                # Check if created after since_date (new memory)
                created_at = memory.get("created_at")
                if created_at:
                    try:
                        created_dt = parse_iso_timestamp(created_at)
                        if created_dt > since_dt:
                            memory["change_type"] = "created"
                            changed_memories.append(memory)
                            continue
                    except (ValueError, AttributeError):
                        pass

                # Check if updated after since_date (modified memory)
                updated_at = memory.get("updated_at")
                if updated_at:
                    try:
                        updated_dt = parse_iso_timestamp(updated_at)
                        if updated_dt > since_dt:
                            memory["change_type"] = "updated"
                            changed_memories.append(memory)
                            continue
                    except (ValueError, AttributeError):
                        pass

            # Sort by updated_at descending (most recent first)
            changed_memories.sort(
                key=lambda m: m.get("updated_at", m.get("created_at", "")), reverse=True
            )

            # Apply limit
            changed_memories = changed_memories[:limit]

            return {
                "results": changed_memories,
                "total_found": len(changed_memories),
                "since_date": since_date,
                "temporal_mode": "changed_since",
            }

        except Exception as e:
            raise MemoryError(f"Failed to search changed memories: {e}")

    def search_recent(
        self,
        agent_id: str,
        type: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Retrieve the most recently stored memories, sorted by created_at descending.

        Args:
            agent_id: Agent whose memories to search
            type: Optional memory type filters
            limit: Max results to return
        """
        try:
            from memanto.app.utils.temporal_helpers import parse_iso_timestamp

            namespaces = self._get_search_namespaces("agent", agent_id)
            if not namespaces:
                return {"results": [], "total_found": 0}

            unique_memories = self._fetch_all_memories(namespaces, type=type)

            # Sort by created_at descending (most recent first)
            def _created_sort_key(m: dict[str, Any]) -> str:
                raw = m.get("created_at")
                if not raw:
                    return ""
                try:
                    return parse_iso_timestamp(str(raw)).isoformat()
                except Exception:
                    return ""

            unique_memories.sort(key=_created_sort_key, reverse=True)

            results = unique_memories[:limit]
            return {"results": results, "total_found": len(results)}

        except Exception as e:
            raise MemoryError(f"Failed to retrieve recent memories: {e}")

    def _fetch_all_memories(
        self,
        namespaces: list[str],
        type: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all stored memories across the given namespaces via Moorcheh's
        documents.fetch_text_data endpoint, applying optional type/tag filters
        and de-duplicating by id.

        Note: Moorcheh's fetch_text_data currently returns up to 100 items per
        namespace and does not paginate.
        """
        items: list[Any] = []
        for ns in namespaces:
            try:
                result = self.client.documents.fetch_text_data(namespace_name=ns)
            except Exception:
                continue
            if isinstance(result, dict):
                items.extend(result.get("items", []) or [])

        seen_ids: set[str] = set()
        memories: list[dict[str, Any]] = []
        for item in items:
            # Skip summary chunks — only return real memory documents
            if isinstance(item, dict) and item.get("is_summary"):
                continue
            formatted = self._format_memory_item(item)
            mid = formatted.get("id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(cast(str, mid))

            if type and formatted.get("type") not in type:
                continue
            if tags:
                mem_tags = formatted.get("tags") or []
                if not any(t in mem_tags for t in tags):
                    continue

            memories.append(formatted)

        return self._filter_expired_memories(memories)

    def _build_filtered_query(
        self,
        query: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        status_filter: list[str] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> str:
        """
        Build enhanced query with Moorcheh's #key:value metadata filters

        Example: "user authentication #memory_type:fact #status:active #confidence:high"

        Note: Temporal filters (created_after/created_before) are applied as post-processing
        since Moorcheh's metadata filters use string comparison
        """
        filter_parts = []

        # Add memory type filters
        if type:
            for mem_type in type:
                filter_parts.append(f"#memory_type:{mem_type}")

        # Add tag filters (keyword syntax)
        if tags:
            for tag in tags:
                filter_parts.append(f"#{tag}")

        # Add status filters
        if status_filter:
            for status in status_filter:
                filter_parts.append(f"#status:{status}")

        # Add confidence filter (convert to category if needed)
        if min_confidence is not None:
            if min_confidence >= 0.8:
                filter_parts.append("#confidence:high")
            elif min_confidence >= 0.5:
                filter_parts.append("#confidence:medium")

        # Add custom metadata filters
        if metadata_filters:
            for key, value in metadata_filters.items():
                filter_parts.append(f"#{key}:{value}")

        # Combine query with filters
        if filter_parts:
            return f"{query} {' '.join(filter_parts)}"
        return query

    def _apply_temporal_filter(
        self,
        results: list[dict[str, Any]],
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Apply temporal filtering to search results

        Args:
            results: List of formatted memory items
            created_after: ISO timestamp - include only memories created after this time
            created_before: ISO timestamp - include only memories created before this time

        Returns:
            Filtered list of results
        """
        from memanto.app.utils.temporal_helpers import parse_iso_timestamp

        filtered = results

        if created_after:
            try:
                after_dt = parse_iso_timestamp(created_after)
                filtered = [
                    r
                    for r in filtered
                    if r.get("created_at")
                    and parse_iso_timestamp(r["created_at"]) >= after_dt
                ]
            except (ValueError, AttributeError):
                pass  # Skip invalid timestamps

        if created_before:
            try:
                before_dt = parse_iso_timestamp(created_before)
                filtered = [
                    r
                    for r in filtered
                    if r.get("created_at")
                    and parse_iso_timestamp(r["created_at"]) <= before_dt
                ]
            except (ValueError, AttributeError):
                pass  # Skip invalid timestamps

        return filtered

    def _filter_expired_memories(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Filter out memories that have expired based on their expires_at timestamp

        This provides application-level TTL enforcement since Moorcheh doesn't
        automatically delete expired documents.

        Args:
            results: List of formatted memory items

        Returns:
            Filtered list with expired memories removed
        """

        from memanto.app.utils.temporal_helpers import parse_iso_timestamp

        now = datetime.now(timezone.utc)

        filtered = []
        for result in results:
            expires_at = result.get("expires_at")

            # If no expiration set, keep the memory
            if not expires_at:
                filtered.append(result)
                continue

            # Parse and check expiration
            try:
                if isinstance(expires_at, str):
                    expires_dt = parse_iso_timestamp(expires_at)
                    # Only include if not expired
                    if expires_dt > now:
                        filtered.append(result)
                else:
                    # If expires_at is already datetime or not parseable, keep it
                    filtered.append(result)
            except (ValueError, AttributeError):
                # If we can't parse, keep the memory (fail open)
                filtered.append(result)

        return filtered

    def generate_answer(
        self, query: str, scope_type: str | None = None, scope_id: str | None = None
    ) -> dict[str, Any]:
        """Generate AI answer from memories"""
        try:
            # Determine namespace for answer generation
            if scope_type and scope_id:
                from typing import cast

                from memanto.app.constants import ScopeType

                scope_type_resolved = (
                    scope_type
                    if scope_type in {"user", "workspace", "agent", "session"}
                    else "agent"
                )
                scope = create_memory_scope(
                    cast(ScopeType, scope_type_resolved), scope_id
                )
                namespace = scope.to_namespace()
            else:
                # Use first available namespace
                namespaces = self.namespace_service.list_namespaces()
                if not namespaces:
                    raise MemoryError("No namespaces found")
                namespace = namespaces[0]

            # Generate answer
            answer_result = self.client.answer.generate(
                namespace=namespace, query=query, ai_model=settings.ANSWER_MODEL
            )

            return {
                "answer": answer_result["answer"],
                "namespace": namespace,
                "query": query,
            }

        except Exception as e:
            raise MemoryError(f"Failed to generate answer: {e}")

    def _get_search_namespaces(
        self, scope_type: str | None = None, scope_id: str | None = None
    ) -> list[str]:
        """Get namespaces to search based on filters"""
        from typing import cast

        from memanto.app.constants import ScopeType

        if scope_type and scope_id:
            # Search specific scope
            scope_type_resolved = (
                scope_type
                if scope_type in {"user", "workspace", "agent", "session"}
                else "agent"
            )
            scope = create_memory_scope(cast(ScopeType, scope_type_resolved), scope_id)
            return [cast(str, scope.to_namespace())]
        else:
            # Search all namespaces
            return cast(list[str], self.namespace_service.list_namespaces())

    def _filter_search_results(
        self,
        results: list[dict[str, Any]],
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Filter search results by metadata (flat field structure).

        Note: This is a fallback filter. Primary filtering should use Moorcheh's
        # syntax in _build_filtered_query() for better performance.
        """
        filtered = results

        # Filter by memory types (flat field: memory_type)
        if type:
            filtered = [r for r in filtered if r.get("memory_type") in type]

        # Filter by tags (flat field: tags as comma-separated string)
        if tags:
            filtered = [
                r
                for r in filtered
                if any(tag in r.get("tags", "").split(",") for tag in tags)
            ]

        # Apply limit
        return filtered[:limit]

    def _format_memory_item(self, item: Any) -> dict[str, Any]:
        """
        Format memory item for response.
        """
        if not hasattr(self, "_memory_record_cls"):
            from memanto.app.core import MemoryRecord

            self._memory_record_cls = MemoryRecord

        # Check if metadata is in nested format (Moorcheh API spec)
        metadata = item.get("metadata", {})

        # Helper to get field from either nested metadata or flat structure
        def get_field(field_name, flat_field_name=None):
            """Get field from metadata object or fallback to flat field"""
            flat_name = flat_field_name or field_name
            # Try metadata object first (API spec), then flat field (fallback)
            return metadata.get(field_name) or item.get(flat_name)

        # Parse tags - can be comma-separated string or array
        tags_value = get_field("tags")
        if isinstance(tags_value, str):
            tags = tags_value.split(",") if tags_value else []
        elif isinstance(tags_value, list):
            tags = tags_value
        else:
            tags = []

        # Extract provenance & trust fields
        provenance = get_field("provenance") or "explicit_statement"
        validation_count = get_field("validation_count") or 0
        contradiction_detected = get_field("contradiction_detected") or False
        superseded_by = get_field("superseded_by")
        supersedes = get_field("supersedes")
        validated_at_str = get_field("validated_at")

        # Parse validated_at timestamp
        validated_at = None
        if validated_at_str:
            try:
                validated_at = datetime.fromisoformat(
                    validated_at_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Parse title and content from Moorcheh document text format:
        raw_text = item.get("text", "")
        title = ""
        content = raw_text

        if raw_text:
            lines = raw_text.split("\n\n", 2)  # Split into at most 3 parts
            first_line = lines[0] if lines else ""

            # Extract title: strip the "[TYPE] " prefix from first line

            title_match = re.match(r"^\[.*?\]\s*(.*)$", first_line)
            if title_match:
                title = title_match.group(1).strip()
                # Content is the rest after the first line (skip tags section)
                if len(lines) > 1:
                    # Check if last part is tags
                    remaining = lines[1:]
                    content_parts = []
                    for part in remaining:
                        if part.startswith("Tags: "):
                            continue
                        content_parts.append(part)
                    content = "\n\n".join(content_parts) if content_parts else ""
                else:
                    content = ""
            else:
                # No [TYPE] prefix — use first line as title, rest as content
                title = first_line.strip()
                content = "\n\n".join(lines[1:]) if len(lines) > 1 else ""

        # Build basic formatted item
        formatted = {
            "id": item.get("id"),
            "title": title,
            "content": content,
            "text": raw_text,
            "type": get_field(
                "memory_type", "memory_type"
            ),  # Flat field name after migration
            "confidence": get_field("confidence"),
            "status": get_field("status"),
            "tags": tags,
            "created_at": get_field("created_at"),
            "updated_at": get_field("updated_at"),
            "expires_at": get_field("expires_at"),
            "ttl_seconds": get_field("ttl_seconds"),
            "actor_id": get_field("actor_id"),
            "source": get_field("source"),
            "scope_type": get_field("scope_type"),
            "scope_id": get_field("scope_id"),
            "score": item.get("score"),  # Search relevance score
            # Provenance & Trust fields
            "provenance": provenance,
            "validation_count": validation_count,
            "contradiction_detected": contradiction_detected,
        }

        # Add optional trust fields
        if superseded_by:
            formatted["superseded_by"] = superseded_by
        if supersedes:
            formatted["supersedes"] = supersedes
        if validated_at:
            formatted["validated_at"] = validated_at.isoformat()

        # skip trust score computation reconstructs MemoryRecord and runs compute_confidence() + trust_score() per result. Skipped for speed.
        ## Compute trust score if we have all required fields
        # try:
        ## Reconstruct MemoryRecord to use compute_confidence and trust_score methods
        #     created_at_str = get_field("created_at")
        #     created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00')) if created_at_str else datetime.utcnow()
        #     memory_rec = MemoryRecord(
        #         id=item.get("id"),
        #         type=get_field("memory_type", "memory_type") or "fact",
        #         title="", # Not stored in search results
        #         content=item.get("text", ""),
        #         scope_type=get_field("scope_type") or "agent",
        #         scope_id=get_field("scope_id") or "unknown",
        #         actor_id=get_field("actor_id") or "unknown",
        #         source=get_field("source") or "agent",
        #         confidence=get_field("confidence") or 0.8,
        #         status=get_field("status") or "active",
        #         provenance=provenance,
        #         validation_count=validation_count,
        #         contradiction_detected=contradiction_detected,
        #         created_at=created_at,
        #         validated_at=validated_at
        #     )
        #     if superseded_by:
        #         memory_rec.superseded_by = superseded_by
        #     if supersedes:
        #         memory_rec.supersedes = supersedes

        # Add computed confidence and trust score
        #     formatted["computed_confidence"] = memory_rec.compute_confidence()
        #     formatted["trust_score"] = memory_rec.trust_score()
        # except Exception as e:
        ## If computation fails, just return basic formatted item
        #     pass

        return formatted
