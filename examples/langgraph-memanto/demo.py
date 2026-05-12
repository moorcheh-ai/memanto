"""
Cross-Session Demo for the Memanto + LangGraph Research Mentor

This script demonstrates persistent memory across two completely independent
sessions.  Session 1 stores project context; Session 2 retrieves it with
zero shared LangGraph state.

Usage:
    # Start the Memanto server first:
    memanto serve

    # Then run:
    OPENAI_API_KEY=sk-... python demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from main import ResearchMentor

console = Console()

# ---------------------------------------------------------------------------
# Session conversations
# ---------------------------------------------------------------------------

SESSION_1_MESSAGES = [
    (
        "I'm working on optimizing LLM inference for edge devices. "
        "My main focus is reducing latency for Llama-3-8B on consumer GPUs."
    ),
    (
        "I've been experimenting with 4-bit AWQ quantization. "
        "On an RTX 4090, I got the per-token latency down from 23ms to 11ms "
        "with only 0.3% perplexity degradation on WikiText-103."
    ),
    (
        "I prefer using PyTorch for all my experiments. "
        "My evaluation pipeline uses lm-eval-harness and I report results "
        "in markdown tables with confidence intervals."
    ),
    (
        "The project deadline is March 15th. I need to have the paper draft "
        "ready by then. My advisor wants to submit to ICML 2027."
    ),
]

SESSION_2_MESSAGES = [
    "Hey, what was I working on?",
    "What quantization results did I get?",
    "Can you summarize my current project status?",
    "When is my deadline and where am I submitting?",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_header(text: str, style: str = "bold cyan") -> None:
    console.print(f"\n{'═' * 60}", style="dim")
    console.print(f"  {text}", style=style)
    console.print(f"{'═' * 60}\n", style="dim")


async def run_session(
    mentor: ResearchMentor,
    messages: list[str],
    session_label: str,
) -> None:
    """Run a sequence of messages through the mentor and print results."""
    print_header(session_label)

    await mentor.start_session()

    for i, msg in enumerate(messages, 1):
        console.print(f"[bold green]You ({i}/{len(messages)}):[/bold green] {msg}\n")

        with console.status("[dim]Thinking...[/dim]"):
            response = await mentor.chat(msg)

        console.print("[bold blue]Mentor:[/bold blue]")
        console.print(Markdown(response))
        console.print()

    await mentor.end_session()


async def show_stored_memories(mentor: ResearchMentor) -> None:
    """Display all stored memories between sessions."""
    print_header("Stored Memories (what Memanto remembers)", "bold yellow")

    await mentor.start_session()

    # Query for all project-related memories
    queries = [
        "LLM inference optimization project",
        "quantization results and experiments",
        "tools preferences and workflow",
        "deadlines and submissions",
    ]

    seen_contents: set[str] = set()
    table = Table(title="Memanto Memory Store", show_lines=True)
    table.add_column("Type", style="cyan", width=12)
    table.add_column("Content", style="white", min_width=40)
    table.add_column("Confidence", style="green", width=12)
    table.add_column("Similarity", style="yellow", width=12)

    for query in queries:
        memories = await mentor.recall_memories(query, limit=5)
        for m in memories:
            if m.content not in seen_contents:
                seen_contents.add(m.content)
                table.add_row(
                    m.memory_type,
                    m.content,
                    f"{m.confidence:.2f}",
                    f"{m.similarity:.2f}",
                )

    console.print(table)
    await mentor.end_session()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        console.print(
            "[bold red]Error:[/bold red] Set OPENAI_API_KEY environment variable.",
            style="red",
        )
        sys.exit(1)

    console.print(
        Panel(
            "[bold]LangGraph + Memanto: Cross-Session Memory Demo[/bold]\n\n"
            "This demo runs TWO independent sessions:\n"
            "  Session 1 — Discusses a research project (stores memories)\n"
            "  Session 2 — New instance, asks about the project (recalls memories)\n\n"
            "The second session has ZERO shared LangGraph state.\n"
            "All context comes from Memanto's persistent memory store.",
            title="Demo",
            border_style="magenta",
        )
    )

    # -- Session 1: "Yesterday" — build up project context --
    mentor_1 = ResearchMentor(agent_name="demo-research-mentor")
    await run_session(mentor_1, SESSION_1_MESSAGES, "Session 1: Yesterday (Building Context)")

    # -- Show what got stored --
    inspector = ResearchMentor(agent_name="demo-research-mentor")
    await show_stored_memories(inspector)

    # -- Session 2: "Today" — completely new instance --
    console.print(
        Panel(
            "[bold]Starting Session 2...[/bold]\n\n"
            "This is a BRAND NEW ResearchMentor instance.\n"
            "No messages, no LangGraph checkpoint, no shared state.\n"
            "The only bridge is Memanto.",
            border_style="green",
        )
    )

    mentor_2 = ResearchMentor(agent_name="demo-research-mentor")
    await run_session(mentor_2, SESSION_2_MESSAGES, "Session 2: Today (Cross-Session Recall)")

    # -- Final verdict --
    print_header("Demo Complete!", "bold green")
    console.print(
        "The Research Mentor successfully recalled project details, "
        "experimental results, tool preferences, and deadlines from "
        "Session 1 — using ONLY Memanto's persistent memory.\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
