"""
Memanto + LangGraph: Cross-Session Memory Agent

A LangGraph agent that uses Memanto as a persistent long-term memory layer,
enabling cross-session recall, typed semantic memory, and grounded RAG answers.

Key Features:
  - Remembers user preferences/facts across completely separate graph sessions
  - Uses Memanto's three primitives: remember, recall, answer
  - Demonstrates conflict detection via versioned memory updates
  - Clean separation: LangGraph state for conversation, Memanto for long-term memory

Architecture:
  ┌─────────────┐
  │  User Input │
  └──────┬──────┘
         ▼
  ┌──────────────────┐
  │  Should I recall │──No──▶┌──────────────┐
  │  past memories?  │      │  Process +   │
  └──────┬───────────┘      │  Remember    │
         │ Yes              └──────┬───────┘
         ▼                         │
  ┌─────────────┐                  │
  │ Recall from │                  │
  │  Memanto    │                  │
  └──────┬──────┘                  │
         │                         │
         └──────────┬──────────────┘
                    ▼
           ┌────────────────┐
           │  Generate      │
           │  Response      │
           └────────────────┘

Usage:
    export MOORCHEH_API_KEY="***"
    python agent.py
"""

import json
import logging
import os
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph_memanto import create_memanto_tools

from memanto.cli.client.sdk_client import SdkClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# The agent name — used to namespace memories in Memanto
AGENT_NAME = "memanto-customer-support"

# System prompt that instructs the LLM when and how to use Memanto tools
SYSTEM_PROMPT = f"""You are a helpful customer support agent named {AGENT_NAME}.

You have access to three Memanto memory tools that allow you to remember
information across completely separate conversations:

## When to use each tool:

### memanto_recall(query, memory_type=None, limit=5)
Call this at the START of EVERY conversation. Look up anything relevant about
the user you're talking to — their name, preferences, past issues, etc.
Example: "What do I know about this user?" or "What are the user's preferences?"

### memanto_remember(content, memory_type="observation")
Call this whenever you learn something important:
- The user's name → store as "fact"
- The user's preferences → store as "preference"
- A decision made → store as "decision"
- A goal mentioned → store as "goal"

### memanto_answer(query)
Call this when the user asks something that requires synthesis across multiple
pieces of stored information. This uses RAG to produce a grounded answer.

## Memory Types Available
instruction, fact, decision, goal, commitment, preference, relationship,
context, event, learning, observation, artifact, error

## Important Rules
1. ALWAYS start a new conversation by calling memanto_recall to load context
2. ALWAYS remember important user information
3. If you detect a contradiction with stored memories, note it and update
4. Be helpful, concise, and proactive about using stored knowledge
"""


# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph State
# ═══════════════════════════════════════════════════════════════════════════════


class AgentState(MessagesState):
    """Extended state with cross-session memory context."""

    memory_context: str = ""
    """Pre-formatted context string from Memanto recall, injected at start."""


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Setup
# ═══════════════════════════════════════════════════════════════════════════════


_client = None
_tools = None


def get_memanto_client_and_tools():
    global _client, _tools
    if _client is None:
        _client = SdkClient(api_key=os.environ.get("MOORCHEH_API_KEY", ""))
        _tools = create_memanto_tools(_client, AGENT_NAME)
    return _client, _tools


def create_llm():
    """Create the LLM with Memanto tools bound."""
    llm = ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "openai/gpt-4o-mini"),
        temperature=0,
        api_key=os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1"),
    )
    _, tools = get_memanto_client_and_tools()
    return llm.bind_tools(tools)


# ═══════════════════════════════════════════════════════════════════════════════
# Graph Nodes
# ═══════════════════════════════════════════════════════════════════════════════


def recall_memories(state: AgentState) -> AgentState:
    """Node: Recall relevant memories from Memanto at the start of a conversation.

    This is the key cross-session recall step. We search Memanto for any
    information about the user based on the current input, and inject the
    results into the state so the LLM has context from past conversations.
    """
    last_message = state["messages"][-1].content if state["messages"] else ""
    if not last_message:
        return state

    # Construct a search query from the user's message
    query = f"What do I know about the user based on: {last_message[:200]}"
    _, tools = get_memanto_client_and_tools()
    memanto_recall = next(t for t in tools if t.name == "memanto_recall")
    result = memanto_recall.invoke({"query": query, "limit": 5})

    state["memory_context"] = result
    logger.info(f"\n📚 MEMANTO RECALL:\n{result}\n")
    return state


def agent_node(state: AgentState) -> AgentState:
    """Node: The main LLM agent that processes input and uses tools."""
    messages = state["messages"]
    llm = create_llm()

    # Inject memory context from recall (if available)
    if (
        state.get("memory_context")
        and "No relevant memories" not in state["memory_context"]
    ):
        context_message = SystemMessage(
            content=f"Here is what I remember from past conversations:\n{state['memory_context']}"
        )
        messages = [context_message] + messages

    # Prepend system prompt
    full_messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    response = llm.invoke(full_messages)
    return AgentState(messages=[response])


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """Router: Check if the agent called any tools, and if so, route to the tool node."""
    last_message = state["messages"][-1]
    if hasattr(
        last_message, "additional_kwargs"
    ) and last_message.additional_kwargs.get("tool_calls"):
        return "tools"
    return "end"


def tool_node(state: AgentState) -> AgentState:
    """Node: Execute any tool calls made by the agent."""
    last_message = state["messages"][-1]
    tool_calls = (last_message.additional_kwargs or {}).get("tool_calls", [])

    new_messages = []
    _, tools = get_memanto_client_and_tools()

    for tc in tool_calls:
        tool_name = tc["function"]["name"]
        arguments = json.loads(tc["function"]["arguments"])
        tool_call_id = tc["id"]

        logger.info(f"\n🔧 Calling Memanto tool: {tool_name}({arguments})")

        for tool in tools:
            if tool.name == tool_name:
                result = tool.invoke(arguments)
                logger.info(f"   Result: {str(result)[:200]}")
                new_messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call_id)
                )
                break

    return {"messages": new_messages}


# ═══════════════════════════════════════════════════════════════════════════════
# Build the Graph
# ═══════════════════════════════════════════════════════════════════════════════


def build_agent() -> StateGraph:
    """Build and compile the LangGraph agent with Memanto integration."""

    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("recall", recall_memories)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    # Add edges
    builder.add_edge(START, "recall")  # Always recall first
    builder.add_edge("recall", "agent")  # Then run the agent
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")  # After tools, go back to agent

    # Compile with in-memory checkpointing for thread-level state
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive Demo CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    """Run the interactive demo.

    Each conversation thread demonstrates independent cross-session recall
    from Memanto's global memory store.
    """
    import uuid

    agent = build_agent()
    print("=" * 60)
    print(f"  {AGENT_NAME} — Memanto-Powered LangGraph Agent")
    print("  Type 'quit' to exit, 'new' to start a new session")
    print("=" * 60)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n📌 Session thread: {thread_id[:8]}...\n")

    while True:
        user_input = input("\n👤 You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if user_input.lower() == "new":
            thread_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": thread_id}}
            print(f"\n📌 New session thread: {thread_id[:8]}...\n")
            continue

        # Run the agent
        for event in agent.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config,
            stream_mode="values",
        ):
            last_msg = event["messages"][-1]
            if isinstance(last_msg, AIMessage) and last_msg.content:
                print(f"\n🤖 Agent: {last_msg.content}")


if __name__ == "__main__":
    main()
