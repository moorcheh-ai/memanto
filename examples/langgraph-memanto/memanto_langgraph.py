"""LangGraph long-term memory backed by Memanto.

This example uses LangGraph's native ``store=`` injection point. The graph
state remains thread-local, while customer memories are written to and recalled
from a separate semantic store that survives new graph invocations.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    SearchItem,
    SearchOp,
)

VALID_MEMORY_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}


class MemantoClient(Protocol):
    """Minimal subset of ``memanto.cli.client.sdk_client.SdkClient`` used here."""

    def remember(
        self,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "user",
        provenance: str | None = None,
    ) -> dict[str, Any]:
        """Store one memory in Memanto."""

    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> dict[str, Any]:
        """Search memories in Memanto."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return _utcnow()


def _namespace_text(namespace: tuple[str, ...]) -> str:
    return "/".join(namespace)


def _tag(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"lg-{prefix}-{digest}"


def _namespace_tags(namespace: tuple[str, ...]) -> list[str]:
    tags = []
    for index in range(1, len(namespace) + 1):
        tags.append(_tag("nsp", _namespace_text(namespace[:index])))
    return tags


def _key_tag(key: str) -> str:
    return _tag("key", key)


def _safe_title(value: dict[str, Any], key: str) -> str:
    for field in ("title", "memory", "text", "content", "summary"):
        raw = value.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()[:96]
    return key[:96]


def _value_text(value: dict[str, Any]) -> str:
    for field in ("memory", "text", "content", "summary"):
        raw = value.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _content_for_memanto(
    namespace: tuple[str, ...],
    key: str,
    value: dict[str, Any],
) -> str:
    value_payload = {
        "namespace": list(namespace),
        "key": key,
        "value": value,
    }
    payload = json.dumps(value_payload, sort_keys=True, separators=(",", ":"))
    memory_text = _value_text(value)
    content = f"{memory_text}\n\nLangGraph item: {payload}"
    if len(content) <= 500:
        return content

    allowed = 500 - len("\n\nLangGraph item: ") - len(payload)
    if allowed <= 32:
        compact_value = {"memory": memory_text[:180], "truncated": True}
        value_payload["value"] = compact_value
        payload = json.dumps(value_payload, sort_keys=True, separators=(",", ":"))
        allowed = max(32, 500 - len("\n\nLangGraph item: ") - len(payload))
    return f"{memory_text[:allowed]}\n\nLangGraph item: {payload}"[:500]


def _payload_from_memanto(memory: dict[str, Any]) -> dict[str, Any]:
    content = str(memory.get("content") or "")
    marker = "LangGraph item: "
    if marker in content:
        raw_payload = content.rsplit(marker, 1)[-1].strip()
        try:
            payload = json.loads(raw_payload)
            if isinstance(payload, dict) and isinstance(payload.get("value"), dict):
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "namespace": ["memanto", "imported"],
        "key": memory.get("id") or str(uuid.uuid4()),
        "value": {
            "memory": content,
            "title": memory.get("title") or "Memanto memory",
            "memory_type": memory.get("type") or "fact",
        },
    }


def _item_from_memory(memory: dict[str, Any]) -> SearchItem:
    payload = _payload_from_memanto(memory)
    value = payload.get("value") if isinstance(payload.get("value"), dict) else {}
    namespace_raw = payload.get("namespace")
    if isinstance(namespace_raw, list):
        namespace = tuple(str(part) for part in namespace_raw)
    elif isinstance(namespace_raw, tuple):
        namespace = tuple(str(part) for part in namespace_raw)
    else:
        namespace = tuple(str(part) for part in memory.get("namespace", ()))

    if not namespace:
        namespace = ("memanto", "imported")

    key = str(payload.get("key") or memory.get("id") or uuid.uuid4())
    stored_value = cast(dict[str, Any], value)
    score = memory.get("score")
    return SearchItem(
        namespace=namespace,
        key=key,
        value=cast(dict[str, Any], stored_value),
        created_at=_parse_dt(memory.get("created_at")),
        updated_at=_parse_dt(memory.get("updated_at")),
        score=float(score) if isinstance(score, (int, float)) else None,
    )


