"""
LangGraph + Memanto Integration

Implements a stateful AI Customer Support Agent with persistent,
cross-session long-term memory using LangGraph and Memanto.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, END

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient


# 1. State Definition
class AgentState(TypedDict):
    """
    Standard LangGraph state schema for our Customer Support Agent.
    
    Attributes:
        user_id: Unique identifier for the customer, acting as the memory namespace.
        messages: Conversation history (list of turns).
        active_memory: semantically recalled long-term context from Memanto.
        latest_reply: The assistant's generated response.
    """
    user_id: str
    messages: List[Dict[str, str]]
    active_memory: str
    latest_reply: str


# 2. Setup Client Helper
def get_memanto_client() -> SdkClient:
    """Initialize the SdkClient from environment."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise ValueError("MOORCHEH_API_KEY environment variable is not set.")
    return SdkClient(api_key=api_key)


def ensure_user_agent_active(client: SdkClient, user_id: str) -> None:
    """Ensure the user has an active agent session in Memanto."""
    try:
        client.create_agent(
            agent_id=user_id,
            pattern="tool",
            description=f"Long-term memory for user {user_id}",
        )
    except AgentAlreadyExistsError:
        pass
    except Exception:
        pass
    client.activate_agent(user_id, duration_hours=24)


# 3. Graph Nodes
def recall_context_node(state: AgentState) -> Dict[str, Any]:
    """
    Node: Recall Context
    
    Queries Memanto for any past decisions, preferences, or profile facts
    relevant to the user's latest query, and loads them into active memory.
    """
    user_id = state["user_id"]
    last_message = state["messages"][-1]["content"] if state["messages"] else ""

    client = get_memanto_client()
    ensure_user_agent_active(client, user_id)

    # Perform semantic search on the user's memories
    print(f"[*] [LangGraph Node: recall_context] Querying long-term memory for: '{last_message}'...")
    recall_result = client.recall(
        agent_id=user_id,
        query=last_message,
        limit=3,
        min_similarity=0.35,
    )

    memories = recall_result.get("memories", [])
    memory_blocks = []

    if memories:
        for idx, mem in enumerate(memories, 1):
            mem_type = mem.get("type", "fact")
            title = mem.get("title", "Info")
            content = mem.get("content", "")
            memory_blocks.append(f"- [{mem_type.upper()}] {title}: {content}")
        
        active_memory = "\n".join(memory_blocks)
        print(f"[+] [LangGraph Node: recall_context] Recalled {len(memories)} matching memory blocks.")
    else:
        active_memory = "No relevant past preferences or profile decisions found."
        print("[*] [LangGraph Node: recall_context] No relevant past memories found.")

    return {"active_memory": active_memory}


def generate_reply_node(state: AgentState) -> Dict[str, Any]:
    """
    Node: Generate Reply
    
    Generates a highly personalized, contextual reply by leveraging
    the recalled active memory. It utilizes Memanto's built-in RAG (answer)
    API to ground the reply in the agent's long-term memory.
    """
    user_id = state["user_id"]
    last_message = state["messages"][-1]["content"] if state["messages"] else ""
    active_memory = state["active_memory"]

    client = get_memanto_client()

    print("[*] [LangGraph Node: generate_reply] Generating reply grounded in memory...")

    # If we have relevant memory, utilize Memanto's RAG (answer) endpoint
    # to synthesize a grounded, intelligent answer using the serverless LLM backend.
    if "No relevant" not in active_memory:
        try:
            rag_result = client.answer(
                agent_id=user_id,
                question=f"Grounded in our past context: '{active_memory}', please answer the user's current message: '{last_message}' politely and personally."
            )
            reply = rag_result.get("answer", "")
        except Exception:
            # Safe fallback if RAG fails
            reply = f"Hello! Grounded in your preferences:\n{active_memory}\n\nHow else can I help you today?"
    else:
        # Fresh user fallback
        reply = f"Welcome! I am your AI Support Assistant. I've noted your message: '{last_message}'. How can I assist you?"

    print("[+] [LangGraph Node: generate_reply] Reply generated successfully.")
    return {"latest_reply": reply}


def extract_memory_node(state: AgentState) -> Dict[str, Any]:
    """
    Node: Extract Memory
    
    Actively listens to the latest user input. If the user shares structural
    profile facts or preferences, it distills them and calls `client.remember`
    to persist them permanently across threads and future sessions.
    """
    user_id = state["user_id"]
    last_message = state["messages"][-1]["content"] if state["messages"] else ""

    client = get_memanto_client()

    # Heuristic/Rule-based parsing to simulate LLM memory extraction
    # inside this lightweight, zero-key example.
    extracted_memories = []
    
    # 1. Detect Name
    if "my name is" in last_message.lower():
        name = last_message.lower().split("my name is")[-1].strip(" .?!").title()
        extracted_memories.append({
            "type": "fact",
            "title": "User Name",
            "content": f"The user's name is {name}.",
            "tags": ["profile", "identity"]
        })

    # 2. Detect Subscription / Plan
    if "premium plan" in last_message.lower() or "premium tier" in last_message.lower():
        extracted_memories.append({
            "type": "fact",
            "title": "User Tier",
            "content": "The user is subscribed to the Premium tier plan.",
            "tags": ["profile", "plan", "billing"]
        })

    # 3. Detect Preferences
    if "i prefer" in last_message.lower() or "i like" in last_message.lower():
        preference = last_message.lower().split("i prefer")[-1].strip(" .?!") if "i prefer" in last_message.lower() else last_message.lower().split("i like")[-1].strip(" .?!")
        extracted_memories.append({
            "type": "preference",
            "title": f"Preference: {preference[:30]}...",
            "content": f"The user prefers {preference}.",
            "tags": ["preference", "ui-config"]
        })

    # Save extracted memories to Memanto
    if extracted_memories:
        print(f"[*] [LangGraph Node: extract_memory] Distilling {len(extracted_memories)} new memories...")
        for mem in extracted_memories:
            client.remember(
                agent_id=user_id,
                memory_type=mem["type"],
                title=mem["title"],
                content=mem["content"],
                tags=mem["tags"],
                source="langgraph-agent",
                provenance="explicit_user_statement"
            )
            print(f"    [+] Saved [{mem['type'].upper()}] '{mem['title']}' to long-term database.")
    else:
        print("[*] [LangGraph Node: extract_memory] No new preferences or profile facts detected in user input.")

    return {}


# 4. Compile the Graph
def build_agent_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""
    builder = StateGraph(AgentState)

    # Add Nodes
    builder.add_node("recall_context", recall_context_node)
    builder.add_node("generate_reply", generate_reply_node)
    builder.add_node("extract_memory", extract_memory_node)

    # Set flow: Recall -> Reply -> Extract -> End
    builder.set_entry_point("recall_context")
    builder.add_edge("recall_context", "generate_reply")
    builder.add_edge("generate_reply", "extract_memory")
    builder.add_edge("extract_memory", END)

    return builder.compile()
