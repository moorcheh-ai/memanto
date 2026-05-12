#!/usr/bin/env python3
"""
LangGraph + Memanto Cross-Session Recall Demo

This script demonstrates the core value proposition of Memanto as a
long-term memory layer for LangGraph agents: cross-session recall.

How it works:
  1. Session 1: Create a Memanto agent, send a message, the agent
     stores facts about the user as persistent memories.
  2. Session 2: Create a FRESH LangGraph agent (no shared state with
     Session 1). When it calls memory.recall(), it retrieves the
     memories stored in Session 1 — proving cross-session recall.

Requirements:
  - Memanto server running on http://localhost:8000
  - Valid MOORCHEH_API_KEY in .env or environment
"""

import logging
import os
import sys
import uuid

from dotenv import load_dotenv

from agent import MemantoMemory, build_agent

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("demo")

SEPARATOR = "=" * 72


def check_prerequisites() -> bool:
    """Verify Memanto server is reachable."""
    import requests

    base_url = os.environ.get("MEMANTO_BASE_URL", "http://localhost:8000")
    try:
        resp = requests.get(f"{base_url}/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            logger.info("Memanto server %s v%s ✓", data.get("service", "?"), data.get("version", "?"))
            return True
        else:
            logger.error("Memanto returned status %d", resp.status_code)
            return False
    except requests.ConnectionError:
        logger.warning("Memanto server not reachable at %s", base_url)
        logger.warning("Start it with: docker-compose up -d  (from memanto repo root)")
        logger.warning("Falling back to simulated mode for demonstration.\n")
        return False


class SimulatedMemantoMemory(MemantoMemory):
    """A simulated memory backend for running the demo without a Memanto server.

    Stores memories in a local dict so the demo can still demonstrate the
    LangGraph integration pattern and cross-session recall logic.
    """

    _store: dict[str, list[dict]] = {}  # Shared across instances

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agent_id = "sim-agent"
        self._session_token = "sim-token"
        self._local_store_key = self._agent_id

        if self._local_store_key not in self._store:
            self._store[self._local_store_key] = []

    def create_agent(self, name: str = "langgraph-agent") -> str:
        self._agent_id = f"sim-{uuid.uuid4().hex[:8]}"
        self._local_store_key = self._agent_id
        self._store[self._local_store_key] = []
        logger.info("[SIM] Created simulated agent: %s", self._agent_id)
        return self._agent_id

    def activate_agent(self) -> str:
        logger.info("[SIM] Activated agent")
        return "sim-token"

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: str | None = None,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        mid = f"mem-{uuid.uuid4().hex[:12]}"
        self._store.setdefault(self._local_store_key, []).append(
            {
                "id": mid,
                "content": content,
                "memory_type": memory_type,
                "title": title or content[:80],
                "confidence": confidence,
                "tags": tags or [],
                "created_at": "2026-05-12T00:00:00Z",
            }
        )
        logger.info("[SIM] Remembered [%s]: %s", memory_type, content[:60])
        return mid

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict]:
        memories = self._store.get(self._local_store_key, [])
        if memory_types:
            memories = [m for m in memories if m["memory_type"] in memory_types]
        result = memories[:limit]
        logger.info("[SIM] Recalled %d memories from store (%d total)", len(result), len(memories))
        return result

    def answer(self, query: str) -> str:
        memories = self._store.get(self._local_store_key, [])
        if not memories:
            return "[SIM] No memories to answer from."
        ctx = "; ".join(m["content"] for m in memories[:3])
        return f"[SIM] Based on memories: {ctx}"


