#!/usr/bin/env python3
"""
Developer Skills Simulator using Memanto Memory Hook.

Simulates two separate CLI command/skill executions to show how Memanto
eliminates context fragmentation by retaining developer preferences across
different sessions.
"""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv
from memory_hook import MemantoSkillsHook
from rich.console import Console
from rich.panel import Panel

console = Console()


def run_session_1(hook: MemantoSkillsHook) -> None:
    console.print(Panel("[bold cyan]Session 1: Brainstorming Architecture / Setting Preferences[/bold cyan]\n"
                        "Running skill [yellow]/grill-with-docs[/yellow] on file [bold]design_notes.md[/bold]"))

    input_text = (
        "Let's define the project configuration. Please note: I strictly prefer using "
        "Tailwind v4 with Outfit typography styling and custom Harmonious HSL colors "
        "to ensure a premium visual design. Never use default Arial/Inter."
    )
    file_path = "design_notes.md"

    # Pre-execute hook (queries past memories)
    console.print("[dim]Pre-skill execution: Querying Memanto...[/dim]")
    injected_context = hook.pre_skill_execute("/grill-with-docs", file_path, input_text)
    if injected_context:
        console.print("[green]✓ Context Injected from Memanto:[/green]")
        console.print(injected_context)
    else:
        console.print("[yellow]○ No past memories found for this task yet. Starting fresh.[/yellow]")

    console.print(f"\n[bold]User Input:[/bold]\n{input_text}")

    # Simulated skill output
    console.print("\n[bold green]Skill Output (LLM generated):[/bold green]")
    output_text = (
        "Understood. We have registered your design specifications. The styling guidelines "
        "will use Tailwind v4 with Outfit typography and custom Harmonious HSL colors. "
        "We have decided to configure the tailwind theme extensions to match this choice."
    )
    console.print(output_text)

    # Post-execute hook (extracts and saves memory)
    console.print("\n[dim]Post-skill execution: Extracting new memories to save...[/dim]")
    stored_memory = hook.post_skill_execute("/grill-with-docs", file_path, input_text, output_text)
    if stored_memory:
        console.print("[bold green]✓ Memory Extilled & Saved to Memanto![/bold green]")
        console.print(f"  [bold]ID:[/bold] {stored_memory['memory_id']}")
        console.print(f"  [bold]Type:[/bold] {stored_memory['type']}")
        console.print(f"  [bold]Title:[/bold] {stored_memory['title']}")
        console.print(f"  [bold]Content:[/bold] {stored_memory['content']}")
    else:
        console.print("[red]✗ No meaningful memory extracted.[/red]")


def run_session_2(hook: MemantoSkillsHook) -> None:
    console.print(Panel("[bold cyan]Session 2: Writing Code in a Fresh Session[/bold cyan]\n"
                        "Running skill [yellow]/tdd[/yellow] on file [bold]index.css[/bold]"))

    input_text = "Generate the core CSS theme setup for our project."
    file_path = "index.css"

    # Pre-execute hook (should recall the preference from Session 1!)
    console.print("[dim]Pre-skill execution: Querying Memanto...[/dim]")
    injected_context = hook.pre_skill_execute("/tdd", file_path, input_text)

    if injected_context:
        console.print("[bold green]✓ Success! Context Injected from Memanto:[/bold green]")
        console.print(injected_context)
    else:
        console.print("[red]✗ Expected to recall preference from Session 1, but nothing found.[/red]")

    console.print(f"\n[bold]User Input:[/bold]\n{input_text}")

    # Simulated skill output utilizing the injected context
    console.print("\n[bold green]Skill Output (LLM generated using injected memory):[/bold green]")
    output_text = (
        "Creating index.css config incorporating Outfit font styling and Harmonious HSL colors "
        "adhering to the project's Tailwind v4 guidelines."
    )
    console.print(output_text)

    # Post-execute hook
    hook.post_skill_execute("/tdd", file_path, input_text, output_text)


def main() -> None:
    load_dotenv()

    # Read Moorcheh API Key
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        # Check standard config file fallback
        _env_path = Path.home() / ".memanto" / ".env"
        if _env_path.exists():
            with open(_env_path) as f:
                for line in f:
                    if line.startswith("MOORCHEH_API_KEY="):
                        api_key = line.split("=")[1].strip()

    if not api_key or api_key == "test-api-key":
        console.print("[bold red]Error: MOORCHEH_API_KEY environment variable is not configured.[/bold red]")
        console.print("Please set it in your environment or ~/.memanto/.env file.")
        sys.exit(1)

    # Initialize Hook
    hook = MemantoSkillsHook(api_key=api_key, agent_id="claudecode-simulator")
    hook.initialize()

    try:
        run_session_1(hook)
        console.print("\n[dim]Simulating time gap between terminal commands...[/dim]\n")
        time.sleep(1.5)
        run_session_2(hook)
    finally:
        hook.close()


if __name__ == "__main__":
    main()
