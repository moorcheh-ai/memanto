"""LangGraph Customer Support Agent with Memanto long-term memory.

Demonstrates cross-session recall: the agent remembers user preferences,
past issues, and resolved tickets from previous conversations.

Usage:
    python support_agent.py --user "user123" --message "My password reset isn't working"
"""

import argparse
import os
import uuid
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from memanto_adapter import MemantoAdapter


# ── State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    user_id: str
    session_id: str
    message: str
    intent: str
    memories: list[dict[str, Any]]
    context: str
    response: str


# ── Node: Classify Intent ──────────────────────────────────────────────

def classify_intent(state: AgentState) -> dict[str, str]:
    msg = state["message"].lower()
    if any(w in msg for w in ["reset", "forgot", "password", "login"]):
        intent = "password_reset"
    elif any(w in msg for w in ["refund", "cancel", "billing", "charge", "payment"]):
        intent = "billing"
    elif any(w in msg for w in ["slow", "bug", "error", "crash", "broken"]):
        intent = "technical_issue"
    elif any(w in msg for w in ["how", "what", "guide", "tutorial", "help"]):
        intent = "howto"
    else:
        intent = "general_inquiry"
    return {"intent": intent}


# ── Node: Retrieve Memories (cross-session) ────────────────────────────

def retrieve_memories(state: AgentState) -> dict[str, Any]:
    adapter = _get_adapter(state["session_id"])
    memories = adapter.get_cross_session_memories(state["user_id"], limit=5)
    return {"memories": memories}


# ── Node: Build Context from Memories ──────────────────────────────────

def build_context(state: AgentState) -> dict[str, str]:
    ctx_parts = []
    for m in state["memories"]:
        ctx_parts.append(f"[{m.get('type','?')}] {m.get('title','')}: {m.get('content','')}")
    context = "\n".join(ctx_parts) if ctx_parts else "No prior context available."
    return {"context": context}


# ── Node: Generate Response ────────────────────────────────────────────

def generate_response(state: AgentState) -> dict[str, str]:
    intent = state["intent"]
    user_msg = state["message"]
    has_memory = bool(state["memories"])

    if intent == "password_reset":
        response = _handle_password_reset(user_msg, state["memories"])
    elif intent == "billing":
        response = _handle_billing(user_msg, state["memories"])
    elif intent == "technical_issue":
        response = _handle_technical(user_msg, state["memories"])
    elif intent == "howto":
        response = _handle_howto(user_msg, state["memories"])
    else:
        response = (
            f"I understand you're asking about: \"{user_msg}\". "
            "Could you provide more details so I can help?"
        )

    if has_memory:
        response += "\n\n(I remembered your previous interactions to provide better support.)"

    return {"response": response}


def _handle_password_reset(msg: str, memories: list) -> str:
    for m in memories:
        if "password" in m.get("content", "").lower():
            return (
                f"I see you've had password issues before. Let me summarize what we know:\n"
                f"- Previous issue: {m.get('content', 'N/A')}\n\n"
                "To reset your password:\n"
                "1. Go to the login page and click 'Forgot Password'\n"
                "2. Check your email for the reset link\n"
                "3. Create a strong password (12+ chars)\n\n"
                "Would you like me to escalate this to our engineering team?"
            )
    return (
        "I can help with password reset. Here's what to do:\n"
        "1. Visit the login page\n"
        "2. Click 'Forgot Password'\n"
        "3. Follow the email instructions\n\n"
        "If the email doesn't arrive within 5 minutes, check your spam folder."
    )


def _handle_billing(msg: str, memories: list) -> str:
    for m in memories:
        if "billing" in m.get("tags", ""):
            return (
                f"You previously asked about billing. Last time: {m.get('content', '')}\n\n"
                "I've noted this is a recurring concern. Let me connect you with billing."
            )
    return "For billing inquiries, please provide your account email and I'll look into it."


def _handle_technical(msg: str, memories: list) -> str:
    for m in memories:
        if "bug" in m.get("type", ""):
            return (
                "I found previous bug reports from your account. "
                f"Last issue: {m.get('content', '')}\n\n"
                "Since this is a recurring technical concern, I've flagged this for priority review."
            )
    return "I'm sorry you're experiencing issues. Please describe what happens step by step."


