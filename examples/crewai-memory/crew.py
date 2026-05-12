"""
Crew orchestration for the CrewAI + Memanto integration example.

Provides factory functions that wire up agents, tasks, and tools
into ready-to-run Crews.
"""

from __future__ import annotations

from agents import create_research_agent, create_writer_agent
from crewai import Crew, Process
from memanto_crewai import create_memanto_tools
from tasks import create_research_task, create_writing_task

from memanto.cli.client.sdk_client import SdkClient


def build_research_crew(
    client: SdkClient,
    agent_id: str,
    topic: str = "AI agent frameworks",
    llm: str = "openrouter/tencent/hy3-preview:free",
) -> Crew:
    """Build a crew with only the Research Agent."""
    tools = create_memanto_tools(client, agent_id)
    researcher = create_research_agent(tools["remember"], tools["recall"], llm=llm)
    research_task = create_research_task(researcher, topic=topic)

    return Crew(
        agents=[researcher],
        tasks=[research_task],
        process=Process.sequential,
        memory=False,  # Memanto replaces CrewAI's built-in LanceDB memory via tools
        verbose=True,
    )


def build_writer_crew(
    client: SdkClient,
    agent_id: str,
    topic: str = "AI agent frameworks",
    llm: str = "openrouter/tencent/hy3-preview:free",
) -> Crew:
    """Build a crew with only the Writer Agent."""
    tools = create_memanto_tools(client, agent_id)
    writer = create_writer_agent(tools["recall"], tools["answer"], llm=llm)
    writing_task = create_writing_task(writer, topic=topic)

    return Crew(
        agents=[writer],
        tasks=[writing_task],
        process=Process.sequential,
        memory=False,  # Memanto replaces CrewAI's built-in LanceDB memory via tools
        verbose=True,
    )


def build_full_crew(
    client: SdkClient,
    agent_id: str,
    topic: str = "AI agent frameworks",
    llm: str = "openrouter/tencent/hy3-preview:free",
) -> Crew:
    """Build the full pipeline: Research Agent -> Writer Agent."""
    tools = create_memanto_tools(client, agent_id)

    researcher = create_research_agent(tools["remember"], tools["recall"], llm=llm)
    writer = create_writer_agent(tools["recall"], tools["answer"], llm=llm)

    research_task = create_research_task(researcher, topic=topic)
    writing_task = create_writing_task(writer, topic=topic)

    return Crew(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        process=Process.sequential,
        memory=False,  # Memanto replaces CrewAI's built-in LanceDB memory via tools
        verbose=True,
    )
