"""
MEMANTO CLI - Core commands (status, serve, ui, main_callback).
"""

import os
import platform
import socket
import threading
import time

import httpx
import typer
from rich.panel import Panel
from rich.table import Table

from memanto.cli.commands._shared import (
    ACCENT,
    BOLD_BRIGHT,
    BOLD_PRIMARY,
    BRIGHT,
    PRIMARY,
    SUCCESS,
    WARNING,
    _error,
    app,
    config_manager,
    console,
    get_client,
    print_logo,
    show_welcome_banner,
)


def _first_run_setup() -> None:
    """Interactive first-run setup: collect API key."""

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Welcome to MEMANTO![/{BOLD_PRIMARY}]\n"
            "Let's get you set up in a few seconds.",
            border_style=PRIMARY,
        )
    )
    console.print()

    # API Key
    console.print(f"[{BOLD_BRIGHT}]Moorcheh API Key[/{BOLD_BRIGHT}]")
    console.print("[dim]Get yours free at https://console.moorcheh.ai[/dim]")
    api_key = typer.prompt("  Enter your Moorcheh API key", hide_input=True)

    if not api_key or not api_key.strip():
        console.print("[red]API key cannot be empty.[/red]")
        raise typer.Exit(1)

    api_key_clean = api_key.strip()
    console.print("  [dim]Verifying API key...[/dim]")
    try:
        from moorcheh_sdk import MoorchehClient
        from moorcheh_sdk.exceptions import AuthenticationError, NamespaceNotFound

        client = MoorchehClient(api_key=api_key_clean)
        try:
            client.documents.get(namespace_name="__memanto_auth_ping__", ids=["1"])
        except AuthenticationError:
            console.print("[red]Invalid Moorcheh API key.[/red]")
            raise typer.Exit(1)
        except NamespaceNotFound:
            pass  # Key is valid
        except Exception as e:
            # For other network errors, assume valid or warn, but don't strictly fail setup
            console.print(
                f"[yellow]Could not fully verify API key (network issue?): {str(e)}[/yellow]"
            )
    except ImportError:
        pass  # SDK not installed or available, skip verify

    config_manager.set_api_key(api_key_clean)
    console.print("[green]  ✓ API key saved[/green]")
    console.print()

    # Write basic default configs to config.yaml
    config_manager.set_server_config("127.0.0.1", 8000)
    config_manager.set_cli_config(interactive_mode=True, smart_parse=True)

    # Done
    console.print(
        Panel(
            "[bold green]Setup complete![/bold green]\n\n"
            f"[dim]Config:[/dim] {config_manager.config_dir}\n"
            f"[dim]API Key:[/dim] [green]●[/green] configured",
            title="Ready",
            border_style=SUCCESS,
        )
    )
    console.print()


