#!/usr/bin/env python3
"""LangGraph + Memanto persistent memory demo.

The graph is intentionally deterministic so the integration can be reviewed
without needing an LLM key. In normal mode it uses Memanto's SdkClient. In
preview mode it writes the same memory records to a local JSON file so the
LangGraph flow can be tested without external credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, TypedDict

AGENT_ID = "langgraph-support-memanto-demo"
PREVIEW_STORE = Path(".langgraph_memanto_preview.json")


class SupportState(TypedDict, total=False):
    customer: str
    message: str
    recalled_memories: list[dict[str, Any]]
    intent: str
    memory_to_store: dict[str, Any] | None
    stored_memory: dict[str, Any] | None
    response: str


class LocalPreviewMemory:
    """Small local store with the same shape used by the Memanto wrapper."""

    def __init__(self, path: Path = PREVIEW_STORE) -> None:
        self.path = path

    def setup(self) -> None:
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")
        print(f"Using local preview memory store: {self.path}")

    def recall(self, customer: str, query: str) -> list[dict[str, Any]]:
        del query
        memories = self._load()
        return [
            memory
            for memory in memories
            if customer.lower() in " ".join(memory.get("tags", [])).lower()
            or customer.lower() in memory.get("content", "").lower()
        ][:5]

    def remember(self, memory: dict[str, Any]) -> dict[str, Any]:
        memories = self._load()
        result = {
            "memory_id": f"preview-{len(memories) + 1}",
            "status": "stored",
            **memory,
        }
        memories.append(result)
        self.path.write_text(json.dumps(memories, indent=2) + "\n", encoding="utf-8")
        return result

    def _load(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))


class MemantoMemory:
    """Memanto-backed memory adapter used by the LangGraph nodes."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        self.api_key = api_key
        self.agent_id = agent_id
        self.client: Any | None = None

    def setup(self) -> None:
        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        self.client = SdkClient(self.api_key)
        try:
            self.client.create_agent(
                self.agent_id,
                pattern="support",
                description="LangGraph support agent with durable Memanto memory",
            )
            print(f"Created Memanto agent: {self.agent_id}")
        except AgentAlreadyExistsError:
            print(f"Using existing Memanto agent: {self.agent_id}")

        self.client.activate_agent(self.agent_id)
        print("Activated Memanto session")

    def recall(self, customer: str, query: str) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("MemantoMemory.setup() must be called before recall().")

        result = self.client.recall(
            agent_id=self.agent_id,
            query=f"{customer}: {query}",
            limit=5,
            tags=[customer.lower()],
        )
        return list(result.get("memories", []))

    def remember(self, memory: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("MemantoMemory.setup() must be called before remember().")

        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory["type"],
            title=memory["title"],
            content=memory["content"],
            confidence=memory["confidence"],
            tags=memory["tags"],
            source="langgraph-demo",
            provenance="explicit_statement",
        )


def build_graph(memory: LocalPreviewMemory | MemantoMemory):
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise SystemExit(
            "LangGraph is not installed. Run `pip install -r requirements.txt` first."
        ) from exc

    def recall_customer_context(state: SupportState) -> SupportState:
        memories = memory.recall(state["customer"], state["message"])
        return {"recalled_memories": memories}

    def classify_request(state: SupportState) -> SupportState:
        message = state["message"].lower()
        customer = state["customer"]

        if "prefers" in message or "wants" in message or "needs" in message:
            return {
                "intent": "capture_customer_context",
                "memory_to_store": {
                    "type": "preference",
                    "title": f"{customer} deployment preference",
                    "content": state["message"],
                    "confidence": 0.92,
                    "tags": [customer.lower(), "deployment", "support"],
                },
            }

        return {"intent": "answer_with_memory", "memory_to_store": None}

    def store_memory(state: SupportState) -> SupportState:
        memory_to_store = state.get("memory_to_store")
        if not memory_to_store:
            return {"stored_memory": None}

        return {"stored_memory": memory.remember(memory_to_store)}

    def draft_response(state: SupportState) -> SupportState:
        stored_memory = state.get("stored_memory")
        recalled_memories = state.get("recalled_memories", [])

        if stored_memory:
            response = (
                f"I saved {state['customer']}'s deployment preference and "
                "communication requirement so future support turns can use it "
                "without asking again."
            )
        elif recalled_memories:
            response = format_recommendation(state["customer"], recalled_memories)
        else:
            response = (
                "I do not have durable customer context yet. Ask one clarifying "
                "question, then store the answer as Memanto memory."
            )

        return {"response": response}

    graph = StateGraph(SupportState)
    graph.add_node("recall_customer_context", recall_customer_context)
    graph.add_node("classify_request", classify_request)
    graph.add_node("store_memory", store_memory)
    graph.add_node("draft_response", draft_response)
    graph.set_entry_point("recall_customer_context")
    graph.add_edge("recall_customer_context", "classify_request")
    graph.add_edge("classify_request", "store_memory")
    graph.add_edge("store_memory", "draft_response")
    graph.add_edge("draft_response", END)
    return graph.compile()


