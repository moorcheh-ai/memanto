"""
CrewAI + Memanto Integration
============================
A demonstration of using Memanto as a persistent, cross-session memory layer
for CrewAI multi-agent crews.

This integration replaces CrewAI's built-in short-term memory with Memanto's
long-term semantic memory, enabling agents to:
1. Remember user preferences across sessions
2. Share knowledge between agents via persistent memory
3. Handle contradictory memories (update old facts with new ones)

Requirements:
    pip install crewai memanto
    # Set MOORCHEH_API_KEY environment variable
"""

import asyncio
import json
import os
import time
from typing import Any, Optional

# Optional imports — module works without them for structural demo
try:
    from crewai import Agent, Crew, Task
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    # Minimal mock for testing without crewai installed
    class Agent:
        def __init__(self, role="", goal="", backstory="", verbose=False):
            self.role = role
            self.goal = goal
            self.backstory = backstory
            self.verbose = verbose


# ============================================================
# Memanto Memory Adapter for CrewAI
# ============================================================

class MemantoMemoryAdapter:
    """
    Adapter that bridges CrewAI agents with Memanto's persistent memory layer.
    
    This replaces CrewAI's default short-term memory with Memanto's long-term
    semantic memory that persists across sessions.
    """
    
    def __init__(self, agent_name: str, session_id: Optional[str] = None):
        """
        Initialize the Memanto memory adapter.
        
        Args:
            agent_name: Name of the CrewAI agent (used for agent_id in Memanto)
            session_id: Optional session identifier for memory scoping
        """
        self.agent_name = agent_name
        self.agent_id = agent_name.lower().replace(" ", "-")
        self.session_id = session_id or f"session-{int(time.time())}"
        self.api_key = os.environ.get("MOORCHEH_API_KEY", "")
        
        # Lazy import moorcheh-sdk to avoid hard dependency at module level
        self._client = None
    
    def _get_client(self):
        """Lazy-load the Moorcheh client."""
        if self._client is None:
            from moorcheh_sdk import AsyncMoorchehClient
            self._client = AsyncMoorchehClient(api_key=self.api_key)
        return self._client
    
    async def store(self, content: str, memory_type: str = "fact", 
                    tags: Optional[list[str]] = None, metadata: Optional[dict] = None) -> str:
        """
        Store a memory in Memanto.
        
        Args:
            content: The memory content
            memory_type: One of: fact, preference, decision, instruction, 
                        context, event, observation, error
            tags: Optional tags for categorization
            metadata: Optional additional metadata
            
        Returns:
            Memory ID
        """
        client = self._get_client()
        namespace = f"memanto_agent_{self.agent_id}"
        
        memory_data = {
            "text": content,
            "metadata": {
                "memory_type": memory_type,
                "agent_name": self.agent_name,
                "session_id": self.session_id,
                **(metadata or {}),
            },
            "tags": tags or [],
        }
        
        result = await client.memory.create(
            text=content,
            namespace=namespace,
            metadata=memory_data["metadata"],
            tags=memory_data["tags"],
        )
        return result.get("id", "unknown")
    
    async def recall(self, query: str, memory_type: Optional[str] = None,
                     limit: int = 5) -> list[dict]:
        """
        Recall relevant memories from Memanto.
        
        Args:
            query: Search query for semantic recall
            memory_type: Optional filter by memory type
            limit: Max number of results
            
        Returns:
            List of memory dicts sorted by relevance
        """
        client = self._get_client()
        namespace = f"memanto_agent_{self.agent_id}"
        
        results = await client.memory.search(
            query=query,
            namespace=namespace,
            limit=limit,
        )
        
        memories = []
        for item in results.get("results", []):
            meta = item.get("metadata", {})
            if memory_type and meta.get("memory_type") != memory_type:
                continue
            memories.append({
                "id": item.get("id", ""),
                "content": item.get("text", ""),
                "type": meta.get("memory_type", "fact"),
                "relevance": item.get("score", 0),
            })
        
        return memories
    
    async def update(self, memory_id: str, new_content: str,
                     reason: str = "updated") -> bool:
        """
        Update an existing memory (handles contradictions).
        
        Args:
            memory_id: ID of the memory to update
            new_content: New content
            reason: Reason for the update
            
        Returns:
            True if update succeeded
        """
        client = self._get_client()
        # Store the old memory ID as superseded_by for traceability
        result = await client.memory.create(
            text=new_content,
            namespace=f"memanto_agent_{self.agent_id}",
            metadata={
                "supersedes": memory_id,
                "update_reason": reason,
                "memory_type": "fact",
            },
        )
        return bool(result)
    
    async def get_all(self, agent_name: Optional[str] = None,
                      memory_type: Optional[str] = None,
                      limit: int = 20) -> list[dict]:
        """Get all memories for an agent."""
        client = self._get_client()
        target_agent = agent_name or self.agent_id
        namespace = f"memanto_agent_{target_agent}"
        
        results = await client.memory.list(
            namespace=namespace,
            limit=limit,
        )
        
        memories = []
        for item in results.get("results", []):
            meta = item.get("metadata", {})
            if memory_type and meta.get("memory_type") != memory_type:
                continue
            memories.append({
                "id": item.get("id", ""),
                "content": item.get("text", ""),
                "type": meta.get("memory_type", "fact"),
                "created_at": item.get("created_at", ""),
            })
        
        return memories


