"""
LangGraph + Memanto: Customer Support Agent with Persistent Memory

A LangGraph-based customer support agent that uses Memanto as its
long-term memory layer. Demonstrates cross-session recall.

Graph: START -> intake -> respond -> remember -> END
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from memanto.cli.client.sdk_client import SdkClient
from memanto.app.utils.errors import AgentAlreadyExistsError


AGENT_ID = "langgraph-customer-support"
MODEL_NAME = os.environ.get("LG_MODEL", "gpt-4o-mini")


class MemantoMemoryManager:
    """Manages Memanto agent lifecycle and memory operations."""

    def __init__(self, api_key: str, agent_id: str = AGENT_ID):
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id

    def setup(self, duration_hours: int = 6) -> None:
        """Create agent (if needed) and activate a session."""
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="Customer support agent with persistent cross-session memory",
            )
            print(f"[memanto] Created agent {self.agent_id}")
        except AgentAlreadyExistsError:
            print(f"[memanto] Agent {self.agent_id} already exists, reusing")
        except Exception as e:
            print(f"[memanto] Warning: could not create agent: {e}")
        self.client.activate_agent(self.agent_id, duration_hours=duration_hours)
        print(f"[memanto] Activated session for {self.agent_id}")

    def teardown(self) -> None:
        """Deactivate the agent session."""
        try:
            self.client.deactivate_agent(self.agent_id)
            print(f"[memanto] Deactivated session for {self.agent_id}")
        except Exception as e:
            print(f"[memanto] Warning: teardown failed: {e}")

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve relevant memories from Memanto."""
        try:
            result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
            return result.get("memories", [])
        except Exception as e:
            print(f"[memanto] Recall error: {e}")
            return []

    def remember(self, memory_type: str, title: str, content: str,
                 confidence: float = 0.9, tags: list[str] | None = None
                 ) -> dict[str, Any] | None:
        """Store a memory in Memanto."""
        try:
            result = self.client.remember(
                agent_id=self.agent_id, memory_type=memory_type,
                title=title, content=content, confidence=confidence,
                tags=tags or [], source="langgraph-cs-agent",
                provenance="explicit_statement",
            )
            mid = result.get("memory_id", "unknown")
            print(f"[memanto] Stored memory: {mid}")
            return result
        except Exception as e:
            print(f"[memanto] Remember error: {e}")
            return None

    def answer(self, question: str) -> str:
        """Get a RAG-grounded answer from Memanto memories."""
        try:
            result = self.client.answer(agent_id=self.agent_id, question=question)
            return result.get("answer", "")
        except Exception as e:
            print(f"[memanto] Answer error: {e}")
            return ""


class SupportState(TypedDict):
    """State for the customer support LangGraph workflow."""

    messages: Annotated[list, add_messages]
    recalled_context: str
    intent: str
    response: str
    memories_to_store: list[dict[str, Any]]


def intake_node(state: SupportState, *, memory: MemantoMemoryManager, llm: ChatOpenAI) -> dict:
    """Classify the customer message and recall relevant memories from Memanto."""
    last_message = state["messages"][-1].content if state["messages"] else ""

    memories = memory.recall(last_message, limit=5)

    recalled_lines = []
    for mem in memories:
        title = mem.get("title", "Untitled")
        content = mem.get("content", "")
        mem_type = mem.get("type", "unknown")
        confidence = mem.get("confidence", "N/A")
        recalled_lines.append(
            f"- [{mem_type}] {title} (confidence: {confidence}): {content}"
        )

    NL = chr(10)
    recalled_context = NL.join(recalled_lines) if recalled_lines else "No prior memories found."

    classification_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a customer support intent classifier. "
            "Classify the customer message into exactly one of: "
            "billing, technical, account, general, complaint, followup. "
            "Respond with ONLY the category name."
        )),
        ("human", "{message}"),
    ])

    chain = classification_prompt | llm
    intent = chain.invoke({"message": last_message}).content.strip().lower()

    print(f"[intake] Intent: {intent}")
    print(f"[intake] Recalled {len(memories)} memory/memories from Memanto")

    return {
        "recalled_context": recalled_context,
        "intent": intent,
    }


