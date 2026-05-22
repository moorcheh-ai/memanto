"""Memanto helpers for LangGraph long-term memory examples.

The adapter in this file is intentionally dependency-light:

* ``JsonlMemoryBackend`` gives reviewers and CI a local, credential-free
  memory store.
* ``MemantoCliBackend`` uses the real ``memanto`` CLI for Moorcheh-backed
  memory when a user wants to run the same graph live.
* ``MemantoGraphMemory`` exposes LangGraph-friendly nodes and a wrapper for
  ordinary graph nodes.

LangGraph passes state dictionaries between nodes. This module follows that
pattern and adds two fields:

* ``memanto_context``: formatted memories to inject into prompts.
* ``memanto_hits``: structured recall hits for custom logic or logging.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


VALID_MEMORY_TYPES = {
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

MARKER_TO_TYPE = {
    "remember": "fact",
    "memory": "fact",
    "fact": "fact",
    "preference": "preference",
    "goal": "goal",
    "decision": "decision",
    "artifact": "artifact",
    "learning": "learning",
    "event": "event",
    "instruction": "instruction",
    "relationship": "relationship",
    "context": "context",
    "observation": "observation",
    "commitment": "commitment",
    "error": "error",
}

TYPED_STATE_KEYS = {
    "remember": "fact",
    "memories_to_save": "fact",
    "facts": "fact",
    "preferences": "preference",
    "goals": "goal",
    "decisions": "decision",
    "artifacts": "artifact",
    "learnings": "learning",
    "events": "event",
    "instructions": "instruction",
    "relationships": "relationship",
    "context_memories": "context",
    "observations": "observation",
    "commitments": "commitment",
    "errors": "error",
}

TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
MARKED_LINE_RE = re.compile(
    r"^\s*(remember|memory|fact|preference|goal|decision|artifact|learning|event|"
    r"instruction|relationship|context|observation|commitment|error)\s*[:=-]\s*(.+)$",
    re.IGNORECASE,
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*['\"]?([^\s'\";,]+)"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


@dataclass
class MemoryHit:
    """A normalized memory recall result."""

    id: str
    content: str
    type: str = "fact"
    score: float = 0.0
    title: str = ""
    tags: tuple[str, ...] = ()
    source: str = "langgraph"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Mapping[str, Any], score: float = 0.0) -> "MemoryHit":
        """Build a normalized hit from a backend storage row."""
        tags = tuple(str(tag) for tag in row.get("tags", []) if tag)
        return cls(
            id=str(row.get("id", "")),
            content=str(row.get("content", "")),
            type=str(row.get("type", "fact")),
            score=score,
            title=str(row.get("title", "")),
            tags=tags,
            source=str(row.get("source", "langgraph")),
            created_at=str(row.get("created_at", "")),
            metadata=dict(row.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for LangGraph state."""
        return asdict(self)


@dataclass
class MemoryCandidate:
    """A memory extracted from graph state or a node response."""

    content: str
    memory_type: str = "fact"
    title: str | None = None
    tags: tuple[str, ...] = ()
    confidence: float = 0.82
    source: str = "langgraph"
    provenance: str = "inferred_from_graph_state"


class MemoryBackend(Protocol):
    """Minimal backend contract used by the LangGraph adapter."""

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: str | None = None,
        tags: Sequence[str] | None = None,
        confidence: float = 0.8,
        source: str = "langgraph",
        provenance: str = "explicit_statement",
    ) -> str:
        """Persist one memory and return its id."""

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: set[str] | None = None,
        tags: set[str] | None = None,
    ) -> list[MemoryHit]:
        """Return relevant memories for a query."""


