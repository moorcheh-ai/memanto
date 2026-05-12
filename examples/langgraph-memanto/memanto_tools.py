"""
Memanto Tools for LangGraph — Persistent, Cross-Session Memory.

This module wraps Memanto's SdkClient (remember / recall / answer) as
LangChain-compatible Tool objects, so they can be used inside LangGraph
StateGraph nodes, LangChain agents, or any tool-calling LLM.

Usage:
    from memanto_tools import create_memanto_tools, MemantoSetup

    setup = MemantoSetup(api_key="your-moorcheh-key")
    client = setup.setup(agent_id="my-agent")
    tools = create_memanto_tools(client, agent_id="my-agent")

    # In a LangGraph node:
    result = tools["recall"].invoke({"query": "What does the user prefer?"})
"""

import os
from typing import Any

from langchain_core.tools import Tool


# ---------------------------------------------------------------------------
# MemantoSetup — one-call bootstrap for LangGraph examples
# ---------------------------------------------------------------------------

class MemantoSetup:
    """Bootstrap helper: creates/activates a Memanto agent from an API key.

    Usage:
        setup = MemantoSetup(api_key="sk-...")
        client = setup.setup(agent_id="my-langgraph-agent")

    The resulting *client* is a fully authenticated ``SdkClient`` with an
    active session.  Call ``setup.teardown()`` when done to release resources.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY is required. "
                "Get one free at https://console.moorcheh.ai/api-keys"
            )
        self._client: Any = None
        self._agent_id: str | None = None

    def setup(self, agent_id: str = "langgraph-agent") -> Any:
        """Create (or reuse) an agent and start a session.

        Returns an ``SdkClient`` with an active session.
        """
        from memanto.cli.client.sdk_client import SdkClient

        self._agent_id = agent_id
        self._client = SdkClient(api_key=self.api_key)

        # Create agent if it doesn't exist yet (idempotent — reuses existing)
        try:
            self._client.get_agent(agent_id)
        except Exception:
            self._client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="LangGraph agent with Memanto persistent memory",
            )

        # Activate session
        self._client.activate_agent(agent_id)
        return self._client

    def teardown(self) -> None:
        """End the current session."""
        if self._client and self._agent_id:
            try:
                self._client.deactivate_agent(self._agent_id)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def create_memanto_tools(client: Any, agent_id: str) -> dict[str, Tool]:
    """Create LangChain Tool objects wrapping Memanto SDK operations.

    Returns a dict with three keys: ``remember``, ``recall``, ``answer``.
    Pass these tools to your LangGraph agent or tool-executing node.

    Parameters
    ----------
    client : SdkClient
        An authenticated Memanto SDK client (from ``MemantoSetup.setup()``).
    agent_id : str
        The agent namespace to read/write memories from.
    """
    return {
        "remember": Tool(
            name="remember_memory",
            description=(
                "Store a new memory for the current agent. "
                "Input should be a JSON string with keys: "
                "content (str, required), "
                "memory_type (str, optional: fact|instruction|decision|goal|preference|event|commitment), "
                "title (str, optional), "
                "confidence (float, optional, 0-1). "
                "Use this whenever the agent learns something worth remembering across sessions."
            ),
            func=lambda input_str: _remember(client, agent_id, input_str),
        ),
        "recall": Tool(
            name="recall_memory",
            description=(
                "Search the agent's persistent memory using a natural-language query. "
                "Input is a plain-text search string (e.g. 'What does the user prefer?'). "
                "Returns relevant memories ranked by semantic relevance. "
                "Use this at the start of every session to restore context."
            ),
            func=lambda query: _recall(client, agent_id, query),
        ),
        "answer": Tool(
            name="answer_from_memory",
            description=(
                "Answer a question using Retrieval-Augmented Generation over the "
                "agent's persistent memory. Input is a plain-text question. "
                "Returns a natural-language answer with source citations. "
                "Use this when you need a synthesized answer from multiple memories."
            ),
            func=lambda question: _answer(client, agent_id, question),
        ),
    }


# ---------------------------------------------------------------------------
# Internal dispatch helpers
# ---------------------------------------------------------------------------

def _remember(client: Any, agent_id: str, input_str: str) -> str:
    import json

    try:
        params = json.loads(input_str)
    except json.JSONDecodeError:
        params = {"content": input_str}

    content = params.get("content", input_str)
    title = params.get("title", content[:47] + "..." if len(content) > 50 else content)
    memory_type = params.get("memory_type", "fact")
    confidence = params.get("confidence", 0.8)

    try:
        result = client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
        )
        return json.dumps(
            {
                "status": "stored",
                "memory_id": result.get("memory_id", "unknown"),
                "type": memory_type,
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def _recall(client: Any, agent_id: str, query: str) -> str:
    import json

    if not query or not query.strip():
        return json.dumps({"status": "error", "message": "Query cannot be empty"})

    try:
        result = client.recall(agent_id=agent_id, query=query, limit=10)
        memories = result.get("memories", [])
        if not memories:
            return json.dumps(
                {"status": "success", "memories": [], "count": 0}
            )

        formatted = []
        for m in memories:
            formatted.append(
                {
                    "id": m.get("id", ""),
                    "type": m.get("type", "unknown"),
                    "title": m.get("title", ""),
                    "content": m.get("content", ""),
                    "confidence": m.get("confidence", 0.0),
                    "created_at": str(m.get("created_at", "")),
                }
            )
        return json.dumps(
            {
                "status": "success",
                "memories": formatted,
                "count": len(formatted),
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def _answer(client: Any, agent_id: str, question: str) -> str:
    import json

    if not question or not question.strip():
        return json.dumps({"status": "error", "message": "Question cannot be empty"})

    try:
        result = client.answer(agent_id=agent_id, question=question)
        return json.dumps(
            {
                "status": "success",
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
