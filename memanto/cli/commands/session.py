"""
MEMANTO CLI - Session commands (info, extend).
"""

from datetime import datetime

import jwt
import typer
from rich.table import Table

from memanto.cli.commands._shared import (
    _error,
    config_manager,
    console,
    format_local_time,
    get_client,
    session_app,
)


@session_app.command("info")
def session_info():
    """Show current session information."""
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        console.print("[yellow]No active session[/yellow]")
        return

    table = Table(title="Active Session", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Agent ID", active_agent_id)
    table.add_row(
        "Session Token",
        active_session_token[:20] + "..." if active_session_token else "None",
    )

    try:
        payload = jwt.decode(active_session_token, options={"verify_signature": False})
        expires_at_str = payload.get("expires_at")
        if expires_at_str:
            # Handle fromisoformat replacing Z if needed
            if expires_at_str.endswith("Z"):
                expires_at_str = expires_at_str[:-1]
            expires_at = datetime.fromisoformat(expires_at_str)
            now = datetime.utcnow()

            if now > expires_at:
                status = "[red]Expired[/red]"
                remaining = "0m"
            else:
                status = "[green]Active[/green]"
                delta = expires_at - now
                hours, remainder = divmod(delta.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                remaining = f"{int(hours)}h {int(minutes)}m"

            table.add_row("Status", status)
            table.add_row("Expires At", format_local_time(expires_at))
            table.add_row("Time Remaining", remaining)
    except Exception:
        table.add_row("Status", "[yellow]Unknown (Token unreadable)[/yellow]")

    console.print(table)


@session_app.command("extend")
def session_extend(
    hours: int = typer.Option(6, "--hours", "-h", help="Number of hours to extend"),
):
    """Extend the current session."""
    if hours <= 0:
        _error("Hours must be greater than 0.")

    active_agent_id, _ = config_manager.get_active_session()

    if not active_agent_id:
        _error(
            "No active session to extend.",
            hint="Run 'memanto agent activate <agent-id>' first.",
        )

    client = get_client()

    try:
        result = client.extend_session(active_agent_id, hours)
        console.print(f"[green]OK Session extended by {hours} hours[/green]")
        console.print(
            f"[dim]New expiration: {result.get('expires_at', 'unknown')}[/dim]"
        )
    except Exception as e:
        _error(f"Failed to extend session: {e}")