class JsonlMemoryBackend:
    """A deterministic local memory backend for demos and tests.

    This is not a replacement for Memanto. It gives the example a zero-key
    path so maintainers can verify the LangGraph wiring before connecting the
    same adapter to the real CLI backend.
    """

    def __init__(self, path: str | Path):
        """Use *path* as the JSONL file that stores local memories."""
        self.path = Path(path)

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: str | None = None,
        tags: Sequence[str] | None = None,
        confidence: float = 0.8,
        source: str = "langgraph",
        provenance: str = "explicit_statement",
    ) -> str:
        """Append one deduplicated, redacted memory to the JSONL store."""
        normalized = normalize_text(redact_secrets(content))
        if not normalized:
            return ""

        memory_type = normalize_memory_type(memory_type)
        tags_tuple = tuple(sorted({normalize_tag(tag) for tag in tags or [] if tag}))
        memory_id = stable_memory_id(memory_type, normalized)

        existing_ids = {str(row.get("id", "")) for row in self._load_rows()}
        if memory_id in existing_ids:
            return memory_id

        row = {
            "id": memory_id,
            "content": normalized,
            "type": memory_type,
            "title": title or make_title(normalized),
            "confidence": float(max(0.0, min(1.0, confidence))),
            "tags": list(tags_tuple),
            "source": source,
            "provenance": provenance,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"backend": "jsonl"},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return memory_id

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: set[str] | None = None,
        tags: set[str] | None = None,
    ) -> list[MemoryHit]:
        """Search local memories with deterministic token-overlap scoring."""
        query_tokens = tokenize(query)
        tag_filter = {normalize_tag(tag) for tag in tags or set()}
        type_filter = {normalize_memory_type(item) for item in memory_types or set()}
        hits: list[MemoryHit] = []

        for row in self._load_rows():
            row_type = normalize_memory_type(str(row.get("type", "fact")))
            row_tags = {normalize_tag(tag) for tag in row.get("tags", [])}

            if type_filter and row_type not in type_filter:
                continue
            if tag_filter and not tag_filter.intersection(row_tags):
                continue

            haystack = " ".join(
                [
                    str(row.get("title", "")),
                    str(row.get("content", "")),
                    " ".join(sorted(row_tags)),
                    row_type,
                ]
            )
            score = score_text(query_tokens, tokenize(haystack))
            if tag_filter and tag_filter.intersection(row_tags):
                score += 0.25
            if query_tokens and score <= 0:
                continue
            hits.append(MemoryHit.from_row(row, score=round(score, 4)))

        hits.sort(key=lambda hit: (hit.score, hit.created_at), reverse=True)
        return hits[: max(0, limit)]

    def _load_rows(self) -> list[dict[str, Any]]:
        """Read valid JSONL memory rows, skipping blank or corrupt lines."""
        if not self.path.exists():
            return []

        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("content"):
                    rows.append(row)
        return rows


