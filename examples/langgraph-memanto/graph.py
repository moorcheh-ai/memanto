"""
LangGraph workflow that keeps long-term memory outside graph state.

LangGraph's checkpointer remembers the current thread. Memanto remembers facts
that should survive when the next run uses a brand-new thread id.
"""

from __future__ import annotations

from typing import Any, TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by users
    if exc.name == "langgraph":
        raise RuntimeError(
            "Install this example's dependencies first: "
            "pip install -r examples/langgraph-memanto/requirements.txt"
        ) from exc
    raise

from memory_store import Memory, MemoryStore


class RecruitingState(TypedDict, total=False):
    user_message: str
    thread_id: str
    recalled_memories: list[dict[str, Any]]
    answer: str
    stored_memories: list[dict[str, Any]]


def build_recruiting_graph(store: MemoryStore):
    workflow = StateGraph(RecruitingState)

    def recall_context(state: RecruitingState) -> RecruitingState:
        memories = store.recall(
            state["user_message"],
            limit=5,
            memory_types=["fact", "preference", "commitment", "instruction"],
        )
        return {"recalled_memories": [memory.to_dict() for memory in memories]}

    def draft_answer(state: RecruitingState) -> RecruitingState:
        recalled = state.get("recalled_memories", [])
        fresh_memories = _extract_candidate_memories(state["user_message"])

        if recalled:
            bullets = "\n".join(
                f"- {item['title']}: {item['content']}" for item in recalled
            )
            answer = (
                "This is a fresh LangGraph thread, but Memanto recalled "
                "yesterday's durable context:\n"
                f"{bullets}\n\n"
                "Interview prep: start with a concise systems question, schedule "
                "after 14:00 UTC, and send the promised take-home by Friday."
            )
        elif fresh_memories:
            answer = (
                "I captured the candidate details and will store them in Memanto "
                "so a later LangGraph thread can recall them without receiving "
                "this message again."
            )
        else:
            answer = "No matching long-term memory was found for this thread yet."

        return {"answer": answer}

    def write_followup_memory(state: RecruitingState) -> RecruitingState:
        memories = _extract_candidate_memories(state["user_message"])
        stored = [store.remember(memory).to_dict() for memory in memories]
        return {"stored_memories": stored}

    workflow.add_node("recall_context", recall_context)
    workflow.add_node("draft_answer", draft_answer)
    workflow.add_node("write_followup_memory", write_followup_memory)

    workflow.add_edge(START, "recall_context")
    workflow.add_edge("recall_context", "draft_answer")
    workflow.add_edge("draft_answer", "write_followup_memory")
    workflow.add_edge("write_followup_memory", END)

    return workflow.compile(checkpointer=MemorySaver())


def _extract_candidate_memories(message: str) -> list[Memory]:
    lower = message.lower()
    if "maya chen" not in lower:
        return []

    return [
        Memory(
            memory_type="fact",
            title="Maya Chen role",
            content=(
                "Yesterday's intake said Maya Chen is interviewing for the "
                "Staff AI Platform role."
            ),
            confidence=0.96,
            tags=["maya-chen", "candidate", "role"],
        ),
        Memory(
            memory_type="preference",
            title="Maya Chen interview style",
            content=(
                "Maya Chen prefers concise technical deep-dives over broad "
                "introductory prompts."
            ),
            confidence=0.92,
            tags=["maya-chen", "preference", "interview-style"],
        ),
        Memory(
            memory_type="fact",
            title="Maya Chen availability",
            content="Maya Chen is available after 14:00 UTC for interviews.",
            confidence=0.9,
            tags=["maya-chen", "schedule"],
        ),
        Memory(
            memory_type="commitment",
            title="Maya Chen take-home commitment",
            content="The team promised Maya Chen a take-home exercise by Friday.",
            confidence=0.94,
            tags=["maya-chen", "commitment", "take-home"],
        ),
    ]
