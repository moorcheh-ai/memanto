"""Memanto integration for LangGraph agents.

Provides persistent memory operations (remember, recall, answer) 
that can be used as LangGraph state modifiers or tools.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Use Memanto's direct client (zero-dependency, lightweight)
from memanto.cli.client.direct_client import MoorchehClient


class LangGraphMemantoMemory:
    """Persistent memory layer for LangGraph agents using Memanto."""
    
    def __init__(self, api_key: Optional[str] = None, agent_id: str = "langgraph-demo"):
        """Initialize Memanto memory for a LangGraph agent.
        
        Args:
            api_key: Moorcheh API key (defaults to MOORCHEH_API_KEY env var)
            agent_id: Agent ID for memory isolation
        """
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY required. "
                "Get one free at https://console.moorcheh.ai/api-keys"
            )
        
        self.agent_id = agent_id
        self.client = MoorchehClient(api_key=self.api_key)
    
    def remember(
        self, 
        content: str, 
        memory_type: str = "fact",
        title: Optional[str] = None,
        confidence: float = 0.9,
        tags: Optional[List[str]] = None,
        source: str = "langgraph"
    ) -> Dict[str, Any]:
        """Store a memory in Memanto.
        
        Args:
            content: The memory content (max 500 chars)
            memory_type: fact, decision, instruction, commitment, event
            title: Optional title (max 100 chars, defaults to content[:100])
            confidence: 0.0-1.0 confidence score
            tags: Optional tags for filtering
            source: Memory source identifier
            
        Returns:
            Memanto response with memory ID
        """
        if title is None:
            title = content[:100] + ("..." if len(content) > 100 else "")
        
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content[:500],
            confidence=confidence,
            tags=tags or [],
            source=source,
        )
    
    def recall(
        self, 
        query: str, 
        top_k: int = 5,
        memory_types: Optional[List[str]] = None,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant memories from Memanto.
        
        Args:
            query: Natural language query
            top_k: Number of memories to retrieve
            memory_types: Filter by memory types
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of relevant memories
        """
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=top_k,
            type=memory_types,
            min_confidence=min_confidence,
        )
        
        # Extract memories from response
        return result.get("memories", [])
    
    def answer(self, question: str, **kwargs) -> str:
        """Generate an LLM-grounded answer from memory.
        
        Unlike recall which returns raw memories, answer synthesizes
        them into a coherent response.
        
        Args:
            question: Question to answer from memory
            
        Returns:
            Synthesized answer
        """
        result = self.client.answer(
            agent_id=self.agent_id,
            question=question,
            **kwargs
        )
        return result.get("answer", "No answer generated.")
    
    def get_context_for_llm(self, query: str, top_k: int = 5) -> str:
        """Format retrieved memories as LLM context string.
        
        This is the key integration point — transforms Memanto's
        structured memories into a context blob that LangGraph's
        LLM node can consume.
        
        Args:
            query: Current user query or topic
            top_k: Number of memories to include
            
        Returns:
            Formatted context string for LLM prompt
        """
        memories = self.recall(query, top_k=top_k)
        
        if not memories:
            return "No relevant memories found."
        
        context_parts = ["=== RELEVANT MEMORIES ==="]
        for i, mem in enumerate(memories, 1):
            ctx = (
                f"[{i}] Type: {mem.get('type', 'unknown')} | "
                f"Confidence: {mem.get('confidence', 'N/A')} | "
                f"Title: {mem.get('title', 'N/A')}\n"
                f"    Content: {mem.get('content', '')}"
            )
            context_parts.append(ctx)
        
        return "\n\n".join(context_parts)


def create_memanto_tools(memory: LangGraphMemantoMemory):
    """Create LangGraph-compatible tools from Memanto operations."""
    return {
        "memanto_remember": memory.remember,
        "memanto_recall": memory.recall,
        "memanto_answer": memory.answer,
    }
