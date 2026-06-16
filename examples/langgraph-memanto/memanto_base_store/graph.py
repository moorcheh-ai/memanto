"""LangGraph customer-support agent backed by MemantoStore.

Graph shape:

    START -> recall_context -> respond -> extract_and_store -> END

* ``recall_context`` reads from the cross-thread store using the current
  user's namespace and the latest user message as the semantic query.
* ``respond`` calls the LLM with the recalled memories injected as system
  context. This is the part the demo recording shows working without any
  prior turn in the current thread.
* ``extract_and_store`` asks the LLM to extract atomic preferences/facts
  from the latest user message and writes each one to the store via
  ``store.aput`` so the next session can use them.

The graph is compiled with both a checkpointer (short-term thread state)
and the MemantoStore (long-term cross-thread memory). That split is the
whole point - see ``examples/langgraph-memanto/README.md`` for why.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Literal

import openai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import RetryPolicy
from langgraph_memanto import MemantoStore
from memanto_base_store.state import SupportState
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

MemoryKind = Literal[
    "fact",
    "preference",
    "goal",
    "decision",
    "observation",
    "instruction",
    "relationship",
    "context",
    "commitment",
]


class ExtractedMemory(BaseModel):
    """One atomic piece of memory extracted from a user message."""

    kind: MemoryKind = Field(
        default="fact",
        description="The semantic category of this memory. Use 'preference' for "
        "user likes/dislikes, 'fact' for objective claims, 'commitment' for "
        "promises, 'goal' for stated aims.",
    )
    title: str = Field(
        default="",
        description="Short title, under 80 characters. Leave blank to auto-derive.",
    )
    content: str = Field(
        description=(
            "One specific fact about the user. Each entry covers exactly one fact "
            "and one fact only. Do not combine multiple facts into this field."
        )
    )
    confidence: float = Field(
        default=0.9, ge=0.0, le=1.0, description="0.95+ for explicit statements."
    )
    tags: list[str] = Field(
        default_factory=list, description="Lowercase tags for categorization."
    )

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: dict) -> dict:
        """Accept 'value' as an alias for 'content' (some models prefer it)."""
        if isinstance(data, dict):
            if "content" not in data and "value" in data:
                data["content"] = data.pop("value")
            if not data.get("title") and data.get("content"):
                data["title"] = str(data["content"])[:80]
        return data


class ExtractedMemories(BaseModel):
    """The structured-output response from the extractor LLM."""

    memories: list[ExtractedMemory] = Field(
        default_factory=list,
        description=(
            "ALL distinct facts found in the message, one entry per fact. "
            "A message with 4 facts MUST produce 4 separate entries. "
            "Never merge multiple facts into one entry. "
            "Empty list only for pure greetings or small talk with zero facts."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _unwrap_bare_list(cls, data):
        """Accept a bare list [{...}, ...] as well as the canonical {memories:[...]}."""
        if isinstance(data, list):
            return {"memories": data}
        return data


_VALID_KINDS = {
    "fact",
    "preference",
    "instruction",
    "commitment",
    "goal",
    "observation",
    "relationship",
    "context",
    "decision",
}


def _parse_memories_response(response) -> ExtractedMemories:
    """Parse LLM output into ExtractedMemories using a line-based format.

    Free-tier OpenRouter models (e.g. openai/gpt-oss-120b:free) do not reliably
    support function calling and frequently produce malformed JSON when asked
    for structured arrays. A single bad character collapses the entire extraction
    to zero or one item.

    We sidestep the problem entirely by asking the model to emit one fact per
    line as ``KIND::CONTENT``. Each line is parsed independently, so a malformed
    line costs at most one memory instead of all of them. JSON fallback is
    retained for backwards compatibility if the model still emits JSON.
    """
    # Unwrap AIMessage -> raw text
    text = response.content if hasattr(response, "content") else str(response)
    if isinstance(text, list):
        text = " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in text
        )

    # Raw model output can contain user-sensitive content (emails, health
    # facts, contact preferences). Log at DEBUG so it's available when a
    # developer opts in but not emitted by default to INFO log sinks.
    logger.info("_parse_memories_response: model returned %d chars", len(text))
    logger.debug(
        "_parse_memories_response: raw model output suppressed (len=%d)",
        len(text),
    )

    # Strip markdown code fences and numbered list prefixes
    text = re.sub(r"```(?:json|text)?\s*", "", text).strip("`").strip()

    # Primary path: line-based KIND::CONTENT format
    memories = _parse_line_format(text)
    if memories:
        logger.info(
            "_parse_memories_response: parsed %d memories via line format",
            len(memories),
        )
        return ExtractedMemories(memories=memories)

    # Fallback: JSON parsing (models that ignored the line-format instruction)
    text_for_json = re.sub(r"(?m)^\s*\d+\.\s*", "", text)
    for candidate in _json_candidates(text_for_json):
        result = _try_load_memories(candidate)
        if result is not None and result.memories:
            logger.info(
                "_parse_memories_response: parsed %d memories via JSON fallback",
                len(result.memories),
            )
            return result

    logger.warning(
        "_parse_memories_response: extracted ZERO memories from model output"
    )
    return ExtractedMemories(memories=[])


def _parse_line_format(text: str) -> list[ExtractedMemory]:
    """Parse ``KIND::CONTENT`` lines into ExtractedMemory objects.

    Lines without ``::`` are skipped. Lines with an unknown KIND fall back to
    ``fact``. Empty content lines are dropped.
    """
    memories: list[ExtractedMemory] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Skip empty lines and obvious decorations
        if not line or line.startswith(("#", "//", "---", "===")):
            continue
        # Strip optional list markers
        line = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line)
        if "::" not in line:
            continue
        kind_raw, _, content = line.partition("::")
        content = content.strip().strip(",").strip('"').strip("'")
        if not content:
            continue
        kind = kind_raw.strip().lower()
        if kind not in _VALID_KINDS:
            kind = "fact"
        title = content[:80]
        try:
            memories.append(ExtractedMemory(kind=kind, content=content, title=title))
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("_parse_line_format: skipping malformed line %r: %s", line, e)
    return memories


def _json_candidates(text: str) -> list[str]:
    """Return a list of JSON string candidates to try, most specific first."""
    candidates = [text]
    # Largest JSON array in the text
    m = re.search(r"\[[\s\S]*\]", text, re.DOTALL)
    if m:
        candidates.append(m.group())
    # Largest JSON object in the text
    m2 = re.search(r"\{[\s\S]*\}", text, re.DOTALL)
    if m2:
        candidates.append(m2.group())
    return candidates


def _try_load_memories(text: str) -> ExtractedMemories | None:
    """Try to parse *text* as JSON and coerce into ExtractedMemories. Returns None on failure."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(data, list):
        return ExtractedMemories.model_validate({"memories": data})
    if isinstance(data, dict):
        # Might be {"memories": [...]} or a single memory object
        if "memories" in data:
            return ExtractedMemories.model_validate(data)
        # Single memory dict accidentally returned at top level
        if "content" in data or "value" in data:
            return ExtractedMemories.model_validate({"memories": [data]})
    return None


