"""
LangGraph + Memanto Integration Example

This module implements a stateful agent graph that integrates Memanto as a 
session-agnostic, long-term memory layer.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Annotated, Any, Dict, List, Sequence, TypedDict, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """
    The state of the graph agent, maintaining message history and 
    intermediate memories retrieved/extracted.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    recalled_memories: List[Dict[str, Any]]
    new_memories_extracted: List[Dict[str, Any]]



class MemantoMemoryManager:
    """
    Manages long-term memories using the Moorcheh Memanto SDK.
    """

    def __init__(self, api_key: str, agent_id: str = "langgraph-agent") -> None:
        """
        Initialize the memory manager.
        """
        self.api_key = api_key
        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self.initialized = False

    def initialize(self) -> None:
        """
        Ensure the agent exists and activate a session.
        """
        if self.initialized:
            return

        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="Long term memory layer for LangGraph agents",
            )
            logger.info("Created LangGraph memory agent '%s'", self.agent_id)
        except AgentAlreadyExistsError:
            logger.info("LangGraph memory agent '%s' already exists, reusing", self.agent_id)
        except Exception as e:
            logger.error("Failed to create memory agent '%s': %s", self.agent_id, e)
            raise

        self.client.activate_agent(self.agent_id, duration_hours=12)
        self.initialized = True

    def recall_memories(self, query: str) -> List[Dict[str, Any]]:
        """
        Query Memanto for matching memories.
        """
        self.initialize()
        try:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=3,
                min_similarity=0.45,
            )
            return result.get("memories", [])
        except Exception as e:
            logger.warning("Failed to recall memories: %s", e)
            return []

    def remember(
        self, memory_type: str, title: str, content: str, tags: List[str]
    ) -> str:
        """
        Store a new memory in Memanto.
        """
        self.initialize()
        try:
            result = self.client.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=1.0,
                tags=tags,
                source="langgraph-integration",
            )
            return result.get("memory_id", "")
        except Exception as e:
            logger.warning("Failed to store memory: %s", e)
            return ""


def build_agent_graph(memory_manager: MemantoMemoryManager) -> StateGraph:
    """
    Constructs the LangGraph StateGraph incorporating memory recall and extraction.
    """

    def recall_memories_node(state: AgentState) -> Dict[str, Any]:
        """
        Retrieves relevant historical memories based on the user's latest message.
        """
        messages = state.get("messages", [])
        if not messages:
            return {"recalled_memories": []}

        # Look for the last human message query
        last_human_query = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_human_query = str(msg.content)
                break

        if not last_human_query:
            return {"recalled_memories": []}

        memories = memory_manager.recall_memories(last_human_query)
        return {"recalled_memories": memories}

    def llm_node(state: AgentState) -> Dict[str, Any]:
        """
        Simulates the LLM reasoning process. Injects recalled memories into system instructions.
        """
        recalled = state.get("recalled_memories", [])
        messages = list(state.get("messages", []))
        user_id = state.get("user_id", "default_user")

        # Format system instructions including recalled memories
        system_instructions = (
            "You are a helpful AI assistant. You have access to a long-term "
            "persistent memory database (Memanto) that stores facts and preferences "
            "across disjointed conversation sessions.\n"
        )
        if recalled:
            system_instructions += "\nRecalled long-term memories for this context:\n"
            for idx, mem in enumerate(recalled, 1):
                system_instructions += f"- [{mem.get('type', 'fact').upper()}] {mem.get('title')}: {mem.get('content')}\n"
            system_instructions += "\nUse this context to address the user correctly."
        else:
            system_instructions += "\nNo relevant historical memories were found."

        # Simulating LLM behavior
        last_msg = messages[-1] if messages else None
        last_content = last_msg.content.lower() if last_msg else ""

        response_content = ""
        # Check if we have relevant memories to reference in our mock response
        if recalled:
            # We mock referencing the memory
            ref_content = recalled[0].get("content", "")
            response_content = (
                f"I remember you mentioned that {ref_content}. "
                "How can I assist you further with that preference today?"
            )
        else:
            # Standard helper response
            if "my name is" in last_content:
                name_match = re.search(r"my name is\s+([a-zA-Z0-9]+)", last_content)
                name = name_match.group(1) if name_match else "friend"
                response_content = f"Nice to meet you, {name}! I have saved this in my permanent memory."
            elif "i prefer" in last_content or "i like" in last_content:
                response_content = "Got it! I have recorded your preference in my persistent memory."
            else:
                response_content = "Hello! I am your graph assistant. I remember details across sessions using Memanto."

        new_message = AIMessage(content=response_content)
        return {"messages": [new_message]}

    def extract_memories_node(state: AgentState) -> Dict[str, Any]:
        """
        Analyzes the conversation for new key facts or preferences, and persists them.
        """
        messages = state.get("messages", [])
        user_id = state.get("user_id", "default_user")
        if len(messages) < 2:
            return {"new_memories_extracted": []}

        # Analyze the latest human message and assistant response interaction
        human_msg = messages[-2]
        assistant_msg = messages[-1]

        if not isinstance(human_msg, HumanMessage):
            return {"new_memories_extracted": []}

        content = str(human_msg.content)
        content_lower = content.lower()
        new_memories = []

        # Simple rule-based active extraction patterns
        # 1. Names
        if "my name is" in content_lower:
            match = re.search(r"my name is\s+([a-zA-Z0-9]+)", content_lower, re.I)
            if match:
                name = match.group(1).capitalize()
                mem_id = memory_manager.remember(
                    memory_type="fact",
                    title="User Profile Name",
                    content=f"The user's name is {name}.",
                    tags=["profile", "name", user_id],
                )
                new_memories.append({"id": mem_id, "type": "fact", "content": f"The user's name is {name}."})

        # 2. Tech Stack preferences
        elif "i prefer" in content_lower or "i write code in" in content_lower:
            pref_match = re.search(r"(?:prefer|write code in)\s+([a-zA-Z0-9\+\#\s\.\-]+)", content_lower)
            if pref_match:
                pref = pref_match.group(1).strip()
                mem_id = memory_manager.remember(
                    memory_type="preference",
                    title="Programming Language Preference",
                    content=f"The user prefers coding in {pref}.",
                    tags=["preference", "coding", user_id],
                )
                new_memories.append({"id": mem_id, "type": "preference", "content": f"The user prefers coding in {pref}."})

        return {"new_memories_extracted": new_memories}

    # Define StateGraph
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("recall", recall_memories_node)
    workflow.add_node("llm", llm_node)
    workflow.add_node("extract", extract_memories_node)

    # Set Edges
    workflow.add_edge(START, "recall")
    workflow.add_edge("recall", "llm")
    workflow.add_edge("llm", "extract")
    workflow.add_edge("extract", END)

    return workflow
