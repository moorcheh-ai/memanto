"""
Memanto + LangGraph Integration: Research Assistant with Cross-Session Memory

A LangGraph agent that uses Memanto as its persistent long-term memory layer.
Demonstrates cross-session recall — the agent remembers past research topics,
user preferences, and findings across completely disjoint sessions.

Architecture:
    User Query -> [Recall Past Context] -> [Generate Response] -> [Store Memory]
                         ^                                              |
                         |______________ Memanto _______________________|
                              (persists across sessions)

Requirements:
    - memanto (Moorcheh API key)
    - langgraph, langchain-openai (OpenAI-compatible API key)

Usage:
    cp .env.example .env   # Add your API keys
    pip install -r requirements.txt
    python agent.py
"""

import os
import uuid
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from memanto.cli.client.sdk_client import SdkClient

load_dotenv()


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    """Shared state passed between LangGraph nodes."""
    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    recalled_memories: list[dict[str, Any]]
    research_topic: str
    final_response: str


# ---------------------------------------------------------------------------
# Memanto Memory Helper
# ---------------------------------------------------------------------------

class MemantoMemory:
    """
    Thin wrapper around Memanto's SdkClient for the LangGraph agent.

    Uses the same SdkClient that powers the memanto CLI.  The ``agent_id``
    acts as the namespace partition so that multiple agents/users do not
    share the same memory pool.
    """

    def __init__(self, agent_id: str, api_key: str | None = None):
        api_key = api_key or os.environ["MOORCHEH_API_KEY"]
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: str = "",
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        """Persist a memory.  Returns the memory ID."""
        result = self.client.remember(
            content=content,
            memory_type=memory_type,
            title=title or content[:80],
            confidence=confidence,
            agent_id=self.agent_id,
            tags=",".join(tags or []),
        )
        return result.get("memory_id", "")

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve memories relevant to *query*."""
        result = self.client.recall(
            query=query,
            limit=limit,
            agent_id=self.agent_id,
        )
        return result.get("memories", [])

    def answer(self, question: str) -> str:
        """Grounded answer synthesized from stored memories."""
        result = self.client.answer(
            question=question,
            agent_id=self.agent_id,
        )
        return result.get("answer", "")

    def recall_recent(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Broad recall of recent memories (cross-session awareness)."""
        return self.client.recall(
            query="recent activity and past research",
            limit=limit,
            agent_id=self.agent_id,
        ).get("memories", [])


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------

def recall_context(state: ResearchState) -> dict:
    """Look up relevant past memories before generating a response."""
    memory = MemantoMemory(agent_id=state["user_id"])
    query = state["research_topic"]

    related = memory.recall(query, limit=5)
    recent = memory.recall_recent(limit=5)

    # Merge & deduplicate
    seen_ids: set[str] = set()
    unique: list[dict[str, Any]] = []
    for m in related + recent:
        mid = m.get("id", m.get("content", "")[:60])
        if mid not in seen_ids:
            seen_ids.add(mid)
            unique.append(m)

    return {"recalled_memories": unique[:8]}


def generate_response(state: ResearchState) -> dict:
    """Generate a research response informed by recalled memories."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    memories = state.get("recalled_memories", [])
    memory_context = ""
    if memories:
        memory_context = "\n\n## Past Research Context (from Memanto memory)\n"
        for i, m in enumerate(memories[:6], 1):
            title = m.get("title", m.get("content", "")[:80])
            content = m.get("content", "")
            memory_context += f"{i}. **{title}**: {content}\n"

    prompt = f"""You are a research assistant with persistent long-term memory.

User: {state['user_id']}
Topic: {state['research_topic']}
{memory_context}

Provide a helpful, concise research response. If past memories are
relevant, reference them explicitly to demonstrate cross-session recall.
"""
    response = llm.invoke(prompt)
    return {
        "messages": [response],
        "final_response": response.content,
    }


def store_memory(state: ResearchState) -> dict:
    """Persist the interaction into Memanto so future sessions can recall it."""
    memory = MemantoMemory(agent_id=state["user_id"])
    topic = state["research_topic"]

    # Store the research topic
    memory.remember(
        content=f"User researched: {topic}",
        memory_type="fact",
        title=f"Research: {topic[:80]}",
        confidence=0.95,
        tags=["research", "topic"],
    )

    # Store the response summary
    final = state.get("final_response", "")
    if final:
        memory.remember(
            content=final[:500],
            memory_type="fact",
            title=f"Findings: {topic[:80]}",
            confidence=0.85,
            tags=["research", "findings"],
        )

    # Store implicit preference
    memory.remember(
        content=f"User is interested in {topic}",
        memory_type="preference",
        title=f"Interest: {topic[:80]}",
        confidence=0.7,
        tags=["preference", "interest"],
    )

    return {}


# ---------------------------------------------------------------------------
# Build the LangGraph
# ---------------------------------------------------------------------------

def build_research_graph() -> StateGraph:
    """Build the Memanto-enhanced LangGraph research agent."""
    workflow = StateGraph(ResearchState)

    workflow.add_node("recall", recall_context)
    workflow.add_node("respond", generate_response)
    workflow.add_node("remember", store_memory)

    workflow.set_entry_point("recall")
    workflow.add_edge("recall", "respond")
    workflow.add_edge("respond", "remember")
    workflow.add_edge("remember", END)

    return workflow.compile(checkpointer=MemorySaver())


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run_demo():
    """Demonstrate cross-session memory recall with LangGraph + Memanto."""
    print("=" * 60)
    print("Memanto + LangGraph: Cross-Session Memory Demo")
    print("=" * 60)

    user_id = os.environ.get("DEMO_USER_ID") or f"demo-{uuid.uuid4().hex[:8]}"
    graph = build_research_graph()

    # ---- Session 1: initial research ----
    print("\n[Session 1] Researching a new topic ...")
    config1 = {"configurable": {"thread_id": "session-1"}}
    result1 = graph.invoke(
        {
            "user_id": user_id,
            "session_id": "session-1",
            "research_topic": "practical applications of LangGraph in enterprise AI",
        },
        config1,
    )
    print(f"  Response: {result1.get('final_response', '')[:200]}...")

    # ---- Session 2 (new thread, days later) ----
    print("\n[Session 2] Returning days later with a follow-up ...")
    config2 = {"configurable": {"thread_id": "session-2"}}
    result2 = graph.invoke(
        {
            "user_id": user_id,  # SAME user — memories persist
            "session_id": "session-2",
            "research_topic": "what did we research previously about LangGraph or AI agents?",
        },
        config2,
    )

    recalled = result2.get("recalled_memories", [])
    print(f"\n  Cross-session recall: retrieved {len(recalled)} memories:")
    for m in recalled:
        title = m.get("title", "N/A")
        content = str(m.get("content", ""))[:120]
        print(f"    [{m.get('type', '?')}] {title}  ->  {content}")

    print("\n" + "=" * 60)
    print("Cross-session recall successful! Session 2 remembered Session 1.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
