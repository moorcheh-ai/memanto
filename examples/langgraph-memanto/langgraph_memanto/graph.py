"""Re-usable LangGraph graph builder for Memanto-backed agents."""

from __future__ import annotations

from typing import Annotated

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from langgraph_memanto.tools import memanto_recall, memanto_remember
from memanto.cli.client.sdk_client import SdkClient


class MemantoState(BaseModel):
    """Shared state for a Memanto-backed LangGraph agent."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(
        default_factory=list,
        description="Conversation history.",
    )
    user_id: str = Field(default="", description="Identifier for the end-user.")
    intent: str = Field(default="", description="Classified intent of the last user message.")
    retrieved_memories: str = Field(
        default="",
        description="Raw text of memories recalled from Memanto.",
    )
    done: bool = Field(default=False, description="Set to True when the workflow should end.")


def build_customer_support_graph(
    llm: BaseChatModel,
    client: SdkClient,
    agent_id: str,
) -> StateGraph:
    """Build a StateGraph for a customer-support agent with long-term memory.

    The graph follows a 4-step pipeline:

    1. **classify_intent** — LLM decides whether the user is reporting a
       *technical_issue*, asking a *billing_question*, making a
       *feature_request*, or just *general_chat*.
    2. **fetch_context** — Recalls previous memories for this ``user_id``
       that match the classified intent.
    3. **generate_response** — LLM drafts a reply that explicitly references
       retrieved memories (if any).
    4. **persist_memory** — Stores salient facts from the latest exchange so
       they survive across sessions.

    Args:
        llm: Any LangChain-compatible chat model (e.g. ChatOpenAI,
            ChatAnthropic, ChatOpenRouter).
        client: Active Memanto :class:`SdkClient`.
        agent_id: Memanto namespace for this agent.

    Returns:
        A compiled LangGraph state graph ready for ``graph.invoke(state)``.
    """

    def classify_intent(state: MemantoState) -> dict:
        """Node 1 — classify the user's intent."""
        if not state.messages:
            return {"intent": "general_chat", "done": True}

        last_msg = state.messages[-1]
        if not isinstance(last_msg, HumanMessage):
            return {"intent": state.intent}

        system = SystemMessage(
            content=(
                "You are an intent-classifier for a customer-support system.\n"
                "Reply with EXACTLY ONE word from this list:\n"
                "  technical_issue, billing_question, feature_request, general_chat\n"
                "No punctuation, no explanation."
            )
        )
        response = llm.invoke([system, HumanMessage(content=last_msg.content)])
        intent = response.content.strip().lower().split()[0]
        valid = {"technical_issue", "billing_question", "feature_request", "general_chat"}
        if intent not in valid:
            intent = "general_chat"
        return {"intent": intent}

    def fetch_context(state: MemantoState) -> dict:
        """Node 2 — recall memories for this user + intent."""
        query = f"{state.intent} for user {state.user_id}"
        memories = memanto_recall(
            client=client,
            agent_id=agent_id,
            query=query,
            limit=5,
        )
        return {"retrieved_memories": memories}

    def generate_response(state: MemantoState) -> dict:
        """Node 3 — draft a response using retrieved memories."""
        system_parts = [
            "You are a helpful customer-support agent.\n",
            "You have access to the user's conversation history and past memories.\n",
        ]
        if state.retrieved_memories and "No memories found" not in state.retrieved_memories:
            system_parts.append(
                "The following memories were retrieved for this user:\n"
                f"{state.retrieved_memories}\n"
            )
        else:
            system_parts.append("No prior memories found for this user.\n")

        system_parts.append(
            "Instructions:\n"
            "- Be concise (3-5 sentences).\n"
            "- If a memory directly answers the question, cite it.\n"
            "- If you need more info, ask a clarifying question.\n"
            "- Never make up facts that aren't in the memories or current message."
        )

        system = SystemMessage(content="".join(system_parts))
        response = llm.invoke([system, *state.messages])
        return {"messages": [response]}

    def persist_memory(state: MemantoState) -> dict:
        """Node 4 — extract and store facts that should survive across sessions."""
        if not state.messages or len(state.messages) < 2:
            return {}

        last_human = None
        last_ai = None
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage) and last_human is None:
                last_human = msg
            elif isinstance(msg, AIMessage) and last_ai is None:
                last_ai = msg
            if last_human and last_ai:
                break

        if not last_human:
            return {}

        extraction_prompt = SystemMessage(
            content=(
                "You are a memory-extraction engine.\n"
                "Given the latest user message and your reply, produce 0-3 atomic facts\n"
                "that should be stored as long-term memory.\n\n"
                "Rules:\n"
                "- Only extract explicit facts, preferences, or decisions.\n"
                "- Do NOT store greetings, pleasantries, or transient info.\n"
                "- Format: 'memory_type | title | content' (one per line).\n"
                "- Valid memory_types: preference, fact, goal, decision, issue.\n"
                "- If nothing worth storing, reply 'NONE'."
            )
        )
        extraction_input = HumanMessage(
            content=f"User: {last_human.content}\nAgent: {last_ai.content if last_ai else 'N/A'}"
        )
        extraction = llm.invoke([extraction_prompt, extraction_input])
        raw = extraction.content.strip()

        if raw.upper() == "NONE" or not raw:
            return {}

        stored = 0
        for line in raw.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) != 3:
                continue
            mem_type, title, content = parts
            try:
                memanto_remember(
                    client=client,
                    agent_id=agent_id,
                    memory_type=mem_type,
                    title=title[:100],
                    content=content[:500],
                    confidence=0.85,
                    tags=["customer_support", state.intent, f"user:{state.user_id}"],
                )
                stored += 1
            except Exception:
                pass  # best-effort; don't crash the chat flow

        return {}

    # ------------------------------------------------------------------
    # Assemble graph
    # ------------------------------------------------------------------
    builder = StateGraph(MemantoState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("fetch_context", fetch_context)
    builder.add_node("generate_response", generate_response)
    builder.add_node("persist_memory", persist_memory)

    builder.set_entry_point("classify_intent")
    builder.add_edge("classify_intent", "fetch_context")
    builder.add_edge("fetch_context", "generate_response")
    builder.add_edge("generate_response", "persist_memory")
    builder.add_edge("persist_memory", END)

    return builder.compile()
