"""
MEMANTO CLI - Memanto Cloud sign-in and backend switching (login, logout, use).
"""

import sys
import time

import typer

from memanto.app.clients.backend import BACKEND_LABELS, BACKEND_NAMES, Backend
from memanto.app.utils.errors import AuthenticationError
from memanto.cli.commands._shared import (
    BRIGHT,
    _error,
    _warn,
    app,
    config_manager,
    console,
)
from memanto.cli.config.manager import MEMANTO_CONSOLE_URL


def _stdin_is_terminal() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _local_backend_in_use() -> bool:
    """True when a local backend (Moorcheh key or on-prem) is set up and active."""
    return (
        bool(config_manager.get("backend"))
        and config_manager.get_backend() != Backend.MEMANTO_CLOUD
        and config_manager.is_configured()
    )


def _ask_to_move(local: Backend) -> bool:
    """Ask whether to move *local*'s memories to Memanto Cloud."""
    label = BACKEND_LABELS[local]
    console.print()
    console.print(f"You were using {label}. What about its memories?")
    console.print(
        f"  [{BRIGHT}]1[/{BRIGHT}]  Move them to Memanto Cloud  "
        "[dim](recommended; your local copy stays)[/dim]"
    )
    console.print(
        f"  [{BRIGHT}]2[/{BRIGHT}]  Continue on Memanto Cloud without them  "
        "[dim](move later with: memanto migrate to-cloud)[/dim]"
    )
    answer: str = typer.prompt("  Enter 1 or 2", default="1")
    return answer.strip() != "2"


def _ask_include_expired() -> bool:
    """Ask whether the move also takes expired memories."""
    console.print("Which memories?")
    console.print(
        f"  [{BRIGHT}]1[/{BRIGHT}]  Active memories only  [dim](recommended)[/dim]"
    )
    console.print(f"  [{BRIGHT}]2[/{BRIGHT}]  All, including expired ones")
    answer: str = typer.prompt("  Enter 1 or 2", default="1")
    return answer.strip() == "2"


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


def _retire_key(key: str) -> str:
    """Delete *key* on Memanto Cloud if 'memanto login' created it, so this computer leaves the Computers list.

    Returns "signed_out", "console_key" (left active), "already" (no longer valid)
    or "unreachable".
    """
    from memanto.cli.client.hosted_client import HostedClient

    client = HostedClient(key, base_url=config_manager.get_memanto_api_url())
    try:
        return "signed_out" if client.sign_out_device() else "console_key"
    except AuthenticationError:
        return "already"
    except Exception:
        return "unreachable"


def _browser_sign_in() -> tuple[str, str | None]:
    """Sign in through the console in a browser; return ``(device key, email)``."""
    from memanto.cli.client.device_auth import DeviceLoginError, device_login

    # Spinner with a live countdown while waiting; plain line when not a terminal.
    status = console.status("", spinner="dots", spinner_style=BRIGHT)
    deadline = time.monotonic()

    def tick() -> None:
        left = max(0, int(deadline - time.monotonic()))
        status.update(
            f"[dim]Waiting for approval in your browser · {left // 60}:{left % 60:02d} left · Ctrl-C to cancel[/dim]"
        )

    def show_code(code: dict, opened: bool) -> None:
        nonlocal deadline
        console.print("To sign in, approve this computer in the Memanto console:")
        console.print(f"  [{BRIGHT}]{code['verification_uri_complete']}[/{BRIGHT}]")
        console.print(f"  Code: [bold]{code['user_code']}[/bold]")
        if not opened:
            console.print(
                "[dim]Could not open a browser here. Open the link on any device.[/dim]"
            )
        if not console.is_terminal:
            console.print("[dim]Waiting for approval... (Ctrl-C to cancel)[/dim]")
            return
        deadline = time.monotonic() + float(code.get("expires_in", 600))
        tick()
        status.start()

    def wait(seconds: float) -> None:
        """Sleep between polls, refreshing the countdown every second."""
        end = time.monotonic() + seconds
        while (remaining := end - time.monotonic()) > 0:
            time.sleep(min(1.0, remaining))
            tick()

    try:
        result = device_login(
            config_manager.get_memanto_api_url(), on_code=show_code, sleep=wait
        )
    except KeyboardInterrupt:
        status.stop()
        console.print("\n[yellow]Sign-in cancelled.[/yellow]")
        raise typer.Exit(1)
    except DeviceLoginError as e:
        status.stop()
        _error(str(e))
    status.stop()
    return result["api_key"], result.get("user_email")


