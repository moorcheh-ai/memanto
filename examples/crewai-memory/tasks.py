"""
Task definitions for the CrewAI + Memanto integration example.
"""

from __future__ import annotations

from crewai import Agent, Task


def create_research_task(agent: Agent, topic: str = "AI agent frameworks") -> Task:
    """Create the market research task."""
    return Task(
        description=(
            f"Research the current state of the {topic} market. "
            "For each key finding, use the memanto_remember tool to store it with:\n"
            "  - An appropriate memory type: 'fact' for data points and statistics, "
            "'observation' for trends and patterns, 'decision' for strategic insights\n"
            "  - A short, descriptive title (under 100 characters)\n"
            "  - Concise content (under 500 characters) with specific details\n"
            "  - A confidence score (0.9-1.0 for verified facts, 0.7-0.85 for estimates)\n"
            "  - Relevant comma-separated tags (e.g. 'market-size,ai,2026')\n\n"
            "Store at least 5 distinct memories covering: market size, key players, "
            "growth trends, technical differentiators, and adoption patterns.\n\n"
            "After storing all findings, use memanto_recall to verify they were saved "
            "by searching for them."
        ),
        expected_output=(
            "A confirmation that all research findings have been stored in Memanto, "
            "with a summary list of stored memory IDs and their titles."
        ),
        agent=agent,
    )


def create_writing_task(agent: Agent, topic: str = "AI agent frameworks") -> Task:
    """Create the briefing writing task."""
    return Task(
        description=(
            f"Write an executive briefing about the {topic} market based entirely "
            "on memories stored by the research team.\n\n"
            "Steps:\n"
            "1. Use memanto_recall with query 'market research findings' to retrieve "
            "all stored research (set limit to 10)\n"
            "2. Use memanto_recall with specific queries like 'market size', "
            "'key players', 'growth trends' to find targeted information\n"
            "3. Use memanto_answer to synthesize insights: "
            "'What are the key trends and strategic implications in the AI agent market?'\n"
            "4. Write a structured briefing with sections: Executive Summary, "
            "Market Overview, Key Players, Trends, and Strategic Recommendations\n\n"
            "Important: Only include information retrieved from memory. "
            "Do not fabricate data points."
        ),
        expected_output=(
            "A well-structured executive briefing (300-500 words) with clear sections, "
            "data points from stored memories, and strategic recommendations."
        ),
        agent=agent,
    )
