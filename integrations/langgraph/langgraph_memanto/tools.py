from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field

from memanto.cli.client.sdk_client import SdkClient

# Valid Memanto memory types with definitions for the LLM
VALID_MEMORY_TYPES = (
    "fact (objective truths/data), "
    "preference (user likes/dislikes), "
    "goal (objectives/targets), "
    "decision (choices made/agreed upon), "
    "artifact (files/code/deliverables), "
    "learning (insights/lessons learned), "
    "event (occurrences/meetings), "
    "instruction (how-tos/directives), "
    "relationship (connections between entities), "
    "context (background info/state), "
    "observation (trends/patterns/notices), "
    "commitment (promises/next steps), "
    "error (failures/mistakes)"
)


def create_memanto_tools(client: SdkClient, agent_id: str):
    import threading

    _setup_lock = threading.Lock()
    _setup_done = False

    def _do_setup():
        nonlocal _setup_done
        with _setup_lock:
            if _setup_done:
                return
            try:
                client.create_agent(agent_id=agent_id, pattern="tool")
            except Exception:
                pass
            try:
                client.activate_agent(agent_id, duration_hours=6)
            except Exception:
                pass
            _setup_done = True

    @tool
    def memanto_remember(
        memory_type: Annotated[
            str,
            Field(
                pattern=r"^(fact|preference|goal|decision|artifact|learning|event|instruction|relationship|context|observation|commitment|error)$",
                description=(
                    f"The semantic type of memory to store. Must be exactly one of the types "
                    f"(without the description): fact, preference, goal, decision, artifact, "
                    f"learning, event, instruction, relationship, context, observation, "
                    f"commitment, or error. Context definitions: {VALID_MEMORY_TYPES}"
                ),
            ),
        ],
        title: Annotated[
            str,
            Field(
                description="Short title for the memory (max 100 characters).",
            ),
        ],
        content: Annotated[
            str,
            Field(
                description="The memory content to store (max 10000 characters). Be concise and atomic.",
            ),
        ],
        confidence: Annotated[
            float,
            Field(
                ge=0.0,
                le=1.0,
                description="Confidence score from 0.0 to 1.0. The agent must evaluate the certainty of the memory. Use 1.0 for verified explicit facts, 0.7-0.85 for observations/estimates, and lower for unverified information.",
            ),
        ],
        tags: Annotated[
            str,
            Field(
                description="Comma-separated tags for categorization (e.g. 'market,ai,trend'). Use lowercase.",
            ),
        ] = "",
    ) -> str:
        """
        Store a structured memory in Memanto for long-term persistence.
        Use this to save facts, observations, decisions, preferences, or any
        information that should be available to other agents or future sessions.
        Each memory has a type, title (max 100 chars), content (max 10000 chars),
        confidence score, and optional tags.
        """
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        try:
            result = client.remember(
                agent_id=agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tag_list,
                source="langgraph-agent",
            )
        except Exception:
            _do_setup()
            result = client.remember(
                agent_id=agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tag_list,
                source="langgraph-agent",
            )

        return f"Memory stored: {result['memory_id']}"

    @tool
    def memanto_recall(
        query: Annotated[
            str,
            Field(
                description="Natural language search query to find relevant memories.",
            ),
        ],
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description="Maximum number of memories to retrieve.",
            ),
        ] = 10,
        memory_types: Annotated[
            str,
            Field(
                description=(
                    "Comma-separated memory types to filter by "
                    "(e.g. 'fact,observation'). Leave empty for all types."
                ),
            ),
        ] = "",
    ) -> str:
        """
        Search Memanto's persistent memory database using natural language.
        Returns stored memories ranked by semantic relevance. Use this to
        retrieve facts, research findings, decisions, or any previously
        stored information from any agent that shares this memory namespace.
        """
        type_list = (
            [t.strip() for t in memory_types.split(",") if t.strip()]
            if memory_types
            else None
        )

        try:
            result = client.recall(
                agent_id=agent_id,
                query=query,
                limit=limit,
                type=type_list,
            )
        except Exception:
            _do_setup()
            result = client.recall(
                agent_id=agent_id,
                query=query,
                limit=limit,
                type=type_list,
            )

        memories = result.get("memories", [])
        if not memories:
            return f"No memories found for query: '{query}'"

        lines = [f"Found {len(memories)} memories for '{query}':\n"]
        for i, mem in enumerate(memories, 1):
            title = mem.get("title", "Untitled")
            content = mem.get("content", "")
            mem_type = mem.get("type", "unknown")
            confidence = mem.get("confidence", "N/A")
            tags = mem.get("tags", [])
            tag_str = f" [tags: {', '.join(tags)}]" if tags else ""

            lines.append(
                f"  {i}. [{mem_type}] {title} (confidence: {confidence}){tag_str}\n"
                f"     {content}\n"
            )

        return "\n".join(lines)

    @tool
    def memanto_answer(
        question: Annotated[
            str,
            Field(
                description="A question to answer using RAG over the agent's stored memories.",
            ),
        ],
    ) -> str:
        """
        Ask a question and get an AI-generated answer grounded in the agent's
        stored memories using Retrieval-Augmented Generation (RAG). This is
        useful for synthesizing insights from multiple stored memories into
        a coherent answer.
        """
        try:
            result = client.answer(agent_id=agent_id, question=question)
        except Exception:
            _do_setup()
            result = client.answer(agent_id=agent_id, question=question)

        answer = result.get("answer", "No answer could be generated.")
        sources = result.get("sources", [])

        output = f"Answer: {answer}"
        if sources:
            output += f"\n\nBased on {len(sources)} memory source(s)."

        return output

    return [memanto_remember, memanto_recall, memanto_answer]
