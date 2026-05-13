"""
langgraph_memory_graph.py — Multi-Agent Collaboration Graph with Memanto Memory

This LangGraph implements a multi-agent architecture where three agents
(Support, Research, Coordinator) collaborate through a shared Memanto
memory layer. Each agent has its own dedicated Memanto agent_id for memory
isolation, plus a shared collaboration space.

Architecture::

  ┌─────────────────────────────────────────────────────┐
  │                   Coordinator                       │
  │  (Route, Plan, Reason — no memory of its own)       │
  └────┬──────────────────────┬─────────────────────────┘
       │                      │
  ┌────▼──────────┐   ┌──────▼──────────┐
  │  Support      │   │  Research       │
  │  (user-facing)│   │  (knowledge)    │
  │  Memanto memory │   │  Memanto memory  │
  └────┬──────────┘   └──────┬──────────┘
       │                      │
  ┌────▼──────────────────────▼──────────┐
  │       Shared Collaboration Space     │
  │  Cross-agent memory (shared agent)   │
  └─────────────────────────────────────┘

No LLM required — purely deterministic LangGraph logic.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import TypedDict

from memanto_adapter import MemantoAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    COORDINATOR = "coordinator"
    SUPPORT = "support"
    RESEARCH = "research"

class Intention(str, Enum):
    ANSWER_QUESTION = "answer_question"
    RESEARCH_TOPIC = "research_topic"
    ROUTE_TO_SUPPORT = "route_to_support"
    ROUTE_TO_RESEARCH = "route_to_research"
    ESCALATE = "escalate"
    REMEMBER_FACT = "remember_fact"
    CHECK_MEMORY = "check_memory"
    CONSOLIDATE = "consolidate"
    COMPLETE = "complete"

@dataclass
class MemoryEntry:
    """A memory to be stored or retrieved."""
    memory_type: str
    title: str
    content: str
    source_agent: str
    confidence: float = 0.8
    tags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class AgentState:
    """The state flowing through the LangGraph graph."""
    # Input
    input_text: str = ""
    input_type: str = "text"  # text, command

    # Routing
    current_agent: str = AgentRole.COORDINATOR.value
    intention: str = ""
    sub_agents_invoked: list[str] = field(default_factory=list)

    # Agent outputs
    support_output: str = ""
    research_output: str = ""
    coordinator_output: str = ""

    # Memory operations
    memories_to_store: list[dict] = field(default_factory=list)
    memories_retrieved: list[dict] = field(default_factory=list)

    # Cross-agent data
    shared_context: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    final_output: str = ""

    def clone(self) -> "AgentState":
        return AgentState(
            input_text=self.input_text,
            input_type=self.input_type,
            current_agent=self.current_agent,
            intention=self.intention,
            sub_agents_invoked=list(self.sub_agents_invoked),
            support_output=self.support_output,
            research_output=self.research_output,
            coordinator_output=self.coordinator_output,
            memories_to_store=list(self.memories_to_store),
            memories_retrieved=list(self.memories_retrieved),
            shared_context=dict(self.shared_context),
            errors=list(self.errors),
            final_output=self.final_output,
        )

# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

class MemoryNodes:
    """
    All the LangGraph nodes that operate on the Memanto memory layer.
    Each node is a pure function that returns state updates.
    """

    def __init__(
        self,
        support_adapter: MemantoAdapter,
        research_adapter: MemantoAdapter,
        shared_adapter: MemantoAdapter,
    ):
        self.sup = support_adapter
        self.res = research_adapter
        self.shr = shared_adapter

    # --- Coordinator nodes ---

    def classify_intention(self, state: AgentState) -> dict:
        """Classify the user's intention based on input text."""
        text = state.input_text.lower()
        intention = Intention.ANSWER_QUESTION
        shared_context = {}

        # Keyword-based intention detection (no LLM)
        memory_keywords = ["remember", "recall", "do you know", "memory", "forget", "who am i",
                           "what did i say", "my name is", "i like", "my preference", "i prefer"]
        research_keywords = ["research", "find out", "search", "look up", "investigate",
                             "what is", "who is", "explain", "tell me about"]
        support_keywords = ["help", "support", "issue", "problem", "error", "bug",
                            "not working", "fix", "how do i", "how to"]
        consolidate_keywords = ["consolidate", "summary", "summarize", "review all",
                                "what do you know", "daily report", "report"]

        # Check memory intent first
        if any(kw in text for kw in memory_keywords):
            if "remember" in text or "my name is" in text or "i like" in text or "i prefer" in text:
                intention = Intention.REMEMBER_FACT
                # Extract what to remember
                for prefix in ["remember that ", "remember: ", "remember ", "my name is "]:
                    if prefix in text:
                        shared_context["fact_to_remember"] = text.split(prefix, 1)[-1].strip()
                        break
                if "my name is" in text:
                    shared_context["fact_to_remember"] = text.split("my name is", 1)[-1].strip()
                if "i like" in text:
                    shared_context["fact_to_remember"] = "preference: " + text.split("i like", 1)[-1].strip()
                if "i prefer" in text:
                    shared_context["fact_to_remember"] = "preference: " + text.split("i prefer", 1)[-1].strip()
            elif "recall" in text or "do you know" in text or "what did" in text or "remember" in text:
                intention = Intention.CHECK_MEMORY
                # Extract the query
                for prefix in ["recall ", "do you know ", "what did i say about "]:
                    if prefix in text:
                        shared_context["recall_query"] = text.split(prefix, 1)[-1].strip()
                        break
                if not shared_context.get("recall_query"):
                    shared_context["recall_query"] = text
        elif any(kw in text for kw in consolidate_keywords):
            intention = Intention.CONSOLIDATE
        elif any(kw in text for kw in research_keywords):
            intention = Intention.RESEARCH_TOPIC
        elif any(kw in text for kw in support_keywords):
            intention = Intention.ROUTE_TO_SUPPORT
        elif text in ["help", "menu", "commands", "?"]:
            intention = Intention.COMPLETE
            shared_context["help_mode"] = True
        else:
            # Default: check memory first, then try to answer
            intention = Intention.CHECK_MEMORY
            shared_context["recall_query"] = text

        return {"intention": intention.value, "shared_context": shared_context}

    def route_from_intention(self, state: AgentState) -> Literal["support_node", "research_node", "memory_remember", "memory_recall", "consolidate_memories", "coordinator_complete"]:
        """Route to the next node based on intention."""
        route_map = {
            Intention.ROUTE_TO_SUPPORT.value: "support_node",
            Intention.ROUTE_TO_RESEARCH.value: "research_node",
            Intention.RESEARCH_TOPIC.value: "research_node",
            Intention.ANSWER_QUESTION.value: "support_node",
            Intention.REMEMBER_FACT.value: "memory_remember",
            Intention.CHECK_MEMORY.value: "memory_recall",
            Intention.CONSOLIDATE.value: "consolidate_memories",
            Intention.COMPLETE.value: "coordinator_complete",
            Intention.ESCALATE.value: "support_node",
        }
        return route_map.get(state.intention, "memory_recall")

    # --- Support Agent nodes ---

    def support_agent(self, state: AgentState) -> dict:
        """Support agent: answers questions using Memanto memory context."""
        # First, recall relevant memories if any
        recall_query = state.input_text
        memories = self.sup.recall(recall_query, limit=3)
        retrieved = memories.get("results", [])

        # Also check shared space for cross-agent context
        shared = self.shr.recall(recall_query, limit=3)
        shared_results = shared.get("results", [])

        # Build response based on context
        if retrieved or shared_results:
            all_memories = retrieved + shared_results
            memory_lines = []
            for m in all_memories[:5]:
                memory_lines.append(f"  [{m.get('type', 'note')}] {m.get('title', '')}: {m.get('content', '')}")
            response = (
                f"🤖 Support Agent (via Memanto memory):\n\n"
                f"I found relevant memories from past sessions:\n" + "\n".join(memory_lines)
            )
            if retrieved and shared_results:
                response += f"\n\n(Retrieved {len(retrieved)} personal + {len(shared_results)} shared memories)"
        else:
            # No memories — provide a template response showing the architecture
            response = (
                f"🤖 Support Agent:\n\n"
                f"Received: \"{state.input_text}\"\n\n"
                f"I don't have relevant memories for this yet. New information will be "
                f"stored in Memanto for cross-session recall.\n\n"
                f"Try asking something like:\n"
                f"  - \"Remember that I use Python and Django\"\n"
                f"  - \"What do you know about me?\"\n"
                f"  - \"Research the LangGraph documentation\""
            )

        # Remember this interaction for future sessions
        self.sup.remember(
            "interaction",
            f"User asked: {state.input_text[:60]}",
            f"Support agent responded to query about: {state.input_text[:200]}",
            confidence=0.7,
            tags=["interaction", "support"],
            source="support_agent",
        )

        return {
            "support_output": response,
            "memories_retrieved": retrieved + shared_results,
            "sub_agents_invoked": state.sub_agents_invoked + ["support"],
        }

    # --- Research Agent nodes ---

    def research_agent(self, state: AgentState) -> dict:
        """Research agent: synthesizes knowledge using Memanto as KB."""
        topic = state.shared_context.get("recall_query", state.input_text)
        research_keywords = ["research", "find out", "search", "look up", "investigate"]
        for kw in research_keywords:
            topic = topic.replace(kw, "").strip()
            topic = topic.lstrip(":").strip()

        # Check what we already know about this topic
        existing = self.res.recall(topic, limit=3)
        existing_results = existing.get("results", [])

        # Also check shared space
        shared = self.shr.recall(f"research: {topic}", limit=3)

        response_parts = [f"🔬 Research Agent (via Memanto knowledge base):\n"]
        response_parts.append(f"Topic: \"{topic}\"\n")

        if existing_results:
            response_parts.append("📚 Existing knowledge:")
            for m in existing_results:
                response_parts.append(f"  ✦ {m.get('title', '')}: {m.get('content', '')[:120]}")
        else:
            response_parts.append("📝 No existing research found. This topic is new.\n")
            response_parts.append("In production, you would connect this to:\n")
            response_parts.append("  • ArXiv API for academic papers")
            response_parts.append("  • Web search for current information")
            response_parts.append("  • Your project's documentation")

        if shared.get("results"):
            response_parts.append(f"\n🤝 Cross-agent context found in shared memory:")
            for m in shared["results"][:2]:
                response_parts.append(f"  [{m.get('type', 'note')}] {m.get('title', '')}")

        response = "\n".join(response_parts)

        # Store the research session
        self.res.remember(
            "research_session",
            f"Research: {topic[:60]}",
            f"Research session initiated for topic: {topic}",
            confidence=0.8,
            tags=["research", topic[:30].lower().replace(" ", "_")],
            source="research_agent",
        )

        return {
            "research_output": response,
            "sub_agents_invoked": state.sub_agents_invoked + ["research"],
        }

    # --- Memory operation nodes ---

    def memory_remember(self, state: AgentState) -> dict:
        """Store information into Memanto long-term memory."""
        fact = state.shared_context.get("fact_to_remember", state.input_text)
        if not fact:
            return {"final_output": "⚠️ No fact to remember was detected."}

        # Determine memory type and title
        if fact.startswith("preference:"):
            memory_type = "preference"
            title = f"User preference: {fact[11:40]}"
            content = fact[11:].strip()
        elif "name is" in fact.lower() or "call me" in fact.lower():
            memory_type = "identity"
            title = "User identity"
            content = fact
        else:
            memory_type = "fact"
            title = f"Fact: {fact[:60]}"
            content = fact

        # Store to support agent's memory
        sup_result = self.sup.remember(
            memory_type, title, content,
            confidence=0.9,
            tags=[memory_type, "user_provided"],
            source="coordinator",
            provenance=f"langgraph_session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        )

        # Also share to the collaboration space
        shr_result = self.shr.remember(
            memory_type, title + " (shared)",
            content,
            confidence=0.8,
            tags=[memory_type, "shared", "user_provided"],
            source="coordinator",
        )

        # Return the response
        output = (
            f"✅ Remembered!\n\n"
            f"📝 Type: {memory_type}\n"
            f"📌 Title: {title}\n"
            f"💾 Content: {content[:200]}\n"
            f"\nThis information is now stored in Memanto. Ask me later "
            f"\"What do you know about me?\" and I'll recall it across sessions."
        )

        return {
            "final_output": output,
            "memories_to_store": state.memories_to_store + [sup_result, shr_result],
        }

    def memory_recall(self, state: AgentState) -> dict:
        """Recall memories from Memanto."""
        query = state.shared_context.get("recall_query", state.input_text)
        if not query.strip():
            query = state.input_text

        # Search across all three agents' memory spaces
        sup_memories = self.sup.recall(query, limit=4)
        res_memories = self.res.recall(query, limit=4)
        shr_memories = self.shr.recall(query, limit=4)

        sup_results = sup_memories.get("results", [])
        res_results = res_memories.get("results", [])
        shr_results = shr_memories.get("results", [])

        # De-duplicate by memory type + title
        seen_keys = set()
        all_memories = []

        def add_unique(m_list, source: str):
            for m in m_list:
                key = (m.get("type", ""), m.get("title", ""))
                if key not in seen_keys:
                    seen_keys.add(key)
                    m["_source"] = source
                    all_memories.append(m)

        add_unique(sup_results, "support")
        add_unique(shr_results, "shared")
        add_unique(res_results, "research")

        if not all_memories:
            output = (
                f"🔍 Memory Search: \"{query}\"\n\n"
                f"No memories found matching your query.\n\n"
                f"💡 Tip: Try asking me to remember something first:\n"
                f"  \"Remember that I use Python and Django\"\n"
                f"  \"My name is Alice\"\n"
                f"  \"I prefer dark mode interfaces\""
            )
        else:
            lines = [f"🔍 Memory Search: \"{query}\"\n"]
            lines.append(f"Found {len(all_memories)} matching memories across "
                         f"{len(set(m['_source'] for m in all_memories))} agent space(s):\n")

            for m in all_memories:
                source_icon = {"support": "🤖", "research": "🔬", "shared": "🤝"}.get(
                    m.get("_source", ""), "📦"
                )
                lines.append(
                    f"{source_icon} [{m.get('type', 'note').upper()}] "
                    f"{m.get('title', '')}\n"
                    f"   {m.get('content', '')[:150]}"
                )
                if m.get("confidence"):
                    lines[-1] += f"\n   (confidence: {m['confidence']})"
                if m.get("tags"):
                    lines[-1] += f"\n   tags: {', '.join(m['tags'][:5])}"
                lines.append("")

            # Also try Memanto's semantic answer if cloud mode
            if not self.sup._preview:
                try:
                    answer_result = self.sup.answer(query)
                    if answer_result.get("answer"):
                        lines.append(f"\n🧠 Semantic answer: {answer_result['answer'][:300]}")
                except Exception:
                    pass

            output = "\n".join(lines)

        return {
            "final_output": output,
            "memories_retrieved": all_memories,
        }

    def consolidate_memories(self, state: AgentState) -> dict:
        """Consolidate memories across agents and generate summary."""
        # Get all memories from all agents
        sup_memories = self.sup.list_memories(limit=50)
        res_memories = self.res.list_memories(limit=50)
        shr_memories = self.shr.list_memories(limit=50)

        sup_list = sup_memories.get("results", []) if isinstance(sup_memories, dict) else []
        res_list = res_memories.get("results", []) if isinstance(res_memories, dict) else []
        shr_list = shr_memories.get("results", []) if isinstance(shr_memories, dict) else []

        all_count = len(sup_list) + len(res_list) + len(shr_list)

        # Count by type
        type_counts: dict[str, int] = {}
        for m in sup_list + res_list + shr_list:
            mt = m.get("type", "unknown")
            type_counts[mt] = type_counts.get(mt, 0) + 1

        # Summary response
        lines = [
            f"📊 Memory Consolidation Report\n",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"",
            f"Total memories: {all_count}",
            f"  • Support Agent: {len(sup_list)}",
            f"  • Research Agent: {len(res_list)}",
            f"  • Shared Space: {len(shr_list)}",
            f"",
            f"Breakdown by type:",
        ]
        for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {t}: {c}")

        # Add conflict detection (cloud only)
        conflicts = []
        if not self.sup._preview:
            try:
                conflicts = self.sup.detect_conflicts()
            except Exception:
                pass

        if conflicts:
            lines.append(f"\n⚠️ {len(conflicts)} memory conflict(s) detected")

        # Try daily summary (cloud only)
        summary_result = self.sup.generate_summary()
        if isinstance(summary_result, dict) and summary_result.get("summary"):
            lines.append(f"\n📅 Daily summary: {summary_result['summary'][:200]}")

        # Store this consolidation as a shared memory
        self.shr.remember(
            "consolidation",
            f"Consolidation: {len(sup_list)} support + {len(res_list)} research memories",
            f"Memory consolidation at {datetime.now(timezone.utc).isoformat()}. "
            f"Total: {all_count} memories across {len(type_counts)} types.",
            confidence=0.95,
            tags=["consolidation", "system"],
            source="coordinator",
        )

        lines.append(f"\n✅ Consolidation complete. Shared memory updated.")

        return {"final_output": "\n".join(lines)}

    def coordinator_complete(self, state: AgentState) -> dict:
        """Generate the final output from all collected responses."""
        if state.final_output:
            return {}  # Already set by a specific node

        parts = []

        if state.support_output:
            parts.append(state.support_output)

        if state.research_output:
            parts.append("\n" + "=" * 50 + "\n")
            parts.append(state.research_output)

        if state.memories_retrieved:
            parts.append(f"\n[Retrieved {len(state.memories_retrieved)} memories across session]")

        if state.errors:
            parts.append(f"\n⚠️ Errors during execution: {len(state.errors)}")

        if not parts:
            parts.append(
                "🤖 Coordinator Agent\n\n"
                "Welcome to the Memanto + LangGraph Multi-Agent System!\n\n"
                "Try these commands:\n"
                "  • \"Remember that I use Python\" — store a memory\n"
                "  • \"What do you know about me?\" — recall memories\n"
                "  • \"Help me with an issue\" — route to support agent\n"
                "  • \"Research LangGraph\" — route to research agent\n"
                "  • \"Consolidate memories\" — get a memory summary\n"
                "  • \"Exit\" or \"quit\" — end the session"
            )

        return {"final_output": "\n".join(parts), "coordinator_output": "\n".join(parts)}

    def error_handler(self, state: AgentState, error: str) -> dict:
        """Handle errors gracefully."""
        logger.error(f"Graph error: {error}")
        return {
            "errors": state.errors + [error],
            "final_output": (
                f"⚠️ An error occurred during execution:\n\n"
                f"  {error}\n\n"
                f"The system is still operational. Try a different command."
            ),
        }

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_memory_graph(
    support_adapter: MemantoAdapter,
    research_adapter: MemantoAdapter,
    shared_adapter: MemantoAdapter,
) -> StateGraph:
    """Construct the LangGraph with Memanto memory integration."""
    nodes = MemoryNodes(support_adapter, research_adapter, shared_adapter)

    # Define state schema
    class GraphState(TypedDict):
        input_text: str
        input_type: str
        current_agent: str
        intention: str
        sub_agents_invoked: list[str]
        support_output: str
        research_output: str
        coordinator_output: str
        memories_to_store: list[dict]
        memories_retrieved: list[dict]
        shared_context: dict[str, Any]
        errors: list[str]
        final_output: str

    # Build graph
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("classify_intention", nodes.classify_intention)
    workflow.add_node("support_node", nodes.support_agent)
    workflow.add_node("research_node", nodes.research_agent)
    workflow.add_node("memory_remember", nodes.memory_remember)
    workflow.add_node("memory_recall", nodes.memory_recall)
    workflow.add_node("consolidate_memories", nodes.consolidate_memories)
    workflow.add_node("coordinator_complete", nodes.coordinator_complete)

    # Set entry point
    workflow.set_entry_point("classify_intention")

    # Add conditional edges
    workflow.add_conditional_edges(
        "classify_intention",
        nodes.route_from_intention,
    )

    # Sub-agents flow back to complete
    workflow.add_edge("support_node", "coordinator_complete")
    workflow.add_edge("research_node", "coordinator_complete")
    workflow.add_edge("memory_remember", END)
    workflow.add_edge("memory_recall", END)
    workflow.add_edge("consolidate_memories", END)
    workflow.add_edge("coordinator_complete", END)

    # Compile with MemorySaver for conversation checkpoints
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Convenience: create a multi-agent graph with defaults
# ---------------------------------------------------------------------------

def create_memory_graph(
    api_key: str | None = None,
    preview: bool = False,
) -> StateGraph:
    """Create a pre-configured multi-agent memory graph.

    Args:
        api_key: Moorcheh API key (or from MOORCHEH_API_KEY env var)
        preview: If True, use local JSON store instead of Memanto cloud

    Returns:
        A compiled LangGraph StateGraph
    """
    api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")

    support_id = os.environ.get("SUPPORT_AGENT_ID", "memanto-langgraph-support-agent")
    research_id = os.environ.get("RESEARCH_AGENT_ID", "memanto-langgraph-research-agent")
    shared_id = os.environ.get("SHARED_AGENT_ID", "memanto-langgraph-shared-space")

    support = MemantoAdapter(api_key=api_key, agent_id=support_id, preview=preview)
    research = MemantoAdapter(api_key=api_key, agent_id=research_id, preview=preview)
    shared = MemantoAdapter(api_key=api_key, agent_id=shared_id, preview=preview)

    return build_memory_graph(support, research, shared)


# ---------------------------------------------------------------------------
# Direct graph runner (no LangGraph — for testing)
# ---------------------------------------------------------------------------

def run_agent(
    adapter: MemantoAdapter,
    text: str,
    graph=None,
) -> str:
    """Run input through the graph and return the output."""
    if graph is None:
        graph = create_memory_graph(preview=adapter._preview)

    initial_state = AgentState(
        input_text=text,
        input_type="text",
    )

    # Convert to dict for LangGraph
    state_dict = {
        "input_text": initial_state.input_text,
        "input_type": initial_state.input_type,
        "current_agent": initial_state.current_agent,
        "intention": initial_state.intention,
        "sub_agents_invoked": list(initial_state.sub_agents_invoked),
        "support_output": initial_state.support_output,
        "research_output": initial_state.research_output,
        "coordinator_output": initial_state.coordinator_output,
        "memories_to_store": list(initial_state.memories_to_store),
        "memories_retrieved": list(initial_state.memories_retrieved),
        "shared_context": dict(initial_state.shared_context),
        "errors": list(initial_state.errors),
        "final_output": initial_state.final_output,
    }

    # Run the graph with required config
    config = {"configurable": {"thread_id": "demo-session-1"}}
    result = graph.invoke(state_dict, config)

    return result.get("final_output", str(result))


if __name__ == "__main__":
    # Quick test
    import dotenv
    dotenv.load_dotenv()

    logging.basicConfig(level=logging.INFO)
    graph = create_memory_graph(preview=True)

    test_inputs = [
        "Remember that my name is Alice and I prefer Python",
        "What do you know about me?",
        "Consolidate memories",
        "Can you help me with a LangGraph issue?",
        "Exit",
    ]

    for inp in test_inputs:
        print(f"\n{'='*60}")
        print(f"INPUT: {inp}")
        print(f"{'='*60}")
        output = run_agent(None, inp, graph)
        print(output)