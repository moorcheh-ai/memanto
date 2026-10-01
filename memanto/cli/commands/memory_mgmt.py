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


def _check_template_updates(project_dir: str):
    """Silently check for outdated agent instructions and print a warning if needed."""
    try:
        from memanto.cli.commands._shared import console
        from memanto.cli.connect.templates import TEMPLATE_VERSION
        from memanto.cli.connect.updater import check_for_updates

        status = check_for_updates(project_dir=project_dir)

        is_outdated = status.get("outdated")
        installed_version = status.get("installed_version")

        if is_outdated:
            console.print(
                f"\n[yellow]⚠️ Notice: Your Memanto agent instructions are out of date (v{installed_version} installed, v{TEMPLATE_VERSION} available).[/yellow]"
            )
            console.print(
                "[yellow]   Run `memanto connect update` to apply the latest instruction hardening.[/yellow]"
            )
    except Exception as e:
        try:
            from memanto.cli.commands._shared import console

            console.print(f"[dim]Failed to check instruction update status: {e}[/dim]")
        except Exception:
            print(f"Failed to check instruction update status: {e}")


@memory_app.command("sync")
def memory_sync(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Agent identifier (defaults to active agent)"
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        help="Connected integration to update when the caller cannot be detected",
    ),
    scope: str | None = typer.Option(
        None,
        "--scope",
        help="Connection scope to update: local or global",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Maximum memories to inject dynamically (default 10). For OKF, max per type.",
    ),
    okf: bool = typer.Option(
        False,
        "--okf",
        help="Sync an OKF (Open Knowledge Format) bundle to <project>/okf",
    ),
    split: str = typer.Option(
        "auto",
        "--split",
        help="OKF layout: auto | file | type (only used with --okf)",
    ),
):
    """Sync agent memories directly into your project's agent instructions.

    Fetches the highest relevance dynamic memories based on global project standards
    and user preferences, and injects them into agent instructions via sentinels.
    The invoking agent determines the connection automatically; manual invocations
    can provide --connection and --scope when the target is ambiguous.
    Pass --okf to instead
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
        _check_template_updates(project_dir)
        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
        return

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Memory Sync[/{BOLD_PRIMARY}]\n"
            f"Agent: [bold]{agent_id}[/bold]  •  Target_dir: {project_dir}",
            border_style=PRIMARY,
        )
    )

    with console.status(f"[{PRIMARY}]Syncing dynamic memories...", spinner="dots"):
        try:
            from memanto.cli.connect.updater import inject_dynamic_memories

            memories_result = client.recall(
                agent_id=agent_id,
                query="Global project standards, architectural rules, agent workflows, and core user preferences",
                type=["instruction", "preference", "goal"],
                min_confidence=0.8,
                min_similarity=0.15,
                limit=limit,
                status="active",
            )

            formatted_bullets = []
            for mem in memories_result.get("memories", []):
                mem_type = mem.get("type", "fact").upper()
                content = mem.get("content", "").strip()
                formatted_bullets.append(f"- [{mem_type}] {content}")

            formatted_text = "\n".join(formatted_bullets)

            injection_results = inject_dynamic_memories(
                project_dir,
                formatted_text,
                connection=connection,
                scope=scope,
            )
            recalled_total = len(memories_result.get("memories", []))

        except Exception as e:
            _error(f"Failed to sync dynamic memories: {e}")

    elapsed = time.perf_counter() - start

    if recalled_total == 0:
        console.print(
            "\n[yellow]No active dynamic memories found. Cleared dynamic sections (if any).[/yellow]"
        )
    else:
        console.print(
            f"\n[green]OK Recalled {recalled_total} dynamic memories![/green]"
        )

    for msg in injection_results.get("updated", []):
        console.print(f"[green]* {msg}[/green]")
    for msg in injection_results.get("already_current", []):
        console.print(f"[dim]* {msg}[/dim]")
    for msg in injection_results.get("no_eligible_target", []):
        console.print(f"[yellow]* {msg}[/yellow]")

    _check_template_updates(project_dir)
    console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
