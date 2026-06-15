"""
Shared LangGraph state schema for the LangGraph + Memanto example.
"""

from typing import Annotated, TypedDict

from langgraph.graph import add_messages


class ResearchState(TypedDict):
    """
    Shared state for the research pipeline.

    Attributes:
        messages: Conversation history (appended by add_messages reducer).
        memanto_agent_id: The Memanto agent namespace for shared memory.
        research_topic: The current topic being researched.
        findings: Key findings discovered during research.
    """

    messages: Annotated[list[dict], add_messages]
    memanto_agent_id: str
    research_topic: str
    findings: list[str]