def version_callback(value: bool):
    if value:
        from memanto.app import __version__

        typer.echo(f"memanto version: {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        help="Show the application's version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    """MEMANTO CLI - Memory that AI Agents Love!"""
    if ctx.invoked_subcommand is None:
        # Print logo
        print_logo()

        # First-run setup if not configured
        if not config_manager.is_configured():
            _first_run_setup()

        # Print the system info/dashboard
        show_welcome_banner(config_manager)


# ============================================================================
# STATUS COMMAND - Comprehensive Scenario Dashboard
# ============================================================================


@app.command()
def status():
    """Show comprehensive MEMANTO scenario dashboard.

    Displays environment, server health, configuration, active session,
    and registered agents at a glance.
    """
    from memanto.app import __version__ as memanto_version

    # Header
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]MEMANTO Status Dashboard[/{BOLD_PRIMARY}]\n"
            f"Memory that AI Agents Love!  •  v{memanto_version}",
            border_style=PRIMARY,
        )
    )
    console.print()

    # Environment
    env_table = Table(show_header=False, box=None, padding=(0, 2))
    env_table.add_column("Key", style="dim")
    env_table.add_column("Value")

    env_table.add_row("Python", platform.python_version())
    env_table.add_row("OS", platform.platform())

    console.print(Panel(env_table, title="Environment", border_style=PRIMARY))
    console.print()

    # Configuration
    is_configured = config_manager.is_configured()
    server_cfg = config_manager.get_server_config()

    cfg_table = Table(show_header=False, box=None, padding=(0, 2))
    cfg_table.add_column("Key", style="dim")
    cfg_table.add_column("Value")

    cfg_table.add_row("Config Dir", str(config_manager.config_dir))

    server_url = f"http://{server_cfg['url']}:{server_cfg['port']}"
    if is_configured:
        cfg_table.add_row("Local REST API URL", server_url)
        cfg_table.add_row("API Key", "[green]● configured[/green]")
    else:
        cfg_table.add_row("Local REST API URL", "[dim]not set[/dim]")
        cfg_table.add_row("API Key", "[red]● not configured[/red]")

    console.print(Panel(cfg_table, title="Configuration", border_style=PRIMARY))
    console.print()

    if not is_configured:
        console.print(
            "[yellow]⚠ MEMANTO is not configured.[/yellow]\n"
            f"  Run [{BRIGHT}]memanto[/{BRIGHT}] to get started.\n"
        )
        raise typer.Exit(0)

    # Server Health
    server_online = False

    try:
        response = httpx.get(f"{server_url}/health", timeout=5.0)
        response.raise_for_status()
        health = response.json()
        server_online = True

        srv_table = Table(show_header=False, box=None, padding=(0, 2))
        srv_table.add_column("Key", style="dim")
        srv_table.add_column("Value")

        srv_table.add_row("URL", server_url)

        h_status = health.get("status", "unknown")
        if h_status == "healthy":
            srv_table.add_row("Status", "[green]● online[/green]")
        elif h_status == "degraded":
            srv_table.add_row("Status", "[yellow]● degraded[/yellow]")
        else:
            srv_table.add_row("Status", f"[red]● {h_status}[/red]")

        srv_table.add_row("Version", health.get("version", "unknown"))

        moorcheh_ok = health.get("moorcheh_connected", False)
        srv_table.add_row(
            "Moorcheh",
            "[green]● connected[/green]"
            if moorcheh_ok
            else "[red]● disconnected[/red]",
        )

        console.print(
            Panel(
                srv_table,
                title="Local REST API",
                border_style=SUCCESS if h_status == "healthy" else WARNING,
            )
        )
        console.print()
    except Exception:
        console.print(
            Panel(
                f"[red]● Local REST API server offline[/red] at {server_url}\n"
                f"[dim]Start it with:[/dim] [{BRIGHT}]memanto serve[/{BRIGHT}]",
                title="Local REST API",
                border_style=PRIMARY,
            )
        )
        console.print()

    # Active Agent
    active_agent_id, active_session_token = config_manager.get_active_session()
    has_session = bool(active_agent_id and active_session_token)

    if has_session and server_online:
        try:
            direct = get_client()
            direct.session_token = active_session_token
            direct.agent_id = active_agent_id
            session_data = direct.get_session_info()

            sess_table = Table(show_header=False, box=None, padding=(0, 2))
            sess_table.add_column("Key", style="dim")
            sess_table.add_column("Value")

            sess_table.add_row(
                "Agent", f"[bold]{session_data.get('agent_id', active_agent_id)}[/bold]"
            )
            sess_table.add_row("Pattern", session_data.get("pattern", "unknown"))
            sess_table.add_row("Namespace", session_data.get("namespace", "unknown"))
            sess_table.add_row(
                "Session Token",
                (active_session_token[:24] + "...") if active_session_token else "None",
            )
            sess_table.add_row(
                "Status", f"[green]● {session_data.get('status', 'active')}[/green]"
            )

            remaining_secs = session_data.get("time_remaining_seconds", 0)
            hours, remainder = divmod(remaining_secs, 3600)
            minutes = remainder // 60
            sess_table.add_row("Remaining", f"{int(hours)}h {int(minutes)}m")

            console.print(Panel(sess_table, title="Active Agent", border_style=SUCCESS))
            console.print()
        except Exception:
            sess_table = Table(show_header=False, box=None, padding=(0, 2))
            sess_table.add_column("Key", style="dim")
            sess_table.add_column("Value")

            sess_table.add_row("Agent", f"[bold]{active_agent_id}[/bold]")
            sess_table.add_row(
                "Session Token",
                (active_session_token[:24] + "...") if active_session_token else "None",
            )
            sess_table.add_row("Status", "[yellow]● activation may be expired[/yellow]")

            console.print(Panel(sess_table, title="Active Agent", border_style=WARNING))
            console.print()
    elif has_session and not server_online:
        try:
            direct = get_client()
            session_data = direct.get_session_info()

            sess_table = Table(show_header=False, box=None, padding=(0, 2))
            sess_table.add_column("Key", style="dim")
            sess_table.add_column("Value")

            sess_table.add_row(
                "Agent", f"[bold]{session_data.get('agent_id', active_agent_id)}[/bold]"
            )
            sess_table.add_row("Pattern", session_data.get("pattern", "unknown"))
            sess_table.add_row("Namespace", session_data.get("namespace", "unknown"))
            sess_table.add_row(
                "Session Token",
                (active_session_token[:24] + "...") if active_session_token else "None",
            )
            sess_table.add_row(
                "Status", f"[green]● {session_data.get('status', 'active')}[/green]"
            )

            remaining_secs = session_data.get("time_remaining_seconds", 0)
            hours, remainder = divmod(remaining_secs, 3600)
            minutes = remainder // 60
            sess_table.add_row("Remaining", f"{int(hours)}h {int(minutes)}m")

            console.print(Panel(sess_table, title="Active Agent", border_style=SUCCESS))
            console.print()
        except Exception:
            sess_table = Table(show_header=False, box=None, padding=(0, 2))
            sess_table.add_column("Key", style="dim")
            sess_table.add_column("Value")

            sess_table.add_row("Agent", f"[bold]{active_agent_id}[/bold]")
            sess_table.add_row(
                "Session Token",
                (active_session_token[:24] + "...") if active_session_token else "None",
            )
            sess_table.add_row("Status", "[yellow]● activation may be expired[/yellow]")

            console.print(Panel(sess_table, title="Active Agent", border_style=WARNING))
            console.print()
    else:
        console.print(
            Panel(
                "[dim]No active agent[/dim]\n"
                f"Activate an agent: [{BRIGHT}]memanto agent activate <agent-id>[/{BRIGHT}]",
                title="Active Agent",
                border_style="dim",
            )
        )
        console.print()

    # Registered Agents
    try:
        direct = get_client()
        agents = direct.list_agents()

        if agents:
            agent_table = Table(
                title="Registered Agents", show_header=True, header_style=BOLD_PRIMARY
            )
            agent_table.add_column("Agent ID", style=BRIGHT)
            agent_table.add_column("Pattern", style=ACCENT)
            agent_table.add_column("Description")
            agent_table.add_column("Sessions", justify="right")
            agent_table.add_column("Status", justify="center")

            for agent in agents:
                is_active = agent.get("agent_id") == active_agent_id
                agent_table.add_row(
                    agent.get("agent_id", "?"),
                    agent.get("pattern", "unknown"),
                    agent.get("description", "") or "[dim]—[/dim]",
                    str(agent.get("session_count", 0)),
                    "[green]● Active[/green]" if is_active else "[dim]Ready[/dim]",
                )

            console.print(agent_table)
        else:
            console.print("[dim]No agents registered yet.[/dim]")
            console.print(
                f"Create one: [{BRIGHT}]memanto agent create <agent-id>[/{BRIGHT}]"
            )
    except Exception:
        console.print("[dim]Could not fetch agent list.[/dim]")

    console.print()