def _matches_filter(value: dict[str, Any], filter_value: dict[str, Any] | None) -> bool:
    if not filter_value:
        return True
    return all(value.get(key) == expected for key, expected in filter_value.items())


def _matches_conditions(
    namespace: tuple[str, ...],
    conditions: tuple[Any, ...] | None,
) -> bool:
    if not conditions:
        return True
    for condition in conditions:
        path = tuple(condition.path)
        if condition.match_type == "prefix" and namespace[: len(path)] != path:
            return False
        if condition.match_type == "suffix" and namespace[-len(path) :] != path:
            return False
    return True


class MemantoLangGraphStore(BaseStore):
    """LangGraph ``BaseStore`` adapter for Memanto semantic memory.

    ``put`` stores a concise LangGraph item as a typed Memanto memory.
    ``search`` uses Memanto semantic recall plus namespace tags so memories can
    be scoped the same way LangGraph's native stores are scoped.
    """

    def __init__(self, client: MemantoClient, agent_id: str) -> None:
        self.client = client
        self.agent_id = agent_id

    def batch(self, ops: Iterable[Op]) -> list[Any]:
        return [self._run_op(op) for op in ops]

    async def abatch(self, ops: Iterable[Op]) -> list[Any]:
        return await asyncio.to_thread(self.batch, list(ops))

    def _run_op(self, op: Op) -> Any:
        if isinstance(op, PutOp):
            return self._put(op)
        if isinstance(op, GetOp):
            return self._get(op)
        if isinstance(op, SearchOp):
            return self._search(op)
        if isinstance(op, ListNamespacesOp):
            return self._list_namespaces(op)
        raise ValueError(f"Unsupported LangGraph store op: {type(op)!r}")

    def _put(self, op: PutOp) -> None:
        if op.value is None:
            self._write_tombstone(op.namespace, op.key)
            return None

        memory_type = str(op.value.get("memory_type") or "artifact")
        if memory_type not in VALID_MEMORY_TYPES:
            memory_type = "artifact"

        tags = [
            "langgraph",
            "langgraph-store",
            _key_tag(op.key),
            *_namespace_tags(op.namespace),
        ]
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=_safe_title(op.value, op.key),
            content=_content_for_memanto(op.namespace, op.key, op.value),
            confidence=float(op.value.get("confidence", 0.9)),
            tags=tags,
            source="agent",
            provenance="explicit_statement",
        )
        return None

    def _write_tombstone(self, namespace: tuple[str, ...], key: str) -> None:
        value = {
            "memory": f"LangGraph item {key} was deleted.",
            "memory_type": "event",
            "deleted": True,
        }
        self.client.remember(
            agent_id=self.agent_id,
            memory_type="event",
            title=f"Deleted LangGraph item {key}"[:96],
            content=_content_for_memanto(namespace, key, value),
            confidence=1.0,
            tags=[
                "langgraph",
                "langgraph-store",
                "langgraph-tombstone",
                _key_tag(key),
                *_namespace_tags(namespace),
            ],
            source="agent",
            provenance="explicit_statement",
        )

    def _get(self, op: GetOp) -> Item | None:
        exact = self._recall(
            query=op.key,
            tags=[_namespace_tags(op.namespace)[-1], _key_tag(op.key)],
            limit=20,
        )
        for result in exact:
            if result.namespace == op.namespace and result.key == op.key:
                return Item(
                    namespace=result.namespace,
                    key=result.key,
                    value=result.value,
                    created_at=result.created_at,
                    updated_at=result.updated_at,
                )
        return None

    def _search(self, op: SearchOp) -> list[SearchItem]:
        query = op.query or "LangGraph memory"
        prefix_tag = _namespace_tags(op.namespace_prefix)[-1]
        results = self._recall(query=query, tags=[prefix_tag], limit=100)
        filtered = [
            item
            for item in results
            if item.namespace[: len(op.namespace_prefix)] == op.namespace_prefix
            and _matches_filter(item.value, op.filter)
            and not item.value.get("deleted")
        ]
        return filtered[op.offset : op.offset + op.limit]

    def _list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        results = self._recall(query="LangGraph memory", tags=["langgraph-store"], limit=100)
        namespaces = sorted(
            {
                item.namespace[: op.max_depth] if op.max_depth else item.namespace
                for item in results
                if _matches_conditions(item.namespace, op.match_conditions)
            }
        )
        return namespaces[op.offset : op.offset + op.limit]

    def _recall(self, query: str, tags: list[str], limit: int) -> list[SearchItem]:
        response = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            tags=tags,
        )
        memories = response.get("memories", [])
        if not isinstance(memories, list):
            return []

        required_tags = set(tags)
        items = []
        for memory in memories:
            memory_tags = set(memory.get("tags") or [])
            if required_tags and not required_tags.issubset(memory_tags):
                continue
            items.append(_item_from_memory(memory))
        return items


