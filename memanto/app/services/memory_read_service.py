"""
Memory Read Service
"""

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.config import settings
from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.app.core import agent_namespace
from memanto.app.utils.errors import MemoryError

_FILTER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_filter_token(value: Any, field_name: str) -> str:
    """Return a safe Moorcheh filter token or reject query-syntax injection."""
    token = str(value).strip()
    if not token or not _FILTER_TOKEN_RE.fullmatch(token):
        raise ValueError(
            f"Invalid {field_name} filter value: only letters, digits, '.', '_', "
            "and '-' are allowed"
        )
    return token


# Moorcheh caps a single similarity search at 100 rows.
MOORCHEH_MAX_TOP_K = 100
# When post-retrieval filters (temporal / confidence) are active we widen
# the fetched candidate pool to this size (bounded by MOORCHEH_MAX_TOP_K) so
# that filtering does not discard relevant rows that rank outside the
# caller's page. See MemoryReadService.search_memories.
POST_FILTER_CANDIDATE_POOL = 100


class MemoryReadService:
    """Read, search, and format memories from the configured Moorcheh backend."""

    def __init__(self, moorcheh_client: "MoorchehClient"):
        """Initialize the reader with an active Moorcheh client."""
        self.client = moorcheh_client
        self._namespace_service = None

    @property
    def namespace_service(self):
        """Return the namespace service, creating it on first access."""
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
        agent_id: str | None = None,
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
            namespaces = self._get_search_namespaces(agent_id)

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

            # Temporal, confidence, and TTL constraints are all enforced as
            # post-processing on the rows the backend returns (see below), so
            # the candidate pool we fetch must be large enough that those
            # filters do not silently drop relevant rows. If we only fetched
            # `limit + offset` rows, a date-scoped, confidence-scoped, or
            # TTL-expired-heavy query would filter *within the top-N
            # most-similar rows*, causing in-window memories that rank just
            # outside the top-N to be lost entirely (timeline amnesia / poor
            # recall). TTL enforcement (_filter_expired_memories) always runs
            # below regardless of caller input, so we always over-fetch up to
            # Moorcheh's hard cap rather than only when a temporal/confidence
            # filter is explicitly requested.
            top_k = min(
                max(requested_limit, POST_FILTER_CANDIDATE_POOL), MOORCHEH_MAX_TOP_K
            )

            # Perform search with server-side filtering.
            # Only enable kiosk_mode when the caller actually set a positive
            # threshold; min_similarity=0.0 means "no filter", but on-prem
            # kiosk_mode + threshold=0.0 still filters everything out.
            use_kiosk = min_similarity_score is not None and min_similarity_score > 0
            search_result = self.client.similarity_search.query(
                query=enhanced_query,
                namespaces=namespaces,
                top_k=top_k,
                threshold=min_similarity_score if use_kiosk else None,
                kiosk_mode=use_kiosk,
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

            if min_confidence is not None:
                all_results = self._filter_by_min_confidence(
                    all_results, min_confidence
                )

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

    def search_as_of(
        self,
        as_of_date: str,
        agent_id: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int | None = 10,
    ) -> dict[str, Any]:
        """
        Point-in-time query: "What was true at this point in time?"

        Returns memories that were:
        1. Created before or at as_of_date
        2. NOT expired at as_of_date

        Args:
            as_of_date: ISO timestamp for point-in-time (e.g., "2025-11-01T00:00:00Z")
            agent_id: Agent whose memories to search
            type: Optional memory type filters
            tags: Optional tag filters
            limit: Max results
        """
        try:
            from memanto.app.utils.temporal_helpers import (
                parse_as_of_timestamp,
                parse_iso_timestamp,
            )

            as_of_dt = parse_as_of_timestamp(as_of_date)

            namespaces = self._get_search_namespaces(agent_id)
            if not namespaces:
                return {
                    "results": [],
                    "total_found": 0,
                    "as_of_date": as_of_date,
                    "temporal_mode": "as_of",
                }

            all_memories = self._fetch_all_memories(namespaces, type=type, tags=tags)
            all_memories = self._apply_temporal_filter(
                all_memories, created_before=as_of_dt.isoformat()
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

                valid_memories.append(memory)

            # Apply limit
            if limit is not None:
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
        limit: int | None = 10,
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

            namespaces = self._get_search_namespaces(agent_id)
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

            # Sort by the timestamp that made the memory qualify.
            def _changed_sort_key(m: dict[str, Any]) -> datetime:
                """Return a stable aware timestamp for changed-memory ordering."""
                if m.get("change_type") == "created":
                    raw = m.get("created_at") or m.get("updated_at")
                else:
                    raw = m.get("updated_at") or m.get("created_at")
                if not raw:
                    return datetime.min.replace(tzinfo=timezone.utc)
                try:
                    return parse_iso_timestamp(str(raw))
                except Exception:
                    return datetime.min.replace(tzinfo=timezone.utc)

            changed_memories.sort(key=_changed_sort_key, reverse=True)

            # Apply limit
            if limit is not None:
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
        tags: list[str] | None = None,
        limit: int | None = 10,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve the most recently stored memories, sorted by created_at descending.

        Args:
            agent_id: Agent whose memories to search
            type: Optional memory type filters
            tags: Optional tag filters
            limit: Max results to return
            created_after: ISO timestamp - include only memories created at/after this time
            created_before: ISO timestamp - include only memories created at/before this time
        """
        try:
            from memanto.app.utils.temporal_helpers import parse_iso_timestamp

            namespaces = self._get_search_namespaces(agent_id)
            if not namespaces:
                return {"results": [], "total_found": 0}

            unique_memories = self._fetch_all_memories(namespaces, type=type, tags=tags)

            if created_after or created_before:
                unique_memories = self._apply_temporal_filter(
                    unique_memories,
                    created_after=created_after,
                    created_before=created_before,
                )

            # Sort by created_at descending (most recent first)
            def _created_sort_key(m: dict[str, Any]) -> str:
                """Return a comparable created-at timestamp for recent ordering."""
                raw = m.get("created_at")
                if not raw:
                    return ""
                try:
                    return parse_iso_timestamp(str(raw)).isoformat()
                except Exception:
                    return ""

            unique_memories.sort(key=_created_sort_key, reverse=True)

            results = unique_memories if limit is None else unique_memories[:limit]
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

        Iterates through all pages using cursor-based pagination (next_token)
        so results are not truncated at the 100-item per-page cap.
        """
        items: list[Any] = []
        for ns in namespaces:
            next_token: str | None = None
            while True:
                kwargs: dict[str, Any] = {"namespace_name": ns, "limit": 100}
                if next_token:
                    kwargs["next_token"] = next_token
                result = self.client.documents.fetch_text_data(**kwargs)
                if not isinstance(result, dict):
                    break
                items.extend(result.get("items", []) or [])
                pagination = result.get("pagination") or {}
                if not pagination.get("has_more"):
                    break
                next_token = pagination.get("next_token")
                if not next_token:
                    break

        latest_by_id: dict[str, tuple[tuple[datetime, int], dict[str, Any]]] = {}
        for index, item in enumerate(items):
            # Skip summary chunks — only return real memory documents
            if isinstance(item, dict) and item.get("is_summary"):
                continue
            formatted = self._format_memory_item(item)
            mid = formatted.get("id")
            if not mid:
                continue

            version_key = self._memory_version_key(formatted, index)
            existing = latest_by_id.get(cast(str, mid))
            if existing is None or version_key >= existing[0]:
                latest_by_id[cast(str, mid)] = (version_key, formatted)

        memories: list[dict[str, Any]] = []
        for _, formatted in latest_by_id.values():
            if type and formatted.get("type") not in type:
                continue
            if tags:
                mem_tags = formatted.get("tags") or []
                if not any(t in mem_tags for t in tags):
                    continue

            memories.append(formatted)

        return self._filter_expired_memories(memories)

    def _memory_version_key(
        self, memory: dict[str, Any], fetch_index: int
    ) -> tuple[datetime, int]:
        """Order duplicate memory ids by their newest known timestamp.

        Delete-and-recreate updates can briefly expose the old and new document
        with the same id. Prefer the newest updated_at/created_at value; when
        timestamps are missing or equal, keep the later fetched item.
        """
        from memanto.app.utils.temporal_helpers import parse_iso_timestamp

        fallback = datetime.min.replace(tzinfo=timezone.utc)
        for field in ("updated_at", "created_at"):
            raw = memory.get(field)
            if not raw:
                continue
            try:
                return parse_iso_timestamp(str(raw)), fetch_index
            except (TypeError, ValueError):
                continue
        return fallback, fetch_index

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

        Example: "user authentication #memory_type:fact #status:active"

        Note: Temporal filters (created_after/created_before) are applied as post-processing
        since Moorcheh's metadata filters use string comparison
        """
        filter_parts = []

        # Add memory type filters
        if type:
            for mem_type in type:
                mem_type = _validate_filter_token(mem_type, "memory_type")
                if mem_type not in VALID_MEMORY_TYPES:
                    raise ValueError(f"Invalid memory_type filter value: {mem_type}")
                filter_parts.append(f"#memory_type:{mem_type}")

        # Add tag filters (keyword syntax)
        if tags:
            for tag in tags:
                tag = _validate_filter_token(tag, "tag")
                filter_parts.append(f"#{tag}")

        # Add status filters
        if status_filter:
            for status in status_filter:
                status = _validate_filter_token(status, "status")
                filter_parts.append(f"#status:{status}")

        # Numeric confidence is stored as a number in memory documents. Applying
        # it via Moorcheh keyword syntax would require exact categorical values
        # that are never written, so callers filter it after formatting results.
        _ = min_confidence

        # Add custom metadata filters
        if metadata_filters:
            for key, value in metadata_filters.items():
                key = _validate_filter_token(key, "metadata key")
                value = _validate_filter_token(value, f"metadata '{key}'")
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

        after_dt = None
        before_dt = None

        if created_after:
            try:
                after_dt = parse_iso_timestamp(created_after)
            except (ValueError, AttributeError, TypeError):
                pass  # Keep existing fail-open behavior for invalid caller input.

        if created_before:
            try:
                before_dt = parse_iso_timestamp(created_before)
            except (ValueError, AttributeError, TypeError):
                pass  # Keep existing fail-open behavior for invalid caller input.

        if after_dt is None and before_dt is None:
            return results

        filtered = []
        for result in results:
            raw_created = result.get("created_at")
            if not raw_created:
                continue

            try:
                created_dt = parse_iso_timestamp(raw_created)
            except (ValueError, AttributeError, TypeError):
                continue

            if after_dt is not None and created_dt < after_dt:
                continue
            if before_dt is not None and created_dt > before_dt:
                continue

            filtered.append(result)

        return filtered

    def _filter_by_min_confidence(
        self, results: list[dict[str, Any]], min_confidence: float
    ) -> list[dict[str, Any]]:
        """Keep only results whose numeric confidence meets the threshold."""
        filtered: list[dict[str, Any]] = []
        for result in results:
            raw_confidence: Any = result.get("confidence")
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                if min_confidence <= 0:
                    filtered.append(result)
                continue
            if confidence >= min_confidence:
                filtered.append(result)
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
                elif isinstance(expires_at, datetime):
                    tz_aware = (
                        expires_at
                        if expires_at.tzinfo
                        else expires_at.replace(tzinfo=timezone.utc)
                    )
                    if tz_aware > now:
                        filtered.append(result)
                else:
                    # Any other type: fail open - keep the memory
                    filtered.append(result)
            except (ValueError, AttributeError):
                # If we can't parse, keep the memory (fail open)
                filtered.append(result)

        return filtered

    def generate_answer(
        self, query: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """Generate AI answer from memories"""
        try:
            # Determine namespace for answer generation
            if agent_id:
                namespace = agent_namespace(agent_id)
            else:
                # Use first available namespace
                namespaces = self.namespace_service.list_namespaces()
                if not namespaces:
                    raise MemoryError("No namespaces found")
                namespace = namespaces[0]

            # Generate answer. Omit ai_model when on-prem state has no LLM
            # configured so the on-prem server uses its own default; the
            # cloud SDK requires a string so don't pass None there.
            gen_kwargs: dict = {"namespace": namespace, "query": query}
            _model = get_active_llm_model(settings.ANSWER_MODEL)
            if _model is not None:
                gen_kwargs["ai_model"] = _model
            answer_result = self.client.answer.generate(**gen_kwargs)

            return {
                "answer": answer_result["answer"],
                "namespace": namespace,
                "query": query,
            }

        except Exception as e:
            raise MemoryError(f"Failed to generate answer: {e}")

    def _get_search_namespaces(self, agent_id: str | None = None) -> list[str]:
        """Get namespaces to search based on filters"""
        from typing import cast

        if agent_id:
            # Search a specific agent's namespace
            return [agent_namespace(agent_id)]
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
        if not isinstance(metadata, dict):
            metadata = {}

        # Helper to get field from either nested metadata or flat structure
        def get_field(field_name, flat_field_name=None):
            """Get field from metadata object or fallback to flat field"""
            flat_name = flat_field_name or field_name
            # Try metadata object first (API spec), then flat field (fallback)
            if field_name in metadata and metadata[field_name] is not None:
                return metadata[field_name]
            return item.get(flat_name)

        # Parse tags - can be comma-separated string or array. External imports
        # and older documents may include spaces after commas, so normalize
        # before exact tag filters run.
        tags_value = get_field("tags")
        if isinstance(tags_value, str):
            tags = [
                tag_value for tag in tags_value.split(",") if (tag_value := tag.strip())
            ]
        elif isinstance(tags_value, list):
            tags = [
                tag_value
                for tag in tags_value
                if tag is not None and (tag_value := str(tag).strip())
            ]
        else:
            tags = []

        # Extract provenance
        provenance = get_field("provenance") or "explicit_statement"

        # Parse title and content from Moorcheh document text format:
        raw_text = item.get("text", "")
        title = ""
        content = raw_text

        if raw_text:
            # Wire format (see MemoryRecord.to_moorcheh_document):
            #   "[TYPE] {title}\n\n{content}"  with an optional trailing
            #   "\n\nTags: {tags}" block appended only when the record has tags.
            # Split off the title on the FIRST blank line; everything after it is
            # the content, which may itself contain blank lines.
            first_line, _, rest = raw_text.partition("\n\n")

            title_match = re.match(r"^\[.*?\]\s*(.*)$", first_line)
            title = title_match.group(1).strip() if title_match else first_line.strip()

            # Strip ONLY a genuine trailing tags block, and only when this record
            # actually has tags (the serializer appends the block iff tags exist).
            # Prevents (a) wiping content that merely begins with "Tags: " and
            # (b) leaking the tags line into multi-paragraph content.
            body, sep, last = rest.rpartition("\n\n")
            if tags and sep and last.startswith("Tags: "):
                content = body
            else:
                content = rest

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
            "source_ref": get_field("source_ref"),
            "agent_id": get_field("agent_id"),
            "score": item.get("score"),  # Search relevance score
            # Provenance
            "provenance": provenance,
        }

        return formatted
