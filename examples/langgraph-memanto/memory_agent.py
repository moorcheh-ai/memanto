"""
LangGraph + Memanto: Long-Term Memory Integration with Cross-Session Recall

Demonstrates Memanto as the durable memory layer for a LangGraph agent.
The agent remembers facts across conversation sessions and recalls them
in future interactions — giving your graph a permanent brain.

Key features:
- Cross-session recall: agent remembers facts from "yesterday"
- In-memory MemantoStore using Memanto's core data model
- Optional LLM enhancement (works without API keys)
- Practical customer-support scenario
"""

import json
import uuid
import os
from datetime import datetime
from typing import Any, Literal, Optional

# Memanto core imports
from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.constants import MemoryType, ScopeType, SourceType

# LangGraph
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

# LangChain (optional — works without it)
try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

# Optional LLM
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HAS_LLM = bool(OPENAI_API_KEY)
if HAS_LLM and HAS_LANGCHAIN:
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)
    except ImportError:
        llm = None
        HAS_LLM = False
else:
    llm = None
    HAS_LLM = False


# =============================================================================
# Memanto Store — In-Memory Implementation
# =============================================================================

class MemantoStore:
    """Lightweight in-memory store using Memanto's core data model.

    This is a local implementation for demonstration purposes.
    In production, use the Memanto/Moorcheh cloud API for persistence,
    search, and multi-agent memory sharing.
    """

    def __init__(self):
        self._memories: dict[str, MemoryRecord] = {}
        self._scopes: dict[str, list[str]] = {}  # scope_namespace → [memory_ids]

    def remember(
        self,
        content: str,
        title: str = "",
        scope_type: str = "user",
        scope_id: str = "default",
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        """Store a fact in long-term memory."""
        record = MemoryRecord(
            type="fact",
            title=title[:100] or content[:50],
            content=content,
            scope_type=scope_type,
            scope_id=scope_id,
            actor_id="langgraph-agent",
            source="user",
            tags=tags or [],
            confidence=confidence,
        )
        self._memories[record.id] = record

        scope_ns = record.get_scope().to_namespace()
        if scope_ns not in self._scopes:
            self._scopes[scope_ns] = []
        self._scopes[scope_ns].append(record.id)

        return {
            "memory_id": record.id,
            "namespace": scope_ns,
            "stored_at": record.created_at.isoformat(),
            "confidence": record.confidence,
        }

    def recall(
        self,
        query: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall relevant memories using keyword matching.

        In production, Memanto/Moorcheh provides semantic search.
        Here we use simple keyword matching for the demo.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        candidates: list[MemoryRecord] = []

        # Filter by scope if specified
        if scope_type and scope_id:
            scope_ns = MemoryScope(
                scope_type=scope_type, scope_id=scope_id
            ).to_namespace()
            if scope_ns in self._scopes:
                for mid in self._scopes[scope_ns]:
                    if mid in self._memories:
                        candidates.append(self._memories[mid])
        else:
            candidates = list(self._memories.values())

        # Score by keyword relevance
        scored = []
        for rec in candidates:
            text = f"{rec.title} {rec.content}".lower()
            score = 0
            for word in query_words:
                if word in text:
                    score += 1
            if score > 0:
                scored.append((score, rec))

        # Sort by relevance score, then confidence
        scored.sort(key=lambda x: (-x[0], -x[1].compute_confidence()))

        results = []
        for score, rec in scored[:top_k]:
            results.append({
                "memory_id": rec.id,
                "title": rec.title,
                "content": rec.content,
                "confidence": round(rec.compute_confidence(), 2),
                "relevance": score,
                "scope": rec.get_scope().to_namespace(),
                "created_at": rec.created_at.isoformat(),
                "trust": rec.trust_score().get("trust_level", "medium"),
            })

        return results

    def get_memory_count(self, scope_type: str | None = None, scope_id: str | None = None) -> int:
        """Count memories in a scope."""
        if scope_type and scope_id:
            scope_ns = MemoryScope(scope_type=scope_type, scope_id=scope_id).to_namespace()
            return len(self._scopes.get(scope_ns, []))
        return len(self._memories)

    def list_memories(self, scope_type: str, scope_id: str) -> list[dict[str, Any]]:
        """List all memories in a scope."""
        scope_ns = MemoryScope(scope_type=scope_type, scope_id=scope_id).to_namespace()
        results = []
        for mid in self._scopes.get(scope_ns, []):
            rec = self._memories.get(mid)
            if rec:
                results.append({
                    "id": rec.id,
                    "title": rec.title,
                    "type": rec.type,
                    "created_at": rec.created_at.isoformat(),
                })
        return results


# =============================================================================
# LangGraph Agent with Memanto Memory
# =============================================================================

class LangGraphMemantoAgent:
    """A LangGraph agent augmented with Memanto long-term memory."""

    def __init__(self, user_id: str = "demo-user"):
        self.store = MemantoStore()
        self.user_id = user_id
        self.scope_id = user_id
        self.graph = self._build_graph() if HAS_LANGGRAPH else None

    # --- State Schema ---

    def get_initial_state(self) -> dict[str, Any]:
        """Create initial state for a new conversation session."""
        return {
            "messages": [],
            "user_input": "",
            "agent_response": "",
            "memories_recalled": [],
            "memory_to_store": None,
            "action": "process",
            "session_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.utcnow().isoformat(),
        }

    # --- Nodes ---

    def recall_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Retrieve relevant memories from Memanto based on user input."""
        state["user_input"] = state.get("user_input", "")
        if not state["user_input"]:
            state["memories_recalled"] = []
            return state

        memories = self.store.recall(
            query=state["user_input"],
            scope_type="user",
            scope_id=self.scope_id,
        )

        msg = f"🤖 Memanto recalled {len(memories)} memory(ies)"
        if memories:
            for m in memories:
                msg += f"\n   [{m['trust']}] {m['title']}: {m['content'][:60]}"

        state["memories_recalled"] = memories
        state["messages"] = state.get("messages", []) + [{"role": "system", "content": msg}]
        return state

    def respond_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate a response using recalled memories and optional LLM."""
        memories = state.get("memories_recalled", [])
        user_input = state.get("user_input", "")

        # Build context from recalled memories
        memory_context = ""
        if memories:
            memory_context = "I recall:\n"
            for m in memories:
                memory_context += f"- {m['title']}: {m['content']}\n"

        if HAS_LLM and llm:
            # LLM-enhanced response
            from langchain_core.messages import HumanMessage, SystemMessage
            system = SystemMessage(
                content=(
                    "You are a helpful assistant with access to Memanto long-term memory. "
                    "Use the recalled memories to answer contextually. "
                    "If you don't have relevant memories, say so and ask for more info.\n\n"
                    f"{memory_context}"
                )
            )
            human = HumanMessage(content=user_input)
            result = llm.invoke([system, human])
            response = result.content
        else:
            # LLM-free response using template
            if memories:
                context_lines = "\n".join(
                    f"- {m['content']}" for m in memories
                )
                response = (
                    f"I checked my Memanto memory and found relevant information:\n"
                    f"{context_lines}\n\n"
                    f"How else can I help you?"
                )
            else:
                response = (
                    f"I don't have any memories about '{user_input}'. "
                    f"I'll remember this for future conversations."
                )

        state["agent_response"] = response
        state["action"] = "assess_memory"
        state["messages"] = state.get("messages", []) + [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response},
        ]
        return state

    def assess_memory_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Decide whether to store the user's input as a new memory."""
        user_input = state.get("user_input", "")
        memories = state.get("memories_recalled", [])

        # Simple heuristic: store if it looks like a fact about the user
        fact_indicators = [
            "my ", "i am ", "i have ", "i like ", "i love ",
            "i hate ", "i prefer ", "my name ", "my birthday ",
            "i work ", "i live ", "i was ", "i'm ",
            "remember that ", "don't forget ",
        ]

        should_store = any(
            indicator in user_input.lower() for indicator in fact_indicators
        )

        # Don't store if it's already recalled (confirmation)
        already_known = any(
            user_input.lower().split("my")[-1].strip().split()[0]
            in m["content"].lower()
            if "my" in user_input.lower()
            else False
            for m in memories
        ) if memories else False

        if should_store and not already_known:
            state["memory_to_store"] = user_input
            state["action"] = "store"
        else:
            state["action"] = "done"
        return state

    def store_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Store the user's input as a new memory in Memanto."""
        content = state.get("memory_to_store", "")
        if not content:
            state["action"] = "done"
            return state

        # Extract a meaningful title
        title = content[:50].strip()
        if len(title) == 50:
            title += "..."

        result = self.store.remember(
            content=content,
            title=title,
            scope_type="user",
            scope_id=self.scope_id,
            tags=["conversation", "langgraph-demo"],
            confidence=0.85,
        )

        memory_msg = f"📝 Stored as memory [{result['memory_id'][:8]}...] with confidence {result['confidence']}"
        state["memory_to_store"] = None
        state["action"] = "done"
        state["messages"] = state.get("messages", []) + [
            {"role": "system", "content": memory_msg}
        ]
        return state

    # --- Router ---

    def route_after_recall(self, state: dict[str, Any]) -> Literal["respond", "respond"]:
        """After recall, always respond."""
        return "respond"

    def route_after_respond(self, state: dict[str, Any]) -> Literal["assess_memory"]:
        """After response, assess memory."""
        return "assess_memory"

    def route_after_assess(self, state: dict[str, Any]) -> Literal["store", "done"]:
        """Route to store or end based on assessment."""
        if state.get("action") == "store":
            return "store"
        return "done"

    def route_after_store(self, state: dict[str, Any]) -> Literal["done"]:
        """After store, always end."""
        return "done"

    # --- Graph Construction ---

    def _build_graph(self):
        """Build the LangGraph state graph."""
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("recall", self.recall_node)
        workflow.add_node("respond", self.respond_node)
        workflow.add_node("assess", self.assess_memory_node)
        workflow.add_node("store", self.store_node)

        # Add edges
        workflow.set_entry_point("recall")
        workflow.add_conditional_edges(
            "recall",
            self.route_after_recall,
            {"respond": "respond"},
        )
        workflow.add_conditional_edges(
            "respond",
            self.route_after_respond,
            {"assess_memory": "assess"},
        )
        workflow.add_conditional_edges(
            "assess",
            self.route_after_assess,
            {"store": "store", "done": END},
        )
        workflow.add_conditional_edges(
            "store",
            self.route_after_store,
            {"done": END},
        )

        # Compile with memory saver for state persistence
        return workflow.compile(checkpointer=MemorySaver())

    # --- Run ---

    def chat(self, user_input: str, verbose: bool = True) -> dict[str, Any]:
        """Process a user message through the LangGraph agent.

        This demonstrates cross-session memory:
        - First call: agent stores user facts
        - Second call (new session): agent recalls those facts
        """
        state = self.get_initial_state()
        state["user_input"] = user_input

        if HAS_LANGGRAPH and self.graph:
            import uuid as _uuid
            config = {"configurable": {"thread_id": f"session-{_uuid.uuid4().hex[:8]}"}}
            result = self.graph.invoke(state, config=config)
        else:
            # Manual pipeline fallback
            state = self.recall_node(state)
            state = self.respond_node(state)
            state = self.assess_memory_node(state)
            if state.get("action") == "store":
                state = self.store_node(state)
            result = state

        if verbose:
            print(f"\n[USER]\n{user_input}\n")
            print(f"[ASSISTANT]\n{result.get('agent_response', '')}\n")
            recalled = result.get("memories_recalled", [])
            if recalled:
                print(f"[MEMANTO] Recalled {len(recalled)} memory(ies)")
                for m in recalled:
                    print(f"  → {m['title']}: {m['content'][:60]}")

        return result

    def get_state_summary(self) -> dict[str, Any]:
        """Get a summary of the agent's memory state."""
        count = self.store.get_memory_count("user", self.scope_id)
        memories = self.store.list_memories("user", self.scope_id)

        return {
            "user_id": self.user_id,
            "memory_count": count,
            "memories": memories,
            "llm_available": HAS_LLM,
            "langgraph_available": HAS_LANGGRAPH,
            "langchain_available": HAS_LANGCHAIN,
        }


# =============================================================================
# Demo Runner — Cross-Session Recall
# =============================================================================

def run_demo():
    """Run a complete cross-session recall demonstration.

    Session 1: User tells the agent personal facts
    Session 2: A new conversation — agent remembers from Session 1
    """
    print("=" * 60)
    print("  MEMANTO + LANGGRAPH: CROSS-SESSION MEMORY DEMO")
    print("  'Give Your Graph a Permanent Brain'")
    print("=" * 60)
    print()

    agent = LangGraphMemantoAgent(user_id="demo-user")
    summary = agent.get_state_summary()
    print(f"Agent ready | LangGraph: {summary['langgraph_available']} | "
          f"LLM: {summary['llm_available']} | "
          f"LangChain: {summary['langchain_available']}")
    print()

    # ── Session 1: User tells the agent personal facts ──
    print("-" * 50)
    print("  🗣️  SESSION 1: Telling the agent personal facts")
    print("-" * 50)
    print()

    facts = [
        "Hi! My name is Alice.",
        "My birthday is May 1st, 1990.",
        "I work as a network engineer in Xi'an.",
        "I love playing guitar and hiking on weekends.",
    ]

    for fact in facts:
        print(f"  👤 User: {fact}")
        result = agent.chat(fact, verbose=False)
        print(f"  🤖 Agent: {result.get('agent_response', '')[:80]}...")

        # Check if memory was stored
        # (stored in the store_node)
        print()
    print(f"  📝 Memories stored: {agent.store.get_memory_count("user", 'demo-user')}")
    print()

    # ── Session 2: New conversation, agent recalls ──
    print("-" * 50)
    print("  🔄 SESSION 2: Starting a NEW conversation (same user)")
    print("  The agent should recall facts from Session 1!")
    print("-" * 50)
    print()

    queries = [
        "What is my name?",
        "When is my birthday?",
        "Where do I work?",
        "What are my hobbies?",
    ]

    for q in queries:
        print(f"  👤 User: {q}")
        # Create a fresh agent state for new "session"
        result = agent.chat(q, verbose=False)
        print(f"  🤖 Agent: {result.get('agent_response', '')[:100]}...")
        recalled = result.get("memories_recalled", [])
        if recalled:
            print(f"     (Recalled {len(recalled)} memories from Memanto)")
        else:
            print(f"     (No memories recalled — demo may need LangGraph)")
        print()

    # ── Summary ──
    print("=" * 60)
    print("  DEMO COMPLETE")
    print("=" * 60)
    summary = agent.get_state_summary()
    print(f"  Total memories in scope: {summary['memory_count']}")
    print(f"  LLM available: {summary['llm_available']}")
    print(f"  LangGraph available: {summary['langgraph_available']}")
    print()
    print("  💡 Key takeaway: Memanto provides persistent memory")
    print("     that LangGraph agents can access across sessions.")
    print("     In production, use Memanto/Moorcheh cloud API")
    print("     for semantic search and multi-agent sharing.")
    print()


if __name__ == "__main__":
    run_demo()
