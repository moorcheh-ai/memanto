"""
MEMANTO CLI - Shared utilities, app instances, and helpers.

All command modules import from here to avoid circular dependencies.
"""

import os
from typing import NoReturn

import typer
from rich.console import Console
from rich.panel import Panel

from memanto.app.services.session_service import get_session_service
from memanto.app.utils.errors import InvalidSessionTokenError, SessionExpiredError

# Re-export temporal helpers
from memanto.app.utils.temporal_helpers import (  # noqa: F401
    format_current_local_time,
    format_local_time,
    parse_relative_time,
    utc_now,
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
    help="MEMANTO CLI - Your agents focus. Memanto remembers.",
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
migrate_app = typer.Typer(
    help="Migrate memories from other providers (Mem0/Letta/Supermemory) into Memanto"
)

app.add_typer(agent_app, name="agent")
app.add_typer(session_app, name="session")
app.add_typer(config_app, name="config")
app.add_typer(schedule_app, name="schedule")
app.add_typer(memory_app, name="memory")
app.add_typer(connect_app, name="connect")
app.add_typer(migrate_app, name="migrate")


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
    from memanto.app.clients.backend import Backend

    backend = config_manager.get_backend()
    if backend == Backend.ON_PREM:
        # On-prem: no API key needed. Pass a placeholder; the underlying
        # OnPremClient ignores it (it talks to localhost:8080).
        api_key = "on-prem"
    else:
        cfg_key = config_manager.get_api_key()
        if not cfg_key:
            _error(
                "MEMANTO not configured.",
                hint="Run 'memanto' to set up your API key.",
            )
        api_key = cfg_key
        # Ensure env is set for app services on the cloud path.
        os.environ["MOORCHEH_API_KEY"] = api_key

    client = SdkClient(api_key)

    # Restore active session if available
    active_agent_id, active_session_token = config_manager.get_active_session()
    session_cfg = config_manager.get_session_config()

    if active_session_token and active_agent_id:
        client.session_token = active_session_token
        client.agent_id = active_agent_id

        # Validate the stored token (signature + expiry) and silently re-activate
        # when auto-renew is enabled. The old expiry-only check missed invalid
        # signatures, which broke analyze LLM narratives mid-run.
        if session_cfg.get("auto_renew_enabled", True):
            session_service = get_session_service()
            needs_reactivate = False
            try:
                session_service.validate_session(active_session_token)
            except (SessionExpiredError, InvalidSessionTokenError):
                needs_reactivate = True

            if needs_reactivate:
                try:
                    client.activate_agent(active_agent_id)
                except Exception:
                    pass

    return client