def respond_node(state: SupportState, *, memory: MemantoMemoryManager, llm: ChatOpenAI) -> dict:
    """Generate a response using the LLM, enriched with recalled Memanto context."""
    NL = chr(10)
    DNL = chr(10) + chr(10)
    system_prompt = (
        "You are a helpful customer support agent. You have access to the "
        "customer history through persistent memories that survive across "
        "sessions. Use the recalled context to provide personalized, informed "
        "responses. If the context mentions prior issues, acknowledge them. "
        "If there is no prior context, treat this as a new interaction." + DNL +
        "Recalled customer context:" + NL + "{recalled_context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
    ] + [("placeholder", "{messages}")])

    chain = prompt | llm
    response = chain.invoke({
        "messages": state["messages"],
        "recalled_context": state.get("recalled_context", "No prior context."),
    })

    ai_message = AIMessage(content=response.content)
    print(f"[respond] Generated response ({len(response.content)} chars)")

    return {
        "messages": [ai_message],
        "response": response.content,
    }


def remember_node(state: SupportState, *, memory: MemantoMemoryManager, llm: ChatOpenAI) -> dict:
    """Extract key information and store it in Memanto for future sessions."""
    last_human = ""
    last_ai = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage) and not last_human:
            last_human = msg.content
        if isinstance(msg, AIMessage) and not last_ai:
            last_ai = msg.content
        if last_human and last_ai:
            break

    NL = chr(10)
    DNL = NL + NL
    extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You analyze customer support conversations and extract key information "
            "that should be stored as persistent memories for future sessions. "
            "Output a JSON array of objects with: memory_type, title, content, "
            "confidence, tags. Only extract info useful in FUTURE sessions. "
            "Return ONLY the JSON array. If nothing is worth remembering, return: []"
        )),
        ("human", (
            "Customer message: {customer_msg}" + DNL +
            "Agent response: {agent_response}" + DNL +
            "Intent: {intent}" + NL +
            "Recalled context: {recalled_context}"
        )),
    ])

    chain = extraction_prompt | llm
    try:
        raw = chain.invoke({
            "customer_msg": last_human,
            "agent_response": last_ai,
            "intent": state.get("intent", "general"),
            "recalled_context": state.get("recalled_context", ""),
        }).content.strip()

        # Parse JSON (handle markdown code blocks)
        BT = chr(96) + chr(96) + chr(96)
        if raw.startswith(BT):
            raw = raw.split(BT)[1]
            if raw.startswith("json"):
                raw = raw[4:]

        memories_data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[remember] Could not extract memories: {e}")
        memories_data = []

    stored = []
    for mem in memories_data:
        result = memory.remember(
            memory_type=mem.get("memory_type", "fact"),
            title=mem.get("title", "Untitled")[:100],
            content=mem.get("content", "")[:500],
            confidence=min(1.0, max(0.0, float(mem.get("confidence", 0.85)))),
            tags=[t.strip() for t in mem.get("tags", "").split(",") if t.strip()],
        )
        if result:
            stored.append(mem)

    print(f"[remember] Stored {len(stored)} new memory/memories in Memanto")
    return {"memories_to_store": stored}


def build_support_graph(
    memory: MemantoMemoryManager,
    llm: ChatOpenAI | None = None,
) -> StateGraph:
    """Build the LangGraph customer support workflow with Memanto memory."""
    if llm is None:
        llm = ChatOpenAI(model=MODEL_NAME, temperature=0.3)

    graph = StateGraph(SupportState)

    def intake(state: SupportState) -> dict:
        return intake_node(state, memory=memory, llm=llm)

    def respond(state: SupportState) -> dict:
        return respond_node(state, memory=memory, llm=llm)

    def remember(state: SupportState) -> dict:
        return remember_node(state, memory=memory, llm=llm)

    graph.add_node("intake", intake)
    graph.add_node("respond", respond)
    graph.add_node("remember", remember)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "respond")
    graph.add_edge("respond", "remember")
    graph.add_edge("remember", END)

    return graph.compile()


def run_session(
    graph: Any,
    memory: MemantoMemoryManager,
    customer_message: str,
    session_label: str = "Session",
) -> str:
    """Run a single customer message through the graph."""
    sep = "=" * 60
    NL = chr(10)
    print(NL + sep)
    print(f"  {session_label}")
    print(f"  Customer: {customer_message}")
    print(sep + NL)

    result = graph.invoke({
        "messages": [HumanMessage(content=customer_message)],
        "recalled_context": "",
        "intent": "",
        "response": "",
        "memories_to_store": [],
    })

    ai_response = result.get("response", "")
    print(NL + "  Agent: " + ai_response + NL)
    return ai_response
