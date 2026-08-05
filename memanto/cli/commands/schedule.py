"""
MEMANTO CLI - Schedule commands (enable, disable, status).
"""

import time
from datetime import datetime

import typer
from rich.panel import Panel

from memanto.cli.commands._shared import (
    SUCCESS,
    WARNING,
    _error,
    config_manager,
    console,
    get_client,
    schedule_app,
)
from memanto.cli.schedule_manager import ScheduleManager


@schedule_app.command("enable")
def schedule_enable():
    """Enable the nightly daily-summary + conflict-detection job."""

    manager = ScheduleManager()
    configured_time = config_manager.get_schedule_time()
    result = manager.enable(configured_time)

    if result.get("status") == "success":
        console.print(f"[green]OK {result.get('message')}[/green]")
    else:
        _error(result.get("message"))


@schedule_app.command("disable")
def schedule_disable():
    """Disable the nightly daily-summary + conflict-detection job."""

    manager = ScheduleManager()
    result = manager.disable()

    if result.get("status") == "success":
        console.print(f"[green]OK {result.get('message')}[/green]")
    else:
        _error(result.get("message"))


@schedule_app.command("_run", hidden=True)
def schedule_run_internal(
    date: str | None = typer.Option(None, "--date", "-d"),
    agent_id: str | None = typer.Option(None, "--agent", "-a"),
):
    """Internal entrypoint invoked by the OS scheduler. Runs daily-summary
    then detect-conflicts in one process. Not intended for direct use —
    run ``memanto daily-summary`` or ``memanto detect-conflicts`` instead.
    """
    from memanto.app.clients.backend import Backend

    if config_manager.get_backend() == Backend.ON_PREM:
        _error(
            "scheduled job uses the LLM Answer endpoint, which is not "
            "available on the on-prem backend.",
            hint="Switch with: memanto config backend cloud",
        )

    start = time.perf_counter()
    active_agent_id, _ = config_manager.get_active_session()

    if not agent_id:
        if not active_agent_id:
            _error(
                "No active agent.",
                hint="Run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    client = get_client()
    failed = False

    try:
        summary_result = client.generate_daily_summary(agent_id=agent_id, date=date)
        summary = summary_result.get("summary", {})
        if summary.get("status") == "success":
            console.print(
                f"[green]Daily summary generated:[/green] {summary.get('summary_path')}"
            )
        else:
            failed = True
            console.print(f"[yellow]! Summary:[/yellow] {summary.get('status')}")
    except Exception as e:
        failed = True
        console.print(f"[red]Daily summary failed: {e}[/red]")

    try:
        conflict_result = client.generate_conflict_report(agent_id=agent_id, date=date)
        conflicts = conflict_result.get("conflicts", {})
        if conflicts.get("status") == "success":
            count = conflicts.get("conflict_count", 0)
            console.print(
                f"[green]Conflict report generated:[/green] "
                f"{conflicts.get('json_path')} ({count} conflict(s))"
            )
        else:
            failed = True
            console.print(f"[yellow]! Conflicts:[/yellow] {conflicts.get('status')}")
    except Exception as e:
        failed = True
        console.print(f"[red]Conflict detection failed: {e}[/red]")

    console.print(f"\n[dim]Completed in {time.perf_counter() - start:.2f}s[/dim]")

    if failed:
        raise typer.Exit(code=1)


@schedule_app.command("status")
def schedule_status():
    """Check the status of the scheduled job."""

    manager = ScheduleManager()
    result = manager.get_status()
    configured_time = config_manager.get_schedule_time()

    if result.get("enabled"):
        console.print(
            Panel(
                f"[green]Scheduled Job: ENABLED[/green]\n\n"
                f"[dim]Time: {configured_time} local time daily[/dim]\n"
                f"[dim]Runs: daily-summary && detect-conflicts[/dim]",
                title="Schedule Status",
                border_style=SUCCESS,
            )
        )
    else:
        console.print(
            Panel(
                "[yellow]Scheduled Job: DISABLED[/yellow]\n\n"
                "[dim]Run 'memanto schedule enable' to activate the nightly "
                "daily-summary + conflict-detection job.[/dim]",
                title="Schedule Status",
                border_style=WARNING,
            )
        )
