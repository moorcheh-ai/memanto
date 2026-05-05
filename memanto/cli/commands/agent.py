"""
MEMANTO CLI - Agent commands (create, list, activate, deactivate, delete, bootstrap).
"""

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import typer
from rich.panel import Panel
from rich.table import Table

from memanto.cli.commands._shared import (
    ACCENT,
    BOLD_PRIMARY,
    BRIGHT,
    PRIMARY,
    SUCCESS,
    WARNING,
    _error,
    agent_app,
    config_manager,
    console,
    format_current_local_time,
    format_local_time,
    get_client,
)


@agent_app.command("create")
def agent_create(
    agent_id: str = typer.Argument(..., help="Unique agent identifier"),
    pattern: str = typer.Option(
        "tool", help="Agent pattern: project, support, or tool"
    ),
    description: str | None = typer.Option(None, help="Agent description"),
):
    """Create a new agent and start a session immediately."""
    client = get_client()

    try:
        client.create_agent(agent_id, pattern, description)
        activation = client.activate_agent(agent_id, 6)
        config_manager.set_active_session(agent_id, activation["session_token"])

        console.print(f"[green]Agent '{agent_id}' created successfully![/green]")
        console.print(f"[dim]Pattern: {pattern}[/dim]")
        if description:
            console.print(f"[dim]Description: {description}[/dim]")
        console.print("[green]Session started automatically for this agent.[/green]")
        console.print(
            f"[dim]Session expires: {activation.get('expires_at', 'unknown')}[/dim]"
        )
        console.print(
            '[dim]You can now run: memanto remember "..." and memanto recall "..."[/dim]'
        )
    except Exception as e:
        _error(f"Failed to create agent: {e}")


@agent_app.command("list")
def agent_list():
    """List all agents."""
    client = get_client()

    try:
        agents = client.list_agents()

        if not agents:
            console.print(
                "[yellow]No agents found. Create one with 'memanto agent create'[/yellow]"
            )
            return

        table = Table(
            title="MEMANTO Agents", show_header=True, header_style=BOLD_PRIMARY
        )
        table.add_column("Agent ID", style=BRIGHT)
        table.add_column("Pattern", style=ACCENT)
        table.add_column("Description", style="white")
        table.add_column("Status", style=SUCCESS)

        active_agent, _ = config_manager.get_active_session()

        for agent in agents:
            status = "[Active] Active" if agent["agent_id"] == active_agent else ""
            table.add_row(
                agent["agent_id"],
                agent.get("pattern", "unknown"),
                agent.get("description", ""),
                status,
            )

        console.print(table)

    except Exception as e:
        _error(f"Failed to list agents: {e}")


@agent_app.command("activate")
def agent_activate(
    agent_id: str = typer.Argument(..., help="Agent ID to activate"),
    duration_hours: int = typer.Option(
        6, help="Session duration in hours (default: 6)"
    ),
):
    """Activate an agent and start a session."""
    client = get_client()

    try:
        result = client.activate_agent(agent_id, duration_hours)

        # Save session to config
        config_manager.set_active_session(agent_id, result["session_token"])

        console.print(f"[green]OK Agent '{agent_id}' activated![/green]")
        console.print(f"[dim]Session duration: {duration_hours} hours[/dim]")
        console.print(
            f"[dim]Session expires: {result.get('expires_at', 'unknown')}[/dim]"
        )

    except Exception as e:
        msg = str(e)
        hint = None
        if "not found" in msg.lower():
            hint = "Run 'memanto agent list' to see available agents, or 'memanto agent create <id>' to create one."
        _error(f"Failed to activate agent '{agent_id}': {msg}", hint=hint)


@agent_app.command("deactivate")
def agent_deactivate():
    """Deactivate the current agent session."""
    active_agent_id, _ = config_manager.get_active_session()

    if not active_agent_id:
        console.print("[yellow]No active agent session[/yellow]")
        return

    config_manager.clear_active_session()

    console.print(f"[green]OK Agent '{active_agent_id}' deactivated[/green]")