def _handle_howto(msg: str, memories: list) -> str:
    for m in memories:
        if "preference" in m.get("type", ""):
            return (
                f"Based on your preferences ({m.get('content', '')}), "
                "here's a guide tailored to your setup.\n\n"
                "Check our documentation at docs.example.com for detailed walkthroughs."
            )
    return "Check our documentation at docs.example.com. What specific feature are you interested in?"


# ── Node: Store Memory ─────────────────────────────────────────────────

def store_memory(state: AgentState) -> dict:
    adapter = _get_adapter(state["session_id"])
    result = adapter.store(
        session_id=state["user_id"],
        memory_type="event",
        title=f"Support: {state['intent']}",
        content=f"User asked: {state['message']}\nAgent responded: {state['response']}",
        tags=[state["intent"], "support", "langgraph"],
        confidence=0.85,
    )
    return {"session_id": result.get("memory_id", state["session_id"])}


# ── Helpers ────────────────────────────────────────────────────────────

_ADAPTER_CACHE: dict[str, MemantoAdapter] = {}

def _get_adapter(session_id: str) -> MemantoAdapter:
    if session_id not in _ADAPTER_CACHE:
        _ADAPTER_CACHE[session_id] = MemantoAdapter(
            api_key=os.getenv("MOORCHEH_API_KEY"),
            db_path=f"memories_{session_id}.db",
        )
    return _ADAPTER_CACHE[session_id]


# ── Build Graph ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("retrieve_memories", retrieve_memories)
    workflow.add_node("build_context", build_context)
    workflow.add_node("generate_response", generate_response)
    workflow.add_node("store_memory", store_memory)

    workflow.set_entry_point("classify_intent")

    workflow.add_conditional_edges(
        "classify_intent",
        lambda s: "retrieve_memories" if s["intent"] != "general_inquiry" else "generate_response",
        {"retrieve_memories": "retrieve_memories", "generate_response": "generate_response"},
    )
    workflow.add_edge("retrieve_memories", "build_context")
    workflow.add_edge("build_context", "generate_response")
    workflow.add_edge("generate_response", "store_memory")
    workflow.add_edge("store_memory", END)

    return workflow.compile()


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LangGraph + Memanto Customer Support Agent")
    parser.add_argument("--user", default="demo-user", help="User ID for cross-session memory")
    parser.add_argument("--message", default="I forgot my password", help="Support message")
    parser.add_argument("--session", default=None, help="Session ID (auto-generated if omitted)")
    args = parser.parse_args()

    graph = build_graph()

    # First interaction
    print(f"\n{'='*60}")
    print(f"User: {args.user}")
    print(f"Message: {args.message}")
    print(f"{'='*60}\n")

    result = graph.invoke({
        "user_id": args.user,
        "session_id": args.session or str(uuid.uuid4()),
        "message": args.message,
        "intent": "",
        "memories": [],
        "context": "",
        "response": "",
    })

    print(f"Intent detected: {result['intent']}")
    print(f"\nMemories recalled: {len(result['memories'])}")
    if result['memories']:
        for m in result['memories']:
            print(f"  - [{m.get('type','?')}] {m.get('title','')}")

    print(f"\nAgent:\n{result['response']}\n")

    # Second interaction — different message, same user (demonstrates cross-session recall)
    print(f"{'='*60}")
    print("CROSS-SESSION DEMO: Same user, new message (next conversation)")
    print(f"{'='*60}\n")

    result2 = graph.invoke({
        "user_id": args.user,
        "session_id": str(uuid.uuid4()),
        "message": "The bug I reported earlier is still happening",
        "intent": "",
        "memories": [],
        "context": "",
        "response": "",
    })

    print(f"Intent detected: {result2['intent']}")
    print(f"\nMemories recalled from PREVIOUS sessions: {len(result2['memories'])}")

    print(f"\nAgent:\n{result2['response']}\n")


if __name__ == "__main__":
    main()
