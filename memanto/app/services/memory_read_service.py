"""
Memory Read Service
"""

import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.config import settings
from memanto.app.constants import REMOVED_TRUST_FIELDS, VALID_MEMORY_TYPES
from memanto.app.core import agent_namespace
from memanto.app.utils.errors import MemoryOperationError

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


def _coerce_timestamp_str(value: Any) -> Any:
    """Return a timestamp field as an ISO string, tolerating raw epoch numbers.

    MemoryRecord always writes ISO strings, but a namespace can contain
    documents written outside Memanto's own store path (manual test data,
    other tools sharing the namespace) with a raw Unix-epoch number instead.
    The response model requires a string, so coerce here rather than let
    FastAPI's response serialization 500 on the whole recall.
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return value


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
        """Retrieve a specific memory by ID.

        Expired memories are returned like any other, carrying their ``status``
        and expiry stamp; it is the caller's job to label or filter them.
        """
        try:
            result = self.client.documents.get(
                namespace_name=namespace, ids=[memory_id]
            )

            if not isinstance(result, dict):
                raise MemoryOperationError(
                    message="Data corruption detected: Received malformed get result from storage layer.",
                    details={"result_preview": str(result)[:100]},
                )

            items: Any = result.get("items", [])
            if not isinstance(items, list):
                raise MemoryOperationError(
                    message="Data corruption detected: Received malformed get items array from storage layer.",
                    details={"items_preview": str(items)[:100]},
                )

            if items and len(items) > 0:
                return self._format_memory_item(items[0])

            return None

        except MemoryOperationError:
            raise
        except Exception as e:
            raise MemoryOperationError(f"Failed to retrieve memory: {e}")

    def search_memories(
        self,
        query: str,
        agent_id: str | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        status: str = "all",
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

            # Moorcheh combines repeated exact-match filters. A document cannot
            # satisfy both ``#memory_type:fact`` and
            # ``#memory_type:preference``, so a list of requested types must be
            # issued as one search per type and merged as a union. Build every
            # query before dispatch so an invalid later type cannot trigger a
            # partial set of backend calls.
            distinct_types = list(dict.fromkeys(type or []))
            type_variants: list[list[str] | None] = (
                [[memory_type] for memory_type in distinct_types]
                if len(distinct_types) > 1
                else [distinct_types or None]
            )
            enhanced_queries = [
                self._build_filtered_query(
                    query=query,
                    type=type_variant,
                    tags=tags,
                    min_confidence=min_confidence,
                    created_after=created_after,
                    created_before=created_before,
                    metadata_filters=metadata_filters,
                )
                for type_variant in type_variants
            ]

            # Build query parameters
            # Request extra results to handle offset (Moorcheh doesn't have native offset support)
            requested_limit = limit + offset

            # Temporal, confidence, and lifecycle-status constraints are all
            # enforced as post-processing on the rows the backend returns (see
            # below), so the candidate pool we fetch must be large enough that
            # those filters do not silently drop relevant rows. If we only
            # fetched `limit + offset` rows, a date-scoped, confidence-scoped,
            # or expired-heavy query would filter *within the top-N most-similar
            # rows*, causing in-window memories that rank just outside the top-N
            # to be lost entirely (timeline amnesia / poor recall). We therefore
            # always over-fetch up to Moorcheh's hard cap rather than only when
            # a filter is explicitly requested.
            top_k = min(
                max(requested_limit, POST_FILTER_CANDIDATE_POOL), MOORCHEH_MAX_TOP_K
            )

            # Perform search with server-side filtering.
            # Only enable kiosk_mode when the caller actually set a positive
            # threshold; min_similarity=0.0 means "no filter", but on-prem
            # kiosk_mode + threshold=0.0 still filters everything out.
            use_kiosk = min_similarity_score is not None and min_similarity_score > 0

            def _dispatch(enhanced_query: str) -> Any:
                """Run one exact-filter search with the shared request options."""
                return self.client.similarity_search.query(
                    query=enhanced_query,
                    namespaces=namespaces,
                    top_k=top_k,
                    threshold=min_similarity_score if use_kiosk else None,
                    kiosk_mode=use_kiosk,
                )

            dispatch_start = monotonic()
            if len(enhanced_queries) == 1:
                search_results = [_dispatch(enhanced_queries[0])]
            else:
                # The variants are independent network calls. Dispatch them in
                # parallel so the latency of a multi-type union is bounded by
                # the slowest search rather than the sum of every round trip.
                # pool.map preserves enhanced-query order for deterministic
                # result aggregation while capping concurrency for direct
                # service callers that pass every supported type.
                max_workers = min(len(enhanced_queries), 8)
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    search_results = list(pool.map(_dispatch, enhanced_queries))
            execution_time = monotonic() - dispatch_start

            search_items: list[Any] = []
            for search_result in search_results:
                if not isinstance(search_result, dict):
                    try:
                        search_result = dict(search_result)
                    except (TypeError, ValueError):
                        raise MemoryOperationError(
                            message=(
                                "Data corruption detected: Received malformed "
                                "search result from storage layer."
                            ),
                            details={"result_preview": str(search_result)[:100]},
                        )

                result_items = search_result.get("results", [])
                if not isinstance(result_items, list):
                    raise MemoryOperationError(
                        message=(
                            "Data corruption detected: Received malformed "
                            "search result array from storage layer."
                        ),
                        details={"items_preview": str(result_items)[:100]},
                    )
                search_items.extend(result_items)

            # Format results
            all_results = [self._format_memory_item(item) for item in search_items]

            if len(enhanced_queries) > 1:
                # Scores from the per-type searches share the same backend
                # scale. Re-rank the union before applying offset/limit and
                # de-duplicate defensively in case malformed metadata causes a
                # row to be returned by more than one variant.
                def _score(memory: dict[str, Any]) -> float:
                    """Return a sortable backend score, placing missing values last."""
                    raw_score = memory.get("score")
                    if raw_score is None:
                        return float("-inf")
                    try:
                        return float(raw_score)
                    except (TypeError, ValueError):
                        return float("-inf")

                all_results.sort(key=_score, reverse=True)
                unique_results: list[dict[str, Any]] = []
                seen_ids: set[Any] = set()
                for memory in all_results:
                    memory_id = memory.get("id")
                    if memory_id is not None and memory_id in seen_ids:
                        continue
                    if memory_id is not None:
                        seen_ids.add(memory_id)
                    unique_results.append(memory)
                all_results = unique_results

            # Apply temporal filtering (post-processing since Moorcheh metadata filters are string-based)
            if created_after or created_before:
                all_results = self._apply_temporal_filter(
                    all_results,
                    created_after=created_after,
                    created_before=created_before,
                )

            # Narrow to the requested lifecycle state. The `#status:` filter
            # above already does this server-side for a single-status request,
            # but records written before the lifecycle field carry no status,
            # so re-apply it here to keep the two paths in agreement.
            all_results = self._filter_by_status(all_results, status)

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
                "enhanced_query": " OR ".join(enhanced_queries),
                "execution_time": execution_time,
            }

        except MemoryOperationError:
            raise
        except Exception as e:
            raise MemoryOperationError(f"Failed to search memories: {e}")

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
        2. Not yet expired at as_of_date

        A memory expired *after* as_of_date is still returned, because it was
        true at the point in time being asked about.

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

            all_memories = self._fetch_all_memories(
                namespaces,
                type=type,
                tags=tags,
                created_before=as_of_dt.isoformat(),
            )
            all_memories = self._apply_temporal_filter(
                all_memories, created_before=as_of_dt.isoformat()
            )

            # Filter to only include memories valid at as_of_date
            valid_memories = []
            for memory in all_memories:
                # Skip if the memory had already expired at as_of_date. A
                # datetime-valued expired_at must not crash a historical recall
                # (bounty #770), so both string and datetime forms are handled.
                expired_at = memory.get("expired_at")
                if expired_at:
                    try:
                        if isinstance(expired_at, str):
                            expired_dt = parse_iso_timestamp(expired_at)
                        elif isinstance(expired_at, datetime):
                            expired_dt = (
                                expired_at
                                if expired_at.tzinfo
                                else expired_at.replace(tzinfo=timezone.utc)
                            )
                        else:
                            expired_dt = None  # Unknown type: fail open
                        if expired_dt is not None and expired_dt <= as_of_dt:
                            continue  # Already expired at as_of_date
                    except (ValueError, AttributeError, TypeError):
                        # Fail open: a malformed expired_at is not proof the
                        # memory had expired at as_of. Falling through to the
                        # append below keeps it in the historical result rather
                        # than silently dropping it (timeline amnesia).
                        pass

                # It was live at as_of even if it is expired now.
                memory = {**memory, "status": "active"}
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
            raise MemoryOperationError(f"Failed to perform as-of query: {e}")

    def search_changed_since(
        self,
        since_date: str,
        agent_id: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int | None = 10,
        status: str = "all",
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

            all_memories = self._fetch_all_memories(
                namespaces, type=type, tags=tags, status=status
            )

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
            raise MemoryOperationError(f"Failed to search changed memories: {e}")

    def search_recent(
        self,
        agent_id: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int | None = 10,
        created_after: str | None = None,
        created_before: str | None = None,
        status: str = "all",
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
            status: Lifecycle filter - ``all`` (default), ``active`` or ``expired``
        """
        try:
            from memanto.app.utils.temporal_helpers import parse_iso_timestamp

            namespaces = self._get_search_namespaces(agent_id)
            if not namespaces:
                return {"results": [], "total_found": 0}

            unique_memories = self._fetch_all_memories(
                namespaces, type=type, tags=tags, status=status
            )

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
            raise MemoryOperationError(f"Failed to retrieve recent memories: {e}")

    def _fetch_all_memories(
        self,
        namespaces: list[str],
        type: list[str] | None = None,
        tags: list[str] | None = None,
        status: str = "all",
        created_before: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all stored memories across the given namespaces via Moorcheh's
        documents.fetch_text_data endpoint, applying optional type/tag filters
        and de-duplicating by id.

        Iterates through all pages using cursor-based pagination (next_token)
        so results are not truncated at the 100-item per-page cap.

        ``status`` narrows to one lifecycle state and defaults to ``all``.
        Point-in-time callers such as ``search_as_of`` must leave it at ``all``
        and apply their own expiry check against the target date, otherwise
        memories that were valid at that past date but have since expired are
        silently dropped (timeline amnesia).

        ``created_before`` drops any version whose ``created_at`` is after the
        given ISO timestamp *before* de-duplication, so point-in-time callers
        can stop a delete-and-recreate that happened after ``as_of`` from
        evicting the version that was valid then during newest-version
        selection (bounty #770).
        """
        from memanto.app.utils.temporal_helpers import parse_iso_timestamp

        before_dt: datetime | None = None
        if created_before:
            try:
                before_dt = parse_iso_timestamp(created_before)
            except (TypeError, ValueError, AttributeError):
                pass  # Fail open: keep newest-version dedup behaviour.

        items: list[Any] = []
        for ns in namespaces:
            next_token: str | None = None
            seen_tokens: set[str] = set()
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
                if not next_token or next_token in seen_tokens:
                    break
                seen_tokens.add(next_token)

        latest_by_id: dict[str, tuple[tuple[datetime, int], dict[str, Any]]] = {}
        for index, item in enumerate(items):
            # Skip summary chunks — only return real memory documents
            if isinstance(item, dict) and item.get("is_summary"):
                continue
            formatted = self._format_memory_item(item)
            mid = formatted.get("id")
            if not mid:
                continue

            # Point-in-time dedup: only versions that existed at the target
            # date compete for the newest-version slot, so a delete-and-recreate
            # after as_of cannot displace the version valid then (bounty #770).
            if before_dt is not None:
                raw_created = formatted.get("created_at")
                if not raw_created:
                    continue
                try:
                    if parse_iso_timestamp(str(raw_created)) > before_dt:
                        continue
                except (TypeError, ValueError):
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

        return self._filter_by_status(memories, status)

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
            except (TypeError, ValueError, OverflowError):
                continue
        return fallback, fetch_index

    def _build_filtered_query(
        self,
        query: str,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> str:
        """
        Build enhanced query with Moorcheh's #key:value metadata filters

        Example: "user authentication #memory_type:fact"

        Note: Temporal, confidence, and lifecycle-status filters are applied as
        post-processing. Status in particular must not be pushed down: records
        written before the lifecycle field carry no ``status`` key at all, and a
        server-side ``#status:active`` would drop them instead of treating them
        as active.
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
            base = (query or "").strip()
            joined = " ".join(filter_parts)
            return f"{base} {joined}".strip() if base else joined
        return (query or "").strip()

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
            except (TypeError, ValueError, OverflowError):
                # Fail open: include memories with unknown confidence rather
                # than silently dropping them. This preserves imported memories
                # that may not carry a confidence score.
                filtered.append(result)
                continue
            if not math.isfinite(confidence):
                # Non-finite values (NaN/inf) are malformed: fail open, same as
                # unparseable confidence above, rather than silently dropping.
                filtered.append(result)
                continue
            if confidence >= min_confidence:
                filtered.append(result)
        return filtered

    @staticmethod
    def _filter_by_status(
        results: list[dict[str, Any]], status: str
    ) -> list[dict[str, Any]]:
        """
        Narrow results to one lifecycle state.

        ``status="all"`` (the default everywhere) returns both active and
        expired memories so callers can label them; expiry is surfaced to the
        reader, not hidden from them. A record with no stored status predates
        the lifecycle field and counts as active.

        Args:
            results: List of formatted memory items
            status: One of ``all``, ``active``, ``expired``

        Returns:
            Filtered list
        """
        if status == "all":
            return results

        return [
            result for result in results if (result.get("status") or "active") == status
        ]

    def generate_answer(
        self, query: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """Generate AI answer from memories"""
        try:
            # Tenant isolation: answer generation must be scoped to one agent's
            # namespace. The previous "first available namespace" fallback let a
            # caller without an ``agent_id`` read memories from whichever tenant
            # happened to sort first in the account's namespace list.
            if not agent_id:
                raise MemoryError(
                    "Tenant isolation: an agent_id is required to scope an answer"
                )
            namespace = agent_namespace(agent_id)

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
            raise MemoryOperationError(f"Failed to generate answer: {e}")

    def _get_search_namespaces(self, agent_id: str | None = None) -> list[str]:
        """Return the single tenant namespace for *agent_id*.

        Tenant isolation: a memory read must be scoped to one agent's namespace.
        Fanning out across every namespace on the server account (the previous
        ``list_namespaces()`` fallback) let a caller with a missing or empty
        ``agent_id`` read every other tenant's memories. Fail closed instead.
        """
        if not agent_id:
            raise MemoryError(
                "Tenant isolation: an agent_id is required to scope a memory read"
            )
        # Search a specific agent's namespace
        return [agent_namespace(agent_id)]

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
                if any(tag in self._normalize_tags(r.get("tags")) for tag in tags)
            ]

        # Apply limit
        return filtered[:limit]

    def _format_memory_item(self, item: Any) -> dict[str, Any]:
        """
        Format memory item for response.
        """
        if not isinstance(item, dict):
            raise MemoryOperationError(
                message="Data corruption detected: Received malformed memory item from storage layer.",
                details={"item_preview": str(item)[:100]},
            )

        if not hasattr(self, "_memory_record_cls"):
            from memanto.app.core import MemoryRecord

            self._memory_record_cls = MemoryRecord

        # Check if metadata is in nested format (Moorcheh API spec)
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise MemoryOperationError(
                message="Data corruption detected: Received malformed metadata from storage layer.",
                details={"item_preview": str(item)[:100]},
            )

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
        tags = self._normalize_tags(get_field("tags"))

        # Extract provenance
        provenance = get_field("provenance") or "explicit_statement"

        # Parse title and content from Moorcheh document text format:
        raw_text = item.get("text", "")
        title = ""
        content = raw_text

        if raw_text:
            first_line, separator, body = raw_text.partition("\n\n")

            # Treat bracketed prefixes as typed headers only for known
            # memory types; otherwise keep the raw first line as title.
            title_match = re.match(r"^\[(.*?)\]\s*(.*)$", first_line, flags=re.DOTALL)
            if title_match and title_match.group(1).lower() in VALID_MEMORY_TYPES:
                title = title_match.group(2).strip()
            else:
                title_match = None
                title = first_line.strip()

            if separator:
                content = body
            elif title_match:
                content = ""
            else:
                content = raw_text

            # ``MemoryRecord.to_moorcheh_document`` appends a display-only
            # tags footer after the content.  Remove exactly that generated
            # footer while preserving arbitrary paragraphs (including a
            # user-authored ``Tags:`` paragraph) in the original content.
            if tags:
                footer_marker = "\n\nTags: "
                content_without_footer, marker, footer_tags = content.rpartition(
                    footer_marker
                )
                normalized_footer_tags = [
                    value.strip() for value in footer_tags.split(",") if value.strip()
                ]
                normalized_metadata_tags = [str(value).strip() for value in tags]
                if marker and normalized_footer_tags == normalized_metadata_tags:
                    content = content_without_footer

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
            # Records written before the lifecycle field carry no status.
            "status": get_field("status") or "active",
            "tags": tags,
            "created_at": _coerce_timestamp_str(get_field("created_at")),
            "updated_at": _coerce_timestamp_str(get_field("updated_at")),
            "expired_at": _coerce_timestamp_str(get_field("expired_at")),
            "expired_by": get_field("expired_by"),
            "actor_id": get_field("actor_id"),
            "source": get_field("source"),
            "source_ref": get_field("source_ref"),
            "agent_id": get_field("agent_id"),
            "score": item.get("score"),  # Search relevance score
            # Provenance
            "provenance": provenance,
        }

        # Preserve extra metadata keys (e.g. original_id) not in the schema.
        # Exclude known keys, removed fields, and "memory_type" (duplicate of "type").
        known_keys = set(formatted.keys()) | {"text", "memory_type", "metadata"}

        extra_sources = [item]
        if isinstance(metadata, dict):
            extra_sources.append(metadata)

        for source_dict in extra_sources:
            for key, value in source_dict.items():
                if key not in known_keys and key not in REMOVED_TRUST_FIELDS:
                    formatted[key] = value

        return formatted

    @staticmethod
    def _normalize_tags(tags_value: Any) -> list[str]:
        if isinstance(tags_value, str):
            parsed_tags = tags_value.split(",")
        elif isinstance(tags_value, list):
            parsed_tags = tags_value
        else:
            return []

        normalized = []
        for tag in parsed_tags:
            if tag is None:
                continue

            clean_tag = str(tag).strip()
            if clean_tag:
                normalized.append(clean_tag)

        return normalized