def _make_llm(temperature: float = 0.2, max_tokens: int | None = None) -> ChatOpenAI:
    """Build a ChatOpenAI instance routed through OpenRouter.

    Requires ``OPENROUTER_API_KEY``. Override the model via ``LANGGRAPH_LLM``.
    Called twice inside build_support_graph: once at temperature=0.2 for the
    conversational responder, once at temperature=0.1 for the extractor.
    Two separate instances are used because chaining .bind(temperature=0) onto
    an existing ChatOpenAI before .with_structured_output() produces a
    RunnableBinding that collapses to single-item output on some OpenRouter models.

    ``max_tokens`` is needed for reasoning models like ``tencent/hy3-preview``
    that consume tokens for an internal thinking phase before emitting visible
    output. Without an explicit cap, OpenRouter reserves the model's full
    context budget (65k+) and rejects the call when the API key's credit
    limit can't cover that reservation.
    """
    # Default: openai/gpt-oss-120b:free - fastest free model on OpenRouter
    # for KIND::CONTENT line extraction. Benchmarked at ~3s for 5 facts.
    # Free, no credits required. Subject to OpenRouter's shared free-tier
    # rate limits; the graph's RetryPolicy handles 429s with 32s backoff.
    # See .env.example for paid alternatives (tencent/hy3-preview etc).
    model = os.environ.get("LLM_MODEL", os.environ.get("LANGGRAPH_LLM", "gpt-4o-mini"))
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY or OPENROUTER_API_KEY is not set. Copy .env.example to .env and add "
            "your API key."
        )
    kwargs: dict = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": os.environ.get(
            "OPENAI_API_BASE",
            "https://openrouter.ai/api/v1"
            if os.environ.get("OPENROUTER_API_KEY")
            else None,
        )
        or None,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