@agent_app.command("delete")
def agent_delete(
    agent_id: str = typer.Argument(..., help="Agent ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Delete an agent and optionally purge its cloud memories.

    Removes local agent metadata and optionally deletes the Moorcheh namespace.
    You will be prompted whether to keep or purge cloud memories.

    Examples:
        memanto agent delete my-agent
        memanto agent delete my-agent --force
    """
    if not force:
        console.print(f"[red]Delete agent '{agent_id}'? This cannot be undone.[/red]")
        confirmed = typer.confirm("Confirm", default=False)
        if not confirmed:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit()

    # Ask whether to keep cloud memories
    console.print()
    console.print(
        "[bold]Keep a copy of agent memory on Moorcheh cloud?[/bold]\n"
        "[dim]You can access it anytime at "
        "[link=https://console.moorcheh.ai/namespaces]https://console.moorcheh.ai/namespaces[/link]"
        " in your Moorcheh account.[/dim]"
    )
    keep_cloud = typer.confirm("Keep cloud memories", default=True)

    # If this agent is currently active, clear the session first
    active_agent_id, _ = config_manager.get_active_session()
    if active_agent_id == agent_id:
        config_manager.clear_active_session()
        console.print(f"[dim]Active session for '{agent_id}' cleared.[/dim]")

    client = get_client()

    try:
        with console.status(f"Deleting agent '{agent_id}'...", spinner="dots"):
            client.delete_agent(agent_id)
    except Exception as e:
        msg = str(e)
        hint = None
        if "not found" in msg.lower():
            hint = "Run 'memanto agent list' to see available agents."
        _error(f"Failed to delete agent '{agent_id}': {msg}", hint=hint)

    if not keep_cloud:
        namespace = f"memanto_agent_{agent_id}"
        try:
            with console.status("Deleting cloud memories...", spinner="dots"):
                client._get_moorcheh().namespaces.delete(namespace)
            console.print(
                f"[green]Agent '{agent_id}' and all cloud memories deleted.[/green]"
            )
        except Exception as e:
            console.print(
                f"[yellow]Agent deleted locally, but failed to delete cloud namespace: {e}[/yellow]"
            )
    else:
        console.print(
            f"[green]Agent '{agent_id}' deleted.[/green] "
            f"[dim]Cloud memories preserved at "
            f"[link=https://console.moorcheh.ai/namespaces]console.moorcheh.ai/namespaces[/link][/dim]"
        )


@agent_app.command("bootstrap")
def agent_bootstrap(
    agent_id: str | None = typer.Argument(
        None, help="Agent ID (defaults to active agent)"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Save report to JSON file"
    ),
):
    """Generate an intelligence snapshot of an agent's memory.

    Examples:
        memanto agent bootstrap
        memanto agent bootstrap my-agent
        memanto agent bootstrap --output snapshot.json
    """
    start = time.perf_counter()

    # Resolve agent ID
    active_agent_id, _ = config_manager.get_active_session()

    if not agent_id:
        if not active_agent_id:
            _error(
                "No agent specified and no active agent.",
                hint="Provide an agent ID or run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id

    client = get_client()

    # Agent Profile
    try:
        agent_info = client.get_agent(agent_id)
    except Exception:
        _error(
            f"Agent '{agent_id}' not found.",
            hint="Run 'memanto agent list' to see available agents.",
        )

    agent_pattern = agent_info.get("pattern", "unknown")
    agent_desc = agent_info.get("description", "") or ""
    agent_namespace = agent_info.get("namespace", "unknown")
    agent_created = agent_info.get("created_at", "unknown")

    # Fetch exact total memory count from namespace
    total_stored_memories = "unknown"
    try:
        ns_list = client._get_moorcheh().namespaces.list()
        for ns_info in ns_list.get("namespaces", []):
            if ns_info.get("namespace_name") == agent_namespace:
                total_stored_memories = str(ns_info.get("itemCount", "unknown"))
                break
    except Exception:
        pass

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Agent Bootstrap — Intelligence Snapshot[/{BOLD_PRIMARY}]\n"
            f"Agent: [bold]{agent_id}[/bold]  •  {format_current_local_time()}",
            border_style=PRIMARY,
        )
    )
    console.print()

    # Helper: fetch memories safely
    def _fetch(
        query: str, memory_types: list[str] | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Fetch memories via recall, return list or empty on error."""
        try:
            result = client.recall(
                agent_id=agent_id,
                query=query,
                limit=limit,
                memory_types=memory_types,
            )
            return cast(list[dict[str, Any]], result.get("memories", []))
        except Exception:
            return []

    # Broad searches
    key_knowledge_raw = _fetch("important information knowledge facts", limit=10)
    recent_raw = _fetch("recent activity changes updates events", limit=10)

    # Per-type samples
    type_queries = {
        "fact": "key facts and information",
        "decision": "decisions and rationale",
        "instruction": "instructions rules constraints",
        "commitment": "commitments obligations promises",
    }
    type_samples: dict[str, list] = {}
    for mem_type, query in type_queries.items():
        type_samples[mem_type] = _fetch(query, memory_types=[mem_type], limit=5)

    # Deduplicate all memories
    all_memories_map: dict[str, dict] = {}
    for mem in key_knowledge_raw + recent_raw:
        mid = mem.get("id")
        if mid:
            all_memories_map[mid] = mem
    for mems in type_samples.values():
        for mem in mems:
            mid = mem.get("id")
            if mid:
                all_memories_map[mid] = mem

    all_memories = list(all_memories_map.values())
    total_sampled = len(all_memories)

    # Handle empty memories
    if total_sampled == 0:
        profile_table = Table(show_header=False, box=None, padding=(0, 2))
        profile_table.add_column("Key", style="dim")
        profile_table.add_column("Value")
        profile_table.add_row("Agent ID", f"[bold]{agent_id}[/bold]")
        profile_table.add_row("Pattern", agent_pattern)
        profile_table.add_row("Description", agent_desc or "[dim]—[/dim]")
        profile_table.add_row("Namespace", agent_namespace)
        profile_table.add_row(
            "Created", format_local_time(agent_created) or str(agent_created)
        )
        profile_table.add_row("Total Stored", total_stored_memories)
        console.print(Panel(profile_table, title="Agent Profile", border_style=PRIMARY))
        console.print()

        console.print(
            Panel(
                "[yellow]No memories found for this agent.[/yellow]\n"
                '[dim]Store memories with: memanto remember "some fact"[/dim]',
                title="Memory Overview",
                border_style=WARNING,
            )
        )

        elapsed = time.perf_counter() - start
        console.print(f"\n[dim]Completed in {elapsed:.2f}s[/dim]")
        return

    # Compute aggregates
    type_counter: Counter = Counter()
    status_counter: Counter = Counter()
    tag_counter: Counter = Counter()
    confidence_values: list[float] = []
    dates: list[str] = []

    for mem in all_memories:
        mem_type = mem.get("type") or "unknown"
        mem_status = mem.get("status") or "unknown"
        mem_conf = mem.get("confidence")
        mem_created = mem.get("created_at")
        mem_tags = mem.get("tags", [])

        type_counter[mem_type] += 1
        status_counter[mem_status] += 1

        if mem_conf is not None:
            try:
                confidence_values.append(float(mem_conf))
            except (ValueError, TypeError):
                pass

        if mem_created:
            dates.append(str(mem_created))

        if isinstance(mem_tags, list):
            for t in mem_tags:
                if t and str(t).strip():
                    tag_counter[str(t).strip()] += 1

    avg_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    )
    dates_sorted = sorted(dates) if dates else []
    oldest = dates_sorted[0] if dates_sorted else "—"
    newest = dates_sorted[-1] if dates_sorted else "—"

    key_knowledge = sorted(
        key_knowledge_raw,
        key=lambda m: float(m.get("confidence") or 0),
        reverse=True,
    )

    recent_activity = sorted(
        recent_raw,
        key=lambda m: m.get("created_at") or "",
        reverse=True,
    )

    # Helper: truncate content
    def _snippet(text: str, max_len: int = 150) -> str:
        if not text:
            return "[dim]—[/dim]"
        text = text.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[:max_len] + "…"
        return text

    # SECTION 1: Agent Profile
    profile_table = Table(show_header=False, box=None, padding=(0, 2))
    profile_table.add_column("Key", style="dim")
    profile_table.add_column("Value")
    profile_table.add_row("Agent ID", f"[bold]{agent_id}[/bold]")
    profile_table.add_row("Pattern", agent_pattern)
    profile_table.add_row("Description", agent_desc or "[dim]—[/dim]")
    profile_table.add_row("Namespace", agent_namespace)
    profile_table.add_row(
        "Created", format_local_time(agent_created) or str(agent_created)
    )
    profile_table.add_row("Total Stored", total_stored_memories)
    profile_table.add_row("Memories Sampled", str(total_sampled))

    console.print(Panel(profile_table, title="Agent Profile", border_style=PRIMARY))
    console.print()

    # SECTION 2: Memory Overview
    overview_table = Table(show_header=False, box=None, padding=(0, 2))
    overview_table.add_column("Key", style="dim")
    overview_table.add_column("Value")

    type_summary = ", ".join(f"{t}: {c}" for t, c in type_counter.most_common())
    status_summary = ", ".join(f"{s}: {c}" for s, c in status_counter.most_common())

    overview_table.add_row("By Type", type_summary or "[dim]—[/dim]")
    overview_table.add_row("By Status", status_summary or "[dim]—[/dim]")
    overview_table.add_row("Avg Confidence", f"{avg_confidence:.2f}")
    overview_table.add_row("Date Range", f"{oldest}  →  {newest}")

    console.print(Panel(overview_table, title="Memory Overview", border_style=PRIMARY))
    console.print()

    # SECTION 3: Key Knowledge
    if key_knowledge:
        kk_table = Table(
            show_header=True, header_style=BOLD_PRIMARY, title_style="bold", expand=True
        )
        kk_table.add_column("#", style="dim", width=3)
        kk_table.add_column("Title", style=BRIGHT, ratio=2)
        kk_table.add_column("Snippet", ratio=4)
        kk_table.add_column("Type", style=ACCENT, width=12)
        kk_table.add_column("Conf", justify="right", width=5)
        kk_table.add_column("Created", style="dim", width=20)

        for i, mem in enumerate(key_knowledge, 1):
            kk_table.add_row(
                str(i),
                _snippet(mem.get("title") or "Untitled", 40),
                _snippet(mem.get("content") or ""),
                mem.get("type") or "—",
                f"{float(mem.get('confidence') or 0):.2f}",
                format_local_time(mem.get("created_at")) or "—",
            )

        console.print(
            Panel(
                kk_table,
                title="Key Knowledge (Top by Confidence)",
                border_style=PRIMARY,
            )
        )
        console.print()

    # SECTION 4: Recent Activity
    if recent_activity:
        ra_table = Table(
            show_header=True, header_style=BOLD_PRIMARY, title_style="bold", expand=True
        )
        ra_table.add_column("#", style="dim", width=3)
        ra_table.add_column("Title", style=BRIGHT, ratio=2)
        ra_table.add_column("Snippet", ratio=4)
        ra_table.add_column("Type", style=ACCENT, width=12)
        ra_table.add_column("Conf", justify="right", width=5)
        ra_table.add_column("Created", style="dim", width=20)

        for i, mem in enumerate(recent_activity, 1):
            ra_table.add_row(
                str(i),
                _snippet(mem.get("title") or "Untitled", 40),
                _snippet(mem.get("content") or ""),
                mem.get("type") or "—",
                f"{float(mem.get('confidence') or 0):.2f}",
                format_local_time(mem.get("created_at")) or "—",
            )

        console.print(
            Panel(
                ra_table, title="Recent Activity (Latest by Time)", border_style=PRIMARY
            )
        )
        console.print()

    # SECTION 5: Memory By Type
    type_labels = {
        "fact": "Facts",
        "decision": "Decisions",
        "instruction": "Instructions",
        "commitment": "Commitments",
    }

    for mem_type, label in type_labels.items():
        mems = sorted(
            type_samples.get(mem_type, []),
            key=lambda m: float(m.get("confidence") or 0),
            reverse=True,
        )[:5]

        if not mems:
            continue

        type_table = Table(show_header=True, header_style=BOLD_PRIMARY, expand=True)
        type_table.add_column("#", style="dim", width=3)
        type_table.add_column("Title", style=BRIGHT, ratio=2)
        type_table.add_column("Snippet", ratio=5)
        type_table.add_column("Conf", justify="right", width=5)

        for i, mem in enumerate(mems, 1):
            type_table.add_row(
                str(i),
                _snippet(mem.get("title") or "Untitled", 40),
                _snippet(mem.get("content") or ""),
                f"{float(mem.get('confidence') or 0):.2f}",
            )

        console.print(Panel(type_table, title=f"{label} (Top 5)", border_style=ACCENT))
        console.print()

    # SECTION 6: Tags Summary
    if tag_counter:
        tags_table = Table(show_header=True, header_style=BOLD_PRIMARY)
        tags_table.add_column("Tag", style=BRIGHT)
        tags_table.add_column("Count", justify="right", style="white")

        for tag, count in tag_counter.most_common(20):
            tags_table.add_row(tag, str(count))

        console.print(Panel(tags_table, title="Tags Summary", border_style=PRIMARY))
        console.print()

    # SECTION 7: Metadata / Footer
    elapsed = time.perf_counter() - start

    footer_table = Table(show_header=False, box=None, padding=(0, 2))
    footer_table.add_column("Key", style="dim")
    footer_table.add_column("Value")
    footer_table.add_row("Generated At", format_current_local_time())
    footer_table.add_row("Memories Sampled", str(total_sampled))
    footer_table.add_row("Total Stored", total_stored_memories)
    footer_table.add_row("Namespace", agent_namespace)
    footer_table.add_row("Completed In", f"{elapsed:.2f}s")

    console.print(Panel(footer_table, title="Bootstrap Metadata", border_style="dim"))

    # Optional JSON export
    if output:

        def _mem_to_dict(m: dict) -> dict:
            return {
                "id": m.get("id"),
                "title": m.get("title") or "",
                "content": (m.get("content") or "")[:150],
                "type": m.get("type") or "",
                "confidence": m.get("confidence"),
                "status": m.get("status") or "",
                "created_at": m.get("created_at") or "",
                "tags": m.get("tags", []),
            }

        report = {
            "agent_profile": {
                "agent_id": agent_id,
                "pattern": agent_pattern,
                "description": agent_desc,
                "namespace": agent_namespace,
                "created_at": str(agent_created),
                "total_stored_memories": total_stored_memories,
            },
            "memory_overview": {
                "by_type": dict(type_counter),
                "by_status": dict(status_counter),
                "avg_confidence": round(avg_confidence, 2),
                "date_range": {"oldest": oldest, "newest": newest},
                "total_sampled": total_sampled,
            },
            "key_knowledge": [_mem_to_dict(m) for m in key_knowledge],
            "recent_activity": [_mem_to_dict(m) for m in recent_activity],
            "memory_by_type": {
                t: [
                    _mem_to_dict(m)
                    for m in sorted(
                        type_samples.get(t, []),
                        key=lambda m: float(m.get("confidence") or 0),
                        reverse=True,
                    )[:5]
                ]
                for t in type_labels
            },
            "tags_summary": dict(tag_counter.most_common(20)),
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_sampled": total_sampled,
                "total_stored_memories": total_stored_memories,
                "namespace": agent_namespace,
                "elapsed_seconds": round(elapsed, 2),
            },
        }

        try:
            Path(output).write_text(
                json.dumps(report, indent=2, default=str),
                encoding="utf-8",
            )
            console.print(f"\n[green]OK Report saved to: {output}[/green]")
        except Exception as e:
            _error(f"Failed to write report: {e}")
