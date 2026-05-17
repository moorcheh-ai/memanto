"""
LangGraph Research Assistant with Memanto Memory.

This module defines a LangGraph workflow for a research assistant that uses
Memanto as its persistent, queryable memory layer:

    1.  Check existing knowledge via ``recall()``
    2.  If knowledge is sufficient → answer the question via ``answer()``
    3.  If knowledge is missing → simulate research, ``remember()`` findings
    4.  Routing logic decides whether to research or answer

Graph structure (StateGraph)::

                     ┌──────────┐
                     │   START   │
                     └────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ check_mem │
                    │   ory     │
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  router   │
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
        ┌─────▼─────┐    │    ┌──────▼──────┐
        │ research_ │    │    │ answer_ques │
        │   topic   │    │    │    tion      │
        └─────┬─────┘    │    └──────┬──────┘
              │           │           │
        ┌─────▼─────┐    │           │
        │ store_fin │    │           │
        │   dings   │    │           │
        └─────┬─────┘    │           │
              │           │           │
        ┌─────▼─────┐    │           │
        │ update_kn │    │           │
        │  owledge  │    │           │
        └─────┬─────┘    │           │
              │           │           │
              └───┬───────┘           │
                  │                   │
                  └───────┬───────────┘
                          │
                    ┌─────▼─────┐
                    │    END     │
                    └───────────┘
"""

import logging
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI

from memory_client import MemantoMemory

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("research_assistant")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """
    Shared state carried through each node invocation.

    Attributes:
        messages: Conversation history (LangGraph message list).
        topic: The research topic or question being investigated.
        memory_hits: Number of relevant memories found by ``recall()``.
        knowledge_sufficient: Whether existing memories are enough to answer.
        research_findings: Raw text generated during the research phase.
        final_answer: Final answer produced by the workflow.
    """

    messages: Annotated[list, add_messages]
    topic: str
    memory_hits: int
    knowledge_sufficient: bool
    research_findings: str | None
    final_answer: str | None


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

# Use environment variable OPENROUTER_API_KEY or set directly.
# For local dev, create a .env file (see .env.example).
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",  # OpenRouter model identifier
    openai_api_key="…",  # populated below after imports
    openai_api_base="https://openrouter.ai/api/v1",
)

# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def check_memory(state: AgentState, memory: MemantoMemory) -> dict[str, Any]:
    """
    Query Memanto's ``recall()`` for existing memories about the current topic.

    Returns:
        Partial state update with ``memory_hits`` and
        ``knowledge_sufficient``.
    """
    topic = state["topic"]
    logger.info("Checking memory for: '%s'", topic)

    results = memory.recall(query=topic, limit=5)

    # If we have at least 2 relevant memories, consider knowledge sufficient
    hits = len(results)
    sufficient = hits >= 2

    logger.info("Memory recall returned %d hit(s) — sufficient=%s", hits, sufficient)

    if results:
        for r in results:
            logger.info("  → [%.2f] %s", r.get("confidence", 0), r.get("title", "?"))

    return {
        "memory_hits": hits,
        "knowledge_sufficient": sufficient,
    }


def router(state: AgentState) -> Literal["research_topic", "answer_question"]:
    """
    Decide next step based on memory check.

    If existing knowledge is sufficient, go directly to answering.
    Otherwise, trigger research.
    """
    if state.get("knowledge_sufficient", False):
        logger.info("Router: knowledge sufficient → answer_question")
        return "answer_question"
    logger.info("Router: insufficient knowledge → research_topic")
    return "research_topic"


def research_topic(state: AgentState) -> dict[str, Any]:
    """
    Simulate research by asking the LLM to generate findings about the topic.

    In a production system you would call a web search API, scrape pages,
    or query a vector database here.
    """
    topic = state["topic"]
    logger.info("Researching topic: '%s'", topic)

    prompt = (
        f"You are a research assistant investigating: {topic}\n\n"
        f"Generate 3 key research findings with supporting details. "
        f"Be factual and cite concrete numbers or sources where possible."
    )

    response = llm.invoke(prompt)
    findings = response.content
    logger.info("Research complete (%d chars)", len(findings))

    return {"research_findings": findings}


def store_findings(state: AgentState, memory: MemantoMemory) -> dict[str, Any]:
    """
    Persist the research findings into Memanto via ``remember()``.

    Each finding is stored as a separate ``fact`` memory so it can be
    individually retrieved and confidence-scored later.
    """
    findings = state.get("research_findings", "")
    topic = state["topic"]
    logger.info("Storing findings in Memanto ...")

    # Split findings into paragraphs and store each as a memory
    paragraphs = [p.strip() for p in findings.split("\n\n") if p.strip()]
    memories_stored = 0

    for i, para in enumerate(paragraphs[:5]):  # cap at 5
        # Use first ~60 chars as title
        title = para[:60].replace("\n", " ").strip() + ("..." if len(para) > 60 else "")
        try:
            memory.remember(
                memory_type="fact",
                title=title,
                content=para,
                confidence=0.85,
                tags=[topic.lower().replace(" ", "-"), "research"],
            )
            memories_stored += 1
        except Exception as e:
            logger.warning("Failed to store memory %d: %s", i, e)

    logger.info("Stored %d memory/memories", memories_stored)
    return {}


def update_knowledge_flag(state: AgentState) -> dict[str, Any]:
    """
    After storing new findings, mark knowledge as sufficient so the
    router will go to ``answer_question`` on the next cycle.
    """
    logger.info("Knowledge flag updated to sufficient")
    return {"knowledge_sufficient": True}


def answer_question(state: AgentState, memory: MemantoMemory) -> dict[str, Any]:
    """
    Use Memanto's ``answer()`` method (RAG over stored memories) to
    generate a final answer for the user.
    """
    topic = state["topic"]
    logger.info("Answering question via Memanto answer() ...")
    logger.info("Current memory_hits=%d", state.get("memory_hits", 0))

    result = memory.answer(question=topic, limit=5)
    answer_text = result.get("answer", "No answer could be generated.")
    sources = result.get("sources", [])

    if sources:
        logger.info("Answer generated from %d source(s)", len(sources))
    else:
        logger.info("Answer generated (no explicit sources)")

    return {"final_answer": answer_text}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph(memory: MemantoMemory) -> StateGraph:
    """
    Build and compile the LangGraph state graph.

    Args:
        memory: Initialised MemantoMemory instance.

    Returns:
        Compiled ``StateGraph`` ready for ``invoke()``.
    """
    builder = StateGraph(AgentState)

    # ── Nodes ──────────────────────────────────────────────────────────
    builder.add_node("check_memory", lambda s: check_memory(s, memory))
    builder.add_node("research_topic", research_topic)
    builder.add_node("store_findings", lambda s: store_findings(s, memory))
    builder.add_node("update_knowledge", update_knowledge_flag)
    builder.add_node("answer_question", lambda s: answer_question(s, memory))

    # ── Edges ──────────────────────────────────────────────────────────
    builder.add_edge(START, "check_memory")
    builder.add_conditional_edges("check_memory", router)
    builder.add_edge("research_topic", "store_findings")
    builder.add_edge("store_findings", "update_knowledge")
    builder.add_edge("update_knowledge", "answer_question")
    builder.add_edge("answer_question", END)

    return builder.compile()
