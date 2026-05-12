from __future__ import annotations
import os
from typing import Annotated, TypedDict, Literal
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from memanto_tools import memanto_remember, memanto_recall, memanto_answer, MEMORY_TOOLS

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    current_agent: str
    memory_approved: bool
    summary: str
    iteration: int

X402_CONFIG = {
    "payTo": "66dG5r5TD37ahhrsAMKUroxML9Cqto5jRduifiMgQQ3G",
    "network": "solana",
    "amount": 0.001,
}

def _last(state):
    msgs = state.get("messages", [])
    if not msgs: return ""
    last = msgs[-1]
    return last.content if isinstance(last, BaseMessage) else str(last)

def supervisor_node(state):
    iteration = state.get("iteration", 0)
    route = "researcher" if iteration == 0 else "writer"
    return {"messages": [AIMessage(content=f"[SUPERVISOR] Routing to {route}.")], "current_agent": route}

def supervisor_router(state) -> Literal["researcher", "writer", "__end__"]:
    agent = state.get("current_agent", "supervisor")
    iteration = state.get("iteration", 0)
    if agent == "supervisor" and iteration == 0: return "researcher"
    if agent == "researcher": return "writer"
    return "__end__"

def researcher_node(state):
    query = _last(state)
    recall = memanto_recall.invoke({"query": query, "top_k": 3})
    response = f"[RESEARCHER] Memories:\n{recall}\n\nFindings for: {query[:60]}"
    return {"messages": [AIMessage(content=response)], "current_agent": "researcher", "iteration": state.get("iteration", 0) + 1}

def researcher_memory_node(state):
    finding = _last(state)
    approved = interrupt({"prompt": "Approve storing this memory?", "content": finding[:200]})
    if approved:
        memanto_remember.invoke({"content": finding[:500], "memory_type": "episodic", "tags": "research"})
        return {"messages": [AIMessage(content="Memory stored.")], "memory_approved": True}
    return {"messages": [AIMessage(content="Memory skipped.")], "memory_approved": False}

def writer_node(state):
    query = _last(state)
    prefs = memanto_recall.invoke({"query": "user preferences style", "top_k": 2})
    response = f"[WRITER] Prefs:\n{prefs}\n\nFinal answer for: {query[:60]}"
    memanto_remember.invoke({"content": f"Wrote about: {query[:100]}", "memory_type": "episodic", "tags": "writer"})
    return {"messages": [AIMessage(content=response)], "current_agent": "writer"}

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("researcher", researcher_node)
    g.add_node("store_memory", researcher_memory_node)
    g.add_node("writer", writer_node)
    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", supervisor_router, {"researcher": "researcher", "writer": "writer", "__end__": END})
    g.add_edge("researcher", "store_memory")
    g.add_edge("store_memory", "writer")
    g.add_edge("writer", END)
    return g.compile()

def invoke(message: str) -> dict:
    graph = build_graph()
    result = graph.invoke({"messages": [HumanMessage(content=message)], "current_agent": "supervisor", "memory_approved": False, "summary": "", "iteration": 0})
    return {"response": result["messages"][-1].content if result["messages"] else ""}

def health() -> dict:
    return {"status": "healthy", "agent": "langgraph-memanto-multi-agent", "architecture": ["supervisor", "researcher", "writer"], "features": ["subgraphs", "human-in-the-loop", "cross-session-memory", "streaming"], "tools": [t.name for t in MEMORY_TOOLS], "x402": X402_CONFIG}
