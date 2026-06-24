"""MemantoStore - a LangGraph BaseStore backed by Memanto.

Compile the graph with ``store=MemantoStore(client, agent_id)`` and nodes
get cross-thread, cross-session memory through the official LangGraph store
API (``store.aput`` / ``store.asearch``).

Mapping between abstractions
----------------------------

    BaseStore                         ->  Memanto
    namespace (tuple[str, ...])       ->  agent_id       (``langgraph_<p0>_<p1>...``)
    key (str)                         ->  reserved tag   ``lg:key:<key>``
    value["kind"] / value["type"]     ->  memory_type    (auto-parsed if absent)
    value["title"]                    ->  title          (auto-derived if absent)
    value["content"]                  ->  content        (auto-stringified if absent)
    value["confidence"]               ->  confidence     (default 0.8)
    value["tags"]                     ->  user tags (non-reserved)
    SearchOp.query                    ->  recall query   (``recall_recent`` if ``"*"``)
    SearchOp.filter["type"]           ->  type filter
    SearchOp.filter["min_confidence"] ->  min_similarity

Documented limitations
----------------------

* **Delete** (``PutOp`` with ``value=None``) routes to Memanto's
  conflict-resolution flow. Use ``memanto conflicts resolve`` instead.
* **TTL** on put is ignored - Memanto does not expire memories on a timer.
* **Pagination offset** in search is ignored - raise ``limit`` instead.
* **_do_get** is best-effort: uses ``recall_recent`` (unbiased by query)
  up to the 100-result cap, then a semantic fallback. A key stored long
  ago beyond the cap window may not be found.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    PutOp,
    SearchItem,
    SearchOp,
)

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

_KEY_TAG_PREFIX = "lg:key:"
_RESERVED_PREFIX = "lg:"

_VALID_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
}


class MemantoStore(BaseStore):
    """LangGraph ``BaseStore`` backed by Memanto's typed semantic memory.

    Drop-in replacement for ``InMemoryStore`` / ``PostgresStore`` /
    ``RedisStore``. Memories persist across threads and sessions because
    Memanto persists them server-side, scoped by ``agent_id``.

    Example::

        from langgraph_memanto import MemantoStore
        from langgraph.checkpoint.memory import MemorySaver

        store = MemantoStore(api_key="your_api_key")
        graph = builder.compile(store=store, checkpointer=MemorySaver())
    """

    # Memanto's recall is server-capped at 100 results.
    _MEMANTO_RECALL_CAP = 100
    # Cache TTL keeps short-interval polls (Streamlit reruns, multiple graph
    # nodes) from burning rate-limit budget on identical queries.
    _CACHE_TTL_S = 30.0

    def __init__(self, api_key: str) -> None:
        """Initialize MemantoStore with an API key."""
        self.api_key = api_key
        self._lock = threading.RLock()
        self._client_pool: dict[str, SdkClient] = {}
        self._agent_prefix = "langgraph_"
        # (namespace, query, limit, type, min_sim) -> (timestamp, list[SearchItem])
        self._search_cache: dict[tuple, tuple[float, list[SearchItem]]] = {}
        # Survives 429s without flashing the UI panel to zero.
        self._last_good: dict[tuple[str, ...], list[SearchItem]] = {}

    def _ensure_client(self, namespace: tuple[str, ...]) -> tuple[SdkClient, str]:
        ns_str = "_".join(namespace) or "default"
        agent_id = f"{self._agent_prefix}{ns_str}"
        with self._lock:
            if agent_id in self._client_pool:
                return self._client_pool[agent_id], agent_id

            from memanto.app.utils.errors import AgentAlreadyExistsError

            client = SdkClient(api_key=self.api_key)
            try:
                client.create_agent(agent_id=agent_id, pattern="tool")
            except AgentAlreadyExistsError:
                pass
            client.activate_agent(agent_id=agent_id)
            self._client_pool[agent_id] = client
            return client, agent_id

    # ------------------------------------------------------------------ #
    # Required abstract methods                                          #
    # ------------------------------------------------------------------ #

    def batch(self, ops: Iterable[Any]) -> list[Any]:
        """Execute a batch of store operations synchronously."""
        return [self._dispatch_one(op) for op in ops]

    async def abatch(self, ops: Iterable[Any]) -> list[Any]:
        """Execute a batch of store operations asynchronously."""
        # Run operations concurrently in threads rather than sequentially
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(None, self._dispatch_one, op) for op in ops]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------ #
    # Per-op dispatch                                                    #
    # ------------------------------------------------------------------ #

    def _dispatch_one(self, op: Any) -> Any:
        if isinstance(op, GetOp):
            return self._do_get(op)
        if isinstance(op, PutOp):
            return self._do_put(op)
        if isinstance(op, SearchOp):
            return self._do_search(op)
        if isinstance(op, ListNamespacesOp):
            return self._do_list_namespaces(op)
        raise NotImplementedError(f"Unsupported store op: {type(op).__name__}")

    # ------------------------------------------------------------------ #
    # GET                                                                #
    # ------------------------------------------------------------------ #

    def _do_get(self, op: GetOp) -> Item | None:
        """Lookup a single memory by key.

        Uses ``recall_recent`` first (no semantic bias) so the target memory
        is not crowded out by cosine-similarity ranking. Falls back to a
        semantic recall if not found in the recent window.
        """
        client, agent_id = self._ensure_client(op.namespace)
        key_tag = self._key_to_tag(op.key)
        required_tags = [key_tag]

        # recall_recent avoids semantic bias in key lookup
        result = client.recall_recent(
            agent_id=agent_id,
            limit=self._MEMANTO_RECALL_CAP,
        )
        for mem in result.get("memories", []):
            tags = mem.get("tags") or []
            if all(t in tags for t in required_tags):
                return self._memory_to_item(mem, op.namespace, op.key)

        # Fallback: semantic recall may surface older memories
        try:
            result = client.recall(
                agent_id=agent_id,
                query=op.key or "*",
                limit=self._MEMANTO_RECALL_CAP,
                tags=[key_tag],
            )
        except Exception as exc:
            logger.warning("MemantoStore._do_get fallback recall failed: %s", exc)
            return None

        for mem in result.get("memories", []):
            tags = mem.get("tags") or []
            if all(t in tags for t in required_tags):
                return self._memory_to_item(mem, op.namespace, op.key)
        return None

    # ------------------------------------------------------------------ #
    # PUT                                                                #
    # ------------------------------------------------------------------ #

    def _do_put(self, op: PutOp) -> None:
        """Persist a ``PutOp.value`` as a Memanto memory.

        When no ``kind``/``type`` is given, passes ``memory_type=None`` so
        the server-side auto-parser (``MemoryParsingService``) infers the
        type from the content via regex + fuzzy logic.
        """
        if op.value is None:
            raise NotImplementedError(
                "MemantoStore does not support delete via PutOp(value=None). "
                "Memanto removals go through the conflict-resolution flow; "
                "use `memanto conflicts resolve` or the SdkClient's resolve API."
            )

        value: dict[str, Any] = dict(op.value)

        # None → let server auto-parser classify from content
        raw_type = value.pop("kind", value.pop("type", None))
        if raw_type is not None:
            raw_type = str(raw_type).lower()
            if raw_type not in _VALID_MEMORY_TYPES:
                raw_type = None
        memory_type: str | None = raw_type

        raw_content = value.pop("content", None)
        if raw_content is None:
            raw_content = self._stringify(value)

        title = value.pop("title", None)
        if not title:
            title = raw_content if len(raw_content) <= 80 else raw_content[:77] + "..."
        title = title[:100]

        confidence = float(value.pop("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        raw_tags = value.pop("tags", []) or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif not isinstance(raw_tags, (list, tuple, set)):
            raw_tags = [str(raw_tags)]

        user_tags = [
            str(t) for t in raw_tags if not str(t).startswith(_RESERVED_PREFIX)
        ]
        all_tags = user_tags + [self._key_to_tag(op.key)]

        client, agent_id = self._ensure_client(op.namespace)
        client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=str(raw_content),
            confidence=confidence,
            tags=all_tags,
            source="langgraph-store",
            provenance="explicit_statement",
        )

        # Invalidate cached searches for this namespace
        prefix = op.namespace
        with self._lock:
            self._search_cache = {
                k: v for k, v in self._search_cache.items() if k[0] != prefix
            }

    # ------------------------------------------------------------------ #
    # SEARCH                                                             #
    # ------------------------------------------------------------------ #

    def _do_search(self, op: SearchOp) -> list[SearchItem]:
        """Retrieve memories matching the namespace.

        Uses ``recall_recent`` for wildcard queries (avoids semantic bias
        when the caller just wants all recent memories in a namespace) and
        ``recall()`` for actual semantic queries. A single call is made in
        both cases; namespace isolation is enforced client-side via tag
        AND-matching after retrieval.
        """
        query = op.query or "*"
        filter_dict = op.filter or {}

        type_filter = filter_dict.get("type") or filter_dict.get("kind")
        if isinstance(type_filter, str):
            type_filter = [type_filter]
        # SearchOp uses "min_confidence"; SdkClient.recall() uses "min_similarity"
        min_similarity = filter_dict.get("min_confidence")
        extra_tags = list(filter_dict.get("tags", []) or [])

        cache_key = (
            op.namespace_prefix,
            query,
            op.limit,
            tuple(extra_tags),
            tuple(type_filter) if type_filter else None,
            min_similarity,
        )
        with self._lock:
            cached = self._search_cache.get(cache_key)
            if cached is not None:
                ts, items = cached
                if time.time() - ts < self._CACHE_TTL_S:
                    return items

        fetch_limit = max(1, min(op.limit, self._MEMANTO_RECALL_CAP))
        rate_limited = False

        client, agent_id = self._ensure_client(op.namespace_prefix)

        try:
            if query == "*" and not min_similarity:
                # recall_recent: no semantic bias, returns newest memories first
                result = client.recall_recent(
                    agent_id=agent_id,
                    limit=self._MEMANTO_RECALL_CAP,
                    type=type_filter or None,
                )
            else:
                result = client.recall(
                    agent_id=agent_id,
                    query=query,
                    limit=fetch_limit,
                    type=type_filter or None,
                    tags=extra_tags if extra_tags else None,
                    min_similarity=min_similarity,
                )
        except Exception as exc:
            logger.warning("MemantoStore._do_search recall failed: %s", exc)
            err = str(exc)
            if any(
                m in err
                for m in (
                    "429",
                    "Limit Exceeded",
                )
            ):
                rate_limited = True
                result = {"memories": []}
            else:
                return []

        out: list[SearchItem] = []
        for mem in result.get("memories", []):
            tags = mem.get("tags") or []
            if extra_tags and not all(t in tags for t in extra_tags):
                continue
            key = self._tags_to_key(tags) or mem.get("id", "")
            out.append(self._memory_to_search_item(mem, op.namespace_prefix, key))

        out = out[: op.limit]

        with self._lock:
            if not out and rate_limited and op.namespace_prefix in self._last_good:
                logger.info(
                    "MemantoStore: rate-limited, returning last-good for %r",
                    op.namespace_prefix,
                )
                return self._last_good[op.namespace_prefix]

            if out and not rate_limited:
                self._search_cache[cache_key] = (time.time(), out)
                self._last_good[op.namespace_prefix] = out

        return out

    # ------------------------------------------------------------------ #
    # LIST NAMESPACES (best-effort)                                      #
    # ------------------------------------------------------------------ #

    def _do_list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        """List namespaces by fetching all Memanto agents with the prefix."""
        client = SdkClient(api_key=self.api_key)
        try:
            agents = client.list_agents()
        except Exception as e:
            logger.warning("MemantoStore: Failed to list agents: %s", e)
            return []

        namespaces = []
        for agent in agents:
            agent_id = agent.get("agent_id") or agent.get("id") or ""
            if agent_id.startswith(self._agent_prefix):
                ns_str = agent_id[len(self._agent_prefix) :]
                if ns_str == "default":
                    namespaces.append(())
                else:
                    namespaces.append(tuple(ns_str.split("_")))

        if op.match_conditions:
            for cond in op.match_conditions:
                if getattr(cond, "match_type", "prefix") == "prefix":
                    namespaces = [
                        ns for ns in namespaces if ns[: len(cond.path)] == cond.path
                    ]
                else:
                    namespaces = [
                        ns for ns in namespaces if ns[-len(cond.path) :] == cond.path
                    ]

        result: list[tuple[str, ...]] = sorted(set(namespaces))
        if op.max_depth is not None:
            result = sorted({ns[: op.max_depth] for ns in result})
        return result[: op.limit] if op.limit else result

    # ------------------------------------------------------------------ #
    # Encoding helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _key_to_tag(key: str) -> str:
        return f"{_KEY_TAG_PREFIX}{key}"

    @staticmethod
    def _tags_to_key(tags: list[str]) -> str | None:
        for t in tags:
            if t.startswith(_KEY_TAG_PREFIX):
                return t[len(_KEY_TAG_PREFIX) :]
        return None

    @staticmethod
    def _stringify(value: dict[str, Any]) -> str:
        if not value:
            return "(empty)"
        return ", ".join(f"{k}={v}" for k, v in value.items())

    # ------------------------------------------------------------------ #
    # Item construction                                                  #
    # ------------------------------------------------------------------ #

    def _memory_to_item(
        self, mem: dict[str, Any], namespace: tuple[str, ...], key: str
    ) -> Item:
        return Item(
            value=self._memory_to_value(mem),
            key=key,
            namespace=namespace,
            created_at=self._parse_dt(mem.get("created_at")),
            updated_at=self._parse_dt(mem.get("updated_at") or mem.get("created_at")),
        )

    def _memory_to_search_item(
        self, mem: dict[str, Any], namespace: tuple[str, ...], key: str
    ) -> SearchItem:
        score = mem.get("score")
        if score is None:
            score = mem.get("similarity")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        return SearchItem(
            value=self._memory_to_value(mem),
            key=key,
            namespace=namespace,
            created_at=self._parse_dt(mem.get("created_at")),
            updated_at=self._parse_dt(mem.get("updated_at") or mem.get("created_at")),
            score=score_f,
        )

    @staticmethod
    def _memory_to_value(mem: dict[str, Any]) -> dict[str, Any]:
        tags = mem.get("tags", []) or []
        user_tags = [t for t in tags if not t.startswith(_RESERVED_PREFIX)]
        return {
            "kind": mem.get("type", "fact"),
            "title": mem.get("title", ""),
            "content": mem.get("content", ""),
            "confidence": mem.get("confidence"),
            "tags": user_tags,
            "memory_id": mem.get("id"),
        }

    @staticmethod
    def _parse_dt(raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(tz=timezone.utc)