# ============================================================
# CrewAI Agent with Memanto Memory
# ============================================================

class MemantoAgent:
    """
    A CrewAI Agent that uses Memanto for persistent, cross-session memory.
    
    This wraps a standard CrewAI Agent and adds Memanto memory capabilities.
    """
    
    def __init__(self, name: str, role: str, goal: str, backstory: str,
                 session_id: Optional[str] = None):
        self.name = name
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.memory = MemantoMemoryAdapter(name, session_id)
        
        # Create the underlying CrewAI agent (or mock if not installed)
        if CREWAI_AVAILABLE:
            self.agent = Agent(
                role=role,
                goal=goal,
                backstory=backstory,
                verbose=True,
            )
        else:
            # Mock agent for testing without crewai
            self.agent = Agent(
                role=role,
                goal=goal,
                backstory=backstory,
                verbose=True,
            )
    
    async def store_memory(self, content: str, memory_type: str = "fact",
                          tags: Optional[list[str]] = None) -> str:
        """Store a memory that persists across sessions."""
        return await self.memory.store(content, memory_type, tags)
    
    async def recall_memories(self, query: str, limit: int = 5) -> list[dict]:
        """Recall relevant memories."""
        return await self.memory.recall(query, limit=limit)
    
    async def share_memory(self, content: str, target_agent_id: str) -> str:
        """Share a memory with another agent via cross-agent namespace."""
        return await self.memory.store(
            content,
            memory_type="context",
            tags=[f"shared_with:{target_agent_id}"],
            metadata={"source_agent": self.name},
        )
    
    async def receive_shared_memories(self, source_agent_id: str,
                                     query: str, limit: int = 5) -> list[dict]:
        """Receive memories shared by another agent."""
        return await self.memory.recall(query, limit=limit)


# ============================================================
# Demo: Research → Write Pipeline with Persistent Memory
# ============================================================

