"""
crew/tools.py
=============
CrewAI BaseTool wrappers around MeMantoCrewMemory operations.
Each tool is bound to a shared memory instance so all agents in the
crew read and write to the same Memanto namespace.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from memanto_bridge import MeMantoCrewMemory


# ── Input schemas ──────────────────────────────────────────────────────────


class StoreInput(BaseModel):
    content: str = Field(description="The finding, fact, or decision to persist.")
    tags: List[str] = Field(default=[], description="Optional topic tags.")


class RecallInput(BaseModel):
    query: str = Field(description="Natural-language question to search memories for.")
    limit: int = Field(default=5, description="Max memories to return.")


class CorrectInput(BaseModel):
    memory_id: str = Field(description="ID of the memory to correct (from a prior recall).")
    new_content: str = Field(description="The corrected, up-to-date fact.")


class AnswerInput(BaseModel):
    question: str = Field(description="Question to answer using stored memories (RAG).")


# ── Tool factory ───────────────────────────────────────────────────────────


def build_tools(shared_memory: "MeMantoCrewMemory", agent_name: str):
    """
    Build and return all Memanto-powered tools bound to a shared memory instance.

    Args:
        shared_memory: The MeMantoCrewMemory instance shared across the crew.
        agent_name:    Name tag stored alongside every memory this agent writes.

    Returns:
        Tuple: (StoreFindingTool, RecallMemoryTool, CorrectMemoryTool, AnswerTool)
    """

    class StoreFindingTool(BaseTool):
        name: str = "store_finding"
        description: str = (
            "Persist a research finding, fact, or decision to Memanto permanent memory. "
            "Call this whenever you discover something worth remembering across sessions. "
            "Returns the memory ID which can be used later to correct it if needed."
        )
        args_schema: type[BaseModel] = StoreInput

        def _run(self, content: str, tags: List[str] = []) -> str:
            mem = shared_memory.store_finding(content=content, agent=agent_name, tags=tags)
            mem_id = mem.get("id", "unknown")
            return (
                f"✅ Memory stored (id={mem_id}).\n"
                f"   Content: {content[:120]}{'…' if len(content) > 120 else ''}\n"
                f"   Save this ID to correct it later: {mem_id}"
            )

    class RecallMemoryTool(BaseTool):
        name: str = "recall_memory"
        description: str = (
            "Search Memanto permanent memory for relevant findings from any agent or session. "
            "ALWAYS call this FIRST before starting research — avoids duplicating work already done. "
            "Returns memories with their IDs (needed if you want to correct one)."
        )
        args_schema: type[BaseModel] = RecallInput

        def _run(self, query: str, limit: int = 5) -> str:
            results = shared_memory.recall_findings(query=query, limit=limit)
            if not results:
                return "📭 No relevant memories found. You are starting fresh on this topic."
            lines = [
                f"  [{r['id']}] {r['memory'][:200]}{'…' if len(r['memory']) > 200 else ''}"
                for r in results
            ]
            return "📚 Retrieved memories:\n" + "\n".join(lines)

    class CorrectMemoryTool(BaseTool):
        name: str = "correct_memory"
        description: str = (
            "Overwrite a previously stored memory with new, contradictory information. "
            "Use when you discover an existing memory is outdated or wrong. "
            "The old content is preserved in the audit trail — only the active fact changes."
        )
        args_schema: type[BaseModel] = CorrectInput

        def _run(self, memory_id: str, new_content: str) -> str:
            updated = shared_memory.correct_memory(memory_id=memory_id, new_fact=new_content)
            return (
                f"🔄 Memory corrected (id={memory_id}).\n"
                f"   New fact: {new_content[:120]}{'…' if len(new_content) > 120 else ''}\n"
                f"   Old content archived in audit metadata."
            )

    class AnswerTool(BaseTool):
        name: str = "answer_from_memory"
        description: str = (
            "Generate a grounded answer to a question using Memanto's built-in RAG. "
            "Use this to synthesize stored findings into a coherent answer without hallucinating."
        )
        args_schema: type[BaseModel] = AnswerInput

        def _run(self, question: str) -> str:
            answer = shared_memory.answer(question)
            return f"🧠 Memory-grounded answer:\n{answer}" if answer else "No answer generated."

    return StoreFindingTool(), RecallMemoryTool(), CorrectMemoryTool(), AnswerTool()