class MemantoCliBackend:
    """Backend that shells out to the installed ``memanto`` CLI."""

    def __init__(
        self,
        agent_id: str = "langgraph-memanto-demo",
        timeout: int = 20,
        auto_create: bool = True,
    ):
        self.agent_id = agent_id
        self.timeout = timeout
        self.auto_create = auto_create
        self._activated = False

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: str | None = None,
        tags: Sequence[str] | None = None,
        confidence: float = 0.8,
        source: str = "langgraph",
        provenance: str = "explicit_statement",
    ) -> str:
        """Persist one memory through the installed Memanto CLI."""
        self.ensure_agent()
        payload = normalize_text(redact_secrets(content))
        args = [
            "memanto",
            "remember",
            payload,
            "--type",
            normalize_memory_type(memory_type),
            "--confidence",
            str(confidence),
            "--source",
            source or self.agent_id,
            "--provenance",
            provenance,
        ]
        if title:
            args.extend(["--title", title])
        if tags:
            args.extend(["--tags", ",".join(normalize_tag(tag) for tag in tags)])

        result = self._run(args)
        digest = stable_memory_id(memory_type, payload)
        stdout = strip_ansi(result.stdout)
        match = re.search(r"Memory ID:\s*([A-Za-z0-9_.:-]+)", stdout)
        return match.group(1) if match else digest

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: set[str] | None = None,
        tags: set[str] | None = None,
    ) -> list[MemoryHit]:
        """Recall memories through the CLI and normalize the console output."""
        self.ensure_agent()
        args = ["memanto", "recall", query, "--limit", str(limit)]
        if memory_types and len(memory_types) == 1:
            args.extend(["--type", next(iter(memory_types))])
        if tags:
            args.extend(["--tags", ",".join(sorted(tags))])

        result = self._run(args)
        text = strip_ansi(result.stdout).strip()
        if not text or "No memories found" in text:
            return []
        return [
            MemoryHit(
                id="memanto-cli-recall",
                content=text,
                type="context",
                score=1.0,
                title="Memanto recall",
                tags=("memanto-cli",),
                source=self.agent_id,
                metadata={"backend": "memanto-cli"},
            )
        ]

    def ensure_agent(self) -> None:
        """Create or activate the configured Memanto agent once per process."""
        if self._activated:
            return
        if not shutil.which("memanto"):
            raise RuntimeError("memanto CLI was not found on PATH")

        if self.auto_create:
            created = self._run(["memanto", "agent", "create", self.agent_id], check=False)
            if created.returncode != 0:
                self._run(["memanto", "agent", "activate", self.agent_id])
        else:
            self._run(["memanto", "agent", "activate", self.agent_id])
        self._activated = True

    def _run(
        self, args: Sequence[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Run a Memanto CLI command with timeout and optional error checking."""
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if check and result.returncode != 0:
            message = strip_ansi(result.stderr or result.stdout).strip()
            raise RuntimeError(f"memanto CLI failed: {message}")
        return result


class MemantoGraphMemory:
    """LangGraph-friendly memory adapter.

    Use ``recall_node`` before an LLM/tool node, ``remember_node`` after it, or
    ``wrap_node`` when you want a one-line integration for an existing node.
    """

    def __init__(
        self,
        backend: MemoryBackend,
        agent_id: str = "langgraph-memanto-demo",
        context_key: str = "memanto_context",
        hits_key: str = "memanto_hits",
        recall_limit: int = 5,
        recall_memory_types: set[str] | None = None,
    ):
        self.backend = backend
        self.agent_id = agent_id
        self.context_key = context_key
        self.hits_key = hits_key
        self.recall_limit = recall_limit
        self.recall_memory_types = recall_memory_types

    def recall_for_state(self, state: Mapping[str, Any]) -> list[MemoryHit]:
        """Build a recall query from state and retrieve matching memories."""
        query = build_recall_query(state)
        if not query:
            return []
        return self.backend.recall(
            query=query,
            limit=self.recall_limit,
            memory_types=self.recall_memory_types,
        )

    def inject_context(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Return a copy of state with formatted recall context injected."""
        hits = self.recall_for_state(state)
        next_state = dict(state)
        next_state[self.context_key] = format_memory_context(hits)
        next_state[self.hits_key] = [hit.to_dict() for hit in hits]
        return next_state

    def recall_node(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """LangGraph node that emits only the memory context update."""
        hydrated = self.inject_context(state)
        return {
            self.context_key: hydrated[self.context_key],
            self.hits_key: hydrated[self.hits_key],
        }

    def remember_node(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """LangGraph node that stores explicit memories from state."""
        saved_ids = self.store_from_state(state, node_name="memanto_remember")
        return {"memanto_saved": len(saved_ids), "memanto_saved_ids": saved_ids}

    def wrap_node(
        self, node: Callable[..., Mapping[str, Any]], node_name: str | None = None
    ) -> Callable[..., Mapping[str, Any]]:
        def wrapped(state: Mapping[str, Any], *args: Any, **kwargs: Any) -> Mapping[str, Any]:
            """Inject recalled context before a node and store memories after it."""
            hydrated = self.inject_context(state)
            result = node(hydrated, *args, **kwargs)
            if isinstance(result, Mapping):
                merged = dict(hydrated)
                merged.update(result)
                self.store_from_state(merged, node_name=node_name)
            return result

        wrapped.__name__ = getattr(node, "__name__", "memanto_wrapped_node")
        return wrapped

    def build_recall_messages(self, state: Mapping[str, Any]) -> list[dict[str, str]]:
        """Return a system-message payload for chat-model prompts."""
        context = self.inject_context(state).get(self.context_key, "")
        if not context:
            return []
        return [{"role": "system", "content": context}]

    def store_from_state(
        self, state: Mapping[str, Any], node_name: str | None = None
    ) -> list[str]:
        """Extract and persist memory candidates from LangGraph state."""
        saved_ids: list[str] = []
        seen: set[str] = set()
        source = node_name or self.agent_id

        for candidate in extract_memory_candidates(state, source=source):
            normalized = normalize_text(candidate.content)
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            tags = tuple(sorted(set(candidate.tags + ("langgraph",))))
            saved_id = self.backend.remember(
                content=normalized,
                memory_type=candidate.memory_type,
                title=candidate.title,
                tags=tags,
                confidence=candidate.confidence,
                source=candidate.source or source,
                provenance=candidate.provenance,
            )
            if saved_id:
                saved_ids.append(saved_id)
        return saved_ids


def make_backend_from_env(
    local_path: str | Path = ".memanto-langgraph-demo/memory.jsonl",
    agent_id: str = "langgraph-memanto-demo",
) -> MemoryBackend:
    """Create a backend from environment settings.

    ``MEMANTO_LANGGRAPH_BACKEND=cli`` uses the real Memanto CLI. Any other value
    uses the local JSONL backend.
    """

    backend = os.getenv("MEMANTO_LANGGRAPH_BACKEND", "local").strip().lower()
    if backend == "cli":
        return MemantoCliBackend(agent_id=agent_id)
    return JsonlMemoryBackend(local_path)


def build_recall_query(state: Mapping[str, Any]) -> str:
    """Build a compact recall query from task fields and the latest user turn."""
    parts: list[str] = []
    for key in ("query", "question", "task", "goal", "input"):
        value = state.get(key)
        if value:
            parts.append(str(value))

    messages = state.get("messages", [])
    if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
        for message in reversed(messages):
            role = message_role(message).lower()
            if role in {"user", "human"}:
                content = message_content(message)
                if content:
                    parts.append(content)
                    break

    return normalize_text(" ".join(parts))[:1200]


def extract_memory_candidates(
    state: Mapping[str, Any], source: str = "langgraph"
) -> list[MemoryCandidate]:
    """Collect explicit memory candidates from state fields and messages."""
    candidates: list[MemoryCandidate] = []

    for key, default_type in TYPED_STATE_KEYS.items():
        if key not in state:
            continue
        for item in iter_candidate_values(state[key]):
            candidate = coerce_candidate(item, default_type=default_type, source=source)
            if candidate:
                candidates.append(candidate)

    messages = state.get("messages", [])
    if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
        for message in messages[-8:]:
            for candidate in extract_marked_candidates(message_content(message), source=source):
                candidates.append(candidate)

    return dedupe_candidates(candidates)


def iter_candidate_values(value: Any) -> Iterable[Any]:
    """Yield candidate-like values from strings, mappings, or sequences."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Mapping):
        if any(key in value for key in ("content", "text", "memory")):
            return [value]
        return [
            {"content": f"{key}: {item}"}
            for key, item in value.items()
            if item is not None
        ]
    if isinstance(value, Iterable):
        return value
    return [value]


def coerce_candidate(
    value: Any, default_type: str = "fact", source: str = "langgraph"
) -> MemoryCandidate | None:
    """Normalize a raw state item into a typed memory candidate."""
    if isinstance(value, Mapping):
        content = value.get("content") or value.get("text") or value.get("memory")
        if not content:
            return None
        tags = value.get("tags") or ()
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",")]
        memory_type = value.get("type") or value.get("memory_type") or default_type
        return MemoryCandidate(
            content=strip_marker(str(content))[1],
            memory_type=normalize_memory_type(str(memory_type)),
            title=str(value.get("title")) if value.get("title") else None,
            tags=tuple(normalize_tag(tag) for tag in tags if tag),
            confidence=float(value.get("confidence", 0.86)),
            source=str(value.get("source") or source),
            provenance=str(value.get("provenance") or "explicit_state_field"),
        )

    text = normalize_text(str(value))
    if not text:
        return None
    inferred_type, stripped = strip_marker(text)
    return MemoryCandidate(
        content=stripped,
        memory_type=normalize_memory_type(inferred_type or default_type),
        tags=(normalize_tag(default_type),),
        confidence=0.84,
        source=source,
        provenance="explicit_state_field",
    )


def extract_marked_candidates(text: str, source: str = "langgraph") -> list[MemoryCandidate]:
    """Parse marked lines such as ``Decision: ...`` into candidates."""
    candidates: list[MemoryCandidate] = []
    for line in text.splitlines():
        match = MARKED_LINE_RE.match(line.strip())
        if not match:
            continue
        marker, content = match.groups()
        memory_type = MARKER_TO_TYPE.get(marker.lower(), "fact")
        candidates.append(
            MemoryCandidate(
                content=normalize_text(content),
                memory_type=memory_type,
                tags=(normalize_tag(memory_type),),
                confidence=0.84,
                source=source,
                provenance="marked_node_output",
            )
        )
    return candidates


def format_memory_context(hits: Sequence[MemoryHit]) -> str:
    """Render recall hits as prompt-ready LangGraph context."""
    if not hits:
        return ""
    lines = [
        "Memanto recalled durable memory relevant to this LangGraph step.",
        "Use these as context, and prefer the current user message if there is a conflict.",
    ]
    for index, hit in enumerate(hits, start=1):
        label = hit.type or "memory"
        score = f"{hit.score:.2f}" if hit.score else "n/a"
        lines.append(f"{index}. [{label}] {hit.content} (score: {score})")
    return "\n".join(lines)


def message_content(message: Any) -> str:
    """Read message content from dict-like or LangChain-style messages."""
    if isinstance(message, Mapping):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")

    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return normalize_text(" ".join(parts))
    return str(content)


def message_role(message: Any) -> str:
    """Read a role/type field from dict-like or object-style messages."""
    if isinstance(message, Mapping):
        return str(message.get("role") or message.get("type") or "")
    return str(getattr(message, "role", getattr(message, "type", "")))


def dedupe_candidates(candidates: Sequence[MemoryCandidate]) -> list[MemoryCandidate]:
    """Remove duplicate candidates while preserving input order."""
    deduped: list[MemoryCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        content = normalize_text(candidate.content)
        if not content:
            continue
        key = (candidate.memory_type, content.lower())
        if key in seen:
            continue
        seen.add(key)
        candidate.content = content
        deduped.append(candidate)
    return deduped


def strip_marker(text: str) -> tuple[str | None, str]:
    """Strip a memory-type marker from one line of text if present."""
    match = MARKED_LINE_RE.match(text)
    if not match:
        return None, text
    marker, content = match.groups()
    return MARKER_TO_TYPE.get(marker.lower(), "fact"), normalize_text(content)


def stable_memory_id(memory_type: str, content: str) -> str:
    """Create a deterministic id from memory type and normalized content."""
    payload = f"{normalize_memory_type(memory_type)}::{normalize_text(content).lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def score_text(query_tokens: set[str], memory_tokens: set[str]) -> float:
    """Score token overlap between a recall query and stored memory text."""
    if not query_tokens or not memory_tokens:
        return 0.0
    overlap = query_tokens.intersection(memory_tokens)
    if not overlap:
        return 0.0
    precision = len(overlap) / max(4, len(query_tokens))
    recall = len(overlap) / max(8, len(memory_tokens))
    return precision + recall


def tokenize(text: str) -> set[str]:
    """Tokenize text for lightweight local recall."""
    return {token.lower() for token in TOKEN_RE.findall(text)}


def normalize_memory_type(memory_type: str) -> str:
    """Return a valid Memanto memory type, falling back to ``fact``."""
    normalized = normalize_tag(memory_type)
    return normalized if normalized in VALID_MEMORY_TYPES else "fact"


def normalize_tag(tag: str) -> str:
    """Convert free-form tag text into a stable slug."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(tag).strip().lower()).strip("-")


def normalize_text(text: str) -> str:
    """Collapse whitespace and trim surrounding space."""
    return re.sub(r"\s+", " ", text or "").strip()


def make_title(content: str, limit: int = 72) -> str:
    """Create a compact display title for stored memory content."""
    content = normalize_text(content)
    if len(content) <= limit:
        return content
    return content[: limit - 3].rstrip() + "..."


def redact_secrets(text: str) -> str:
    """Mask obvious API keys, tokens, passwords, and ``sk-`` style secrets."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(replace_secret_match, redacted)
    return redacted


def replace_secret_match(match: re.Match[str]) -> str:
    """Replace only the secret value when the regex exposes one."""
    if match.lastindex and match.lastindex >= 2:
        return match.group(0).replace(match.group(2), "[REDACTED]")
    return "[REDACTED]"


def strip_ansi(text: str) -> str:
    """Remove ANSI color/control sequences from CLI output."""
    return ANSI_RE.sub("", text or "")


__all__ = [
    "JsonlMemoryBackend",
    "MemantoCliBackend",
    "MemantoGraphMemory",
    "MemoryCandidate",
    "MemoryHit",
    "build_recall_query",
    "extract_memory_candidates",
    "format_memory_context",
    "make_backend_from_env",
]
