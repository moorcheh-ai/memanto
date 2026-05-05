"""
CrewAI + Memanto Integration Demo
==================================

Demonstrates cross-agent memory sharing using Memanto as the persistent
memory backend for a CrewAI Crew.

Scenario:
    1. A Research Agent investigates a topic and stores findings in Memanto
    2. A Writer Agent retrieves those findings from Memanto and writes a summary
    3. On subsequent runs, agents recall information from previous sessions

This proves:
    - Inter-agent memory (Research → Writer within same run)
    - Cross-session persistence (memories survive between executions)

Requirements:
    pip install crewai memanto

Environment:
    MOORCHEH_API_KEY=your-key-here
    OPENAI_API_KEY=your-key-here  (for CrewAI's LLM)

Usage:
    python main.py                    # Run the full demo
    python main.py --recall-only      # Only recall from previous run (proves persistence)
    python main.py --topic "quantum computing"  # Custom research topic
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from crewai import Agent, Crew, Task
from crewai.memory.unified_memory import Memory

from memanto_backend import MemantoStorageBackend


def create_memory(namespace: str = "crewai-demo") -> Memory:
    """Create a Memory instance backed by Memanto.

    This is the key integration point — swapping CrewAI's default
    in-memory storage for Memanto's persistent semantic backend.
    """
    backend = MemantoStorageBackend(
        api_key=os.environ.get("MOORCHEH_API_KEY"),
        namespace=namespace,
    )
    return Memory(storage=backend)


def build_research_agent() -> Agent:
    """Research Agent — gathers information and commits it to memory."""
    return Agent(
        role="Senior Research Analyst",
        goal=(
            "Conduct thorough research on the assigned topic. "
            "Store all key findings, facts, and insights in memory "
            "so other agents (and future sessions) can access them."
        ),
        backstory=(
            "You are a meticulous researcher with a talent for distilling "
            "complex topics into clear, memorable insights. You always "
            "commit your findings to memory for your team to use later."
        ),
        verbose=True,
        allow_delegation=False,
    )


def build_writer_agent() -> Agent:
    """Writer Agent — retrieves research from memory and produces content."""
    return Agent(
        role="Content Writer",
        goal=(
            "Write a compelling, well-structured summary based on research "
            "findings stored in memory. You should recall what the Research "
            "Agent discovered and synthesize it into polished prose."
        ),
        backstory=(
            "You are a skilled writer who transforms raw research into "
            "engaging content. You rely on your team's shared memory to "
            "access research findings without needing to redo the work."
        ),
        verbose=True,
        allow_delegation=False,
    )


def run_research_phase(topic: str, memory: Memory) -> str:
    """Phase 1: Research Agent gathers info and stores in Memanto."""
    print("\n" + "=" * 60)
    print("  PHASE 1: RESEARCH (storing to Memanto)")
    print("=" * 60 + "\n")

    researcher = build_research_agent()

    research_task = Task(
        description=(
            f"Research the topic: '{topic}'. "
            f"Identify 3-5 key findings, important facts, and notable insights. "
            f"Present your findings clearly with supporting details."
        ),
        expected_output=(
            "A structured research report with 3-5 key findings, "
            "each with a brief explanation and supporting evidence."
        ),
        agent=researcher,
    )

    crew = Crew(
        agents=[researcher],
        tasks=[research_task],
        memory=memory,
        verbose=True,
    )

    result = crew.kickoff()
    output = str(result)

    # Explicitly store the research output in memory with metadata
    # This ensures the Writer Agent can retrieve it by topic
    memory.remember(
        content=f"Research findings on '{topic}': {output}",
        scope="/research",
        categories=["research", "findings"],
        metadata={"topic": topic, "agent": "researcher", "phase": "research"},
        importance=0.9,
    )

    print(f"\n✓ Research complete. Findings stored in Memanto under scope '/research'.")
    print(f"  Topic: {topic}")
    print(f"  Timestamp: {datetime.utcnow().isoformat()}")

    return output


def run_writing_phase(topic: str, memory: Memory) -> str:
    """Phase 2: Writer Agent recalls research from Memanto and writes."""
    print("\n" + "=" * 60)
    print("  PHASE 2: WRITING (recalling from Memanto)")
    print("=" * 60 + "\n")

    # First, demonstrate recall — show what the Writer can access
    recalled = memory.recall(
        query=f"research findings on {topic}",
        scope_prefix="/research",
        limit=5,
    )

    if recalled:
        print(f"✓ Writer Agent recalled {len(recalled)} memories from Memanto:")
        for i, match in enumerate(recalled[:3], 1):
            snippet = match.content[:100] + "..." if len(match.content) > 100 else match.content
            print(f"  [{i}] (score: {match.score:.3f}) {snippet}")
        print()
    else:
        print("⚠ No prior memories found — Writer will work from scratch.\n")

    writer = build_writer_agent()

    writing_task = Task(
        description=(
            f"Write a compelling summary about '{topic}' based on research "
            f"findings available in your memory. The research was conducted "
            f"by the Research Agent and stored for you to access. "
            f"Recall the key findings and synthesize them into a polished piece."
        ),
        expected_output=(
            "A well-written 2-3 paragraph summary that synthesizes "
            "the research findings into engaging, accessible prose."
        ),
        agent=writer,
    )

    crew = Crew(
        agents=[writer],
        tasks=[writing_task],
        memory=memory,
        verbose=True,
    )

    result = crew.kickoff()
    output = str(result)

    # Store the final output too
    memory.remember(
        content=f"Written summary on '{topic}': {output}",
        scope="/output",
        categories=["summary", "final_output"],
        metadata={"topic": topic, "agent": "writer", "phase": "writing"},
        importance=0.8,
    )

    print(f"\n✓ Writing complete. Summary stored in Memanto under scope '/output'.")
    return output


def run_recall_only(topic: str, memory: Memory) -> None:
    """Demonstrate cross-session recall — proves persistence."""
    print("\n" + "=" * 60)
    print("  CROSS-SESSION RECALL (proving persistence)")
    print("=" * 60 + "\n")

    print(f"Searching Memanto for memories about: '{topic}'...\n")

    # Recall research
    research_memories = memory.recall(
        query=f"research findings on {topic}",
        scope_prefix="/research",
        limit=3,
    )

    # Recall outputs
    output_memories = memory.recall(
        query=f"written summary about {topic}",
        scope_prefix="/output",
        limit=3,
    )

    if not research_memories and not output_memories:
        print("❌ No memories found. Run without --recall-only first to populate.")
        return

    if research_memories:
        print(f"📚 Found {len(research_memories)} research memories:")
        for match in research_memories:
            print(f"   Score: {match.score:.3f} | {match.content[:120]}...")
        print()

    if output_memories:
        print(f"📝 Found {len(output_memories)} output memories:")
        for match in output_memories:
            print(f"   Score: {match.score:.3f} | {match.content[:120]}...")
        print()

    print("✓ Cross-session recall successful — Memanto persisted memories between runs!")


def main():
    parser = argparse.ArgumentParser(
        description="CrewAI + Memanto Integration Demo"
    )
    parser.add_argument(
        "--topic",
        default="the impact of large language models on software engineering",
        help="Research topic for the demo",
    )
    parser.add_argument(
        "--recall-only",
        action="store_true",
        help="Only recall from previous run (proves cross-session persistence)",
    )
    parser.add_argument(
        "--namespace",
        default="crewai-demo",
        help="Memanto namespace to use",
    )
    args = parser.parse_args()

    # Validate environment
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("Error: MOORCHEH_API_KEY environment variable not set.")
        print("Get your key at: https://console.moorcheh.ai/api-keys")
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("CrewAI requires an LLM provider. Set OPENAI_API_KEY or configure alternatives.")
        sys.exit(1)

    # Create shared memory backed by Memanto
    memory = create_memory(namespace=args.namespace)

    print("\n" + "━" * 60)
    print("  CrewAI + Memanto Integration Demo")
    print("━" * 60)
    print(f"  Topic:     {args.topic}")
    print(f"  Namespace: {args.namespace}")
    print(f"  Mode:      {'Recall Only' if args.recall_only else 'Full Pipeline'}")
    print("━" * 60)

    if args.recall_only:
        run_recall_only(args.topic, memory)
    else:
        # Run full pipeline: Research → Store → Recall → Write
        research_output = run_research_phase(args.topic, memory)
        writing_output = run_writing_phase(args.topic, memory)

        print("\n" + "━" * 60)
        print("  DEMO COMPLETE")
        print("━" * 60)
        print("\n📋 Final Summary:\n")
        print(writing_output)
        print("\n" + "━" * 60)
        print("  Next steps:")
        print("  • Run again with --recall-only to prove cross-session persistence")
        print("  • Try a different --topic to see memory accumulate")
        print("  • Check Memanto dashboard at https://console.moorcheh.ai")
        print("━" * 60 + "\n")


if __name__ == "__main__":
    main()
