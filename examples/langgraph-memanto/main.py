"""
LangGraph + Memanto: Research Mentor with Persistent Cross-Session Memory

A LangGraph workflow that uses Memanto as its long-term memory layer.
The agent remembers facts, preferences, decisions, and project context
across completely independent sessions — no shared LangGraph state needed.

Architecture:

    ┌─────────┐     ┌────────┐     ┌──────────┐     ┌─────────┐     ┌───────┐
    │  intake  │ ──▸ │ recall │ ──▸ │ generate │ ──▸ │ extract │ ──▸ │ store │
    └─────────┘     └────────┘     └──────────┘     └─────────┘     └───────┘
       user input    Memanto ↕        LLM call       LLM → JSON     Memanto ↕
                     semantic         with memory      identify       persist
                     search           context          new facts      memories

Memory lives in Memanto, NOT in the LangGraph checkpoint.
This is what enables cross-session recall.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from memanto_client import MemantoClient, MemoryResult

# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class MentorState(TypedDict):
    """State carried through the LangGraph workflow.

    NOTE: Memory context comes from Memanto at runtime — never from
    the graph checkpoint.  This is the key design decision that makes
    cross-session recall work.
    """
    user_input: str
    messages: list[dict[str, str]]
    recalled_memories: list[dict[str, Any]]
    new_memories: list[dict[str, Any]]
    response: str

# ---------------------------------------------------------------------------
# System prompt templates
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """\
You are a Research Mentor — a knowledgeable, encouraging assistant that helps \
researchers organize their work, track experiments, and maintain context across \
sessions.

You have access to a persistent memory system.  When memories from previous \
sessions are provided, you should naturally incorporate them into your responses \
without explicitly saying "I recall from memory that…".  Instead, demonstrate \
your understanding of the user's ongoing work by referencing details naturally, \
as a real mentor would.

Be concise but thorough.  Use markdown formatting when it helps clarity."""

MEMORY_CONTEXT_TEMPLATE = """\

## Recalled Memories from Previous Sessions

The following memories are retrieved from your long-term memory store.  Use them \
to maintain continuity with the user's prior work:

{memories}

---
Remember: incorporate these naturally.  Do NOT list them back or say "from my memory".\
"""

EXTRACTION_PROMPT = """\
You are a memory extraction engine.  Given a conversation between a user and an \
AI mentor, identify NEW facts, preferences, decisions, goals, events, or \
commitments worth persisting in long-term memory.

Rules:
- Extract only information from the LATEST user message and assistant response.
- Do NOT re-extract information that already appears in the recalled memories.
- Each memory should be a single, self-contained statement.
- Assign an appropriate type from: fact, preference, goal, decision, artifact, \
  learning, event, instruction, relationship, context, observation, commitment, error.
- Assign a confidence score (0.0–1.0) reflecting how certain the information is.
- Assign 1–3 short tags.
- If there is nothing new worth remembering, return an empty list.

Respond with ONLY a JSON array.  No markdown fences, no commentary.

Example output:
[
  {{"content": "User is working on LLM inference optimization", "type": "fact", "confidence": 0.95, "tags": ["llm", "optimization"]}},
  {{"content": "User prefers PyTorch over TensorFlow", "type": "preference", "confidence": 0.9, "tags": ["tooling"]}}
]

---

Recalled memories (already stored — do NOT re-extract):
{recalled_memories}

---

Latest conversation turn:

