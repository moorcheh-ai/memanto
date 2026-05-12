"""
LangGraph StateGraph wired to Memanto as a long-term memory layer.

The graph models a tiny support-assistant pipeline:

    intake -> recall -> reason -> remember -> respond

Only `intake`, `reason`, and `respond` write to LangGraph's thread
state. The `recall` and `remember` nodes call Memanto tools — those
operations persist *outside* the thread state, which is what gives
the graph cross-session memory.

We deliberately do not bind an LLM here so the example stays free
to run with just a Moorcheh API key. The "reason" step is a simple
rule-based summarizer that consumes recalled memories and the new
user turn. Swap it for an LLM call (any LangChain chat model) if
you want richer behavior.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph

from memanto.cli.client.sdk_client import SdkClient

from memanto_tools import create_memanto_tools


class GraphState(TypedDict, total=False):
    """
    Per-thread state for the LangGraph run.

    Note: this state is ephemeral — it does NOT carry memory between
    threads or runs. Anything that needs to survive across sessions
    must go through Memanto via the `remember` / `recall` tools.
    """

    user_input: str
    mode: str  # "ingest" or "recall"
    fact_type: str
    fact_title: str
    fact_content: str
    fact_tags: str
    recalled: str
    answer: str
    response: str


def _intake_node(state: GraphState) -> dict[str, Any]:
    """Normalize the incoming turn. Pure function on thread state."""
    mode = state.get("mode", "recall")
    return {"mode": mode, "user_input": state.get("user_input", "")}


def _make_recall_node(recall_tool: StructuredTool, answer_tool: StructuredTool):
    """
    Build a node that pulls long-term memory for the current turn.

    This is where Memanto replaces LangGraph's thread state as the
    source of truth for "what does the assistant already know".
    """

    def _recall_node(state: GraphState) -> dict[str, Any]:
        query = state.get("user_input", "") or "user context"
        recalled = recall_tool.invoke({"query": query, "limit": 5})
        answer = answer_tool.invoke({"question": query})
        return {"recalled": recalled, "answer": answer}

    return _recall_node


def _reason_node(state: GraphState) -> dict[str, Any]:
    """
    Plan the response using recalled memories + the current turn.

    Rule-based by design so the example runs without an LLM key.
    Replace this with a `ChatModel.invoke(...)` call to make it agentic.
    """
    user_input = state.get("user_input", "")
    recalled = state.get("recalled", "")
    answer = state.get("answer", "")

    if state.get("mode") == "ingest":
        plan = (
            "Storing the user's latest statement as a long-term memory in Memanto "
            "so a future LangGraph run (different thread, different process) can "
            "recall it without any LangGraph checkpoint."
        )
    else:
        plan = (
            "Composing a reply that cites long-term memory pulled from Memanto, "
            "not from LangGraph's thread state. The recalled block below was "
            "fetched via memanto_recall; the answer block via memanto_answer."
        )

    response = (
        f"[plan]\n{plan}\n\n"
        f"[user turn]\n{user_input}\n\n"
        f"[memanto.recall]\n{recalled}\n\n"
        f"[memanto.answer]\n{answer}\n"
    )
    return {"response": response}


def _make_remember_node(remember_tool: StructuredTool):
    """
    Build a node that writes the current turn's takeaway to Memanto.

    Only fires when `mode == "ingest"`. The fact fields come from the
    caller (typically the `run_ingest.py` script) so the example is
    deterministic and easy to verify.
    """

    def _remember_node(state: GraphState) -> dict[str, Any]:
        if state.get("mode") != "ingest":
            return {}

        result = remember_tool.invoke(
            {
                "memory_type": state.get("fact_type", "fact"),
                "title": state.get("fact_title", "Untitled fact"),
                "content": state.get("fact_content", state.get("user_input", "")),
                "confidence": 0.95,
                "tags": state.get("fact_tags", ""),
            }
        )
        previous = state.get("response", "")
        return {"response": f"{previous}\n[memanto.remember]\n{result}\n"}

    return _remember_node


def _respond_node(state: GraphState) -> dict[str, Any]:
    """Final node — just passes the composed response through."""
    return {"response": state.get("response", "")}


def build_graph(
    client: SdkClient,
    agent_id: str,
):
    """
    Wire the StateGraph: intake -> recall -> reason -> remember -> respond.

    The compiled graph is returned without a checkpointer on purpose:
    we want to prove that memory persists *without* any LangGraph
    checkpoint. All cross-session state lives in Memanto.
    """
    tools = create_memanto_tools(client, agent_id)

    graph = StateGraph(GraphState)
    graph.add_node("intake", _intake_node)
    graph.add_node("recall", _make_recall_node(tools["recall"], tools["answer"]))
    graph.add_node("reason", _reason_node)
    graph.add_node("remember", _make_remember_node(tools["remember"]))
    graph.add_node("respond", _respond_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "recall")
    graph.add_edge("recall", "reason")
    graph.add_edge("reason", "remember")
    graph.add_edge("remember", "respond")
    graph.add_edge("respond", END)

    return graph.compile()
