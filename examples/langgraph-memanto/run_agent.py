#!/usr/bin/env python3
"""
LangGraph + Memanto Integration Simulator

Simulates two separate execution sessions of a LangGraph agent. It shows how
Memanto stores user preferences in Session 1 and dynamically retrieves them
in Session 2 (cross-session recall) outside of thread-scoped State.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from agent import AgentState, MemantoMemoryManager, build_agent_graph
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.panel import Panel

console = Console()



def run_session_1(app: Any, user_id: str) -> None:
    """
    Session 1: User introduces themselves and states a programming language preference.
    The agent extracts and persists this preference.
    """
    console.print(
        Panel(
            "[bold cyan]Session 1: User onboarding & preference declaration[/bold cyan]\n"
            "Starting agent execution..."
        )
    )

    initial_message = (
        "Hello! My name is Alex. I write code in Python and prefer LangGraph for agent design."
    )
    console.print(f"[bold]User Input:[/bold]\n{initial_message}\n")

    # Initial state
    inputs = {
        "messages": [HumanMessage(content=initial_message)],
        "user_id": user_id,
        "recalled_memories": [],
        "new_memories_extracted": [],
    }

    # Run the graph
    console.print("[dim]Executing Graph Nodes: recall -> llm -> extract[/dim]")
    outputs = app.invoke(inputs)

    # Print LLM response
    final_msg = outputs["messages"][-1]
    console.print(f"\n[bold green]Agent Response:[/bold green]\n{final_msg.content}\n")

    # Show saved memories
    saved = outputs.get("new_memories_extracted", [])
    if saved:
        console.print("[bold green]✓ Memory Extracted & Saved to Memanto:[/bold green]")
        for s in saved:
            console.print(f"  - [{s['type'].upper()}] {s['content']}")
    else:
        console.print("[red]✗ No memories saved.[/red]")


def run_session_2(app: Any, user_id: str) -> None:
    """
    Session 2: User asks a generic question in a brand new session.
    The agent recalls the preference stored in Session 1 and uses it.
    """
    console.print(
        Panel(
            "[bold cyan]Session 2: Fresh session / Cross-Session Recall[/bold cyan]\n"
            "Running a completely disjointed agent execution..."
        )
    )

    follow_up_message = "What programming tools should we use for our project?"
    console.print(f"[bold]User Input:[/bold]\n{follow_up_message}\n")

    # Fresh state (simulating a new day / new session)
    inputs = {
        "messages": [HumanMessage(content=follow_up_message)],
        "user_id": user_id,
        "recalled_memories": [],
        "new_memories_extracted": [],
    }

    # Run the graph
    console.print("[dim]Executing Graph Nodes: recall -> llm -> extract[/dim]")
    outputs = app.invoke(inputs)

    # Print recalled memory context
    recalled = outputs.get("recalled_memories", [])
    if recalled:
        console.print("[bold green]✓ Success! Context recalled from Memanto:[/bold green]")
        for idx, m in enumerate(recalled, 1):
            console.print(f"  {idx}. [{m.get('type','fact').upper()}] {m.get('title')}: {m.get('content')}")
    else:
        console.print("[red]✗ No memories recalled from Memanto.[/red]")

    # Print final agent response utilizing the memory
    final_msg = outputs["messages"][-1]
    console.print(f"\n[bold green]Agent Response (Contextualized):[/bold green]\n{final_msg.content}")


def main() -> None:
    load_dotenv()

    # Retrieve Moorcheh API Key
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        _env_path = Path.home() / ".memanto" / ".env"
        if _env_path.exists():
            with open(_env_path) as f:
                for line in f:
                    if line.startswith("MOORCHEH_API_KEY="):
                        api_key = line.split("=")[1].strip()

    if not api_key:
        api_key = "test-api-key"
        console.print("[yellow]Warning: MOORCHEH_API_KEY is not configured. Running in local mock mode with 'test-api-key'.[/yellow]")


    # Unique user ID for isolation
    user_id = f"user_{int(time.time())}"

    # Setup Memory Manager and Graph
    memory_manager = MemantoMemoryManager(api_key=api_key, agent_id=f"langgraph-sim-{user_id}")
    memory_manager.initialize()

    workflow = build_agent_graph(memory_manager)
    app = workflow.compile()

    try:
        run_session_1(app, user_id)
        console.print("\n[dim]Simulating session closure & time gap...[/dim]\n")
        time.sleep(2)
        run_session_2(app, user_id)
    finally:
        # Clean up agent session
        if memory_manager.initialized:
            try:
                memory_manager.client.deactivate_agent(memory_manager.agent_id)
            except Exception:
                pass


if __name__ == "__main__":
    main()
