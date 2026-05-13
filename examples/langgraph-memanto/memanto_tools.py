"""
Memanto Tools for LangChain / LangGraph

This module provides LangChain-compatible tools that wrap Memanto's SdkClient.
These tools allow LangGraph agents to store and retrieve long-term persistent 
memories that survive across sessions.
"""

from typing import Optional
from langchain_core.tools import tool

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

# Valid Memanto memory types for reference in tool descriptions
VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)

class MemantoToolbox:
    """
    A helper class to manage Memanto SdkClient and provide LangChain tools.
    """
    def __init__(self, api_key: str, agent_id: str):
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id
        self._setup_done = False

    def ensure_setup(self):
        """Ensure the agent exists and a session is active."""
        if self._setup_done:
            return
        
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="LangGraph Persistent Memory Agent"
            )
        except AgentAlreadyExistsError:
            pass
        
        self.client.activate_agent(self.agent_id)
        self._setup_done = True

    def get_tools(self):
        """Return a list of LangChain tools bound to this toolbox."""
        
        @tool
        def memanto_remember(
            memory_type: str,
            title: str,
            content: str,
            confidence: float = 0.85,
            tags: Optional[str] = None
        ) -> str:
            """
            Store a structured memory in Memanto for long-term persistence.
            Use this to save facts, observations, decisions, preferences, or any
            information that should be available in future sessions.
            
            Args:
                memory_type: Semantic type. Must be one of: fact, preference, goal, decision, artifact, learning, event, instruction, relationship, context, observation, commitment, error.
                title: Short title for the memory (max 100 chars).
                content: The memory content to store (max 500 chars).
                confidence: Confidence score 0.0-1.0.
                tags: Comma-separated tags (optional).
            """
            self.ensure_setup()
            tag_list = [t.strip() for t in tags.split(",")] if tags else []
            
            result = self.client.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tag_list
            )
            
            return f"Memory stored: {title} (ID: {result['memory_id']})"

        @tool
        def memanto_recall(
            query: str,
            limit: int = 5,
            memory_types: Optional[str] = None
        ) -> str:
            """
            Search and retrieve memories from Memanto's persistent database.
            Use this to retrieve facts, research findings, or any previously stored info.
            
            Args:
                query: Natural language search query.
                limit: Max number of memories to retrieve (1-20).
                memory_types: Comma-separated memory types to filter by (optional).
            """
            self.ensure_setup()
            type_list = [t.strip() for t in memory_types.split(",")] if memory_types else None
            
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=limit,
                type=type_list
            )
            
            memories = result.get("memories", [])
            if not memories:
                return f"No memories found for query: '{query}'"
            
            formatted = [f"- [{m.get('type')}] {m.get('title')}: {m.get('content')}" for m in memories]
            return "\n".join(formatted)

        @tool
        def memanto_answer(question: str) -> str:
            """
            Ask a question and get an AI-generated answer grounded in stored memories (RAG).
            Synthesizes insights from multiple stored memories.
            """
            self.ensure_setup()
            result = self.client.answer(
                agent_id=self.agent_id,
                question=question
            )
            return result.get("answer", "No answer could be generated.")

        return [memanto_remember, memanto_recall, memanto_answer]
