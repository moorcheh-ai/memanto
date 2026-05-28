from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

load_dotenv()


class GraphState(TypedDict):
    prompt: str
    recalled_context: str
    answer: str
    memory_to_store: str


@dataclass
class MemantoMemory:
    client: SdkClient
    agent_id: str

    @classmethod
    def from_env(cls) -> MemantoMemory:
        api_key = os.environ["MOORCHEH_API_KEY"]
        agent_id = os.getenv("MEMANTO_AGENT_ID", "langgraph-memanto-demo")
        client = SdkClient(api_key=api_key)

        try:
            client.create_agent(
                agent_id=agent_id,
                pattern="project",
                description="LangGraph example that persists project decisions across sessions.",
            )
        except AgentAlreadyExistsError:
            pass

        client.activate_agent(agent_id, duration_hours=6)
        return cls(client=client, agent_id=agent_id)

    def remember_decision(self, content: str) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type="decision",
            title="Project architecture decision",
            content=content,
            confidence=0.95,
            tags=["langgraph", "architecture", "demo"],
            source="langgraph-demo",
            provenance="explicit_statement",
        )

    def recall(self, query: str, limit: int = 5) -> str:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=["decision", "preference", "fact", "context"],
        )
        memories = result.get("memories", [])
        if not memories:
            return "No relevant long-term memories found."

        lines = []
        for item in memories:
            memory_type = item.get("type", "memory")
            content = item.get("content") or item.get("title") or ""
            lines.append(f"- [{memory_type}] {content}")
        return "\n".join(lines)


def build_graph(memory: MemantoMemory):
    graph = StateGraph(GraphState)

    def recall_context(state: GraphState) -> GraphState:
        return {
            **state,
            "recalled_context": memory.recall(state["prompt"]),
        }

    def answer_with_context(state: GraphState) -> GraphState:
        prompt = state["prompt"]
        context = state["recalled_context"]
        if "No relevant long-term memories found." in context:
            recommendation = (
                "I do not have a stored long-term decision for this yet. "
                "Run day 1 first so the graph can persist the project decision."
            )
        else:
            recommendation = (
                "Use the stored long-term decision from Memanto. "
                "For this demo, that means keeping the audit-log backend on "
                "PostgreSQL because the earlier session saved that compliance "
                "and export requirements drove the choice."
            )
        answer = (
            "I checked long-term Memanto memory before answering.\n\n"
            f"Relevant memory:\n{context}\n\n"
            f"Question: {prompt}\n"
            f"Answer: {recommendation}"
        )
        return {**state, "answer": answer}

    def persist_new_memory(state: GraphState) -> GraphState:
        memory_to_store = state.get("memory_to_store", "").strip()
        if memory_to_store:
            memory.remember_decision(memory_to_store)
        return state

    graph.add_node("recall_context", recall_context)
    graph.add_node("answer_with_context", answer_with_context)
    graph.add_node("persist_new_memory", persist_new_memory)

    graph.set_entry_point("recall_context")
    graph.add_edge("recall_context", "answer_with_context")
    graph.add_edge("answer_with_context", "persist_new_memory")
    graph.add_edge("persist_new_memory", END)

    return graph.compile()
