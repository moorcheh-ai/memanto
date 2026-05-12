"""
LangGraph + Memanto: Customer Support Agent with Persistent Memory

Demonstrates Cross-Session Recall: the agent remembers customer preferences
and past issues from previous sessions stored in Memanto.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from memanto.app.clients.sdk_client import SdkClient
from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.constants import MemoryType, ScopeType, SourceType
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Memanto helpers
# ---------------------------------------------------------------------------

AGENT_ID = "langgraph-support-bot"


def _scope(customer_id: str) -> MemoryScope:
    return MemoryScope(scope_type=ScopeType.agent, scope_id=customer_id)


def remember(
    client: SdkClient,
    customer_id: str,
    title: str,
    content: str,
    memory_type: MemoryType = "fact",
) -> None:
    """Store a memory about the customer in Memanto."""
    scope = _scope(customer_id)
    record = MemoryRecord(
        type=memory_type,
        title=title,
        content=content,
        scope_type=scope.scope_type,
        scope_id=scope.scope_id,
        actor_id=AGENT_ID,
        source=SourceType.conversation,
        confidence=0.9,
    )
    client.store(record.to_moorcheh_document(), namespace=scope.to_namespace())


def recall(client: SdkClient, customer_id: str, query: str, top_k: int = 5) -> str:
    """Retrieve relevant memories about the customer from Memanto."""
    scope = _scope(customer_id)
    results = client.search(query, namespace=scope.to_namespace(), top_k=top_k)
    if not results:
        return "No memories found for this customer."
    lines = []
    for r in results:
        text = r.get("text", "")
        score = r.get("score", 0.0)
        lines.append(f"[score={score:.2f}] {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class SupportState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    customer_id: str
    past_memories: str
    new_memory_title: str | None
    new_memory_content: str | None


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def recall_node(state: SupportState, client: SdkClient) -> dict[str, Any]:
    """Retrieve cross-session memories before responding."""
    last_user_msg = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )
    memories = recall(client, state["customer_id"], query=last_user_msg)
    return {"past_memories": memories}


def respond_node(state: SupportState, llm: ChatOpenAI) -> dict[str, Any]:
    """Generate a response using retrieved memories as context."""
    system_prompt = (
        "You are a helpful customer support agent with access to persistent memory "
        "about each customer. Use the retrieved memories to personalise your responses.\n\n"
        f"Customer ID: {state['customer_id']}\n\n"
        f"== Past memories from previous sessions ==\n{state['past_memories']}\n"
        "== End of memories ==\n\n"
        "Based on the above context, answer the customer's latest message. "
        "After answering, identify ONE key fact worth remembering from this conversation "
        "and append it as:\nREMEMBER_TITLE: <short title>\nREMEMBER_CONTENT: <content>"
    )
    messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
    response = llm.invoke(messages)

    # Parse memory extraction from response
    raw = response.content
    title: str | None = None
    content: str | None = None
    if "REMEMBER_TITLE:" in raw and "REMEMBER_CONTENT:" in raw:
        try:
            after_title = raw.split("REMEMBER_TITLE:")[1]
            title = after_title.split("\n")[0].strip()
            content = raw.split("REMEMBER_CONTENT:")[1].strip().split("\n")[0].strip()
            # Strip memory extraction from displayed message
            display_text = raw.split("REMEMBER_TITLE:")[0].strip()
            response = AIMessage(content=display_text)
        except (IndexError, ValueError):
            pass

    return {
        "messages": [response],
        "new_memory_title": title,
        "new_memory_content": content,
    }


def remember_node(state: SupportState, client: SdkClient) -> dict[str, Any]:
    """Persist a new memory to Memanto for future sessions."""
    if state.get("new_memory_title") and state.get("new_memory_content"):
        remember(
            client,
            state["customer_id"],
            title=state["new_memory_title"],
            content=state["new_memory_content"],
        )
    return {}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph(client: SdkClient, llm: ChatOpenAI) -> Any:
    """Build and compile the LangGraph support agent."""
    builder = StateGraph(SupportState)

    builder.add_node("recall", lambda s: recall_node(s, client))
    builder.add_node("respond", lambda s: respond_node(s, llm))
    builder.add_node("remember", lambda s: remember_node(s, client))

    builder.set_entry_point("recall")
    builder.add_edge("recall", "respond")
    builder.add_edge("respond", "remember")
    builder.add_edge("remember", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()

    moorcheh_key = os.environ.get("MOORCHEH_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not moorcheh_key or not openai_key:
        raise SystemExit(
            "Set MOORCHEH_API_KEY and OPENAI_API_KEY in your .env file."
        )

    client = SdkClient(api_key=moorcheh_key)
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key)
    graph = build_graph(client, llm)

    customer_id = os.environ.get("CUSTOMER_ID", "demo-customer-001")

    print(f"\n{'=' * 60}")
    print("  LangGraph + Memanto: Customer Support Agent")
    print(f"  Customer ID : {customer_id}")
    print(f"  (memories persist across sessions via Memanto)")
    print(f"{'=' * 60}\n")

    user_message = os.environ.get(
        "USER_MESSAGE",
        "Hi, I prefer dark mode and I'm having issues with my subscription renewal.",
    )

    print(f"User: {user_message}\n")

    result = graph.invoke(
        {
            "messages": [HumanMessage(content=user_message)],
            "customer_id": customer_id,
            "past_memories": "",
            "new_memory_title": None,
            "new_memory_content": None,
        }
    )

    final_msg = result["messages"][-1]
    print(f"Agent: {final_msg.content}\n")
    if result.get("new_memory_title"):
        print(f"[Memory saved] {result['new_memory_title']}")


if __name__ == "__main__":
    main()
