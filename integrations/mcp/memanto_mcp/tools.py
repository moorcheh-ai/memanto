"""Memanto MCP tools.

Each tool is a thin, well-documented wrapper around the Memanto ``SdkClient``.
Tool descriptions are tuned for LLM tool-selection: they start with a verb,
explain *when* to use the tool, and list its non-obvious constraints.

Tools never raise raw Python exceptions back through the MCP transport - they
catch and re-format them so the calling model gets actionable feedback.

Note: this module deliberately does NOT use ``from __future__ import
annotations``. FastMCP evaluates parameter annotations with ``eval_str=True``
at tool-registration time, and we use closure-scoped type aliases (e.g.
``AgentIdField``) that won't resolve once they have been deferred to strings.
"""

import logging
from typing import Annotated, Any, Literal, TypeVar

from memanto.app.constants import (
    VALID_MEMORY_TYPES,
    VALID_PROVENANCE_TYPES,
)
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    MemantoError,
)
from memanto.app.utils.validation import InputLimits
from pydantic import BaseModel, Field

from memanto_mcp.lifecycle import MemantoLifecycle, NoAgentConfiguredError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases pulled from Memanto core so the JSON schema we expose matches
# what the server validates internally. Keeping these as Literals gives the
# calling model a hard enum to pick from.
# ---------------------------------------------------------------------------

MemoryTypeLiteral = Literal[
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
]

ProvenanceLiteral = Literal[
    "explicit_statement",
    "inferred",
    "corrected",
    "validated",
    "observed",
    "imported",
]

# Hard caps mirroring the Memanto core service (see SdkClient).
_MAX_CONTENT_LENGTH = InputLimits.MAX_TEXT_LENGTH
_MAX_TITLE_LENGTH = 100
_MAX_BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Structured output models. FastMCP serializes return values to text content,
# but using BaseModel keeps the schema self-documenting and stable.
# ---------------------------------------------------------------------------


class RememberResult(BaseModel):
    """Outcome of storing a single memory."""

    status: str = Field(description="'ok' on success, 'error' otherwise.")
    memory_id: str | None = Field(default=None, description="Memanto-assigned ID.")
    agent_id: str = Field(description="Agent the memory belongs to.")
    namespace: str | None = Field(default=None, description="Underlying namespace.")
    confidence: float | None = Field(default=None, description="Confidence stored.")
    message: str | None = Field(default=None, description="Human-readable detail.")


class MemoryHit(BaseModel):
    """A single retrieved memory."""

    id: str | None = None
    type: str | None = None
    title: str | None = None
    content: str | None = None
    confidence: float | None = None
    tags: list[str] = Field(default_factory=list)
    status: str | None = None
    source: str | None = Field(
        default=None, description="Origin of the memory (e.g. user, agent, tool)."
    )
    source_ref: str | None = Field(
        default=None, description="Reference to the source (e.g. file name, tool id)."
    )
    provenance: str | None = Field(
        default=None,
        description="How the memory was obtained (explicit_statement, inferred, ...).",
    )
    created_at: str | None = None
    score: float | None = Field(
        default=None, description="Similarity score when available."
    )


class RecallResult(BaseModel):
    """Outcome of a recall query."""

    status: str
    agent_id: str
    query: str | None = None
    mode: str = Field(
        default="semantic", description="semantic | recent | as_of | changed_since"
    )
    count: int = 0
    memories: list[MemoryHit] = Field(default_factory=list)
    message: str | None = None


class AnswerResult(BaseModel):
    """Outcome of a RAG ``answer`` call."""

    status: str
    agent_id: str
    question: str
    answer: str | None = None
    sources: list[Any] = Field(default_factory=list)
    namespace: str | None = None
    message: str | None = None


class BatchRememberItemResult(BaseModel):
    id: str | None = None
    status: str
    error: str | None = None


class BatchRememberResult(BaseModel):
    status: str
    agent_id: str
    namespace: str | None = None
    total_submitted: int = 0
    successful: int = 0
    failed: int = 0
    results: list[BatchRememberItemResult] = Field(default_factory=list)
    message: str | None = None


