"""
MEMANTO CLI - Memanto Cloud sign-in commands (login, logout).
"""

import typer

from memanto.app.clients.backend import Backend
from memanto.app.utils.errors import AuthenticationError
from memanto.cli.commands._shared import (
    BRIGHT,
    _error,
    app,
    config_manager,
    console,
)
from memanto.cli.config.manager import MEMANTO_CONSOLE_URL


def _switch_backend(backend: Backend) -> None:
    """Persist *backend* and drop the active agent, which belonged to the old store."""
    config_manager.set_backend(backend)
    config_manager.clear_active_session()


@app.command()
def login(
    key: str = typer.Option(
        ...,
        "--key",
        prompt="Memanto Cloud API key",
        hide_input=True,
        help=f"Memanto Cloud API key (mk_...). Create one at {MEMANTO_CONSOLE_URL}/api-keys",
    ),
):
    """Sign in to Memanto Cloud with an API key and make it the active backend.

    The key is checked against Memanto Cloud, then stored in ~/.memanto/.env.
    Your previous backend is remembered so 'memanto logout' can restore it.

    Examples:
        memanto login --key mk_...
    """
    from memanto.cli.client.hosted_client import HostedClient

    key = key.strip()
    if not key:
        _error("API key must not be empty.")

    client = HostedClient(key, base_url=config_manager.get_memanto_api_url())
    try:
        with console.status("Checking key with Memanto Cloud...", spinner="dots"):
            account = client.get_account()
            if account is None:
                # Server without /me yet: any authenticated call validates the key.
                client.list_agents()
    except AuthenticationError:
        _error(
            "Memanto Cloud rejected this API key.",
            hint=f"Create a key at {MEMANTO_CONSOLE_URL}/api-keys",
        )
    except Exception as e:
        _error(f"Could not verify the key with Memanto Cloud: {e}")

    current = config_manager.get_backend()
    if current != Backend.MEMANTO_CLOUD and config_manager.get("backend"):
        config_manager.set("previous_backend", current.value)
    config_manager.set_memanto_api_key(key)
    if current != Backend.MEMANTO_CLOUD:
        _switch_backend(Backend.MEMANTO_CLOUD)

    who = (
        f" as [bold]{account['email']}[/bold]"
        if account and account.get("email")
        else ""
    )
    console.print(f"[green]Signed in to Memanto Cloud{who}.[/green]")
    console.print(
        f"[dim]Next:[/dim] [{BRIGHT}]memanto connect <tool>[/{BRIGHT}] "
        "[dim]or[/dim] "
        f"[{BRIGHT}]memanto agent activate <agent>[/{BRIGHT}]"
    )


@app.command()
def logout():
    """Sign out of Memanto Cloud and switch back to your previous backend.

    Removes the Memanto Cloud key from ~/.memanto/.env. Memories stay on
    Memanto Cloud.

    Examples:
        memanto logout
    """
    if not config_manager.get_memanto_api_key():
        console.print("[yellow]Not signed in to Memanto Cloud.[/yellow]")
        raise typer.Exit(0)

    config_manager.clear_memanto_api_key()
    previous = config_manager.get("previous_backend")
    if config_manager.get_backend() == Backend.MEMANTO_CLOUD:
        restored = Backend(previous) if previous else Backend.CLOUD
        _switch_backend(restored)
        console.print(
            f"[green]Signed out of Memanto Cloud.[/green] Backend: {restored.value}"
        )
    else:
        console.print("[green]Signed out of Memanto Cloud.[/green]")
    if previous is not None:
        data = config_manager.load_yaml()
        data.pop("previous_backend", None)
        config_manager.save_yaml(data)
