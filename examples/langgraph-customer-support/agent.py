"""
LangGraph Customer Support Agent with Memanto Persistent Memory.

Workflow:
    TICKET → TRIAGE → INVESTIGATE → RESOLVE → FOLLOW_UP

- TRIAGE: Classify ticket severity and check Memanto for customer history
- INVESTIGATE: Search knowledge base, recall prior solutions from memory
- RESOLVE: Apply solution, store resolution as a memory for future sessions
- FOLLOW_UP: Generate follow-up, store commitment to check back

Key Feature: Cross-Session Recall
    If customer A reported a bug yesterday, and customer B reports the same
    issue today, the agent *remembers* the previous resolution because it's
    stored in Memanto — not in the ephemeral LangGraph state.
"""

import os
import json
import logging
from typing import Any, TypedDict, Literal
from datetime import datetime

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from memanto_tool import MemantoTool

logger = logging.getLogger(__name__)


# ─── Allowed enum values ──────────────────────────────────────

SEVERITY_LEVELS = {"low", "medium", "high", "critical"}
CATEGORIES = {"billing", "technical", "account", "feature_request", "general"}


# ─── Graph State ───────────────────────────────────────────────

class SupportState(TypedDict):
    """State that flows through the LangGraph support workflow.

    Note: Memanto memories are NOT stored here — they persist
    in Memanto across sessions. This state is ephemeral.
    """
    ticket_id: str
    customer_id: str
    message: str
    severity: str
    category: str
    customer_history: list[dict[str, Any]]
    similar_issues: list[dict[str, Any]]
    investigation_notes: list[str]
    resolution: str
    follow_up: str
    session_id: str


# ─── Nodes ─────────────────────────────────────────────────────

def triage_node(state: SupportState, *, llm: ChatOpenAI, memanto: MemantoTool) -> dict:
    """Classify the ticket and recall customer history from Memanto."""
    message = state["message"]
    customer_id = state["customer_id"]

    # 1. Recall customer history from previous sessions (cross-session recall!)
    customer_history = memanto.recall(
        query=f"customer {customer_id} issues preferences history",
        limit=5,
    )

    # 2. Recall similar issues from ANY customer (knowledge base in memory)
    similar_issues = memanto.recall(
        query=message,
        limit=5,
        memory_types=["fact", "instruction", "learning"],
    )

    # 3. Classify severity and category with LLM
    history_context = ""
    if customer_history:
        history_context = "\n\n## Customer History (from Memanto):\n"
        for m in customer_history[:3]:
            history_context += f"- [{m.get('type', '?').upper()}] {m.get('content', '')[:100]}\n"

    similar_context = ""
    if similar_issues:
        similar_context = "\n\n## Similar Past Issues (from Memanto):\n"
        for m in similar_issues[:3]:
            similar_context += f"- [{m.get('type', '?').upper()}] {m.get('content', '')[:100]}\n"

    prompt = [
        SystemMessage(content=(
            "You are a customer support triage agent. Classify the incoming ticket. "
            "Respond in JSON format with keys: severity (low/medium/high/critical), "
            "category (billing/technical/account/feature_request/general). "
            "Only output the JSON object, nothing else."
        )),
        HumanMessage(content=(
            f"Customer message: {message}\n"
            f"Customer ID: {customer_id}"
            f"{history_context}"
            f"{similar_context}"
        )),
    ]

    response = llm.invoke(prompt)
    try:
        classification = json.loads(response.content)
    except json.JSONDecodeError:
        classification = {"severity": "medium", "category": "general"}

    # Normalize and clamp classification to allowed values
    severity_raw = classification.get("severity", "medium")
    category_raw = classification.get("category", "general")
    severity = str(severity_raw).strip().lower()
    category = str(category_raw).strip().lower()
    # Normalize common separator variants (e.g. "feature request" -> "feature_request")
    category = category.replace(" ", "_").replace("-", "_")
    if severity not in SEVERITY_LEVELS:
        logger.warning("LLM returned unknown severity '%s', defaulting to 'medium'", severity_raw)
        severity = "medium"
    if category not in CATEGORIES:
        logger.warning("LLM returned unknown category '%s', defaulting to 'general'", category_raw)
        category = "general"

    # 4. Store this triage event as a memory
    try:
        memanto.remember(
            content=f"Customer {customer_id} submitted ticket: {message[:120]}",
            title=f"Ticket triage: {customer_id}",
            memory_type="event",
            confidence=0.95,
            tags=["triage", customer_id, category],
        )
    except Exception as e:
        logger.warning("Failed to store triage memory: %s", e)

    return {
        "severity": severity,
        "category": category,
        "customer_history": customer_history,
        "similar_issues": similar_issues,
    }


