"""
Memanto + LangGraph Integration

This module provides a long-term memory layer for LangGraph agents
using Memanto as the persistent memory backend.
"""

from typing import Any, Dict, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, MessagesState
from memanto import MemantoClient


class MemantoLangGraphMemory:
    """Integrates Memanto as long-term memory for LangGraph agents."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.client = MemantoClient(api_key=api_key, base_url=base_url)

    def save_conversation(
        self,
        session_id: str,
        messages: List[BaseMessage],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save conversation messages to Memanto long-term memory."""
        memory_entries = []
        for msg in messages:
            entry = {
                "role": "human" if isinstance(msg, HumanMessage) else "ai",
                "content": msg.content,
                "session_id": session_id,
                "metadata": metadata or {},
            }
            memory_entries.append(entry)
        return self.client.store_batch(memory_entries)

    def recall(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Recall relevant memories from Memanto."""
        filters = {}
        if session_id:
            filters["session_id"] = session_id
        return self.client.search(query, top_k=top_k, filters=filters)

    def get_context_for_prompt(self, query: str, top_k: int = 5) -> str:
        """Get formatted memory context for injection into prompts."""
        memories = self.recall(query, top_k=top_k)
        if not memories:
            return ""
        context_lines = ["[Relevant past context:]"]
        for mem in memories:
            role = mem.get("role", "unknown")
            content = mem.get("content", "")
            context_lines.append(f"  {role}: {content}")
        return "\n".join(context_lines)


def create_memory_enabled_agent(memory: MemantoLangGraphMemory):
    """Create a LangGraph agent with Memanto long-term memory."""

    def should_save_memory(state: MessagesState) -> str:
        """Decide whether to save to memory after each turn."""
        return "save_memory"

    def chat_with_memory(state: MessagesState) -> Dict:
        """Chat node that incorporates long-term memory."""
        last_message = state["messages"][-1]
        if isinstance(last_message, HumanMessage):
            context = memory.get_context_for_prompt(last_message.content)
            # In a real implementation, you would inject context into the LLM call
            return {"messages": state["messages"], "memory_context": context}
        return {"messages": state["messages"]}

    def save_to_memory(state: MessagesState) -> Dict:
        """Save the conversation turn to long-term memory."""
        # This would be called asynchronously in production
        return {"messages": state["messages"]}

    # Build the graph
    graph = StateGraph(MessagesState)
    graph.add_node("chat", chat_with_memory)
    graph.add_node("save_memory", save_to_memory)
    graph.add_edge("chat", "save_memory")
    graph.add_edge("save_memory", "__end__")
    graph.set_entry_point("chat")

    return graph.compile()


# Example usage
if __name__ == "__main__":
    memory = MemantoLangGraphMemory(api_key="your-api-key")

    # Save a conversation
    messages = [
        HumanMessage(content="What is the capital of France?"),
        AIMessage(content="The capital of France is Paris."),
    ]
    memory.save_conversation("session-1", messages)

    # Recall relevant memories
    results = memory.recall("France capital")
    print(f"Found {len(results)} relevant memories")

    # Create an agent with memory
    agent = create_memory_enabled_agent(memory)
    result = agent.invoke({"messages": [HumanMessage(content="Tell me about France")]})
    print(result)