class LocalJsonMemantoStore(BaseStore):
    """Offline store with Memanto-like persistence for demos and tests.

    It implements the same LangGraph ``BaseStore`` operations and persists to a
    JSON file, so reviewers can verify cross-session recall without API keys.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def batch(self, ops: Iterable[Op]) -> list[Any]:
        data = self._load()
        results: list[Any] = []
        dirty = False
        for op in ops:
            if isinstance(op, PutOp):
                self._apply_put(data, op)
                results.append(None)
                dirty = True
            elif isinstance(op, GetOp):
                results.append(self._apply_get(data, op))
            elif isinstance(op, SearchOp):
                results.append(self._apply_search(data, op))
            elif isinstance(op, ListNamespacesOp):
                results.append(self._apply_list_namespaces(data, op))
            else:
                raise ValueError(f"Unsupported LangGraph store op: {type(op)!r}")
        if dirty:
            self._save(data)
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Any]:
        return await asyncio.to_thread(self.batch, list(ops))

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        return cast(dict[str, dict[str, dict[str, Any]]], json.loads(self.path.read_text()))

    def _save(self, data: dict[str, dict[str, dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def _apply_put(
        self,
        data: dict[str, dict[str, dict[str, Any]]],
        op: PutOp,
    ) -> None:
        namespace = _namespace_text(op.namespace)
        if op.value is None:
            data.get(namespace, {}).pop(op.key, None)
            return

        now = _utcnow().isoformat()
        existing = data.get(namespace, {}).get(op.key, {})
        data.setdefault(namespace, {})[op.key] = {
            "namespace": list(op.namespace),
            "key": op.key,
            "value": op.value,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }

    def _apply_get(
        self,
        data: dict[str, dict[str, dict[str, Any]]],
        op: GetOp,
    ) -> Item | None:
        raw = data.get(_namespace_text(op.namespace), {}).get(op.key)
        if not raw:
            return None
        return Item(
            namespace=tuple(raw["namespace"]),
            key=raw["key"],
            value=raw["value"],
            created_at=_parse_dt(raw.get("created_at")),
            updated_at=_parse_dt(raw.get("updated_at")),
        )

    def _apply_search(
        self,
        data: dict[str, dict[str, dict[str, Any]]],
        op: SearchOp,
    ) -> list[SearchItem]:
        candidates = []
        for namespace_key, entries in data.items():
            namespace = tuple(namespace_key.split("/"))
            if namespace[: len(op.namespace_prefix)] != op.namespace_prefix:
                continue
            for raw in entries.values():
                value = raw["value"]
                if _matches_filter(value, op.filter):
                    candidates.append(self._local_search_item(raw, op.query))

        candidates.sort(
            key=lambda item: (
                item.score if item.score is not None else 0.0,
                item.updated_at.isoformat(),
            ),
            reverse=True,
        )
        return candidates[op.offset : op.offset + op.limit]

    def _local_search_item(self, raw: dict[str, Any], query: str | None) -> SearchItem:
        value = raw["value"]
        score = None
        if query:
            text = _value_text(value)
            score = _lexical_score(query, text)
        return SearchItem(
            namespace=tuple(raw["namespace"]),
            key=raw["key"],
            value=value,
            created_at=_parse_dt(raw.get("created_at")),
            updated_at=_parse_dt(raw.get("updated_at")),
            score=score,
        )

    def _apply_list_namespaces(
        self,
        data: dict[str, dict[str, dict[str, Any]]],
        op: ListNamespacesOp,
    ) -> list[tuple[str, ...]]:
        namespaces = []
        for namespace_key in data:
            namespace = tuple(namespace_key.split("/"))
            if _matches_conditions(namespace, op.match_conditions):
                namespaces.append(namespace[: op.max_depth] if op.max_depth else namespace)
        return sorted(set(namespaces))[op.offset : op.offset + op.limit]


def _lexical_score(query: str, text: str) -> float:
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    text_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
    if not query_terms:
        return 0.0
    return len(query_terms & text_terms) / len(query_terms)


class SupportState(TypedDict):
    """State that belongs to one LangGraph thread only."""

    customer_id: str
    message: str
    session_label: str
    recalled_memories: list[str]
    response: str
    stored_memory_keys: list[str]


def build_customer_success_graph(store: BaseStore):
    """Build a deterministic LangGraph workflow that uses injected memory."""

    def recall_customer_memory(state: SupportState, *, store: BaseStore) -> dict[str, Any]:
        namespace = _customer_namespace(state["customer_id"])
        recalled = store.search(namespace, query=state["message"], limit=8)
        return {
            "recalled_memories": [
                str(item.value.get("memory", item.value)) for item in recalled
            ]
        }

    def draft_response(state: SupportState) -> dict[str, Any]:
        if state["recalled_memories"]:
            memory_block = "\n".join(f"- {memory}" for memory in state["recalled_memories"])
        else:
            memory_block = "- No durable customer memory found."

        response = (
            f"{state['session_label']} response for {state['customer_id']}:\n"
            f"{memory_block}\n"
            "Recommended next action: answer with the recalled constraints first, "
            "then ask only for missing details."
        )
        return {"response": response}

    def write_durable_memory(
        state: SupportState,
        *,
        store: BaseStore,
    ) -> dict[str, Any]:
        namespace = _customer_namespace(state["customer_id"])
        stored_keys = []
        for value in _extract_durable_memories(state["message"]):
            key = _stable_key(value["memory"])
            store.put(namespace, key, value, index=["memory"])
            stored_keys.append(key)
        return {"stored_memory_keys": stored_keys}

    graph = StateGraph(SupportState)
    graph.add_node("recall_customer_memory", recall_customer_memory)
    graph.add_node("draft_response", draft_response)
    graph.add_node("write_durable_memory", write_durable_memory)
    graph.add_edge(START, "recall_customer_memory")
    graph.add_edge("recall_customer_memory", "draft_response")
    graph.add_edge("draft_response", "write_durable_memory")
    graph.add_edge("write_durable_memory", END)
    return graph.compile(store=store)


def _customer_namespace(customer_id: str) -> tuple[str, ...]:
    return ("customers", customer_id, "memories")


def _stable_key(memory: str) -> str:
    return hashlib.sha1(memory.encode("utf-8")).hexdigest()[:16]


def _extract_durable_memories(message: str) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    lower = message.lower()

    name_match = re.search(
        r"\b(?:i am|i'm|this is)\s+([A-Z][a-zA-Z-]+)",
        message,
        flags=re.IGNORECASE,
    )
    if name_match:
        memories.append(
            _memory(
                f"Customer's name is {name_match.group(1)}.",
                "fact",
                ["identity"],
            )
        )

    ticket_match = re.search(r"\b[A-Z]{2}-\d{4,}\b", message)
    if ticket_match:
        memories.append(
            _memory(
                f"Customer is discussing support ticket {ticket_match.group(0)}.",
                "fact",
                ["ticket"],
            )
        )

    if "hipaa" in lower:
        memories.append(
            _memory(
                "Customer works under HIPAA constraints; avoid unnecessary PHI.",
                "instruction",
                ["compliance"],
            )
        )

    if "concise" in lower and "bullet" in lower:
        memories.append(
            _memory(
                "Customer prefers concise bullet-point updates.",
                "preference",
                ["style"],
            )
        )

    if "replacement-before-refund" in lower or (
        "replacement" in lower and "refund" in lower
    ):
        memories.append(
            _memory(
                "Customer's account policy is replacement-before-refund.",
                "decision",
                ["policy"],
            )
        )

    return memories


def _memory(memory: str, memory_type: str, tags: list[str]) -> dict[str, Any]:
    return {
        "memory": memory,
        "memory_type": memory_type,
        "confidence": 0.95,
        "tags": tags,
    }