# ============================================================================
# SERVE COMMAND - Embedded Server Mode
# ============================================================================


@app.command()
def serve(
    host: str = typer.Option(None, "--host", help="Server host (defaults to config)"),
    port: int = typer.Option(None, "--port", help="Server port (defaults to config)"),
    reload: bool = typer.Option(
        False, "--reload", help="Enable auto-reload for development"
    ),
):
    """Start MEMANTO server."""
    server_cfg = config_manager.get_server_config()
    host = host or server_cfg.get("url", "0.0.0.0")
    if host == "localhost":
        host = "0.0.0.0"  # Typically want 0.0.0.0 for bind
    port = port or server_cfg.get("port", 8000)

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]MEMANTO REST API Starting...[/{BOLD_PRIMARY}]\n"
            f"Host: {host}:{port}",
            border_style=PRIMARY,
        )
    )

    # Check if configured
    api_key = config_manager.get_api_key()
    if not api_key:
        console.print("\n[yellow]Warning: MEMANTO not configured yet.[/yellow]")
        console.print(f"Run [{BRIGHT}]memanto[/{BRIGHT}] to set up your API key.")
        console.print("The server will start but won't be able to use Moorcheh.")
    else:
        os.environ["MOORCHEH_API_KEY"] = api_key

    # Import uvicorn here to avoid loading FastAPI for CLI commands
    try:
        import uvicorn
    except ImportError:
        _error(
            "uvicorn is not installed.",
            hint="Install it with: pip install uvicorn[standard]",
        )

    # Check if port is already in use

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("localhost", port))
    sock.close()

    if result == 0:
        _error(
            f"Port {port} is already in use.",
            hint=f"MEMANTO may already be running. Try: memanto serve --port {port + 1}",
        )

    display_host = "localhost" if host == "0.0.0.0" else host
    console.print("\n[green]Starting local REST API...[/green]")
    console.print(f"[dim]Server URL: http://{display_host}:{port}[/dim]")
    console.print(f"[dim]API Docs: http://{display_host}:{port}/docs[/dim]")
    console.print(f"[dim]Health Check: http://{display_host}:{port}/health[/dim]")
    console.print(
        "\n[bold]Next step:[/bold] Open a new terminal and run [bright_white]memanto agent create <agent-id>[/bright_white]."
    )
    console.print("[dim]A session will start automatically after agent creation.[/dim]")
    console.print("\n[bold]Server is running. Press CTRL+C to stop.[/bold]\n")

    # Start server
    try:
        uvicorn.run(
            "memanto.app.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Server stopped.[/yellow]")
    except Exception as e:
        _error(f"Server failed to start: {e}")


