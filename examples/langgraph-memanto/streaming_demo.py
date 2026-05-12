from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from memanto_tools import memanto_recall

class StreamState(TypedDict):
    messages: Annotated[list, add_messages]

def stream_node(state: StreamState) -> dict:
    query = state["messages"][-1].content if state["messages"] else ""
    memories = memanto_recall.invoke({"query": query, "top_k": 3})
    full = f"[STREAMING] Recalled: {memories[:100]} | Response generated."
    return {"messages": [AIMessage(content=full)]}

def build_stream_graph():
    g = StateGraph(StreamState)
    g.add_node("stream", stream_node)
    g.set_entry_point("stream")
    g.add_edge("stream", END)
    return g.compile()

def run_streaming(query: str):
    if not os.getenv("MOORCHEH_API_KEY"):
        print("ERROR: set MOORCHEH_API_KEY first")
        return
    print(f"\nStreaming for: '{query}'\n" + "-"*50)
    graph = build_stream_graph()
    for chunk in graph.stream({"messages": [HumanMessage(content=query)]}):
        for node, value in chunk.items():
            for m in value.get("messages", []):
                print(m.content, flush=True)
    print("-"*50)

if __name__ == "__main__":
    run_streaming("What do you remember about my project?")