def sign_in(key: str | None = None) -> None:
    """Sign in to Memanto Cloud (browser, or *key* when given) and make it the active backend.

    The key is stored in ~/.memanto/.env. The previous backend is remembered
    so 'memanto logout' can restore it. A key from an earlier 'memanto login'
    on this computer is deleted once the new one is in place, so signing in
    again replaces this computer instead of adding another. When a local
    backend was in use and stdin is a terminal, asks whether to move its
    memories (active only, or including expired) before continuing on
    Memanto Cloud. Exits on failure.
    """
    old_key = config_manager.get_memanto_api_key()
    if key is not None:
        key = key.strip()
        if not key:
            _error("API key must not be empty.")
        account = _verify_key(key)
        email = account.get("email") if account else None
    else:
        key, email = _browser_sign_in()

    current = config_manager.get_backend()
    local = current if _local_backend_in_use() else None
    config_manager.set_memanto_api_key(key)
    who = f" as [bold]{email}[/bold]" if email else ""
    console.print(f"[green]Signed in to Memanto Cloud{who}.[/green]")

    if old_key and old_key != key and _retire_key(old_key) == "unreachable":
        console.print(
            "[dim]Could not remove this computer's previous sign-in. "
            f"Sign it out at {MEMANTO_CONSOLE_URL}/api-keys[/dim]"
        )

    move = local is not None and _stdin_is_terminal() and _ask_to_move(local)
    include_expired = move and _ask_include_expired()

    if current != Backend.MEMANTO_CLOUD:
        if config_manager.get("backend"):
            config_manager.set("previous_backend", current.value)
        _switch_backend(Backend.MEMANTO_CLOUD)
    if move and local:
        from memanto.cli.commands.migrate import run_cloud_move

        run_cloud_move(local, include_expired=include_expired)


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
    If you use Memanto local today (with Moorcheh Cloud or on-prem), you can
    move those memories to Memanto Cloud or continue without them.

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

    Signs this computer out on Memanto Cloud (its key stops working and it
    leaves the Computers list) and removes the key from ~/.memanto/.env.
    A key created in the console (memanto login --key) stays active.
    Memories stay on Memanto Cloud.

    Examples:
        memanto logout
    """
    key = config_manager.get_memanto_api_key()
    if not key:
        console.print("[yellow]Not signed in to Memanto Cloud.[/yellow]")
        raise typer.Exit(0)

    with console.status("Signing out of Memanto Cloud...", spinner="dots"):
        outcome = _retire_key(key)
    config_manager.clear_memanto_api_key()
    previous = config_manager.get("previous_backend")
    if config_manager.get_backend() == Backend.MEMANTO_CLOUD:
        restored = Backend(previous) if previous else Backend.CLOUD
        _switch_backend(restored)
        console.print(
            f"[green]Signed out of Memanto Cloud.[/green] Backend: {BACKEND_NAMES[restored]}"
        )
    else:
        console.print("[green]Signed out of Memanto Cloud.[/green]")
    if outcome == "console_key":
        console.print(
            "[dim]The API key you signed in with is still active. "
            f"Manage it at {MEMANTO_CONSOLE_URL}/api-keys[/dim]"
        )
    elif outcome == "unreachable":
        _warn(
            "Could not reach Memanto Cloud, so this computer is still listed. "
            f"Sign it out at {MEMANTO_CONSOLE_URL}/api-keys"
        )
    if previous is not None:
        data = config_manager.load_yaml()
        data.pop("previous_backend", None)
        config_manager.save_yaml(data)


_USE_TARGETS = {
    "cloud": Backend.MEMANTO_CLOUD,
    "moorcheh": Backend.CLOUD,
    "on-prem": Backend.ON_PREM,
    "local": Backend.ON_PREM,
    # The names the CLI prints for each backend work too.
    **{name: backend for backend, name in BACKEND_NAMES.items()},
}


@app.command()
def use(
    target: str = typer.Argument(
        ...,
        help="cloud (Memanto Cloud), moorcheh (Memanto local with Moorcheh "
        "Cloud), or on-prem (Memanto local with Moorcheh on-prem; alias: local).",
    ),
):
    """Switch where Memanto keeps memories. Connected tools follow automatically.

    Switching to Memanto Cloud signs you in first if needed. Memories are not
    moved; to copy local memories up, run 'memanto migrate to-cloud'.

    Examples:
        memanto use cloud
        memanto use on-prem
    """
    from memanto.cli.commands.config_cmd import switch_to_backend

    backend = _USE_TARGETS.get(target.strip().lower())
    if backend is None:
        _error(
            f"Unknown backend '{target}'.",
            hint="Use: memanto use cloud | moorcheh | on-prem",
        )
    switch_to_backend(backend)
