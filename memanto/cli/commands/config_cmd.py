"""
MEMANTO CLI - Config commands (show) and backend switching for `memanto use`.
"""

from rich.panel import Panel
from rich.table import Table

from memanto.app.clients.backend import BACKEND_NAMES, Backend
from memanto.cli.commands._shared import (
    BRIGHT,
    SUCCESS,
    config_app,
    config_manager,
    console,
)


@config_app.command("show")
def config_show():
    """Display current configuration."""
    api_key = config_manager.get_api_key()
    server_cfg = config_manager.get_server_config()
    cli_cfg = config_manager.get_cli_config()
    ans_cfg = config_manager.get_answer_config()
    rec_cfg = config_manager.get_recall_config()
    active_agent_id, active_session_token = config_manager.get_active_session()
    schedule_time = config_manager.get_schedule_time()

    table = Table(title="MEMANTO Configuration", show_header=False)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    backend = config_manager.get_backend()
    table.add_row("Backend", BACKEND_NAMES[backend])
    if backend == Backend.ON_PREM:
        op = config_manager.get_onprem_config()
        table.add_row("On-Prem URL", op.get("url", ""))
        table.add_row("Embedding", op.get("embedding_provider") or "—")
    table.add_row("Config Dir", str(config_manager.config_dir))
    table.add_row("Server URL", f"{server_cfg['url']}:{server_cfg['port']}")
    if backend == Backend.CLOUD:
        table.add_row("API Key", "***configured***" if api_key else "not set")
    table.add_row("Active Agent", active_agent_id or "none")
    table.add_row("Session Active", "yes" if active_session_token else "no")
    table.add_row("Schedule Time", schedule_time)
    table.add_row("Interactive Mode", str(cli_cfg.get("interactive_mode", True)))
    table.add_row("Smart Parse", str(cli_cfg.get("smart_parse", True)))

    # Answer Config
    table.add_section()
    table.add_row("[bold]Answer Config[/bold]", "")
    table.add_row("  Model", ans_cfg.get("model", "—"))
    table.add_row("  Temperature", str(ans_cfg.get("temperature", 0.7)))
    table.add_row("  Limit", str(ans_cfg.get("answer_limit", 5)))
    table.add_row("  Threshold", str(ans_cfg.get("threshold", 0.25)))

    # Recall Config
    table.add_section()
    table.add_row("[bold]Recall Config[/bold]", "")
    table.add_row("  Limit (Top N)", str(rec_cfg.get("limit", 10)))
    table.add_row("  Min Similarity", str(rec_cfg.get("min_similarity", 0.0)))

    console.print(table)


def switch_to_backend(target_backend: Backend) -> None:
    """Make *target_backend* active, running its setup (or sign-in) first if needed.

    Clears the active agent session. Switching to Memanto Cloud remembers the
    current backend so 'memanto logout' can restore it.
    """
    target = BACKEND_NAMES[target_backend]
    current = config_manager.get_backend()
    if target_backend == current:
        console.print(
            f"[{BRIGHT}]Backend is already '{target}'.[/{BRIGHT}] Nothing to do."
        )
        return

    # Run the backend-specific setup if not already configured.
    if target_backend == Backend.MEMANTO_CLOUD:
        if not config_manager.get_memanto_api_key():
            from memanto.cli.commands.auth import sign_in

            sign_in()  # Signs in, offers to move memories, and switches.
            return
        if config_manager.get("backend"):
            config_manager.set("previous_backend", current.value)
    elif target_backend == Backend.CLOUD:
        if not config_manager.get_api_key():
            from memanto.cli.commands.core import _cloud_setup

            _cloud_setup()
    else:
        from memanto.cli.commands.core import _onprem_setup

        _onprem_setup()

    # Persist + propagate.
    config_manager.set_backend(target_backend)
    config_manager.clear_active_session()
    try:
        from memanto.app.clients.moorcheh import moorcheh_client as _singleton
        from memanto.app.config import settings as _settings

        _settings.MEMANTO_BACKEND = target_backend.value
        _singleton.reset_client()
    except Exception:
        pass

    console.print(
        Panel(
            f"[bold green]Switched backend to {target}.[/bold green]\n"
            f"[dim]Active session was cleared.[/dim]",
            title="Backend",
            border_style=SUCCESS,
        )
    )
