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


def _verify_key(key: str) -> dict | None:
    """Check *key* with Memanto Cloud; return the ``/me`` account when the server has it."""
    from memanto.cli.client.hosted_client import HostedClient

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
    return account


def _browser_sign_in() -> tuple[str, str | None]:
    """Sign in through the console in a browser; return ``(device key, email)``."""
    from memanto.cli.client.device_auth import DeviceLoginError, device_login

    def show_code(code: dict, opened: bool) -> None:
        console.print("To sign in, approve this computer in the Memanto console:")
        console.print(f"  [{BRIGHT}]{code['verification_uri_complete']}[/{BRIGHT}]")
        console.print(f"  Code: [bold]{code['user_code']}[/bold]")
        if not opened:
            console.print(
                "[dim]Could not open a browser here. Open the link on any device.[/dim]"
            )
        console.print("[dim]Waiting for approval... (Ctrl-C to cancel)[/dim]")

    try:
        result = device_login(config_manager.get_memanto_api_url(), on_code=show_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Sign-in cancelled.[/yellow]")
        raise typer.Exit(1)
    except DeviceLoginError as e:
        _error(str(e))
    return result["api_key"], result.get("user_email")


def sign_in(key: str | None = None) -> None:
    """Sign in to Memanto Cloud (browser, or *key* when given) and make it the active backend.

    The key is stored in ~/.memanto/.env. The previous backend is remembered
    so 'memanto logout' can restore it. Exits on failure.
    """
    if key is not None:
        key = key.strip()
        if not key:
            _error("API key must not be empty.")
        account = _verify_key(key)
        email = account.get("email") if account else None
    else:
        key, email = _browser_sign_in()

    current = config_manager.get_backend()
    if current != Backend.MEMANTO_CLOUD and config_manager.get("backend"):
        config_manager.set("previous_backend", current.value)
    config_manager.set_memanto_api_key(key)
    if current != Backend.MEMANTO_CLOUD:
        _switch_backend(Backend.MEMANTO_CLOUD)

    who = f" as [bold]{email}[/bold]" if email else ""
    console.print(f"[green]Signed in to Memanto Cloud{who}.[/green]")


@app.command()
def login(
    key: str | None = typer.Option(
        None,
        "--key",
        help="Sign in with an API key (mk_...) instead of the browser, e.g. for CI. "
        f"Create one at {MEMANTO_CONSOLE_URL}/api-keys",
    ),
):
    """Sign in to Memanto Cloud and make it the active backend.

    Opens the Memanto console in your browser to approve this computer; no key
    to copy. Over SSH, open the printed link on any device. With --key, signs
    in with an existing API key instead (headless / CI).
    Your previous backend is remembered so 'memanto logout' can restore it.

    Examples:
        memanto login
        memanto login --key mk_...
    """
    sign_in(key)
    console.print(
        f"[dim]Next:[/dim] [{BRIGHT}]memanto connect[/{BRIGHT}] "
        "[dim]to set up your coding tools.[/dim]"
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
