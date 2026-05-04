"""
CrewAI + Memanto Integration Example
=====================================
Demonstrates persistent memory across agent sessions.

- ResearchAgent: Investigates a topic, stores findings in Memanto
- WriterAgent: Retrieves those findings later and writes a summary

Run twice to see memory persistence:
  python crewai_memanto_example.py --mode research  # Session 1
  python crewai_memanto_example.py --mode write     # Session 2 (or days later)
"""

import argparse
import subprocess
import json
import os
from datetime import datetime
from crewai import Agent, Crew, Task, LLM
from crewai.tools import BaseTool
from pydantic import Field


# ── Memanto Memory Bridge ─────────────────────────────────────────────────────

class MemantoMemory:
    """Thin wrapper around the Memanto CLI for CrewAI agents."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._activate()

    def _activate(self):
        result = subprocess.run(
            ["memanto", "agent", "activate", self.agent_id],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            # Create if not exists
            subprocess.run(
                ["memanto", "agent", "create", self.agent_id],
                capture_output=True, text=True
            )

    def remember(self, content: str, memory_type: str = "fact", tags: str = "") -> str:
        cmd = [
            "memanto", "remember", content,
            "--type", memory_type,
            "--source", self.agent_id,
            "--confidence", "0.9",
        ]
        if tags:
            cmd.extend(["--tags", tags])
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr}"

    def recall(self, query: str, limit: int = 5) -> str:
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit)],
            capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def answer(self, question: str) -> str:
        result = subprocess.run(
            ["memanto", "answer", question],
            capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else ""


# ── CrewAI Tools ─────────────────────────────────────────────────────────────

class RememberTool(BaseTool):
    name: str = "remember"
    description: str = (
        "Store a finding or fact in persistent Memanto memory. "
        "Input: JSON string with keys 'content' (the fact), "
        "'type' (fact/insight/preference/learning), and optional 'tags'."
    )
    memory: MemantoMemory = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        try:
            data = json.loads(input_str)
        except json.JSONDecodeError:
            data = {"content": input_str, "type": "fact"}
        return self.memory.remember(
            data.get("content", input_str),
            data.get("type", "fact"),
            data.get("tags", ""),
        )


class RecallTool(BaseTool):
    name: str = "recall"
    description: str = (
        "Retrieve relevant memories from Memanto. "
        "Input: a natural-language search query string."
    )
    memory: MemantoMemory = Field(exclude=True)

    def _run(self, query: str) -> str:
        results = self.memory.recall(query, limit=10)
        return results if results else "No memories found for this query."


class AskMemoryTool(BaseTool):
    name: str = "ask_memory"
    description: str = (
        "Ask a question and get an answer synthesized from stored memories. "
        "Input: a question string."
    )
    memory: MemantoMemory = Field(exclude=True)

    def _run(self, question: str) -> str:
        answer = self.memory.answer(question)
        return answer if answer else "Could not find a relevant answer in memory."


# ── Agents ────────────────────────────────────────────────────────────────────

def build_research_crew(topic: str, memory: MemantoMemory) -> Crew:
    remember_tool = RememberTool(memory=memory)

    researcher = Agent(
        role="Research Analyst",
        goal=f"Research '{topic}' thoroughly and store all key findings in Memanto memory.",
        backstory=(
            "You are a meticulous research analyst. You investigate topics deeply "
            "and store structured findings so other agents can build on your work later."
        ),
        tools=[remember_tool],
        verbose=True,
    )

    research_task = Task(
        description=(
            f"Research the topic: '{topic}'\n\n"
            "For each key finding, call the 'remember' tool with JSON:\n"
            '  {"content": "<the finding>", "type": "fact", "tags": "<relevant,tags>"}\n\n'
            "Store at least 5 distinct findings. Include:\n"
            "- Core definition / what it is\n"
            "- Key use cases\n"
            "- Advantages over alternatives\n"
            "- Current limitations\n"
            "- Future outlook\n\n"
            f"Tag all memories with '{topic.lower().replace(' ', '_')}' for easy retrieval."
        ),
        expected_output=f"Confirmation that 5+ findings about '{topic}' were stored in Memanto.",
        agent=researcher,
    )

    return Crew(agents=[researcher], tasks=[research_task], verbose=True)


def build_writer_crew(topic: str, memory: MemantoMemory) -> Crew:
    recall_tool = RecallTool(memory=memory)
    ask_tool = AskMemoryTool(memory=memory)

    writer = Agent(
        role="Technical Writer",
        goal=f"Write a comprehensive summary about '{topic}' using only stored Memanto memories.",
        backstory=(
            "You are a technical writer who synthesizes research findings into clear, "
            "structured reports. You rely on a shared Memanto memory bank populated "
            "by the research team."
        ),
        tools=[recall_tool, ask_tool],
        verbose=True,
    )

    write_task = Task(
        description=(
            f"Write a comprehensive summary about '{topic}'.\n\n"
            "Instructions:\n"
            f"1. Use 'recall' tool with query '{topic}' to retrieve stored findings\n"
            "2. Use 'ask_memory' for specific questions if needed\n"
            "3. Synthesize findings into a structured report with sections:\n"
            "   - Overview\n"
            "   - Key Use Cases\n"
            "   - Advantages\n"
            "   - Limitations\n"
            "   - Conclusion\n\n"
            "The report should be 400-600 words and cite the retrieved memories."
        ),
        expected_output=f"A structured 400-600 word report about '{topic}' based on stored memories.",
        agent=writer,
    )

    return Crew(agents=[writer], tasks=[write_task], verbose=True)


# ── Demo: Contradictory Memory Handling ──────────────────────────────────────

def demo_contradictory_memories(memory: MemantoMemory):
    """Show Memanto updating stale facts with new information."""
    print("\n=== Demo: Contradictory Memory Handling ===")

    # Store an old fact
    memory.remember(
        "Python 3.9 is the latest stable Python version",
        memory_type="fact",
        tags="python,version,outdated"
    )
    print("Stored: 'Python 3.9 is the latest stable Python version'")

    # Store the correction
    memory.remember(
        "Python 3.13 is the latest stable Python version (as of 2024). "
        "Previous belief that 3.9 was latest is OUTDATED.",
        memory_type="learning",
        tags="python,version,correction,current"
    )
    print("Stored correction: Python 3.13 is the latest")

    # Ask the question — Memanto should surface the more confident/recent answer
    answer = memory.answer("What is the latest Python version?")
    print(f"\nMemanto answer: {answer}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CrewAI + Memanto memory demo")
    parser.add_argument(
        "--mode",
        choices=["research", "write", "both", "contradiction"],
        default="both",
        help="research: store findings | write: retrieve & write | both: full demo",
    )
    parser.add_argument(
        "--topic",
        default="large language models in production",
        help="Topic to research and write about",
    )
    parser.add_argument(
        "--agent-id",
        default="crewai-demo-agent",
        help="Memanto agent ID (shared between research and writer sessions)",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"CrewAI + Memanto Demo | Mode: {args.mode}")
    print(f"Topic: {args.topic}")
    print(f"Agent ID: {args.agent_id}")
    print(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    memory = MemantoMemory(args.agent_id)

    if args.mode in ("research", "both"):
        print("--- PHASE 1: Research Agent storing findings ---")
        crew = build_research_crew(args.topic, memory)
        result = crew.kickoff()
        print(f"\nResearch complete. Result: {result}")

    if args.mode in ("write", "both"):
        print("\n--- PHASE 2: Writer Agent retrieving from memory ---")
        crew = build_writer_crew(args.topic, memory)
        result = crew.kickoff()
        print(f"\nReport:\n{result}")

    if args.mode == "contradiction":
        demo_contradictory_memories(memory)

    print("\n✓ Demo complete. Memories persist for future sessions.")
    print(f"  Run again with --mode write to retrieve findings without re-researching.")


if __name__ == "__main__":
    main()