# ============================================================================
# UI COMMAND - Web Dashboard
# ============================================================================


@app.command()
def ui(
    host: str = typer.Option(None, "--host", help="Server host (defaults to config)"),
    port: int = typer.Option(None, "--port", help="Server port (defaults to config)"),
):
    """Start MEMANTO server and open the Web UI Dashboard."""
    import webbrowser

    server_cfg = config_manager.get_server_config()
    host = host or server_cfg.get("url", "0.0.0.0")
    if host == "localhost":
        host = "0.0.0.0"
    port = port or server_cfg.get("port", 8000)

    # Check if configured
    api_key = config_manager.get_api_key()
    if not api_key:
        console.print("\n[yellow]Warning: MEMANTO not configured yet.[/yellow]")
        console.print(f"Run [{BRIGHT}]memanto[/{BRIGHT}] to set up your API key.")
    else:
        os.environ["MOORCHEH_API_KEY"] = api_key

    try:
        import uvicorn
    except ImportError:
        _error(
            "uvicorn is not installed.",
            hint="Install it with: pip install uvicorn[standard]",
        )

    # Check if port is already in use — if so, just open the browser
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_in_use = sock.connect_ex(("localhost", port)) == 0
    sock.close()

    ui_url = f"http://localhost:{port}/ui"

    def _open_dashboard_window(url: str):
        import subprocess
        import sys

        # On Windows, try to open Edge or Chrome in standalone app mode for a native feel
        success = False
        if sys.platform == "win32":
            try:
                # Need shell=True for `start` command to resolve registry paths
                subprocess.Popen(f'start msedge --app="{url}"', shell=True)
                success = True
            except Exception:
                try:
                    subprocess.Popen(f'start chrome --app="{url}"', shell=True)
                    success = True
                except Exception:
                    pass

        # Fallback to default browser
        if not success:
            webbrowser.open_new(url)

    if port_in_use:
        console.print(f"\n[green]Server already running on port {port}.[/green]")
        console.print(f"[{BRIGHT}]Opening dashboard:[/{BRIGHT}] {ui_url}")
        _open_dashboard_window(ui_url)
        return

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Memanto Dashboard Starting...[/{BOLD_PRIMARY}]\n"
            f"Server: {host}:{port}",
            border_style=PRIMARY,
        )
    )
    console.print(f"\n[{BRIGHT}]Dashboard:[/{BRIGHT}]  {ui_url}")
    console.print(f"[dim]API Docs:   http://localhost:{port}/docs[/dim]")
    console.print("\n[bold]Press CTRL+C to stop.[/bold]\n")

    # Open browser after a short delay (in background thread)
    def _open_browser():
        time.sleep(1.5)
        _open_dashboard_window(ui_url)

    browser_thread = threading.Thread(target=_open_browser, daemon=True)
    browser_thread.start()

    # Start server
    try:
        os.environ["MEMANTO_UI_MODE"] = "true"
        uvicorn.run("memanto.app.main:app", host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Dashboard stopped.[/yellow]")
    except Exception as e:
        _error(f"Server failed to start: {e}")
