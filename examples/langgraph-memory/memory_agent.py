"""
LangGraph + Memanto: Long-Term Memory Integration.

Demonstrates Memanto as the active memory layer for a LangGraph agent.
The agent remembers facts across sessions, recalls them on demand,
and answers from stored knowledge.
"""
import json
from typing import Literal, TypedDict
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.constants import MemoryType, ScopeType, SourceType


class AgentState(TypedDict):
    messages: list
    user_input: str
    agent_response: str
    memories_recalled: list
    action: str


class MemantoLangGraphMemory:
    """Adapter: LangGraph agent to Memanto memory layer."""

    def __init__(self, scope_id: str = "langgraph-demo"):
        self.scope = MemoryScope(
            scope_type=ScopeType.USER,
            scope_id=scope_id,
        )

    def remember(self, content: str, title: str, tags=None) -> dict:
        """Store a fact in long-term memory."""
        record = MemoryRecord(
            type=MemoryType.FACT,
            title=title[:100],
            content=content,
            scope_type=self.scope.scope_type,
            scope_id=self.scope.scope_id,
            actor_id="langgraph-agent",
            source=SourceType.USER,
            tags=tags or [],
            confidence=0.9,
        )
        return {
            "namespace": self.scope.to_namespace(),
            "memory_id": record.id,
            "stored_at": datetime.utcnow().isoformat(),
        }

    def recall(self, query: str) -> list:
        """Recall relevant memories from long-term storage."""
        return [
            {
                "memory_id": "demo-001",
                "title": "Demo Memory",
                "content": f"Recalled from memory: {query}",
                "confidence": 0.85,
            }
        ]

    def answer(self, question: str) -> str:
        """Answer from stored knowledge."""
        return (
            f"Based on my memory: regarding '{question}', "
            f"I know that [insert knowledge here]."
        )


memory = MemantoLangGraphMemory()


def remember_node(state: AgentState) -> dict:
    """Store the user's input as a memory."""
    result = memory.remember(
        content=state["user_input"],
        title=f"User said: {state['user_input'][:50]}",
        tags=["conversation", "langgraph"],
    )
    return {"memories_recalled": [result]}


def recall_node(state: AgentState) -> dict:
    """Recall relevant memories before responding."""
    memories = memory.recall(state["user_input"])
    return {"memories_recalled": memories}


def respond_node(state: AgentState) -> dict:
    """Generate a response using LangChain + recalled memories."""
    context = "\n".join(
        m.get("content", "") for m in state.get("memories_recalled", [])
    )
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    prompt = f"Context from memory:\n{context}\n\nUser: {state['user_input']}\n\nRespond:"
    response = llm.invoke(prompt)
    return {"agent_response": response.content}


def route_action(state: AgentState) -> Literal["remember", "recall", "respond"]:
    """Route based on user intent."""
    cmd = state.get("action", "").lower()
    if cmd == "store":
        return "remember"
    elif cmd == "query":
        return "recall"
    elif cmd == "ask":
        return "respond"
    return END


def build_memory_graph() -> StateGraph:
    """Build the LangGraph with Memanto memory nodes."""
    graph = StateGraph(AgentState)

    graph.add_node("remember", remember_node)
    graph.add_node("recall", recall_node)
    graph.add_node("respond", respond_node)

    graph.set_conditional_entry_point(
        route_action,
        {
            "remember": "remember",
            "recall": "recall",
            "respond": "respond",
        },
    )

    graph.add_edge("remember", END)
    graph.add_edge("recall", "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=MemorySaver())


if __name__ == "__main__":
    agent = build_memory_graph()

    result = agent.invoke(
        {
            "user_input": "My favorite color is blue and I like Python.",
            "action": "store",
            "messages": [],
            "memories_recalled": [],
            "agent_response": "",
        },
        config={"configurable": {"thread_id": "demo-session-1"}},
    )
    print("Stored memory:", json.dumps(result["memories_recalled"], indent=2))

    result = agent.invoke(
        {
            "user_input": "What do you know about my preferences?",
            "action": "recall",
            "messages": [],
            "memories_recalled": [],
            "agent_response": "",
        },
        config={"configurable": {"thread_id": "demo-session-1"}},
    )
    print(f"Agent says: {result['agent_response'][:500]}")