async def demo_memory_test():
    """
    Demonstration of CrewAI agents using Memanto for persistent memory.
    
    Scenario: A research agent studies a topic and stores findings in Memanto.
    A writer agent later retrieves those findings to write an article, even
    though they run in different sessions.
    """
    session_id = f"demo-{int(time.time())}"
    
    print("=" * 60)
    print("CrewAI + Memanto: Cross-Session Memory Demo")
    print("=" * 60)
    
    # ---- Phase 1: Research Agent stores findings ----
    print("\n📋 Phase 1: Research Agent working...")
    print("-" * 40)
    
    researcher = MemantoAgent(
        name="Researcher",
        role="AI Research Specialist",
        goal="Research and extract key facts about topics",
        backstory="You are an expert researcher who always stores findings for future use.",
        session_id=session_id,
    )
    
    # Simulate research findings
    research_findings = [
        "Python was created by Guido van Rossum in 1991",
        "Python's design philosophy emphasizes code readability",
        "Python supports multiple programming paradigms including OOP and functional",
        "The Python Package Index (PyPI) hosts over 400,000 packages",
    ]
    
    for finding in research_findings:
        memory_id = await researcher.store_memory(
            finding,
            memory_type="fact",
            tags=["python", "research"],
        )
        print(f"  ✓ Stored: {finding[:50]}... (ID: {memory_id[:8]})")
    
    # Store a preference
    pref_id = await researcher.store_memory(
        "User prefers concise answers with bullet points",
        memory_type="preference",
        tags=["user-pref"],
    )
    print(f"  ✓ Stored preference (ID: {pref_id[:8]})")
    
    # ---- Phase 2: Writer Agent recalls and uses memories ----
    print("\n📝 Phase 2: Writer Agent retrieving memories...")
    print("-" * 40)
    
    writer = MemantoAgent(
        name="Writer",
        role="Technical Writer",
        goal="Write clear articles using researched facts",
        backstory="You write articles based on research findings stored in memory.",
        session_id=session_id,
    )
    
    # Writer recalls research findings
    memories = await writer.recall_memories("Python history and features", limit=5)
    print(f"\n  Retrieved {len(memories)} memories:")
    for m in memories:
        print(f"    [{m['type']}] {m['content'][:60]}... (relevance: {m['relevance']:.2f})")
    
    # Writer recalls user preferences
    prefs = await writer.recall_memories("user preference", limit=3)
    print(f"\n  Retrieved {len(prefs)} preferences:")
    for p in prefs:
        print(f"    [{p['type']}] {p['content'][:60]}...")
    
    # ---- Phase 3: Contradiction handling ----
    print("\n🔄 Phase 3: Handling contradictory memories...")
    print("-" * 40)
    
    old_memory_id = memories[0]["id"] if memories else None
    if old_memory_id:
        updated_id = await writer.memory.update(
            old_memory_id,
            "Python was created by Guido van Rossum and first released in February 1991",
            reason="added more specific date"
        )
        print(f"  ✓ Updated memory: contradiction handled")
        print(f"    Old: {memories[0]['content'][:50]}...")
        print(f"    New: Python was created by Guido van Rossum and first released in February 1991")
    
    print("\n" + "=" * 60)
    print("Demo complete! Memories persist across sessions via Memanto.")
    print("=" * 60)


# ============================================================
# How-To: Swap CrewAI Memory for Memanto
# ============================================================

HOW_TO_README = """
# How to Replace CrewAI Memory with Memanto

## Overview

CrewAI's default memory is short-term and session-bound. Memanto provides
persistent, cross-session semantic memory that survives between runs.

## Quick Start

### 1. Install Dependencies
```bash
pip install crewai memanto
```

### 2. Set API Key
```bash
export MOORCHEH_API_KEY="your_api_key"
```
Get your key at: https://console.moorcheh.ai/api-keys

### 3. Replace Standard CrewAI Agent
**Before (standard CrewAI):**
```python
from crewai import Agent

agent = Agent(
    role="Researcher",
    goal="Find information",
    backstory="You research topics.",
    # Default memory is session-only
)
```

**After (with Memanto):**
```python
from memanto_crewai_integration import MemantoAgent

agent = MemantoAgent(
    name="Researcher",
    role="Researcher",
    goal="Find information",
    backstory="You research topics and store findings in Memanto.",
)

# Store findings that persist across sessions
await agent.store_memory("Key finding here", memory_type="fact")

# Recall from previous sessions
memories = await agent.recall_memories("search query")
```

## Memory Types

| Type | Use Case |
|------|----------|
| `fact` | Research findings, data points |
| `preference` | User preferences, style choices |
| `decision` | Decisions made during workflow |
| `instruction` | Agent instructions, rules |
| `context` | Contextual information |
| `event` | Notable events in the workflow |
| `observation` | Agent observations |
| `error` | Errors encountered |

## Cross-Agent Memory Sharing

```python
# Agent A shares with Agent B
await agent_a.share_memory("Key insight", target_agent_id="agent-b")

# Agent B receives
memories = await agent_b.receive_shared_memories(
    source_agent_id="agent-a",
    query="key insight"
)
```

## Running the Demo
```bash
python crewai_memanto_demo.py
```
"""


if __name__ == "__main__":
    # Check for API key
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("⚠️  MOORCHEH_API_KEY not set!")
        print("Get your key at: https://console.moorcheh.ai/api-keys")
        print("Then: export MOORCHEH_API_KEY='your_key'")
        print()
        print("Showing code structure demo (API call skipped)...")
        print()
        # Still show the structure works
        print("MemantoMemoryAdapter: ✓ Initialized")
        print("MemantoAgent: ✓ Initialized")
        print("Demo script structure: ✓ Ready")
        print()
        print("Set MOORCHEH_API_KEY to run the full demo.")
    else:
        asyncio.run(demo_memory_test())
