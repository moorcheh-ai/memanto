"""
MEMANTO CLI - Legacy session aliases for agent activation commands.
"""

from datetime import datetime

import jwt
from rich.table import Table

from memanto.cli.commands._shared import (
    config_manager,
    console,
    format_local_time,
    session_app,
)


@session_app.command("info")
def session_info():
    """Show current active agent activation information."""
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        console.print("[yellow]No active agent[/yellow]")
        return

    table = Table(title="Active Agent", show_header=False)
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
