"""
Agent definitions for the CrewAI + Memanto integration example.

Two agents share a single Memanto memory namespace so the Writer
can retrieve memories stored by the Researcher.
"""

from __future__ import annotations

from crewai import Agent
from crewai.tools import BaseTool


def create_research_agent(
    remember_tool: BaseTool,
    recall_tool: BaseTool,
    llm: str = "openrouter/tencent/hy3-preview:free",
) -> Agent:
    """Create the Senior Market Research Analyst agent."""
    return Agent(
        role="Senior Market Research Analyst",
        goal=(
            "Research the AI agent framework market thoroughly and store "
            "every key finding as a structured memory using the memanto_remember tool. "
            "Each memory must be concise (under 500 characters), use the correct "
            "memory type, and include relevant tags."
        ),
        backstory=(
            "You are an expert market analyst specializing in AI and developer tools. "
            "You systematically break down complex topics into atomic, well-categorized "
            "findings. You always store your research in the team's shared memory so "
            "that other team members can access it later, even in future sessions."
        ),
        tools=[remember_tool, recall_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )


def create_writer_agent(
    recall_tool: BaseTool,
    answer_tool: BaseTool,
    llm: str = "openrouter/tencent/hy3-preview:free",
) -> Agent:
    """Create the Technical Briefing Writer agent."""
    return Agent(
        role="Technical Briefing Writer",
        goal=(
            "Retrieve all research findings from memory using the memanto_recall tool "
            "and write a clear, data-driven executive briefing. Use memanto_answer "
            "for synthesizing insights from multiple memories."
        ),
        backstory=(
            "You are a skilled technical writer who creates concise executive briefings "
            "for leadership. You never fabricate data — you only use information "
            "retrieved from the team's shared memory. You cite your sources and "
            "organize findings into clear sections."
        ),
        tools=[recall_tool, answer_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )
