from __future__ import annotations

from typing import TypedDict

from memory_backends import MemoryBackend, MemoryItem


class SupportState(TypedDict, total=False):
    agent_id: str
    customer_id: str
    ticket: str
    session_label: str
    should_store: bool
    recalled_memories: list[MemoryItem]
    stored_memories: list[MemoryItem]
    action: str
    reply: str


def build_support_graph(backend: MemoryBackend):
    from langgraph.graph import END, StateGraph

    graph = StateGraph(SupportState)

    def load_ticket(state: SupportState) -> SupportState:
        ticket = state.get("ticket") or (
            "Customer Ada asks whether her analytics export can be sent by email "
            "and whether the response can avoid marketing language."
        )
        return {
            **state,
            "customer_id": state.get("customer_id", "ada-lovelace"),
            "ticket": ticket,
        }

    def recall_customer_context(state: SupportState) -> SupportState:
        query = (
            f"{state['customer_id']} preferences plan timezone email concise "
            f"support context for ticket: {state['ticket']}"
        )
        memories = backend.recall(
            agent_id=state["agent_id"],
            query=query,
            limit=5,
        )
        return {**state, "recalled_memories": memories}

    def choose_action(state: SupportState) -> SupportState:
        memory_text = " ".join(memory.content.lower() for memory in state["recalled_memories"])
        if "email" in memory_text and "concise" in memory_text:
            action = "draft_concise_email_first_reply"
        elif state["recalled_memories"]:
            action = "draft_personalized_reply"
        else:
            action = "ask_clarifying_question"
        return {**state, "action": action}

    def store_profile_memories(state: SupportState) -> SupportState:
        if not state.get("should_store", False):
            return {**state, "stored_memories": []}

        memories = [
            {
                "memory_type": "preference",
                "title": "Ada prefers concise support replies",
                "content": (
                    "Customer ada-lovelace prefers concise, direct support replies "
                    "without marketing language."
                ),
                "tags": ["ada-lovelace", "support", "tone"],
            },
            {
                "memory_type": "preference",
                "title": "Ada wants email delivery",
                "content": (
                    "Customer ada-lovelace prefers analytics exports and follow-up "
                    "instructions delivered by email."
                ),
                "tags": ["ada-lovelace", "delivery", "email"],
            },
            {
                "memory_type": "fact",
                "title": "Ada is on the Pro plan",
                "content": (
                    "Customer ada-lovelace is on the Pro plan and can use scheduled "
                    "analytics exports."
                ),
                "tags": ["ada-lovelace", "plan", "analytics"],
            },
        ]

        stored = [
            backend.remember(
                agent_id=state["agent_id"],
                memory_type=item["memory_type"],
                title=item["title"],
                content=item["content"],
                confidence=0.95,
                tags=item["tags"],
            )
            for item in memories
        ]
        return {**state, "stored_memories": stored}

    def draft_reply(state: SupportState) -> SupportState:
        if not state["recalled_memories"]:
            reply = (
                "I can help set that up. Which email address should receive the "
                "analytics export?"
            )
            return {**state, "reply": reply}

        bullets = [
            f"- {memory.title}: {memory.content}"
            for memory in state["recalled_memories"][:3]
        ]
        reply = "\n".join(
            [
                "Hi Ada,",
                "",
                "Yes. Since you are on the Pro plan, I can keep this concise and "
                "set the analytics export to be delivered by email.",
                "",
                "I used these recalled memories:",
                *bullets,
                "",
                "Next step: confirm the destination email address and export cadence.",
            ]
        )
        return {**state, "reply": reply}

    graph.add_node("load_ticket", load_ticket)
    graph.add_node("recall_customer_context", recall_customer_context)
    graph.add_node("choose_action", choose_action)
    graph.add_node("store_profile_memories", store_profile_memories)
    graph.add_node("draft_reply", draft_reply)

    graph.set_entry_point("load_ticket")
    graph.add_edge("load_ticket", "recall_customer_context")
    graph.add_edge("recall_customer_context", "choose_action")
    graph.add_edge("choose_action", "store_profile_memories")
    graph.add_edge("store_profile_memories", "draft_reply")
    graph.add_edge("draft_reply", END)

    return graph.compile()


def print_run_summary(result: SupportState) -> None:
    print(f"Session: {result.get('session_label', 'demo')}")
    print(f"Customer: {result['customer_id']}")
    print(f"Action: {result['action']}")
    print(f"Stored memories: {len(result.get('stored_memories', []))}")
    print(f"Recalled memories: {len(result.get('recalled_memories', []))}")

    if result.get("stored_memories"):
        print("\nStored:")
        for memory in result["stored_memories"]:
            print(f"- {memory.type}: {memory.title} [{memory.id}]")

    if result.get("recalled_memories"):
        print("\nRecalled:")
        for memory in result["recalled_memories"]:
            print(f"- {memory.type}: {memory.title} (score={memory.score:.2f})")

    print("\nReply:")
    print(result["reply"])