# max_tokens cap on every LLM call. Reasoning models like tencent/hy3-preview
# consume tokens for an internal thinking phase before emitting visible output,
# and OpenRouter's pre-flight credit reservation rejects calls whose
# max_tokens exceeds the remaining key budget. 7000 is the sweet spot:
#   * enough thinking budget for tencent/hy3-preview to emit visible output
#   * fits inside a $5+ OpenRouter key credit limit across multiple turns
#   * non-reasoning models (gpt-oss-20b:free etc) use much less than this
# If you see "extracted ZERO memories" with an empty model output: bump this,
# OR increase your OpenRouter key's credit limit, OR switch to a free model.
_DEFAULT_MAX_TOKENS = 7000


def _default_llm() -> ChatOpenAI:
    """Conversational LLM at temperature=0.2 (natural replies)."""
    return _make_llm(temperature=0.2, max_tokens=_DEFAULT_MAX_TOKENS)


def _user_id_from_config(config) -> str:
    """Extract user_id from LangGraph runnable config; raise if missing.

    Memories are namespaced by user_id, so silently defaulting to a shared
    sentinel like "anonymous" would merge unrelated users' memories together
    and leak recalled context across sessions. The demo invokers always
    supply user_id explicitly via ``config={"configurable": {"user_id": ...}}``.
    """
    if not config:
        raise ValueError(
            "graph invocation is missing config; pass "
            'config={"configurable": {"thread_id": "...", "user_id": "..."}}'
        )
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        raise ValueError(
            "graph invocation is missing configurable.user_id; "
            "memories are user-scoped and cannot fall back to a shared default"
        )
    return user_id