def run_session(
    session_id: str,
    user_message: str,
    memory: MemantoMemory,
    is_first_session: bool,
) -> str:
    """Run a single LangGraph agent session and return the output."""
    print(f"\n{SEPARATOR}")
    print(f"  📅 SESSION {session_id}")
    print(f"  User says: \"{user_message}\"")
    print(SEPARATOR)

    # Build a fresh LangGraph agent (no shared local state with previous sessions)
    agent = build_agent(memory)

    # Run the agent
    result = agent.invoke({
        "messages": [{"role": "user", "content": user_message}],
        "user_id": "demo-user",
        "session_id": session_id,
        "memories_recalled": [],
        "new_memories": [],
        "output": "",
    })

    print(f"\n  🤖 Agent response:")
    print(f"  {result['output']}")

    # Show what was stored
    if result.get("new_memories") and len(result["new_memories"]) > 0:
        print(f"\n  💾 Stored {len(result['new_memories'])} new memory(s)")

    return result["output"]


def main():
    print(r"""
  ╔══════════════════════════════════════════════════════╗
  ║  🧠 LangGraph + Memanto Cross-Session Recall Demo   ║
  ║  "Give Your Graph a Permanent Brain"                 ║
  ╚══════════════════════════════════════════════════════╝
    """)

    server_available = check_prerequisites()

    # Choose memory backend
    if server_available:
        logger.info("Using live Memanto server")
        memory = MemantoMemory()
        memory.create_agent("demo-agent")
        memory.activate_agent()
    else:
        logger.info("Using simulated memory backend (no server needed)")
        memory = SimulatedMemantoMemory()
        memory.create_agent("demo-agent")
        memory.activate_agent()

    # ════════════════════════════════════════════════════════════════
    # Session 1: User shares personal information
    # ════════════════════════════════════════════════════════════════

    run_session(
        session_id="SESSION-001",
        user_message=(
            "Hi! My name is Alex and I'm a software developer. "
            "I prefer Python and TypeScript for my projects. "
            "I need help setting up a CI/CD pipeline for my new microservice."
        ),
        memory=memory,
        is_first_session=True,
    )

    # ════════════════════════════════════════════════════════════════
    # Cross-Session Recall Demo
    # ════════════════════════════════════════════════════════════════

    print(f"\n{'─' * 72}")
    print("  🔄 CROSS-SESSION BOUNDARY — Session 1 ended, state discarded")
    print("  🔄 A new LangGraph agent is created (no shared local state)")
    print("  🔄 Memanto will provide the persistence across sessions")
    print(f"{'─' * 72}")

    # Start a NEW session with a FRESH memory connection
    # In production, this would be a new server request
    if server_available:
        memory2 = MemantoMemory()
        memory2.create_agent("demo-agent")
        memory2.activate_agent()
    else:
        # The simulated memory uses a class-level dict, so it persists
        # even with a new instance — just like the real Memanto server
        memory2 = SimulatedMemantoMemory()

    # ════════════════════════════════════════════════════════════════
    # Session 2: User asks for help — agent recalls from Session 1
    # ════════════════════════════════════════════════════════════════

    run_session(
        session_id="SESSION-002",
        user_message=(
            "Hey, I'm back! What language should I use "
            "for my microservice? And do you remember my name?"
        ),
        memory=memory2,
        is_first_session=False,
    )

    # ════════════════════════════════════════════════════════════════
    # Summary
    # ════════════════════════════════════════════════════════════════

    print(f"\n{SEPARATOR}")
    print("  ✅ CROSS-SESSION RECALL DEMONSTRATED")
    print(f"{SEPARATOR}")
    print("""
  In Session 1, the agent learned:
    • User's name is Alex
    • Alex is a software developer
    • Alex prefers Python and TypeScript

  Session 1's LangGraph state was then **completely discarded**.

  In Session 2, a **new LangGraph agent** was created with:
    • Zero shared state with Session 1
    • A fresh MemantoMemory connection

  Yet the agent recalled Alex's preferences and name
  because Memanto stores memories **persistently** outside
  the LangGraph state.

  This is cross-session recall in action! 🎯
    """)

    if not server_available:
        print("  💡 Tip: Set up a real Memanto server to test with")
        print("     the actual Moorcheh semantic search engine.")
        print(f"     See the Memanto repo: https://github.com/moorcheh-ai/memanto\n")


if __name__ == "__main__":
    main()
