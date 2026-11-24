"""
``memanto widget on`` / ``memanto widget off``: the desktop widget.

The widget needs ``pywebview``, which is not a memanto dependency: ``on``
installs it into this Python the first time, so ``pip install memanto`` stays
light for everyone who never uses the widget.
"""

import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

import typer
from filelock import FileLock, Timeout

from memanto.cli.commands._shared import _error, app, config_manager, console
from memanto.cli.widget.app import lock_path, pid_path

# Linux has no built-in web view, so pull in the Qt one; Windows (WebView2)
# and macOS (WebKit) use the system's.
WEBVIEW_REQUIREMENT = (
    "pywebview[qt]>=6,<7" if sys.platform.startswith("linux") else "pywebview>=6,<7"
)
_START_TIMEOUT_SECONDS = 20.0
_STOP_TIMEOUT_SECONDS = 5.0


class WidgetAction(str, Enum):
    on = "on"
    off = "off"


def _log_path() -> Path:
    return config_manager.config_dir / "widget.log"


def is_widget_running() -> bool:
    """True while a widget process holds the widget lock."""
    path = lock_path(config_manager)
    if not path.exists():
        return False
    lock = FileLock(str(path))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return True
    lock.release()
    return False


def install_command() -> list[str]:
    """How to install pywebview into the Python running memanto.

    pip when this environment has it; otherwise uv (uv-made environments,
    e.g. ``uv tool install memanto``, ship without pip).

    Raises:
        RuntimeError: If neither pip nor uv is available.
    """
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install", WEBVIEW_REQUIREMENT]
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", sys.executable, WEBVIEW_REQUIREMENT]
    raise RuntimeError("Neither pip nor uv is available to install pywebview.")


def _ensure_webview() -> None:
    """Install pywebview on first use."""
    if importlib.util.find_spec("webview") is not None:
        return
    try:
        cmd = install_command()
    except RuntimeError as e:
        _error(str(e), hint=f'Install it yourself: pip install "{WEBVIEW_REQUIREMENT}"')

    console.print(
        "[dim]First run: installing the widget's window library (pywebview)…[/dim]"
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _error(
            "Could not install pywebview.\n"
            + (result.stderr or result.stdout).strip()[-800:],
            hint=f'Install it yourself, then retry: pip install "{WEBVIEW_REQUIREMENT}"',
        )
    importlib.invalidate_caches()


def _spawn_widget() -> subprocess.Popen:
    """Start the widget process detached from this terminal."""
    # A first-time user may not have ~/.memanto yet.
    config_manager.config_dir.mkdir(parents=True, exist_ok=True)
    log = open(_log_path(), "w", encoding="utf-8")  # noqa: SIM115 - handed to the child
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
    python = sys.executable
    if sys.platform == "win32":
        # pythonw has no console window to flash up or close with the terminal.
        pythonw = Path(python).with_name("pythonw.exe")
        if pythonw.exists():
            python = str(pythonw)
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen([python, "-m", "memanto.cli.widget"], **kwargs)
    finally:
        log.close()


def _widget_on() -> None:
    if is_widget_running():
        console.print("[green]The Memanto widget is already on.[/green]")
        return
    _ensure_webview()

    proc = _spawn_widget()
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if pid_path(config_manager).exists() and is_widget_running():
            console.print(
                "[green]OK Memanto widget is on[/green] [dim](bottom-right corner; "
                "turn it off with 'memanto widget off' or its power button)[/dim]"
            )
            return
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    log = _log_path().read_text(encoding="utf-8", errors="replace").strip()
    _error(
        "The widget did not start." + (f"\n{log[-800:]}" if log else ""),
        hint=f"Full log: {_log_path()}",
    )


def _stop_pid(pid: int) -> None:
    if sys.platform == "win32":
        # /T also ends the WebView2 child processes.
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _widget_off() -> None:
    pid_file = pid_path(config_manager)
    if not is_widget_running():
        pid_file.unlink(missing_ok=True)
        console.print("The Memanto widget is already off.")
        return

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        _error(
            "The widget is running but its pid file is missing or unreadable.",
            hint=f"Close it from its power button. Pid file: {pid_file}",
        )
    _stop_pid(pid)

    deadline = time.monotonic() + _STOP_TIMEOUT_SECONDS
    while is_widget_running():
        if time.monotonic() > deadline:
            _error(f"The widget (pid {pid}) did not stop.")
        time.sleep(0.1)
    pid_file.unlink(missing_ok=True)
    console.print("[green]OK Memanto widget is off[/green]")


@app.command()
def widget(
    action: WidgetAction = typer.Argument(..., help="on or off"),
):
    """Show or hide the Memanto desktop widget (a small always-on-top agent).

    It shows the active agent, its session and stats, lets you switch or
    reset the agent, and chat with its memory. Works on Memanto local and
    Memanto Cloud, sharing the CLI's active agent and session.
    The first 'on' installs the window library it needs (pywebview).
    """
    if action == WidgetAction.on:
        _widget_on()
    else:
        _widget_off()