def build_support_graph(
    api_key: str,
    llm: ChatOpenAI | None = None,
):
    """Compile a customer-support graph with MemantoStore + InMemorySaver.

    Args:
        api_key: Moorcheh API key to provision Memanto clients.
        llm: Optional override for the underlying chat model.
    """
    chat = llm or _default_llm()
    # Separate extractor at temperature=0.1 (not 0) for reliable multi-item output.
    # temperature=0 causes greedy single-token selection and the model stops after
    # emitting the first (highest-confidence) memory item instead of all of them.
    # 0.1 adds just enough entropy to traverse the full list without sacrificing
    # accuracy. Responder stays at temperature=0.2 for natural replies.
    # We instantiate a fresh ChatOpenAI (not chat.bind()) because bind() +
    # with_structured_output() collapses to single-item output on some models.
    extractor_llm = (
        _make_llm(temperature=0.1, max_tokens=_DEFAULT_MAX_TOKENS)
        if llm is None
        else llm
    )
    # Do NOT use with_structured_output here. Free-tier OpenRouter models
    # (e.g. openai/gpt-oss-120b:free) do not reliably support function/tool
    # calling and return plain text instead of structured tool arguments.
    # with_structured_output() routes through Pydantic's model_validate_json()
    # which raises json_invalid on any non-standard format the model emits.
    # Instead we pipe the raw AIMessage through _parse_memories_response which
    # handles numbered lists, bare arrays, wrapped objects, and code fences.
    extractor = extractor_llm | RunnableLambda(_parse_memories_response)
    # MemantoStore is created here and passed to compile(store=...) below.
    # LangGraph then injects it into any node that declares `*, store: BaseStore`.
    store = MemantoStore(api_key=api_key)

    async def recall_context(state: SupportState, config, *, store: BaseStore) -> dict:
        """Pull cross-thread memories for this user, scoped by user_id."""
        user_id = _user_id_from_config(config)
        last_user_msg = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        query = last_user_msg.content if last_user_msg else "*"

        memories = await store.asearch(
            (user_id, "memories"),
            query=str(query),
            limit=8,
        )

        if not memories:
            logger.info("recall_context: no prior memories for user=%s", user_id)
            return {}

        formatted = "\n".join(
            f"- [{m.value.get('kind', 'fact')}] "
            f"{m.value.get('title') or m.value.get('content', '')}: "
            f"{m.value.get('content', '')}"
            for m in memories
        )
        logger.info(
            "recall_context: loaded %d memories for user=%s", len(memories), user_id
        )
        context_msg = SystemMessage(
            content=(
                "Known facts about the current user (recalled from long-term memory, "
                "not from this thread's history):\n" + formatted
            )
        )
        return {"messages": [context_msg]}

    async def respond(state: SupportState, config) -> dict:
        """Generate the assistant's reply with the recalled context in scope."""
        system_prefix = SystemMessage(
            content=(
                "You are a helpful customer-support assistant. "
                "Long-term facts about the current user may appear as a system "
                "message below this one; respect those preferences. Be concise."
            )
        )
        reply = await chat.ainvoke([system_prefix] + state["messages"])
        return {"messages": [reply]}

    async def extract_and_store(
        state: SupportState, config, *, store: BaseStore
    ) -> dict:
        """Pull atomic preferences/facts from the latest user turn and persist them."""
        user_id = _user_id_from_config(config)

        last_user_msg = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if not last_user_msg:
            return {}

        try:
            extracted: ExtractedMemories = await extractor.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "You are a fact extractor. Extract EVERY distinct fact "
                            "from the user message and output them ONE PER LINE.\n\n"
                            "OUTPUT FORMAT: each line is exactly\n"
                            "    KIND::CONTENT\n"
                            "where KIND is one of: fact, preference, instruction, "
                            "commitment, goal, observation, relationship, context, "
                            "decision\n\n"
                            "RULES:\n"
                            "- ONE fact per line. A message with 4 facts produces "
                            "4 lines. A message with 1 fact produces 1 line.\n"
                            "- NEVER combine multiple facts on the same line.\n"
                            "- NO JSON, NO markdown, NO numbering, NO extra prose. "
                            "Just KIND::CONTENT lines.\n"
                            "- If the message is a pure greeting with zero facts, "
                            "output nothing at all.\n\n"
                            "EXAMPLE\n"
                            "Input: I'm Bob, allergic to peanuts (epi-pen), email "
                            "bob@example.com, never call.\n"
                            "Output:\n"
                            "fact::User's name is Bob\n"
                            "fact::User is allergic to peanuts (requires epi-pen)\n"
                            "fact::User's email is bob@example.com\n"
                            "instruction::Never contact user by phone"
                        )
                    ),
                    HumanMessage(content=str(last_user_msg.content)),
                ]
            )
        except openai.RateLimitError:
            raise  # let RetryPolicy handle backoff and retry
        except Exception as e:
            logger.warning("extract_and_store: extraction failed: %s", e)
            return {}

        for mem in extracted.memories:
            await store.aput(
                (user_id, "memories"),
                str(uuid.uuid4()),
                {
                    "kind": mem.kind,
                    "title": mem.title,
                    "content": mem.content,
                    "confidence": mem.confidence,
                    "tags": mem.tags,
                },
            )
        if extracted.memories:
            logger.info(
                "extract_and_store: persisted %d memories for user=%s",
                len(extracted.memories),
                user_id,
            )
        return {}

    # Retry LLM nodes on 429 rate-limit errors from OpenRouter's free tier.
    # initial_interval=32s is just above OpenRouter's "retry after 30s" window.
    _rate_limit_retry = RetryPolicy(
        initial_interval=32.0,
        backoff_factor=1.5,
        max_interval=120.0,
        max_attempts=5,
        retry_on=openai.RateLimitError,
    )

    builder = StateGraph(SupportState)
    builder.add_node("recall_context", recall_context)
    builder.add_node("respond", respond, retry_policy=_rate_limit_retry)
    builder.add_node(
        "extract_and_store", extract_and_store, retry_policy=_rate_limit_retry
    )
    builder.add_edge(START, "recall_context")
    builder.add_edge("recall_context", "respond")
    builder.add_edge("respond", "extract_and_store")
    builder.add_edge("extract_and_store", END)

    return builder.compile(
        checkpointer=InMemorySaver(),
        store=store,
    )


def latest_assistant_text(messages: list) -> str:
    """Return the most recent AIMessage content as a plain string."""
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            content = m.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                ]
                return "".join(parts)
    return "(no assistant reply)"
