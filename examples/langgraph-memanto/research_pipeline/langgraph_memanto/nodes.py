"""
LangGraph node definitions for the Research + Writer pipeline.

Each node is a function (state_in, state_out) that gets compiled into
the LangGraph pipeline via langgraph_memanto.graph.build_graph().
"""

from __future__ import annotations

import os
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from langgraph_memanto import create_memanto_tools
from memanto.cli.client.sdk_client import SdkClient

client = SdkClient(api_key=os.environ.get("MOORCHEH_API_KEY", ""))
tools = create_memanto_tools(client, "research_agent")
_memanto_remember = next(t for t in tools if t.name == "memanto_remember")
memanto_recall = next(t for t in tools if t.name == "memanto_recall")
memanto_answer = next(t for t in tools if t.name == "memanto_answer")

load_dotenv()

MOORCHEH_API_KEY = os.getenv("MOORCHEH_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


def _get_moorcheh_api_key() -> str:
    """Return the configured Moorcheh API key or fail with setup guidance."""
    if not MOORCHEH_API_KEY:
        raise RuntimeError(
            "MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
        )
    return MOORCHEH_API_KEY


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_llm():
    """Build a flexible ChatOpenAI model."""
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "openai/gpt-4o-mini"),
        api_key=os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or OPENROUTER_API_KEY,
        base_url=os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1"),
        temperature=0.7,
    )


# ---------------------------------------------------------------------------
# LangChain Tool wrapper factory (enables actual tool calling by the LLM)
# ---------------------------------------------------------------------------


def _build_memanto_remember_tool(agent_id: str):
    """Build a LangChain-compatible tool bound to the current Memanto namespace."""

    @tool("memanto_remember")
    def memanto_remember_tool(
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> str:
        """Store a structured memory in Memanto for later cross-session recall."""
        from memanto.cli.client.sdk_client import SdkClient

        client = SdkClient(api_key=_get_moorcheh_api_key())
        try:
            res = client.remember(
                agent_id=agent_id,
                content=(content or "")[:500],
                memory_type=memory_type or "observation",
                title=(title or "")[:100],
                tags=tags or [],
                source="langgraph-research",
                confidence=float(confidence),
            )
            return f"Successfully stored memory: {res.get('memory_id')}"
        except Exception as e:
            return f"Error storing memory: {e}"

    return memanto_remember_tool


# ---------------------------------------------------------------------------
# Research Agent nodes
# ---------------------------------------------------------------------------


def research_agent_factory(tools: list):
    """
    Returns a node function for the Research Agent.
    """
    memanto_remember = next((t for t in tools if t.name == "memanto_remember"), None)
    tools_to_bind = [memanto_remember] if memanto_remember else tools
    llm = _get_llm()
    llm_with_tools = llm.bind_tools(tools_to_bind)

    def research_agent(state: dict[str, Any]) -> dict[str, Any]:
        topic = state.get("research_topic", "")
        system_prompt = (
            f"You are a Senior Market Research Analyst specialized in '{topic}'.\n"
            f"Your job is to research this topic thoroughly and store every significant "
            f"finding as a structured Memanto memory using the memanto_remember tool.\n\n"
            f"Research approach:\n"
            f"1. Think about the key aspects of '{topic}'\n"
            f"2. Use the memanto_remember tool to store at least 3 findings\n"
            f"3. Each memory should be atomic: one fact/observation per memory\n\n"
            f"Memory types: fact, observation, decision, learning, event\n"
            f"Confidence: 1.0 for verified facts, 0.7-0.9 for observations\n"
            f"Tags: relevant keywords like ['AI', 'market', 'trends']\n\n"
            f"After storing memories, summarize what you found in 2-3 sentences."
        )

        messages = [{"role": "system", "content": system_prompt}] + state.get(
            "messages", []
        )
        response = llm_with_tools.invoke(messages)

        return {"messages": [response]}

    return research_agent


def writer_agent_factory(tools: list):
    """
    Returns a node function for the Writer Agent.
    """
    # Exclude remember so writer only recalls/answers
    tools_to_bind = [t for t in tools if t.name in ("memanto_recall", "memanto_answer")]
    llm = _get_llm()
    llm_with_tools = llm.bind_tools(tools_to_bind)

    def writer_agent(state: dict[str, Any]) -> dict[str, Any]:
        topic = state.get("research_topic", "")
        synthesis_prompt = (
            f"You are a Technical Briefing Writer.\n"
            f"Topic: {topic}\n\n"
            f"Your goal is to write a clear, data-driven executive briefing on '{topic}'.\n"
            f"First, use the 'memanto_recall' and 'memanto_answer' tools to retrieve the research findings that were just stored.\n"
            f"Then, using ONLY that retrieved information, write the executive briefing. "
            f"Do not fabricate data. Cite sources based on the memories."
        )

        # Inject the system prompt and append the tool calls that the writer_agent might have already done in this loop
        # We need to filter out previous messages from the research agent to avoid confusing the writer,
        # OR just append a system message instructing the writer to begin its job.

        writer_messages = []
        for msg in state.get("messages", []):
            if hasattr(msg, "name") and msg.name in (
                "memanto_recall",
                "memanto_answer",
            ):
                writer_messages.append(msg)
            elif hasattr(msg, "tool_calls") and any(
                tc.get("name") in ("memanto_recall", "memanto_answer")
                for tc in msg.tool_calls
            ):
                writer_messages.append(msg)

        messages = [{"role": "system", "content": synthesis_prompt}] + writer_messages
        response = llm_with_tools.invoke(messages)

        return {"messages": [response]}

    return writer_agent


def should_continue(state: dict[str, Any]) -> Literal["research", "writer", "end"]:
    """
    Routing logic: research → writer → end.
    """
    messages = state.get("messages", [])
    if not messages:
        return "research"
    last = messages[-1]

    # Check if last message is from the assistant (either object or dict)
    is_assistant = False
    if hasattr(last, "type") and last.type == "ai":
        is_assistant = True
    elif isinstance(last, dict) and last.get("role") == "assistant":
        is_assistant = True

    if is_assistant:
        return "writer"
    return "end"
