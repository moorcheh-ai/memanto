"""
MEMANTO CLI - Memory management commands (export, sync).
"""

import time

import typer
from rich.panel import Panel
from rich.table import Table

from memanto.app.services.memory_export_service import (
    MEMORY_TYPE_META,
    MEMORY_TYPE_ORDER,
)
from memanto.cli.commands._shared import (
    BOLD_PRIMARY,
    BRIGHT,
    PRIMARY,
    _error,
    config_manager,
    console,
    get_client,
    memory_app,
)


@memory_app.command("export")
def memory_export(
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Agent identifier (defaults to active agent)"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Custom output path for the memory.md file"
    ),
    limit: int = typer.Option(
        25, "--limit", "-n", help="Maximum memories per type (default 25)"
    ),
    okf: bool = typer.Option(
        False,
        "--okf",
        help="Export as an OKF (Open Knowledge Format) bundle directory instead of memory.md",
    ),
    split: str = typer.Option(
        "auto",
        "--split",
        help="OKF layout: auto | file | type (only used with --okf)",
    ),
):
    """Export all memories into a structured memory.md file.

    Generates a Markdown file with all 13 memory types organized into
    sections, ready for agent consumption. Pass --okf to instead write an OKF
    bundle (a directory of markdown files, grouped by type).

    Examples:
        memanto memory export
        memanto memory export --agent my-agent
        memanto memory export -o ./memory.md
        memanto memory export -n 50
        memanto memory export --okf
    """
    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not agent_id:
        if not active_agent_id or not active_session_token:
            _error(
                "No agent specified and no active agent.",
                hint="Provide --agent or run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id

    client = get_client()

    if okf:
        if split not in ("auto", "file", "type"):
            _error("--split must be one of: auto, file, type")

        console.print(
            Panel.fit(
                f"[{BOLD_PRIMARY}]OKF Export[/{BOLD_PRIMARY}]\n"
                f"Agent: [bold]{agent_id}[/bold]  •  Split: {split}  •  "
                f"Limit: {limit}/type",
                border_style=PRIMARY,
            )
        )

        with console.status(f"[{PRIMARY}]Building OKF bundle...", spinner="dots"):
            try:
                result = client.export_okf_bundle(
                    agent_id=agent_id,
                    output_dir=output,
                    split=split,
                    limit_per_type=limit,
                )
            except Exception as e:
                _error(f"Failed to export OKF bundle: {e}")

        elapsed = time.perf_counter() - start
        total = result.get("total_memories", 0)
        per_type = result.get("per_type_counts", {})
        out_path = result.get("output_path", "unknown")

        if total == 0:
            console.print("\n[yellow]No memories found for this agent.[/yellow]")
        else:
            table = Table(
                show_header=True,
                header_style=BOLD_PRIMARY,
                title="OKF Bundle Counts",
            )
            table.add_column("Type", style=BRIGHT)
            table.add_column("Count", justify="right", style="white")
            for mem_type in MEMORY_TYPE_ORDER:
                count = per_type.get(mem_type, 0)
                if count > 0:
                    label, _ = MEMORY_TYPE_META[mem_type]
                    table.add_row(label, str(count))
            console.print()
            console.print(table)
            console.print(
                f"\n[green]OK Exported {total} memories to OKF bundle![/green]"
            )

        console.print(f"[dim]Bundle: {out_path}[/dim]")
        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
        return

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Memory Export[/{BOLD_PRIMARY}]\n"
            f"Agent: [bold]{agent_id}[/bold]  •  Limit: {limit}/type",
            border_style=PRIMARY,
        )
    )

    with console.status(f"[{PRIMARY}]Fetching memories...", spinner="dots"):
        try:
            result = client.export_memory_md(
                agent_id=agent_id,
                output_path=output,
                limit_per_type=limit,
            )
        except Exception as e:
            _error(f"Failed to export memories: {e}")

    elapsed = time.perf_counter() - start

    # Display results
    total = result.get("total_memories", 0)
    per_type = result.get("per_type_counts", {})
    out_path = result.get("output_path", "unknown")

    if total == 0:
        console.print("\n[yellow]No memories found for this agent.[/yellow]")
        console.print(f"[dim]Empty template written to: {out_path}[/dim]")
    else:
        # Summary table
        table = Table(
            show_header=True, header_style=BOLD_PRIMARY, title="Exported Memory Counts"
        )
        table.add_column("Type", style=BRIGHT)
        table.add_column("Count", justify="right", style="white")

        for mem_type in MEMORY_TYPE_ORDER:
            count = per_type.get(mem_type, 0)
            if count > 0:
                label, _ = MEMORY_TYPE_META[mem_type]
                table.add_row(f"{label}", str(count))

        console.print()
        console.print(table)
        console.print(f"\n[green]OK Exported {total} memories successfully![/green]")

    console.print(f"[dim]Output: {out_path}[/dim]")
    console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")


