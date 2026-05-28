"""CLI hook for CLAUDE.md integration.

Usage:
    python .claude/memanto-hook.py capture --skill tdd --summary "Used vitest..."
    python .claude/memanto-hook.py inject --skill diagnose
"""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.markdown import Markdown

from claudecode_memanto.config import MemantoConfig
from claudecode_memanto.memory import SkillMemory

console = Console()


@click.group()
def cli():
    """Memanto cross-skill memory hook for Claude Code."""
    pass


@cli.command()
@click.option("--skill", required=True, help="Skill name (e.g., tdd, diagnose)")
@click.option("--summary", required=True, help="Conversation summary")
@click.option("--decisions", multiple=True, help="Architectural decisions")
@click.option("--preferences", multiple=True, help="Coding preferences")
@click.option("--facts", multiple=True, help="Codebase facts")
@click.option("--tags", multiple=True, help="Additional tags")
def capture(
    skill: str,
    summary: str,
    decisions: tuple[str, ...],
    preferences: tuple[str, ...],
    facts: tuple[str, ...],
    tags: tuple[str, ...],
):
    """Capture memories from a completed skill session."""
    try:
        config = MemantoConfig()
        memory = SkillMemory(config)

        memory_ids = memory.capture(
            skill=skill,
            summary=summary,
            decisions=list(decisions),
            preferences=list(preferences),
            facts=list(facts),
            tags=list(tags),
        )

        console.print(f"[green]✓ Captured {len(memory_ids)} memories from /{skill}[/green]")
        for mid in memory_ids:
            console.print(f"  • {mid}")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--skill", required=True, help="Skill name being started")
@click.option("--file-context", default=None, help="File path or context")
def inject(skill: str, file_context: str | None):
    """Inject relevant memories into a skill session."""
    try:
        config = MemantoConfig()
        memory = SkillMemory(config)

        context = memory.inject(skill=skill, file_context=file_context)

        if context:
            console.print(Markdown(context))
        else:
            console.print("[dim]No relevant memories found.[/dim]")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--type", "memory_type", default=None, help="Filter by memory type")
def list(memory_type: str | None):
    """List all stored memories."""
    try:
        config = MemantoConfig()
        memory = SkillMemory(config)

        memories = memory.list_memories(memory_type=memory_type)

        if not memories:
            console.print("[dim]No memories stored yet.[/dim]")
            return

        for mem in memories:
            mem_type = mem.get("memory_type", "unknown")
            title = mem.get("title", "Untitled")
            confidence = mem.get("confidence", 0)
            console.print(f"[bold]{mem_type}[/bold] | {title} | confidence: {confidence:.0%}")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
