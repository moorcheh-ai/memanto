"""
LangGraph + Memanto: Cross-Session Persistent Memory Demo
=========================================================

This example demonstrates a LangGraph workflow that uses Memanto
as its persistent memory layer.  The key feature is **cross-session
recall**: information stored in one session is available in a
completely new session — even after the first program exits.

Scenario
--------
A customer-support agent that interacts with a user across
multiple sessions.  In Session 1 the user states preferences;
in Session 2 the agent recalls them automatically without
being told again.

How to run
----------
    export MOORCHEH_API_KEY="sk-..."
    python run_cross_session.py

The script exits 0 on success.  It requires no interactive input.
"""

import json
import os
import sys
import time
import textwrap
from typing import Any, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, Annotated


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """State passed between graph nodes."""
    messages: Annotated[list, add_messages]
    memanto_context: str  # Context loaded from Memanto at the start of a session
    session_phase: str    # "startup", "processing", "shutdown"


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def build_graph(tools: dict) -> StateGraph:
    """Construct and return a compiled LangGraph StateGraph.

    Parameters
    ----------
    tools : dict
        Dict with keys ``remember``, ``recall``, ``answer`` — the output
        of ``create_memanto_tools()``.
    """

    # ---- Node: load session context from Memanto ---------------------------

    def load_context(state: AgentState) -> dict:
        """At session start, recall any existing memories."""
        recall_tool = tools["recall"]
        result = recall_tool.invoke(
            {"query": "What does the agent already know about this user?"}
        )
        data = json.loads(result)
        if data.get("status") == "success" and data.get("count", 0) > 0:
            memories = data["memories"]
            lines = []
            for m in memories:
                lines.append(
                    f"  [{m['type']}, conf={m['confidence']}] "
                    f"{m['title']}: {m['content']}"
                )
            context = f"Existing memories for this user:\n" + "\n".join(lines)
        else:
            context = "No existing memories found. This appears to be a new user."
        return {"memanto_context": context, "session_phase": "processing"}

    # ---- Node: demonstrate recall of specific facts ------------------------

    def demonstrate_recall(state: AgentState) -> dict:
        """Demonstrate recalling specific memories."""
        recall_tool = tools["recall"]

        # 1. Recall user preferences
        pref_result = recall_tool.invoke(
            {"query": "User preferences and settings"}
        )
        # 2. Recall any decisions made
        decision_result = recall_tool.invoke(
            {"query": "What decisions has the user made?"}
        )

        combined = f"[RECALL RESULT]\n"
        combined += f"--- Preferences ---\n{pref_result}\n\n"
        combined += f"--- Decisions ---\n{decision_result}\n"

        return {"messages": [("assistant", combined)]}

    # ---- Node: store new information ---------------------------------------

    def store_memories(state: AgentState) -> dict:
        """Store sample memories that will persist across sessions."""
        remember_tool = tools["remember"]

        memories_to_store = [
            {
                "content": "The user prefers dark mode for all interfaces.",
                "memory_type": "preference",
                "title": "Dark mode preference",
            },
            {
                "content": "The user's timezone is Asia/Shanghai (UTC+8).",
                "memory_type": "fact",
                "title": "Timezone",
            },
            {
                "content": "The user decided to use Memanto as their memory backend for LangGraph.",
                "memory_type": "decision",
                "title": "Memory backend decision",
            },
        ]

        results = []
        for mem in memories_to_store:
            r = remember_tool.invoke({"input": json.dumps(mem)})
            results.append(json.loads(r))

        status_line = f"Stored {len(memories_to_store)} memories: "
        status_line += ", ".join(
            f"{mem['memory_type']} ({r.get('status', '?')})"
            for mem, r in zip(memories_to_store, results)
        )
        return {"messages": [("assistant", status_line)]}

    # ---- Node: answer from memory ------------------------------------------

    def answer_question(state: AgentState) -> dict:
        """Use Memanto's ``answer`` (RAG) to answer a question from memory."""
        answer_tool = tools["answer"]
        question = "What do I know about my user, and how should I interact with them?"
        result = answer_tool.invoke({"input": question})
        return {"messages": [("assistant", f"[ANSWER]\n{result}")]}

    # ---- Node: session summary ---------------------------------------------

    def summarize(state: AgentState) -> dict:
        """Provide a final summary of what was accomplished in this session."""
        context = state.get("memanto_context", "No context")
        summary = (
            f"## Session Summary\n\n"
            f"**Startup context loaded from Memanto:**\n{context}\n\n"
            f"**Session complete.** All memories are persisted in Memanto "
            f"and will be available in future sessions.\n"
            f"To verify cross-session recall, run this script again — "
            f"the second run will load memories stored by the first run."
        )
        return {
            "messages": [("assistant", summary)],
            "session_phase": "shutdown",
        }

    # ---- Build graph -------------------------------------------------------

    builder = StateGraph(AgentState)

    builder.add_node("load_context", load_context)
    builder.add_node("demonstrate_recall", demonstrate_recall)
    builder.add_node("store_memories", store_memories)
    builder.add_node("answer_question", answer_question)
    builder.add_node("summarize", summarize)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "demonstrate_recall")
    builder.add_edge("demonstrate_recall", "store_memories")
    builder.add_edge("store_memories", "answer_question")
    builder.add_edge("answer_question", "summarize")
    builder.add_edge("summarize", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Width for print formatting
W = 72


def _box(title: str, body: str) -> None:
    """Print a labelled box to stdout."""
    print("┌" + "─" * (W - 2) + "┐")
    for line in textwrap.wrap(title, width=W - 6):
        print(f"│  {line: <{W - 5}}│")
    print("│" + "─" * (W - 2) + "│")
    for line in body.strip().splitlines():
        for chunk in textwrap.wrap(line, width=W - 4):
            print(f"│  {chunk: <{W - 5}}│")
    print("└" + "─" * (W - 2) + "┘")
    print()


def main():
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("ERROR: MOORCHEH_API_KEY environment variable is not set.")
        print("Get a free key at https://console.moorcheh.ai/api-keys")
        sys.exit(1)

    agent_id = "langgraph-support-agent"

    # ---- Setup Memanto -----------------------------------------------------
    _box("⏳ Setup", "Initializing Memanto agent and session...")
    from memanto_tools import MemantoSetup, create_memanto_tools

    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(agent_id=agent_id)
    tools = create_memanto_tools(client, agent_id=agent_id)
    print("  ✓ Memanto agent ready:", agent_id)

    # ---- Build and run the LangGraph ---------------------------------------
    graph = build_graph(tools)

    # Print the graph structure for visual verification
    try:
        # LangGraph 1.x uses get_graph() with print()
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            graph.get_graph().print_ascii()
        _box("🧠 LangGraph Structure", f.getvalue())
    except Exception:
        pass  # Older versions may not support print_ascii

    _box("🚀 Running Session", "Executing the LangGraph workflow...")

    # Initial state — no prior messages, the graph loads context from Memanto
    initial = {
        "messages": [],
        "memanto_context": "",
        "session_phase": "startup",
    }

    output = None
    for event in graph.stream(initial):
        for node_name, values in event.items():
            msgs = values.get("messages", [])
            if msgs:
                for msg in msgs:
                    if hasattr(msg, "content"):
                        print(f"  [{node_name}] {msg.content}")
                    elif isinstance(msg, tuple):
                        print(f"  [{node_name}] {msg[1]}")
                    elif isinstance(msg, str):
                        print(f"  [{node_name}] {msg}")
            if values.get("memanto_context"):
                ctx = values["memanto_context"]
                preview = ctx[:120] + "..." if len(ctx) > 120 else ctx
                print(f"  [{node_name}] Context loaded: {preview}")
            output = values

    # ---- Summary -----------------------------------------------------------
    print()
    _box(
        "✅ Session Complete",
        (
            "All memories have been stored in Memanto.\n\n"
            "To verify CROSS-SESSION RECALL, run this script again.\n"
            "The second run will automatically find the memories\n"
            "stored by this run — proving persistence beyond the\n"
            "LangGraph state lifecycle.\n\n"
            f"  python {__file__}\n"
        ),
    )

    # ---- Teardown ----------------------------------------------------------
    setup.teardown()


if __name__ == "__main__":
    main()