@memory_app.command("sync")
def memory_sync(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Agent identifier (defaults to active agent)"
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-n",
        help="Maximum memories per type if fresh export needed (default 25)",
    ),
    okf: bool = typer.Option(
        False,
        "--okf",
        help="Sync an OKF (Open Knowledge Format) bundle (<project>/okf) instead of MEMORY.md",
    ),
    split: str = typer.Option(
        "auto",
        "--split",
        help="OKF layout: auto | file | type (only used with --okf)",
    ),
):
    """Sync agent memories to a project directory's MEMORY.md.

    Always performs a fresh export before syncing to ensure the latest
    memories are captured in the project's MEMORY.md file. Pass --okf to instead
    sync an OKF bundle into ``<project>/okf``.

    Examples:
        memanto memory sync
        memanto memory sync --project-dir ./my-project
        memanto memory sync -p C:\\\\Projects\\\\my-app --agent my-agent
        memanto memory sync --okf -p ./my-project
    """
    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not agent_id:
        if not active_agent_id or not active_session_token:
            _error(
                "No agent specified and no active agent.",
                hint="Provide --agent or run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id

    client = get_client()

    if okf:
        if split not in ("auto", "file", "type"):
            _error("--split must be one of: auto, file, type")

        console.print(
            Panel.fit(
                f"[{BOLD_PRIMARY}]OKF Sync[/{BOLD_PRIMARY}]\n"
                f"Agent: [bold]{agent_id}[/bold]  •  Split: {split}  •  "
                f"Target_dir: {project_dir}",
                border_style=PRIMARY,
            )
        )

        with console.status(f"[{PRIMARY}]Syncing OKF bundle...", spinner="dots"):
            try:
                result = client.sync_okf_to_project(
                    agent_id=agent_id,
                    project_dir=project_dir,
                    split=split,
                    limit_per_type=limit,
                )
            except Exception as e:
                _error(f"Failed to sync OKF bundle: {e}")

        elapsed = time.perf_counter() - start
        total = result.get("total_memories", 0)
        source = result.get("source", "unknown")
        out_path = result.get("output_path", "unknown")
        source_label = {
            "fresh": "fresh export",
            "stale-cache": "stale cache (backend unreachable)",
        }.get(source, source)

        if total == 0:
            console.print("\n[yellow]No memories found for this agent.[/yellow]")
        else:
            console.print(f"\n[green]OK Synced {total} memories to OKF bundle![/green]")
            console.print(f"[dim]Source: {source_label}[/dim]")

        if source == "stale-cache":
            console.print(
                "[yellow]Warning: backend was unreachable; reused the previous "
                "OKF bundle. Memories may be out of date.[/yellow]"
            )

        console.print(f"[dim]Output: {out_path}[/dim]")
        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
        return

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Memory Sync[/{BOLD_PRIMARY}]\n"
            f"Agent: [bold]{agent_id}[/bold]  •  Target_dir: {project_dir}",
            border_style=PRIMARY,
        )
    )

    with console.status(f"[{PRIMARY}]Syncing memories...", spinner="dots"):
        try:
            result = client.sync_memory_to_project(
                agent_id=agent_id,
                project_dir=project_dir,
                limit_per_type=limit,
            )
        except Exception as e:
            _error(f"Failed to sync memories: {e}")

    elapsed = time.perf_counter() - start

    total = result.get("total_memories", 0)
    source = result.get("source", "unknown")
    out_path = result.get("output_path", "unknown")

    if source == "cache":
        source_label = "cached export"
    elif source == "stale-cache":
        source_label = "stale cache (backend unreachable)"
    else:
        source_label = "fresh export"

    if total == 0:
        console.print("\n[yellow]No memories found for this agent.[/yellow]")
        console.print(f"[dim]Empty memory.md written to: {out_path}[/dim]")
    else:
        console.print(f"\n[green]OK Synced {total} memories successfully![/green]")
        console.print(f"[dim]Source: {source_label}[/dim]")

    if source == "stale-cache":
        console.print(
            "[yellow]Warning: backend was unreachable; reused the previous "
            "export. Memories may be out of date.[/yellow]"
        )

    console.print(f"[dim]Output: {out_path}[/dim]")
    console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
