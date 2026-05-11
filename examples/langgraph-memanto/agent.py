import os
from typing import Annotated, TypedDict, Literal

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage

from memory import MemantoMemory

load_dotenv()

MEMANTO_AGENT_ID = os.getenv("AGENT_ID", "langgraph-customer-support")


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    memory_context: str


class CustomerSupportGraph:
    """LangGraph workflow with Memanto-backed cross-session memory."""

    def __init__(self, memory: MemantoMemory):
        self.memory = memory
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)

        builder.add_node("load_memory", self.load_memory)
        builder.add_node("process_query", self.process_query)
        builder.add_node("store_memory", self.store_memory)

        builder.set_entry_point("load_memory")
        builder.add_edge("load_memory", "process_query")
        builder.add_edge("process_query", "store_memory")
        builder.add_conditional_edges(
            "store_memory",
            self.should_continue,
            {"continue": "load_memory", "end": END},
        )

        return builder.compile()

    def load_memory(self, state: AgentState) -> dict:
        user_id = state["user_id"]
        prefs = self.memory.recall_preferences(user_id)
        recent = self.memory.recall_user_context(
            user_id, "recent conversations and issues"
        )

        ctx_parts = []
        if prefs:
            ctx_parts.append("User Preferences:")
            for m in prefs:
                ctx_parts.append(f"  - {m.get('content', '')}")

        if recent:
            ctx_parts.append("Recent Context:")
            for m in recent:
                ctx_parts.append(f"  - [{m.get('created_at', '?')}] {m.get('content', '')}")

        memory_context = "\n".join(ctx_parts) if ctx_parts else "No prior context found."
        return {"memory_context": memory_context}

    def process_query(self, state: AgentState) -> dict:
        last_message = state["messages"][-1].content if state["messages"] else ""
        context = state.get("memory_context", "")

        prompt = f"""You are a customer support agent with access to persistent memory.

Memory from previous sessions:
{context}

User message: {last_message}

Respond helpfully using the memory context if relevant."""

        response = f"[Agent recalls from memory]\n{context}\n\nHandling query: {last_message}"
        return {"messages": [AIMessage(content=response)]}

    def store_memory(self, state: AgentState) -> dict:
        user_id = state["user_id"]
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                self.memory.remember_conversation(user_id, msg.content, role="user")

                if "prefer" in msg.content.lower():
                    self.memory.remember_preference(user_id, msg.content)

        return {}

    @staticmethod
    def should_continue(state: AgentState) -> Literal["continue", "end"]:
        return "end"

    def run(self, user_id: str, message: str, session_id: str = "session-1"):
        initial_state: AgentState = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "session_id": session_id,
            "memory_context": "",
        }
        return self.graph.invoke(initial_state)


def simulate_cross_session_recall(memory: MemantoMemory):
    """Demonstrate cross-session recall across two separate sessions."""

    print("=" * 60)
    print("SESSION 1: User sets a preference")
    print("=" * 60)

    graph = CustomerSupportGraph(memory)
    result1 = graph.run(
        user_id="user-alice",
        message="Hi! I prefer concise answers, and I use dark mode.",
        session_id="session-2026-05-11",
    )
    print(f"Response:\n{result1['messages'][-1].content}\n")

    print("=" * 60)
    print("SESSION 2 (next day): User returns with a new question")
    print("=" * 60)

    result2 = graph.run(
        user_id="user-alice",
        message="What theme should my dashboard use?",
        session_id="session-2026-05-12",
    )
    print(f"Response:\n{result2['messages'][-1].content}\n")

    print("=" * 60)
    print("VERIFICATION: Memory persists across sessions")
    print("=" * 60)
    stored = memory.recall_user_context("user-alice", "dark mode preference")
    print(f"Memories found: {len(stored)}")
    for m in stored:
        print(f"  [{m.get('type')}] {m.get('content', '')}")

    return result1, result2


if __name__ == "__main__":
    memory = MemantoMemory(agent_id=MEMANTO_AGENT_ID)
    try:
        simulate_cross_session_recall(memory)
    finally:
        memory.close()
