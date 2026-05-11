"""
Memanto Tools for LangGraph Agents.

Provides LangChain-compatible tools to Remember and Recall memories
via the Memanto REST API, enabling persistent, cross-session memory.
"""

import os
import json
import requests
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

MEMANTO_API_KEY = os.getenv("MEMANTO_API_KEY", "")
MEMANTO_BASE_URL = os.getenv("MEMANTO_BASE_URL", "https://memanto.moorcheh.ai")
AGENT_ID = os.getenv("MEMANTO_AGENT_ID", "langgraph-default-agent")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {MEMANTO_API_KEY}",
        "Content-Type": "application/json",
    }


def remember(content: str, memory_type: str = "observation",
             tags: Optional[list[str]] = None) -> str:
    """
    Store a memory in Memanto.
    
    Args:
        content: The memory content to store
        memory_type: One of: fact, observation, decision, conversation, summary, preference
        tags: Optional tags for filtering
    
    Returns:
        Memory ID string
    """
    if not MEMANTO_API_KEY:
        return "ERROR: MEMANTO_API_KEY not set. Set it in .env file."

    payload = {
        "agent_id": AGENT_ID,
        "content": content,
        "type": memory_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if tags:
        payload["tags"] = tags

    try:
        resp = requests.post(
            f"{MEMANTO_BASE_URL}/api/v1/agents/{AGENT_ID}/memories",
            json=payload,
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return f"✅ Memory stored (ID: {data.get('id', 'unknown')})"
    except Exception as e:
        return f"❌ Failed to store memory: {str(e)}"


def recall(query: str, limit: int = 5) -> str:
    """
    Search and retrieve relevant memories from Memanto.
    
    Args:
        query: Natural language search query
        limit: Max number of memories to return
    
    Returns:
        Formatted string of matching memories
    """
    if not MEMANTO_API_KEY:
        return "ERROR: MEMANTO_API_KEY not set."

    try:
        resp = requests.post(
            f"{MEMANTO_BASE_URL}/api/v1/agents/{AGENT_ID}/recall",
            json={"query": query, "limit": limit},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        memories = data.get("memories", data.get("results", []))

        if not memories:
            return "No relevant memories found."

        output = "**📖 Past Memories:**\n"
        for i, m in enumerate(memories[:limit], 1):
            content = m.get("content", m.get("text", "?"))
            mtype = m.get("type", m.get("memory_type", "unknown"))
            score = m.get("similarity", m.get("score", "N/A"))
            dt = m.get("timestamp", m.get("created_at", ""))[:10] if m.get("timestamp") else ""
            output += f"\n  {i}. [{mtype}] {content[:120]}"
            if score != "N/A":
                output += f" (score: {score:.2f})"
            if dt:
                output += f" [{dt}]"
        return output
    except Exception as e:
        return f"❌ Failed to recall memories: {str(e)}"


def list_memories(memory_type: Optional[str] = None, limit: int = 10) -> str:
    """List recent memories."""
    if not MEMANTO_API_KEY:
        return "ERROR: MEMANTO_API_KEY not set."

    try:
        url = f"{MEMANTO_BASE_URL}/api/v1/agents/{AGENT_ID}/memories"
        params = {"limit": limit}
        if memory_type:
            params["type"] = memory_type

        resp = requests.get(url, params=params, headers=_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        memories = data.get("memories", data.get("results", []))

        if not memories:
            return "No memories stored yet."

        output = f"**📚 Memories ({len(memories)}):**\n"
        for m in memories:
            content = m.get("content", m.get("text", "?"))[:80]
            mtype = m.get("type", m.get("memory_type", "?"))
            dt = m.get("timestamp", m.get("created_at", ""))[:10] if m.get("timestamp") else ""
            output += f"\n  [{mtype}] {content} {f'({dt})' if dt else ''}"
        return output
    except Exception as e:
        return f"❌ Failed to list memories: {str(e)}"
