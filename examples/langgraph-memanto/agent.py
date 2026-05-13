"""
LangGraph Agent for Memanto

This module defines a LangGraph workflow for a Research Assistant
that uses Memanto for long-term memory.
"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent


def create_memanto_agent(model_name: str, tools: list):
    """
    Create a LangGraph agent that uses Memanto tools.
    """
    model = ChatOpenAI(model=model_name, temperature=0)
    
    # We use the prebuilt create_react_agent for simplicity
    agent = create_react_agent(model, tools)
    return agent