class AgentInfoResult(BaseModel):
    status: str
    agent_id: str | None = None
    namespace: str | None = None
    pattern: str | None = None
    description: str | None = None
    created_at: str | None = None
    message: str | None = None


class AgentListResult(BaseModel):
    status: str
    count: int = 0
    agents: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


# ---------------------------------------------------------------------------
# Error shaping
# ---------------------------------------------------------------------------


T = TypeVar("T", bound=BaseModel)
# NOTE: we cannot use 'from __future__ import annotations' here (see module docstring)
# so we use traditional type hints.


def _error_payload(model_cls: type[T], message: str, **defaults: Any) -> T:
    """Build a uniform error response of the given result model type."""
    return model_cls(status="error", message=message, **defaults)


def _format_exception(exc: Exception) -> str:
    """Render an exception as a short human-readable string."""
    if isinstance(exc, MemantoError):
        return str(exc.message)
    return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: Any, lifecycle: MemantoLifecycle) -> None:
    """Register every Memanto MCP tool against the given FastMCP instance.

    Imported lazily so tests can swap out the lifecycle implementation.
    """

    settings = lifecycle.settings
    default_hint = (
        f" (defaults to '{settings.default_agent_id}')"
        if settings.default_agent_id
        else " (required: no MEMANTO_DEFAULT_AGENT_ID is configured)"
    )

    AgentIdField = Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Memanto agent identifier the memory belongs to" + default_hint + "."
            ),
        ),
    ]

    # ============================================================ #
    # remember
    # ============================================================ #
    @mcp.tool(
        name="remember",
        description=(
            "Store a single piece of information in the agent's long-term "
            "memory. Use this whenever the user shares a stable fact, "
            "preference, decision, goal, or instruction you should recall "
            "in a future conversation. Memory is typed (13 categories) and "
            "carries confidence + provenance so later retrievals can rank "
            f"and filter intelligently. Content is capped at "
            f"{_MAX_CONTENT_LENGTH} chars - store atomic, self-contained "
            "statements."
        ),
    )
    def remember(
        content: Annotated[
            str,
            Field(
                description=(
                    "The memory itself - one atomic statement. "
                    f"Max {_MAX_CONTENT_LENGTH} characters."
                ),
                min_length=1,
                max_length=_MAX_CONTENT_LENGTH,
            ),
        ],
        type: Annotated[
            MemoryTypeLiteral,
            Field(
                description=(
                    "Semantic memory type. Use 'preference' for likes/styles, "
                    "'fact' for stable factual claims, 'decision' for choices "
                    "the user has made, 'goal' for objectives, 'instruction' "
                    "for explicit how-to directives, 'event' for things that "
                    "happened, 'observation' for inferred behavior."
                ),
            ),
        ] = "fact",
        title: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Short label (<= 100 chars). If omitted, derived from content."
                ),
                max_length=_MAX_TITLE_LENGTH,
            ),
        ] = None,
        confidence: Annotated[
            float,
            Field(
                description=(
                    "How sure you are this is true (0.0-1.0). Use 1.0 only "
                    "for things the user stated explicitly. 0.6-0.8 is a "
                    "sensible default for inferred information."
                ),
                ge=0.0,
                le=1.0,
            ),
        ] = 0.85,
        tags: Annotated[
            list[str] | None,
            Field(
                default=None,
                description="Optional lowercase tag list for later filtering.",
            ),
        ] = None,
        provenance: Annotated[
            ProvenanceLiteral,
            Field(
                description=(
                    "How this memory was obtained. 'explicit_statement' means "
                    "the user said it; 'inferred' means you deduced it; "
                    "'observed' means you saw it during a tool call; "
                    "'corrected' means it overrides an earlier wrong memory."
                ),
            ),
        ] = "explicit_statement",
        source: Annotated[
            str,
            Field(
                description=(
                    "Free-form label for the source of this memory "
                    "(e.g. 'user', 'web', 'tool-call', or your agent name)."
                ),
            ),
        ] = "mcp-agent",
        agent_id: AgentIdField = None,
    ) -> RememberResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            resolved_title = title or (
                content[: _MAX_TITLE_LENGTH - 3] + "..."
                if len(content) > _MAX_TITLE_LENGTH
                else content
            )
            result = lifecycle.client.remember(
                agent_id=resolved,
                memory_type=type,
                title=resolved_title,
                content=content,
                confidence=confidence,
                tags=tags or [],
                source=source,
                provenance=provenance,
            )
            return RememberResult(
                status="ok",
                memory_id=result.get("memory_id"),
                agent_id=resolved,
                namespace=result.get("namespace"),
                confidence=result.get("confidence", confidence),
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(RememberResult, str(exc), agent_id=agent_id or "")
        except Exception as exc:
            logger.exception("remember failed")
            return _error_payload(
                RememberResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
            )

    # ============================================================ #
    # batch_remember
    # ============================================================ #
    @mcp.tool(
        name="batch_remember",
        description=(
            "Store many memories at once (up to 100). Use this when you have "
            "a list of independent facts to persist - e.g. extracting "
            "structured data from a document. For a single item, prefer "
            "`remember`."
        ),
    )
    def batch_remember(
        memories: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "List of memory dicts. Each item supports the same fields "
                    "as `remember` (content [required], type, title, "
                    "confidence, tags, source, provenance). Max 100 items."
                ),
                min_length=1,
                max_length=_MAX_BATCH_SIZE,
            ),
        ],
        agent_id: AgentIdField = None,
    ) -> BatchRememberResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            # Validate before round-trip so we fail fast with a clear error.
            for i, item in enumerate(memories):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"memories[{i}] must be an object, got {type(item).__name__}"
                    )
                if "content" not in item or not str(item["content"]).strip():
                    raise ValueError(
                        f"memories[{i}] is missing required field 'content'"
                    )
                m_type = item.get("type", "fact")
                if m_type not in VALID_MEMORY_TYPES:
                    raise ValueError(
                        f"memories[{i}].type={m_type!r} is not a valid memory type. "
                        f"Choose one of: {sorted(VALID_MEMORY_TYPES)}"
                    )
                prov = item.get("provenance", "explicit_statement")
                if prov not in VALID_PROVENANCE_TYPES:
                    raise ValueError(
                        f"memories[{i}].provenance={prov!r} is not valid. "
                        f"Choose one of: {sorted(VALID_PROVENANCE_TYPES)}"
                    )

            result = lifecycle.client.batch_remember(
                agent_id=resolved,
                memories=memories,
            )
            sub_results = [
                BatchRememberItemResult(
                    id=r.get("id"),
                    status=r.get("status", "queued"),
                    error=r.get("error"),
                )
                for r in result.get("results", [])
            ]
            return BatchRememberResult(
                status="ok",
                agent_id=resolved,
                namespace=result.get("namespace"),
                total_submitted=result.get("total_submitted", len(memories)),
                successful=result.get("successful", 0),
                failed=result.get("failed", 0),
                results=sub_results,
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(
                BatchRememberResult, str(exc), agent_id=agent_id or ""
            )
        except Exception as exc:
            logger.exception("batch_remember failed")
            return _error_payload(
                BatchRememberResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
            )

    # ============================================================ #
    # recall
    # ============================================================ #
    @mcp.tool(
        name="recall",
        description=(
            "Search the agent's memories by semantic similarity. Returns the "
            "top-N most relevant items. Use this FIRST before asking the user "
            "to repeat information - the agent may already remember it. The "
            "query should be natural language ('what does the user prefer for "
            "code style?'), not keywords."
        ),
    )
    def recall(
        query: Annotated[
            str,
            Field(
                description="Natural-language search query.",
                min_length=1,
                max_length=2000,
            ),
        ],
        limit: Annotated[
            int,
            Field(
                description="Max number of memories to return (1-100).",
                ge=1,
                le=100,
            ),
        ] = 10,
        type: Annotated[
            list[MemoryTypeLiteral] | None,
            Field(
                default=None,
                description=(
                    "Optional type filter - e.g. ['preference'] to only "
                    "retrieve user preferences."
                ),
            ),
        ] = None,
        min_similarity: Annotated[
            float | None,
            Field(
                default=None,
                ge=0.0,
                le=1.0,
                description="Minimum similarity score 0-1.",
            ),
        ] = None,
        agent_id: AgentIdField = None,
    ) -> RecallResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            result = lifecycle.client.recall(
                agent_id=resolved,
                query=query,
                limit=limit,
                type=list(type) if type else None,
            )
            hits = [_to_memory_hit(m) for m in result.get("memories", [])]
            if min_similarity is not None:
                hits = [h for h in hits if (h.score or 0.0) >= min_similarity]
            return RecallResult(
                status="ok",
                agent_id=resolved,
                query=query,
                mode="semantic",
                count=len(hits),
                memories=hits,
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(
                RecallResult, str(exc), agent_id=agent_id or "", query=query
            )
        except Exception as exc:
            logger.exception("recall failed")
            return _error_payload(
                RecallResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
                query=query,
            )

    # ============================================================ #
    # recall_recent
    # ============================================================ #
    @mcp.tool(
        name="recall_recent",
        description=(
            "Return the most recently stored memories (newest first). Use "
            "this to surface fresh context - e.g. 'what did we just decide?' "
            "- when you don't have a specific search query."
        ),
    )
    def recall_recent(
        limit: Annotated[
            int,
            Field(description="Max number of memories to return.", ge=1, le=100),
        ] = 10,
        type: Annotated[
            list[MemoryTypeLiteral] | None,
            Field(default=None, description="Optional type filter."),
        ] = None,
        agent_id: AgentIdField = None,
    ) -> RecallResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            result = lifecycle.client.recall_recent(
                agent_id=resolved,
                limit=limit,
                type=list(type) if type else None,
            )
            hits = [_to_memory_hit(m) for m in result.get("memories", [])]
            return RecallResult(
                status="ok",
                agent_id=resolved,
                mode="recent",
                count=len(hits),
                memories=hits,
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(RecallResult, str(exc), agent_id=agent_id or "")
        except Exception as exc:
            logger.exception("recall_recent failed")
            return _error_payload(
                RecallResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
            )

    # ============================================================ #
    # recall_as_of
    # ============================================================ #
    @mcp.tool(
        name="recall_as_of",
        description=(
            "Point-in-time recall: return only memories that were known "
            "before the given timestamp. Use this when the user asks "
            "historical questions like 'what did we know on 2025-11-01?' or "
            "to reconstruct context at a previous moment."
        ),
    )
    def recall_as_of(
        as_of: Annotated[
            str,
            Field(
                description=(
                    "Cutoff timestamp. Accepts YYYY-MM-DD (interpreted as end "
                    "of that day) or full ISO 8601 e.g. 2025-11-01T14:30:00Z."
                ),
                min_length=1,
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        type: Annotated[
            list[MemoryTypeLiteral] | None,
            Field(default=None, description="Optional type filter."),
        ] = None,
        agent_id: AgentIdField = None,
    ) -> RecallResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            result = lifecycle.client.recall_as_of(
                agent_id=resolved,
                as_of=as_of,
                limit=limit,
                type=list(type) if type else None,
            )
            hits = [_to_memory_hit(m) for m in result.get("memories", [])]
            return RecallResult(
                status="ok",
                agent_id=resolved,
                mode="as_of",
                count=len(hits),
                memories=hits,
                message=f"as_of={as_of}",
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(RecallResult, str(exc), agent_id=agent_id or "")
        except Exception as exc:
            logger.exception("recall_as_of failed")
            return _error_payload(
                RecallResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
            )

    # ============================================================ #
    # recall_changed_since
    # ============================================================ #
    @mcp.tool(
        name="recall_changed_since",
        description=(
            "Differential retrieval: return memories created or updated "
            "after the given timestamp. Use this for 'what's new since X?' "
            "or to catch up on activity between sessions."
        ),
    )
    def recall_changed_since(
        since: Annotated[
            str,
            Field(
                description=(
                    "Lower-bound timestamp. Accepts YYYY-MM-DD (start of day) "
                    "or full ISO 8601 e.g. 2025-11-01T00:00:00Z."
                ),
                min_length=1,
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        type: Annotated[
            list[MemoryTypeLiteral] | None,
            Field(default=None, description="Optional type filter."),
        ] = None,
        agent_id: AgentIdField = None,
    ) -> RecallResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            result = lifecycle.client.recall_changed_since(
                agent_id=resolved,
                since=since,
                limit=limit,
                type=list(type) if type else None,
            )
            hits = [_to_memory_hit(m) for m in result.get("memories", [])]
            return RecallResult(
                status="ok",
                agent_id=resolved,
                mode="changed_since",
                count=len(hits),
                memories=hits,
                message=f"since={since}",
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(RecallResult, str(exc), agent_id=agent_id or "")
        except Exception as exc:
            logger.exception("recall_changed_since failed")
            return _error_payload(
                RecallResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
            )

    # ============================================================ #
    # answer (RAG)
    # ============================================================ #
    @mcp.tool(
        name="answer",
        description=(
            "Ask a natural-language question and get an LLM-generated answer "
            "grounded ONLY in the agent's stored memories (RAG). Prefer this "
            "over `recall` when you need a synthesized answer rather than a "
            "ranked list. Returns the answer text plus the supporting memory "
            "sources."
        ),
    )
    def answer(
        question: Annotated[
            str,
            Field(description="The question to answer.", min_length=1, max_length=2000),
        ],
        limit: Annotated[
            int | None,
            Field(
                default=None,
                ge=1,
                le=100,
                description="Number of context memories to retrieve. Defaults to server config.",
            ),
        ] = None,
        temperature: Annotated[
            float | None,
            Field(
                default=None,
                ge=0.0,
                le=2.0,
                description="LLM temperature. Defaults to server config.",
            ),
        ] = None,
        kiosk_mode: Annotated[
            bool,
            Field(
                description=(
                    "If true, refuses to answer when no memory clears the "
                    "similarity threshold (useful for strictly grounded "
                    "applications)."
                ),
            ),
        ] = False,
        agent_id: AgentIdField = None,
    ) -> AnswerResult:
        try:
            resolved = lifecycle.ensure_ready(lifecycle.resolve_agent_id(agent_id))
            result = lifecycle.client.answer(
                agent_id=resolved,
                question=question,
                limit=limit,
                temperature=temperature,
                kiosk_mode=kiosk_mode,
            )
            return AnswerResult(
                status="ok",
                agent_id=resolved,
                question=question,
                answer=result.get("answer"),
                sources=result.get("sources", []),
                namespace=result.get("namespace"),
            )
        except NoAgentConfiguredError as exc:
            return _error_payload(
                AnswerResult, str(exc), agent_id=agent_id or "", question=question
            )
        except Exception as exc:
            logger.exception("answer failed")
            return _error_payload(
                AnswerResult,
                _format_exception(exc),
                agent_id=agent_id or settings.default_agent_id or "",
                question=question,
            )

    # ============================================================ #
    # Optional agent administration tools
    # ============================================================ #
    if settings.expose_admin_tools:
        _register_admin_tools(mcp, lifecycle)


def _register_admin_tools(mcp: Any, lifecycle: MemantoLifecycle) -> None:
    """Optional agent lifecycle tools, gated by MEMANTO_EXPOSE_ADMIN."""

    @mcp.tool(
        name="create_agent",
        description=(
            "Create a new Memanto agent (memory namespace). Most users only "
            "need one agent per project - it is fine to leave this disabled "
            "and rely on auto-create."
        ),
    )
    def create_agent(
        agent_id: Annotated[
            str,
            Field(
                description="Unique agent id (letters, numbers, '-', '_').",
                min_length=1,
                max_length=64,
            ),
        ],
        pattern: Annotated[
            Literal["support", "project", "tool"],
            Field(description="Agent pattern - affects default behaviors."),
        ] = "tool",
        description: Annotated[
            str | None,
            Field(default=None, description="Optional human-readable description."),
        ] = None,
    ) -> AgentInfoResult:
        try:
            agent = lifecycle.client.create_agent(
                agent_id=agent_id, pattern=pattern, description=description
            )
            return AgentInfoResult(
                status="ok",
                agent_id=agent.get("agent_id"),
                namespace=agent.get("namespace"),
                pattern=agent.get("pattern"),
                description=agent.get("description"),
                created_at=str(agent.get("created_at"))
                if agent.get("created_at")
                else None,
            )
        except AgentAlreadyExistsError as exc:
            return AgentInfoResult(
                status="exists",
                agent_id=agent_id,
                message=exc.message,
            )
        except Exception as exc:
            logger.exception("create_agent failed")
            return _error_payload(
                AgentInfoResult, _format_exception(exc), agent_id=agent_id
            )

    @mcp.tool(
        name="list_agents",
        description="List every Memanto agent visible to the current API key.",
    )
    def list_agents() -> AgentListResult:
        try:
            agents = lifecycle.client.list_agents()
            return AgentListResult(status="ok", count=len(agents), agents=agents)
        except Exception as exc:
            logger.exception("list_agents failed")
            return _error_payload(AgentListResult, _format_exception(exc))

    @mcp.tool(
        name="get_agent",
        description="Look up an agent's metadata by id.",
    )
    def get_agent(
        agent_id: Annotated[
            str, Field(description="Agent id to look up.", min_length=1)
        ],
    ) -> AgentInfoResult:
        try:
            agent = lifecycle.client.get_agent(agent_id)
            return AgentInfoResult(
                status="ok",
                agent_id=agent.get("agent_id"),
                namespace=agent.get("namespace"),
                pattern=agent.get("pattern"),
                description=agent.get("description"),
                created_at=str(agent.get("created_at"))
                if agent.get("created_at")
                else None,
            )
        except AgentNotFoundError as exc:
            return AgentInfoResult(
                status="not_found", agent_id=agent_id, message=exc.message
            )
        except Exception as exc:
            logger.exception("get_agent failed")
            return _error_payload(
                AgentInfoResult, _format_exception(exc), agent_id=agent_id
            )

    @mcp.tool(
        name="delete_agent",
        description=(
            "Delete an agent's local metadata. Note: by default this does NOT "
            "delete the remote Moorcheh namespace - memories are retained "
            "until explicitly purged via the Memanto CLI/REST API."
        ),
    )
    def delete_agent(
        agent_id: Annotated[
            str, Field(description="Agent id to delete.", min_length=1)
        ],
    ) -> AgentInfoResult:
        try:
            lifecycle.client.delete_agent(agent_id)
            return AgentInfoResult(status="ok", agent_id=agent_id, message="deleted")
        except AgentNotFoundError as exc:
            return AgentInfoResult(
                status="not_found", agent_id=agent_id, message=exc.message
            )
        except Exception as exc:
            logger.exception("delete_agent failed")
            return _error_payload(
                AgentInfoResult, _format_exception(exc), agent_id=agent_id
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_memory_hit(raw: dict[str, Any]) -> MemoryHit:
    """Map a Memanto recall result row into the MCP MemoryHit shape.

    Memanto returns slightly different keys across endpoints (e.g. ``score``
    vs ``similarity_score``). We coalesce them here so tool consumers see a
    stable schema.
    """
    return MemoryHit(
        id=str(raw.get("id")) if raw.get("id") is not None else None,
        type=raw.get("type"),
        title=raw.get("title"),
        content=raw.get("content"),
        confidence=raw.get("confidence"),
        tags=list(raw.get("tags") or []),
        status=raw.get("status"),
        source=raw.get("source"),
        source_ref=raw.get("source_ref"),
        provenance=raw.get("provenance"),
        created_at=str(raw.get("created_at")) if raw.get("created_at") else None,
        score=(
            raw.get("score")
            if raw.get("score") is not None
            else raw.get("similarity_score")
        ),
    )
