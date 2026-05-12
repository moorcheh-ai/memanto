"""
MEMANTO CLI - Shared utilities, app instances, and helpers.

All command modules import from here to avoid circular dependencies.
"""

import os
from datetime import datetime
from typing import NoReturn

import jwt
import typer
from rich.console import Console
from rich.panel import Panel

# Re-export temporal helpers
from memanto.app.utils.temporal_helpers import (  # noqa: F401
    format_current_local_time,
    format_local_time,
    parse_relative_time,
)
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.config.manager import ConfigManager

# Re-export connect utilities
from memanto.cli.connect.agent_registry import (  # noqa: F401
    AGENT_REGISTRY,
    detect_agents_in_project,
    detect_memanto_installed,
    detect_memanto_installed_global,
    list_agents,
)
from memanto.cli.connect.engine import install_agent, remove_agent  # noqa: F401

# Re-export display functions
from memanto.cli.ui.display import print_logo, show_welcome_banner  # noqa: F401

# Re-export theme constants for all command modules
from memanto.cli.ui.theme import (  # noqa: F401
    ACCENT,
    BOLD_BRIGHT,
    BOLD_PRIMARY,
    BRIGHT,
    DIM,
    ERROR,
    PRIMARY,
    SUCCESS,
    WARNING,
)

# Initialize Typer app and console
app = typer.Typer(
    name="memanto",
    help="MEMANTO CLI - Memory that AI Agents Love!",
    add_completion=False,
)
console = Console()
config_manager = ConfigManager()

# Create subcommands
agent_app = typer.Typer(help="Agent management commands")
session_app = typer.Typer(help="Legacy aliases for agent activation commands")
config_app = typer.Typer(help="Configuration commands")
schedule_app = typer.Typer(help="Daily summary scheduling commands")
memory_app = typer.Typer(help="Memory management commands")
connect_app = typer.Typer(help="Connect MEMANTO to external tools")

app.add_typer(agent_app, name="agent")
app.add_typer(session_app, name="session")
app.add_typer(config_app, name="config")
app.add_typer(schedule_app, name="schedule")
app.add_typer(memory_app, name="memory")
app.add_typer(connect_app, name="connect")


def _error(message: str, hint: str | None = None) -> NoReturn:
    """Print a consistent red error Panel and exit."""
    body = message
    if hint:
        body += f"\n[dim]{hint}[/dim]"
    console.print(Panel(body, title="Error", border_style="red"))
    raise typer.Exit(1)


def _warn(message: str) -> None:
    """Print a non-fatal warning."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def get_client() -> SdkClient:
    """Get configured SDK client or exit if not initialized."""
    api_key = config_manager.get_api_key()

    if not api_key:
        _error("MEMANTO not configured.", hint="Run 'memanto' to set up your API key.")

    # Ensure env is set for app services
    os.environ["MOORCHEH_API_KEY"] = api_key

    client = SdkClient(api_key)

    # Restore active session if available
    active_agent_id, active_session_token = config_manager.get_active_session()
    session_cfg = config_manager.get_session_config()

    if active_session_token and active_agent_id:
        client.session_token = active_session_token
        client.agent_id = active_agent_id

        # Check if the token is completely expired, and auto-renew if enabled
        if session_cfg.get("auto_renew_enabled", True):
            try:
                payload = jwt.decode(
                    active_session_token, options={"verify_signature": False}
                )
                expires_at_str = payload.get("expires_at", "")
                if expires_at_str.endswith("Z"):
                    expires_at_str = expires_at_str[:-1]

                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)

                    if datetime.utcnow() > expires_at:
                        # Silently revive the session — activate_agent updates
                        # SessionService state and the client's own token.
                        client.activate_agent(active_agent_id)
            except Exception:
                pass  # Fall back to letting the underlying request fail if something is malformed

    return client