def investigate_node(state: SupportState, *, llm: ChatOpenAI, memanto: MemantoTool) -> dict:
    """Investigate the issue using LLM reasoning and recalled memories."""
    message = state["message"]
    similar_issues = state.get("similar_issues", [])
    customer_history = state.get("customer_history", [])
    category = state.get("category", "general")
    severity = state.get("severity", "medium")

    # Build context from recalled memories
    memory_context = ""
    if similar_issues:
        memory_context += "\n## Similar Past Issues:\n"
        for m in similar_issues:
            memory_context += f"- {m.get('content', '')[:150]} (confidence: {m.get('confidence', 0):.2f})\n"

    if customer_history:
        memory_context += "\n## Customer History:\n"
        for m in customer_history:
            memory_context += f"- {m.get('content', '')[:150]} (confidence: {m.get('confidence', 0):.2f})\n"

    prompt = [
        SystemMessage(content=(
            "You are a senior support engineer investigating a customer issue. "
            "Review the ticket and any recalled context from previous sessions. "
            "Provide a numbered list of investigation steps and findings. "
            "If similar issues were resolved before, reference those solutions."
        )),
        HumanMessage(content=(
            f"Ticket: {message}\n"
            f"Category: {category} | Severity: {severity}\n"
            f"{memory_context}\n\n"
            "Investigate this issue step by step."
        )),
    ]

    response = llm.invoke(prompt)
    notes = [line.strip() for line in response.content.split("\n") if line.strip()]

    # Store investigation findings as memories
    for i, note in enumerate(notes[:5]):
        memory_type = _classify_investigation(note)
        try:
            memanto.remember(
                content=note,
                title=f"Investigation: ticket about {message[:40]}",
                memory_type=memory_type,
                confidence=0.80,
                tags=["investigation", state.get("customer_id", "unknown"), category],
            )
        except Exception as e:
            logger.warning("Failed to store investigation memory #%d: %s", i, e)

    return {"investigation_notes": notes}


def resolve_node(state: SupportState, *, llm: ChatOpenAI, memanto: MemantoTool) -> dict:
    """Generate a resolution based on investigation and recalled solutions."""
    message = state["message"]
    notes = state.get("investigation_notes", [])
    similar_issues = state.get("similar_issues", [])
    severity = state.get("severity", "medium")

    # Build context
    notes_text = "\n".join(notes[:10])
    solutions_text = ""
    if similar_issues:
        solutions_text = "\n## Previous Solutions:\n"
        for m in similar_issues[:3]:
            solutions_text += f"- {m.get('content', '')[:200]}\n"

    prompt = [
        SystemMessage(content=(
            "You are a customer support resolution specialist. Based on the investigation "
            "and any recalled solutions from previous sessions, provide a clear resolution. "
            "If this issue was resolved before, reference the previous solution explicitly. "
            "Format: 1) Root cause 2) Resolution steps 3) Prevention advice"
        )),
        HumanMessage(content=(
            f"Ticket: {message}\n"
            f"Severity: {severity}\n\n"
            f"## Investigation:\n{notes_text}\n"
            f"{solutions_text}\n"
            "Provide the resolution."
        )),
    ]

    response = llm.invoke(prompt)
    resolution = response.content

    # Store the resolution as a high-confidence memory for future sessions
    try:
        memanto.remember(
            content=f"Resolved '{message[:60]}': {resolution[:200]}",
            title=f"Resolution: {message[:50]}",
            memory_type="fact",
            confidence=0.90,
            tags=["resolution", state.get("customer_id", "unknown"),
                  state.get("category", "general")],
        )
    except Exception as e:
        logger.warning("Failed to store resolution memory: %s", e)

    # Store customer preference if severity was high
    if severity in ("high", "critical"):
        try:
            memanto.remember(
                content=f"Customer {state.get('customer_id', 'unknown')} experienced "
                        f"a {severity} severity issue: {message[:80]}",
                title=f"High-severity issue: {state.get('customer_id', 'unknown')}",
                memory_type="observation",
                confidence=0.85,
                tags=["high_severity", state.get("customer_id", "unknown")],
            )
        except Exception as e:
            logger.warning("Failed to store high-severity memory: %s", e)

    return {"resolution": resolution}