User: {user_input}
Assistant: {response}\
"""

# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def build_graph(
    memanto: MemantoClient,
    agent_id: str,
    model_name: str = "gpt-4o-mini",
) -> StateGraph:
    """Build and compile the Research Mentor LangGraph workflow."""

    llm = ChatOpenAI(model=model_name, temperature=0.4)
    extraction_llm = ChatOpenAI(model=model_name, temperature=0.0)

    # -- 1. intake ----------------------------------------------------------

    async def intake(state: MentorState) -> MentorState:
        """Append the latest user input to the message history."""
        state["messages"].append({"role": "user", "content": state["user_input"]})
        return state

    # -- 2. recall ----------------------------------------------------------

    async def recall(state: MentorState) -> MentorState:
        """Search Memanto for memories relevant to the current input.

        This node is what enables cross-session recall: it queries the
        Memanto server for semantically similar memories, regardless of
        when they were stored.
        """
        try:
            result = await memanto.recall(
                agent_id,
                query=state["user_input"],
                limit=8,
                min_similarity=0.25,
            )
            state["recalled_memories"] = [
                {
                    "content": m.content,
                    "type": m.memory_type,
                    "confidence": m.confidence,
                    "similarity": m.similarity,
                }
                for m in result.memories
            ]
        except Exception:
            # Graceful degradation: if Memanto is unavailable, proceed
            # without recalled context.
            state["recalled_memories"] = []
        return state

    # -- 3. generate --------------------------------------------------------

    async def generate(state: MentorState) -> MentorState:
        """Generate the assistant response using recalled memories as context."""

        # Build system prompt — inject recalled memories if any
        system = BASE_SYSTEM_PROMPT
        if state["recalled_memories"]:
            memory_text = "\n".join(
                f"- [{m['type']}] (confidence: {m['confidence']:.1f}) {m['content']}"
                for m in state["recalled_memories"]
            )
            system += MEMORY_CONTEXT_TEMPLATE.format(memories=memory_text)

        messages = [SystemMessage(content=system)]
        for msg in state["messages"]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        result = await llm.ainvoke(messages)
        response_text = result.content

        state["response"] = response_text
        state["messages"].append({"role": "assistant", "content": response_text})
        return state

    # -- 4. extract ---------------------------------------------------------

    async def extract(state: MentorState) -> MentorState:
        """Use a second LLM call to extract new facts worth persisting."""

        recalled_text = "\n".join(
            f"- {m['content']}" for m in state["recalled_memories"]
        ) or "(none)"

        prompt = EXTRACTION_PROMPT.format(
            recalled_memories=recalled_text,
            user_input=state["user_input"],
            response=state["response"],
        )

        result = await extraction_llm.ainvoke([HumanMessage(content=prompt)])
        raw = result.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            extracted = json.loads(raw)
            if not isinstance(extracted, list):
                extracted = []
        except (json.JSONDecodeError, ValueError):
            extracted = []

        state["new_memories"] = extracted
        return state

    # -- 5. store -----------------------------------------------------------

    async def store(state: MentorState) -> MentorState:
        """Persist newly extracted memories to Memanto."""
        for mem in state["new_memories"]:
            try:
                await memanto.remember(
                    agent_id,
                    content=mem.get("content", ""),
                    memory_type=mem.get("type", "fact"),
                    confidence=mem.get("confidence", 0.8),
                    tags=mem.get("tags", []),
                    source="agent",
                    provenance="inferred",
                )
            except Exception:
                # Log but don't fail the conversation if a single store fails
                pass
        return state

    # -- Build graph --------------------------------------------------------

    graph = StateGraph(MentorState)
    graph.add_node("intake", intake)
    graph.add_node("recall", recall)
    graph.add_node("generate", generate)
    graph.add_node("extract", extract)
    graph.add_node("store", store)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "recall")
    graph.add_edge("recall", "generate")
    graph.add_edge("generate", "extract")
    graph.add_edge("extract", "store")
    graph.add_edge("store", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# High-level wrapper
# ---------------------------------------------------------------------------

class ResearchMentor:
    """Convenient wrapper around the LangGraph + Memanto workflow.

    Usage::

        mentor = ResearchMentor()
        await mentor.start_session()
        response = await mentor.chat("Tell me about my project")
        await mentor.end_session()
    """

    def __init__(
        self,
        agent_name: str = "research-mentor",
        memanto_url: str = "http://localhost:8000",
        model_name: str = "gpt-4o-mini",
    ) -> None:
        self.agent_name = agent_name
        self.memanto_url = memanto_url
        self.model_name = model_name
        self._client: MemantoClient | None = None
        self._agent_id: str = ""
        self._graph: Any = None
        self._messages: list[dict[str, str]] = []

    async def start_session(self) -> None:
        """Initialize Memanto connection, ensure agent exists, activate session."""
        self._client = MemantoClient(base_url=self.memanto_url)
        await self._client.__aenter__()

        agent_info = await self._client.ensure_agent(self.agent_name, pattern="conversational")
        self._agent_id = agent_info.agent_id

        await self._client.activate(self._agent_id)

        self._graph = build_graph(self._client, self._agent_id, self.model_name)
        self._messages = []

    async def chat(self, message: str) -> str:
        """Send a message and get the mentor's response."""
        if not self._graph or not self._client:
            raise RuntimeError("Call start_session() first")

        state: MentorState = {
            "user_input": message,
            "messages": list(self._messages),
            "recalled_memories": [],
            "new_memories": [],
            "response": "",
        }

        result = await self._graph.ainvoke(state)

        # Update local message history for multi-turn context
        self._messages = result["messages"]

        return result["response"]

    async def recall_memories(self, query: str, limit: int = 10) -> list[MemoryResult]:
        """Directly query Memanto for stored memories."""
        if not self._client:
            raise RuntimeError("Call start_session() first")
        result = await self._client.recall(self._agent_id, query=query, limit=limit)
        return result.memories

    async def ask_memories(self, question: str) -> str:
        """Use Memanto's RAG endpoint to answer from stored memories."""
        if not self._client:
            raise RuntimeError("Call start_session() first")
        result = await self._client.answer(self._agent_id, question=question)
        return result.answer

    async def end_session(self) -> None:
        """Deactivate the Memanto session and close the HTTP client."""
        if self._client:
            try:
                await self._client.deactivate(self._agent_id)
            except Exception:
                pass
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def __aenter__(self) -> "ResearchMentor":
        await self.start_session()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.end_session()


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

async def interactive_cli() -> None:
    """Run the Research Mentor in interactive mode."""
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    console.print(
        Panel(
            "[bold cyan]Research Mentor[/bold cyan]\n"
            "A LangGraph agent with persistent memory via Memanto.\n"
            "Type [bold]quit[/bold] to exit, [bold]recall <query>[/bold] to search memories.",
            title="Welcome",
            border_style="cyan",
        )
    )

    async with ResearchMentor() as mentor:
        while True:
            try:
                user_input = console.input("\n[bold green]You:[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            # Special command: recall
            if user_input.lower().startswith("recall "):
                query = user_input[7:]
                memories = await mentor.recall_memories(query)
                if memories:
                    console.print(f"\n[dim]Found {len(memories)} memories:[/dim]")
                    for m in memories:
                        console.print(
                            f"  [{m.memory_type}] (sim: {m.similarity:.2f}) {m.content}"
                        )
                else:
                    console.print("[dim]No memories found.[/dim]")
                continue

            with console.status("[dim]Thinking...[/dim]"):
                response = await mentor.chat(user_input)

            console.print("\n[bold blue]Mentor:[/bold blue]")
            console.print(Markdown(response))

    console.print("\n[dim]Session ended. Memories have been saved.[/dim]")


if __name__ == "__main__":
    asyncio.run(interactive_cli())
