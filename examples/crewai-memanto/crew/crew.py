"""
crew/crew.py
============
Defines the Research → Writer Crew with Memanto as the shared memory layer.

Flow
----
  Session 1 (or any session):
    ResearchAgent  investigates a topic → stores findings in Memanto
    
  Session 2 (even days later):
    WriterAgent    recalls those findings → drafts a polished article

Because both agents share ONE Memanto agent namespace, every fact stored
by the ResearchAgent is immediately and permanently retrievable by the
WriterAgent — across any number of separate Python process runs.
"""

from __future__ import annotations

import textwrap
from typing import Optional

from crewai import Agent, Crew, Process, Task

from memanto_bridge import MeMantoCrewMemory
from crew.tools import build_tools


def build_crew(
    topic: str,
    memanto_base_url: Optional[str] = None,
    memanto_api_key: Optional[str] = None,
    namespace: str = "research-writer-crew",
    llm_model: str = "gpt-4o",
    run_mode: str = "full",  # "full" | "research_only" | "write_only"
) -> Crew:
    """
    Build and return a Research → Writer Crew backed by Memanto.

    Args:
        topic:             The research topic for this crew run.
        memanto_base_url:  Memanto server URL (or set MEMANTO_BASE_URL env var).
        memanto_api_key:   Moorcheh API key (or set MOORCHEH_API_KEY env var).
        namespace:         Memanto agent_id — the shared memory bucket.
        llm_model:         LLM model name for CrewAI agents.
        run_mode:          Control which tasks run (demonstrates cross-session recall).
    """

    # ── Shared Memanto memory ────────────────────────────────────────────────
    shared_memory = MeMantoCrewMemory(
        base_url=memanto_base_url,
        api_key=memanto_api_key,
        agent_id=namespace,
    )

    # ── Agent tools (all share the same memory instance) ────────────────────
    r_store, r_recall, r_correct, r_answer = build_tools(shared_memory, "ResearchAgent")
    _, w_recall, _, w_answer = build_tools(shared_memory, "WriterAgent")

    # ── Agents ───────────────────────────────────────────────────────────────
    research_agent = Agent(
        role="Senior Research Analyst",
        goal=textwrap.dedent(f"""
            Produce a thorough, well-sourced research brief on: '{topic}'.
            Before starting, ALWAYS call recall_memory to check what we already know.
            Store every key finding with store_finding so the Writer can use them later.
            If you find a stored fact is outdated, use correct_memory to update it.
        """).strip(),
        backstory=textwrap.dedent("""
            You are a meticulous research analyst who never wastes effort re-researching
            facts already in memory. You source every claim, tag memories by topic, and
            proactively correct outdated facts when you spot contradictions.
            Memanto gives you a photographic cross-session memory — use it.
        """).strip(),
        tools=[r_store, r_recall, r_correct],
        llm=llm_model,
        verbose=True,
        allow_delegation=False,
    )

    writer_agent = Agent(
        role="Senior Content Strategist & Writer",
        goal=textwrap.dedent(f"""
            Draft a compelling, publication-ready article about: '{topic}'.
            ALWAYS start by calling recall_memory to retrieve what the Research Agent stored.
            Use answer_from_memory to synthesize findings into coherent paragraphs.
            Never fabricate facts — every claim must come from recalled memories.
        """).strip(),
        backstory=textwrap.dedent("""
            You are a world-class writer who builds entirely on verified research.
            You rely on Memanto to bridge the gap between the research session and yours —
            even if the research was done weeks ago. You turn dry facts into engaging prose.
        """).strip(),
        tools=[w_recall, w_answer],
        llm=llm_model,
        verbose=True,
        allow_delegation=False,
    )

    # ── Tasks ─────────────────────────────────────────────────────────────────
    research_task = Task(
        description=textwrap.dedent(f"""
            Research the topic: '{topic}'

            Steps:
            1. Call recall_memory(query="{topic}") — check existing knowledge.
            2. Identify gaps and research them thoroughly.
            3. For each key finding, call store_finding with relevant tags.
            4. If any stored fact contradicts new information, call correct_memory.
            5. Produce a structured research brief listing all findings.

            Your output must include a bullet list of all memory IDs you stored
            so the Writer Agent can reference them.
        """).strip(),
        expected_output=(
            "A structured research brief with key findings, each annotated "
            "with its Memanto memory ID. Include a summary of what was already "
            "in memory vs. what is newly discovered."
        ),
        agent=research_agent,
    )

    write_task = Task(
        description=textwrap.dedent(f"""
            Write a polished 600-800 word article about: '{topic}'

            Steps:
            1. Call recall_memory(query="{topic}", limit=10) to retrieve all research.
            2. Call answer_from_memory for any specific questions about the data.
            3. Structure the article: Hook → Background → Key Findings → Implications → Conclusion.
            4. Every factual claim must be grounded in recalled memories.
            5. Do NOT call store_finding — your job is to consume, not produce research.
        """).strip(),
        expected_output=(
            "A publication-ready 600-800 word article with a compelling headline, "
            "structured sections, and every claim sourced from Memanto-recalled research."
        ),
        agent=writer_agent,
        context=[research_task],
    )

    # ── Crew ──────────────────────────────────────────────────────────────────
    tasks = []
    if run_mode in ("full", "research_only"):
        tasks.append(research_task)
    if run_mode in ("full", "write_only"):
        tasks.append(write_task)

    crew = Crew(
        agents=[research_agent, writer_agent],
        tasks=tasks,
        process=Process.sequential,
        memory=True,
        memory_config={
            "provider": "custom",
            "config": {"memory": shared_memory},
        },
        verbose=True,
    )

    return crew