def follow_up_node(state: SupportState, *, llm: ChatOpenAI, memanto: MemantoTool) -> dict:
    """Generate a follow-up plan and store a commitment memory."""
    message = state["message"]
    resolution = state.get("resolution", "")
    severity = state.get("severity", "medium")
    customer_id = state.get("customer_id", "unknown")

    prompt = [
        SystemMessage(content=(
            "You are a customer success manager. Generate a brief follow-up message "
            "to the customer summarizing the resolution and next steps. "
            "Be warm and professional. Keep it concise."
        )),
        HumanMessage(content=(
            f"Customer message: {message}\n"
            f"Resolution: {resolution[:500]}\n"
            f"Severity: {severity}\n\n"
            "Write the follow-up message."
        )),
    ]

    response = llm.invoke(prompt)
    follow_up = response.content

    # Store a commitment memory so we remember to check back
    if severity in ("high", "critical"):
        try:
            memanto.remember(
                content=f"Follow up with customer {customer_id} about: {message[:60]} "
                        f"— resolved on {datetime.utcnow().strftime('%Y-%m-%d')}",
                title=f"Follow-up commitment: {customer_id}",
                memory_type="commitment",
                confidence=0.95,
                tags=["follow_up", customer_id, severity],
            )
        except Exception as e:
            logger.warning("Failed to store follow-up commitment: %s", e)

    return {"follow_up": follow_up}


# ─── Helper ────────────────────────────────────────────────────

def _classify_investigation(note: str) -> str:
    """Classify an investigation note into a Memanto memory type."""
    note_lower = note.lower()
    if any(kw in note_lower for kw in ["root cause", "caused by", "due to", "because"]):
        return "fact"
    if any(kw in note_lower for kw in ["should", "must", "recommend", "suggest"]):
        return "instruction"
    if any(kw in note_lower for kw in ["observed", "found that", "noticed", "appears"]):
        return "observation"
    if any(kw in note_lower for kw in ["resolved", "fixed", "solution", "workaround"]):
        return "learning"
    return "fact"


# ─── Conditional Edge ──────────────────────────────────────────

def should_escalate(state: SupportState) -> str:
    """Route based on severity: critical tickets get extra attention."""
    if state.get("severity") == "critical":
        return "investigate"
    return "investigate"


# ─── Graph Construction ────────────────────────────────────────

def build_graph(llm: ChatOpenAI, memanto: MemantoTool) -> StateGraph:
    """Build the LangGraph customer support agent workflow."""

    graph = StateGraph(SupportState)

    # Add nodes with bound dependencies
    graph.add_node(
        "triage",
        lambda state: triage_node(state, llm=llm, memanto=memanto),
    )
    graph.add_node(
        "investigate",
        lambda state: investigate_node(state, llm=llm, memanto=memanto),
    )
    graph.add_node(
        "resolve",
        lambda state: resolve_node(state, llm=llm, memanto=memanto),
    )
    graph.add_node(
        "follow_up",
        lambda state: follow_up_node(state, llm=llm, memanto=memanto),
    )

    # Define edges: triage → investigate → resolve → follow_up → END
    graph.set_entry_point("triage")
    graph.add_edge("triage", "investigate")
    graph.add_edge("investigate", "resolve")
    graph.add_edge("resolve", "follow_up")
    graph.add_edge("follow_up", END)

    return graph.compile()


# ─── Factory ───────────────────────────────────────────────────

def create_agent(
    moorcheh_api_key: str | None = None,
    openai_api_key: str | None = None,
    model: str = "gpt-4o-mini",
    agent_id: str = "langgraph-support-agent",
    scope_id: str = "customer-support",
) -> Any:
    """Create and return a compiled LangGraph support agent with Memanto memory.

    Args:
        moorcheh_api_key: Moorcheh API key (or set MOORCHEH_API_KEY env var)
        openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var)
        model: LLM model to use
        agent_id: Unique agent identifier for Memanto
        scope_id: Memory scope for isolation

    Returns:
        Compiled LangGraph agent

    Raises:
        ValueError: If MOORCHEH_API_KEY or OPENAI_API_KEY is not provided
    """
    oai_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not oai_key:
        raise ValueError(
            "OPENAI_API_KEY is required. Set it in .env or pass openai_api_key."
        )

    llm = ChatOpenAI(
        model=model,
        api_key=oai_key,
        temperature=0.3,
    )

    memanto = MemantoTool(
        agent_id=agent_id,
        scope_id=scope_id,
        moorcheh_api_key=moorcheh_api_key,
    )

    return build_graph(llm, memanto)