def format_recommendation(customer: str, memories: list[dict[str, Any]]) -> str:
    combined = " ".join(memory.get("content", "") for memory in memories).lower()
    details: list[str] = []

    if "hosted" in combined:
        details.append("the hosted deployment path")
    if "soc 2" in combined:
        details.append("SOC 2 compliance")
    if "email" in combined:
        details.append("async email updates after each deployment step")

    if not details:
        return f"Use the recalled {customer} context to answer the support request."

    first, *rest = details
    if rest:
        return f"Recommend {first} for {customer}, emphasize {', and '.join(rest)}."
    return f"Recommend {first} for {customer}."


def scenario(mode: str) -> SupportState:
    if mode == "seed":
        return {
            "customer": "ACME",
            "message": (
                "ACME prefers hosted deployments that are SOC 2 compliant. "
                "They want async email updates after each deployment step."
            ),
        }

    return {
        "customer": "ACME",
        "message": "ACME is asking which deployment path we recommend before launch.",
    }


def print_result(result: SupportState) -> None:
    print(f"\nCustomer: {result['customer']}")
    print(f"Message: {result['message']}")

    print("\nRecalled memories:")
    memories = result.get("recalled_memories", [])
    if memories:
        for memory in memories:
            print(
                f"- {memory.get('title', 'Untitled')}: "
                f"{memory.get('content', '')}"
            )
    else:
        print("- No previous memories found.")

    print("\nGraph classification:")
    print(f"- intent: {result.get('intent', 'unknown')}")
    print(
        "- should_store_memory: "
        f"{'yes' if result.get('memory_to_store') else 'no'}"
    )

    stored_memory = result.get("stored_memory")
    if stored_memory:
        print("\nStored memory:")
        print(f"- {stored_memory.get('title', stored_memory.get('memory_id'))}")

    print("\nAssistant response:")
    print(result.get("response", ""))


def run_once(memory: LocalPreviewMemory | MemantoMemory, mode: str) -> SupportState:
    app = build_graph(memory)
    return app.invoke(scenario(mode))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["seed", "follow-up", "full"],
        default="full",
        help="Run the seed turn, follow-up turn, or both turns.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_AGENT_ID", AGENT_ID),
        help="Memanto agent id to create/use.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Use a local JSON preview store instead of the Memanto API.",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv:
        load_dotenv()
    api_key = os.environ.get("MOORCHEH_API_KEY")
    use_preview = args.preview or not api_key

    if use_preview:
        if not args.preview:
            print("MOORCHEH_API_KEY is not set; running local preview mode.")
        memory: LocalPreviewMemory | MemantoMemory = LocalPreviewMemory()
    else:
        memory = MemantoMemory(api_key=api_key or "", agent_id=args.agent_id)

    memory.setup()

    modes = ["seed", "follow-up"] if args.mode == "full" else [args.mode]
    for index, mode in enumerate(modes):
        if index:
            print("\n" + "=" * 72)
        print_result(run_once(memory, mode))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
