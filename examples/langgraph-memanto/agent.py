"""
LangGraph agent with Memanto-powered long-term memory.

This agent has access to three custom tools wrapping Memanto's primitives:
  - remember(content, memory_type)  → stores a memory
  - recall(query)                   → searches memories
  - answer(question)                → grounded answer from memory

The agent's state is intentionally minimal — Memanto handles persistence
so the agent can forget across sessions and still recall "yesterday's" facts.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from memanto_client import MemantoClient, MemantoConfig

load_dotenv()

# ── Memanto client (shared by tools) ───────────────────────────────
_memanto: MemantoClient | None = None


def get_memanto() -> MemantoClient:
    global _memanto
    if _memanto is None:
        config = MemantoConfig(api_key=os.getenv("MOORCHEH_API_KEY", ""))
        _memanto = MemantoClient(config)
        _memanto.activate_session()
    return _memanto


# ── Tool definitions (wrapping Memanto primitives) ─────────────────


@tool
def remember_tool(content: str, memory_type: str = "fact") -> str:
    """Store a memory so the agent can recall it later — even in a new session.

    Memory types: instruction, fact, decision, goal, commitment, preference,
    relationship, context, event, learning, observation, artifact, error.

    Args:
        content: What to remember (e.g., "User prefers concise answers").
        memory_type: Semantic category for the memory.

    Returns:
        Confirmation message.
    """
    result = get_memanto().remember(content, memory_type=memory_type)
    return f"✅ Remembered ({memory_type}): {content}"


@tool
def recall_tool(query: str, top_k: int = 5) -> str:
    """Search the agent's long-term memory for information relevant to a query.

    Args:
        query: Natural language search query.
        top_k: How many memories to return (max 20).

    Returns:
        Formatted memory entries.
    """
    results = get_memanto().recall(query, top_k=top_k)
    if not results:
        return "No relevant memories found."

    lines = ["📚 Memories found:\n"]
    for i, r in enumerate(results, 1):
        content = r.get("content", r.get("text", ""))
        mem_type = r.get("type", "unknown")
        conf = r.get("confidence", "?")
        ts = r.get("created_at", r.get("timestamp", ""))[:19]
        lines.append(f"  [{i}] ({mem_type}, confidence: {conf}) {content}")
        lines.append(f"       stored: {ts}")
    return "\n".join(lines)


@tool
def answer_tool(question: str) -> str:
    """Ask a question and get a grounded answer generated from stored memories.

    Unlike recall_tool which returns raw memory entries, this generates a
    natural answer using the memories as context (built-in RAG).

    Args:
        question: The question to answer using memory context.

    Returns:
        A natural language answer.
    """
    answer = get_memanto().answer(question)
    return answer


# ── LangGraph agent setup ──────────────────────────────────────────

tools = [remember_tool, recall_tool, answer_tool]
tool_node = ToolNode(tools)

# Use a capable LLM — prefer gpt-4o-mini or any model with tool-calling
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0.3,
).bind_tools(tools)


AGENT_SYSTEM_PROMPT = """\
You are a helpful AI assistant with access to **Memanto**, a persistent long-term memory system.

You have three memory tools:
1. **remember** — Store important information users share about themselves.
2. **recall** — Search your memories for relevant context.
3. **answer** — Ask a grounded question about stored memories.

**Guidelines:**
- Always search memory first before answering personal questions.
- Store user preferences, facts, goals, and commitments proactively.
- Use memory types: `preference` for likes/dislikes, `fact` for personal info,
  `goal` for objectives, `decision` for choices made.
- When a user returns in a new session, recall their context automatically.
"""


def call_agent(state: MessagesState) -> dict[str, list[BaseMessage]]:
    """Invoke the LLM with system prompt and conversation history."""
    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]
    response = llm.invoke(messages)
    return {"messages": [response]}


def should_continue(state: MessagesState) -> Literal["tools", END]:
    """Route to tools if LLM called a tool, otherwise end."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


# ── Build the graph ────────────────────────────────────────────────

def build_agent() -> StateGraph:
    """Construct the LangGraph agent with Memanto memory tools."""
    workflow = StateGraph(MessagesState)

    workflow.add_node("agent", call_agent)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    return workflow


def run_agent(
    message: str,
    checkpointer: MemorySaver | None = None,
    thread_id: str = "default",
) -> list[BaseMessage]:
    """Run the agent on a single user message.

    Args:
        message: User's input message.
        checkpointer: LangGraph MemorySaver for in-session state (NOT long-term).
        thread_id: Thread ID for session tracking.

    Returns:
        All messages produced in this turn.
    """
    graph = build_agent().compile(checkpointer=checkpointer or MemorySaver())
    config = {"configurable": {"thread_id": thread_id}}

    output = graph.invoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )
    return output["messages"]


def cleanup() -> None:
    """Deactivate the Memanto session."""
    global _memanto
    if _memanto:
        try:
            _memanto.deactivate_session()
        except Exception:
            pass
        _memanto.close()
        _memanto = None


# ── Quick test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🧠 LangGraph + Memanto Agent\n")
    print("Type 'quit' to exit.\n")

    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver()
    thread = "demo-session"

    while True:
        user_input = input("You: ")
        if user_input.lower() in ("quit", "exit", "q"):
            break

        messages = run_agent(user_input, checkpointer=checkpointer, thread_id=thread)
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.content:
                print(f"\nAgent: {msg.content}\n")

    cleanup()
