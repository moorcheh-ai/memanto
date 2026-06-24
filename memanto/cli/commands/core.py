"""
MEMANTO CLI - Core commands (status, serve, ui, main_callback).
"""

import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import typer
from rich.panel import Panel
from rich.table import Table

from memanto.app.clients.backend import Backend
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
    """Interactive first-run setup: pick backend, then configure it."""

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Welcome to MEMANTO![/{BOLD_PRIMARY}]\n"
            "Let's get you set up in a few seconds.",
            border_style=PRIMARY,
        )
    )
    console.print()

    backend = _prompt_backend_choice()
    if backend == Backend.ON_PREM:
        _onprem_setup()
    else:
        _cloud_setup()

    # Common defaults
    config_manager.set_server_config("127.0.0.1", 8000)
    config_manager.set_cli_config(interactive_mode=True, smart_parse=True)
    config_manager.set_backend(backend)

    # Reset the backend dispatcher so the next call picks up the new choice.
    from memanto.app.clients.moorcheh import moorcheh_client as _singleton
    from memanto.app.config import settings as _settings

    _settings.MEMANTO_BACKEND = backend.value
    _singleton.reset_client()

    backend_label = "Cloud" if backend == Backend.CLOUD else "On-Prem"
    extras = (
        "[dim]API Key:[/dim] [green]●[/green] configured"
        if backend == Backend.CLOUD
        else f"[dim]Server:[/dim] {config_manager.get_onprem_config()['url']}\n"
        f"[dim]Embedding:[/dim] {config_manager.get_onprem_config()['embedding_provider'] or 'unknown'}"
    )
    console.print(
        Panel(
            "[bold green]Setup complete![/bold green]\n\n"
            f"[dim]Backend:[/dim] {backend_label}\n"
            f"[dim]Config:[/dim] {config_manager.config_dir}\n"
            f"{extras}",
            title="Ready",
            border_style=SUCCESS,
        )
    )
    console.print()


def _prompt_backend_choice() -> Backend:
    """Ask the user which backend they want. Default: Cloud."""
    console.print(f"[{BOLD_BRIGHT}]Choose your backend[/{BOLD_BRIGHT}]")
    console.print(
        f"  [{BRIGHT}]1[/{BRIGHT}]  Moorcheh Cloud  "
        "[dim](instant, needs API key, all features)[/dim]"
    )
    console.print(
        f"  [{BRIGHT}]2[/{BRIGHT}]  Moorcheh On-Prem  "
        "[dim](~5-10 min install, Docker required, no API key)[/dim]"
    )
    choice = typer.prompt("  Enter 1 or 2", default="1")
    console.print()
    return Backend.ON_PREM if str(choice).strip() == "2" else Backend.CLOUD


def _cloud_setup() -> None:
    """Cloud branch: collect and verify Moorcheh API key."""
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
            console.print(
                f"[yellow]Could not fully verify API key (network issue?): {str(e)}[/yellow]"
            )
    except ImportError:
        pass

    config_manager.set_api_key(api_key_clean)
    console.print("[green]  ✓ API key saved[/green]")
    console.print()


def _prompt_onprem_setup_mode() -> bool:
    """Ask user for setup mode. Returns True for Quick Setup, False for Choose Models."""
    console.print()
    console.print(f"[{BOLD_BRIGHT}]On-Prem Setup Mode[/{BOLD_BRIGHT}]")
    console.print(
        f"  [{BRIGHT}]1[/{BRIGHT}]  Quick Setup  "
        f"[dim]- Ollama with nomic-embed-text (embedding) + qwen2.5 (LLM), zero config[/dim]"
    )
    console.print(
        f"  [{BRIGHT}]2[/{BRIGHT}]  Choose Models  "
        f"[dim]- pick your own embedding and LLM providers[/dim]"
    )
    choice = typer.prompt("  Enter 1 or 2", default="1")
    console.print()
    return str(choice).strip() == "1"


def _onprem_setup() -> None:
    """On-prem branch: install moorcheh-client if missing, configure, start."""
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Setting up Moorcheh On-Prem[/{BOLD_PRIMARY}]\n"
            "[dim]This may take 5-10 minutes on first run.[/dim]",
            border_style=PRIMARY,
        )
    )
    console.print()

    _ensure_docker_available()
    _ensure_moorcheh_client_installed()

    existing_state = config_manager.get_onprem_state()
    if (
        existing_state.get("embedding_provider")
        and existing_state.get("embedding_model")
        and existing_state.get("llm_provider")
        and existing_state.get("llm_model")
    ):
        embedding_provider = existing_state["embedding_provider"]
        embedding_model = existing_state["embedding_model"]
        embedding_key = _recover_moorcheh_api_key("embedding", embedding_provider)
        llm_provider = existing_state["llm_provider"]
        llm_model = existing_state["llm_model"]
        llm_key = _recover_moorcheh_api_key("llm", llm_provider)
        console.print(
            f"[dim]  Reusing previous on-prem setup: "
            f"{embedding_provider} / {embedding_model} + {llm_provider} / {llm_model}[/dim]"
        )
    else:
        quick_setup = _prompt_onprem_setup_mode()
        if quick_setup:
            embedding_provider, embedding_model, embedding_key = (
                "ollama",
                "nomic-embed-text",
                "",
            )
            llm_provider, llm_model, llm_key = "ollama", "qwen2.5", ""
            console.print(
                "[dim]  Quick Setup: Ollama with nomic-embed-text "
                "(embedding) + qwen2.5 (LLM)[/dim]"
            )
        else:
            embedding_provider, embedding_model, embedding_key = (
                _prompt_embedding_provider()
            )
            llm_provider, llm_model, llm_key = _prompt_llm_provider(
                embedding_provider, embedding_key
            )
    # Write the FULL config (embedding + LLM) to ~/.moorcheh/config.json BEFORE
    # `moorcheh up`, so the server reads the complete config on first boot and
    # we don't have to bounce the stack. `moorcheh up` itself only knows
    # `--embedding-*` flags, so without this pre-write the LLM section would
    # be missing until we restart.
    _persist_moorcheh_llm_config(
        embedding_provider,
        embedding_model,
        embedding_key,
        llm_provider,
        llm_model,
        llm_key,
    )
    _moorcheh_up_and_wait(embedding_provider, embedding_model, embedding_key)

    # Pull any Ollama models needed (embedding and/or LLM). `moorcheh up` uses
    # native host Ollama when one is running and a bundled container otherwise;
    # _pull_ollama_model handles both.
    if embedding_provider == "ollama":
        _pull_ollama_model(embedding_model)
    if llm_provider == "ollama" and llm_model != embedding_model:
        _pull_ollama_model(llm_model)

    # Persist everything on-prem in ~/.memanto/on-prem/state.json — the
    # shared ~/.memanto/config.yaml belongs to the cloud backend; on-prem
    # never writes into it. ``ConfigManager.get_answer_config()`` reads
    # ``llm_model`` from this file when the active backend is on-prem, so
    # ``memanto answer`` automatically picks the right LLM without any
    # cross-backend pollution.
    config_manager.set_onprem_state(
        installed_at=datetime.utcnow().isoformat() + "Z",
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        llm_provider=llm_provider,
        llm_model=llm_model,
        url="http://localhost:8080",
    )


def _ensure_docker_available() -> None:
    """Fail clearly if Docker is missing or daemon is not running."""
    if shutil.which("docker") is None:
        _error(
            "Docker is not installed (required for Moorcheh on-prem).",
            hint="Install Docker Desktop: https://www.docker.com/products/docker-desktop",
        )
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            _error(
                "Docker is installed but the daemon is not reachable.",
                hint="Start Docker Desktop and try again.",
            )
    except Exception as e:
        _error(
            f"Could not run `docker info`: {e}",
            hint="Make sure Docker Desktop is running.",
        )
    console.print("[green]  ✓ Docker is running[/green]")


def _ensure_moorcheh_client_installed() -> None:
    """pip install moorcheh-client if the ``moorcheh`` package is missing."""
    import importlib.util

    if importlib.util.find_spec("moorcheh") is not None:
        console.print("[green]  ✓ moorcheh-client already installed[/green]")
        return

    console.print("[dim]  Installing moorcheh-client...[/dim]")
    try:
        # >=0.1.3 exposes namespaces/documents/files/answer resources matching
        # the cloud SDK shape; on-prem Answer requires this version.
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "moorcheh-client>=0.1.3"]
        )
    except subprocess.CalledProcessError as e:
        _error(f"Failed to install moorcheh-client: {e}")
    console.print("[green]  ✓ moorcheh-client installed[/green]")


def _prompt_embedding_provider() -> tuple[str, str, str]:
    """Ask user for embedding provider. Returns (provider, model, api_key_or_empty)."""
    console.print()
    console.print(f"[{BOLD_BRIGHT}]Embedding provider[/{BOLD_BRIGHT}]")
    console.print(
        f"  [{BRIGHT}]1[/{BRIGHT}]  Ollama (local, zero API keys)  "
        "[dim]- we'll pull the embedding model for you[/dim]"
    )
    console.print(
        f"  [{BRIGHT}]2[/{BRIGHT}]  Bring your own (OpenAI or Cohere)  "
        "[dim]- cloud-hosted embeddings, requires an API key[/dim]"
    )
    choice = typer.prompt("  Enter 1 or 2", default="1")
    console.print()

    if str(choice).strip() == "2":
        console.print(
            f"  [{BRIGHT}]a[/{BRIGHT}]  OpenAI   [{BRIGHT}]b[/{BRIGHT}]  Cohere"
        )
        sub = typer.prompt("  Enter a or b", default="a")
        provider = "openai" if str(sub).strip().lower() != "b" else "cohere"
        model = (
            "text-embedding-3-small" if provider == "openai" else "embed-english-v3.0"
        )
        key = typer.prompt(f"  Enter your {provider.title()} API key", hide_input=True)
        if not key or not key.strip():
            _error(f"{provider.title()} API key cannot be empty.")
        return provider, model, key.strip()

    # Ollama: no native install needed. `moorcheh up` reuses a native Ollama if
    # one is already running, otherwise it starts a bundled container. We pull
    # the embedding model once the server is healthy (see _pull_ollama_model).
    console.print(
        "[dim]  `moorcheh up` will reuse a running Ollama or start one in a "
        "container. The embedding model will be pulled automatically.[/dim]"
    )
    return "ollama", "nomic-embed-text", ""


# Valid on-prem LLM identifiers, sourced from moorcheh.user_config. Listed
# explicitly so the prompt is stable even if moorcheh-client adds/removes
# models. Keep in sync with ``moorcheh.user_config.LLM_PROVIDER_MODELS``.
_LLM_RECOMMENDED = {
    "ollama": "qwen2.5",
    "openai": "gpt-4o-mini",
    "cohere": "command-r-plus-08-2024",
}


def _prompt_llm_provider(
    embedding_provider: str, embedding_key: str
) -> tuple[str, str, str]:
    """Ask user for LLM provider for ``answer.generate``.

    Returns ``(provider, model, api_key_or_empty)``. Mirrors the embedding
    flow: pick a provider, the recommended model is used automatically
    (``qwen2.5`` / ``gpt-4o-mini`` / ``command-r-plus-08-2024``). Users who
    want a different model can edit ``answer.model`` in
    ``~/.memanto/on-prem/config.yaml`` later.
    """
    console.print()
    console.print(f"[{BOLD_BRIGHT}]Answer LLM provider[/{BOLD_BRIGHT}]")
    console.print(
        f"  [{BRIGHT}]1[/{BRIGHT}]  Ollama (local, zero API keys)  "
        f"[dim]- model: {_LLM_RECOMMENDED['ollama']}[/dim]"
    )
    console.print(
        f"  [{BRIGHT}]2[/{BRIGHT}]  OpenAI  "
        f"[dim]- model: {_LLM_RECOMMENDED['openai']}, requires an API key[/dim]"
    )
    console.print(
        f"  [{BRIGHT}]3[/{BRIGHT}]  Cohere  "
        f"[dim]- model: {_LLM_RECOMMENDED['cohere']}, requires an API key[/dim]"
    )
    # Default to whichever provider was chosen for embeddings (likely already
    # has its key set), else Ollama.
    default_choice = {"ollama": "1", "openai": "2", "cohere": "3"}.get(
        embedding_provider, "1"
    )
    choice = typer.prompt("  Enter 1, 2, or 3", default=default_choice)
    provider = {"1": "ollama", "2": "openai", "3": "cohere"}.get(
        str(choice).strip(), "ollama"
    )
    model = _LLM_RECOMMENDED[provider]
    console.print()

    if provider in ("openai", "cohere"):
        # Reuse the embedding API key when the same provider was chosen so we
        # don't double-prompt; otherwise ask.
        if provider == embedding_provider and embedding_key:
            console.print(
                f"[dim]  Reusing {provider.title()} API key from embedding setup.[/dim]"
            )
            key = embedding_key
        else:
            key = typer.prompt(
                f"  Enter your {provider.title()} API key", hide_input=True
            ).strip()
            if not key:
                _error(f"{provider.title()} API key cannot be empty.")
        return provider, model, key

    console.print(
        f"[dim]  Ollama LLM model {model} will be pulled into the container.[/dim]"
    )
    return "ollama", model, ""


def _recover_moorcheh_api_key(section: str, provider: str) -> str:
    """Read an api_key out of ``~/.moorcheh/config.json`` for re-onboarding.

    ``section`` is ``"embedding"`` or ``"llm"``. Returns ``""`` for providers
    that don't need a key (ollama) or when the file/key is missing — callers
    must handle that (typically by failing fast at ``moorcheh up`` if a paid
    provider needs a key we couldn't recover).
    """
    if provider == "ollama":
        return ""
    import json as _json

    cfg = Path.home() / ".moorcheh" / "config.json"
    if not cfg.exists():
        return ""
    try:
        data = _json.loads(cfg.read_text())
    except Exception:
        return ""
    block = data.get(section) or {}
    key = block.get("api_key") or ""
    return key if isinstance(key, str) else ""


def _persist_moorcheh_llm_config(
    embedding_provider: str,
    embedding_model: str,
    embedding_key: str,
    llm_provider: str,
    llm_model: str,
    llm_key: str,
) -> None:
    """Write the LLM section into ``~/.moorcheh/config.json``.

    ``moorcheh up`` writes only the embedding section; the on-prem server
    needs both to serve ``answer.generate``. Uses moorcheh-client's own
    ``save_runtime_config`` helper so the schema stays in sync.
    """
    try:
        from moorcheh.user_config import (  # type: ignore[import-not-found]
            EmbeddingConfig,
            LlmConfig,
            default_base_url,
            save_runtime_config,
        )
    except ImportError as e:
        _error(f"moorcheh.user_config unavailable: {e}")
        return

    embedding_cfg = EmbeddingConfig(
        provider=embedding_provider,
        model=embedding_model,
        api_key=embedding_key or None,
        base_url=default_base_url(embedding_provider),
    )
    llm_cfg = LlmConfig(
        provider=llm_provider,
        model=llm_model,
        api_key=llm_key or None,
        base_url=default_base_url(llm_provider),
    )
    try:
        save_runtime_config(embedding_cfg, llm_cfg)
        console.print("[green]  ✓ LLM config saved to ~/.moorcheh/config.json[/green]")
    except Exception as e:
        _error(f"Failed to persist LLM config: {e}")


def _pull_ollama_model(model: str) -> None:
    """Pull an Ollama model after ``moorcheh up`` started the stack.

    ``moorcheh up`` reuses a native Ollama already running on the host and only
    starts a bundled container when none is reachable. In both cases the Ollama
    HTTP API is exposed on the host at 127.0.0.1:11434 (the bundled container
    publishes the port), so pull over HTTP when reachable and only fall back to
    ``docker exec`` for a bundled container we can't reach over HTTP.
    """
    try:
        from moorcheh.ollama_setup import ollama_is_reachable, pull_ollama_model_http
    except ImportError:
        ollama_is_reachable = None

    if ollama_is_reachable is not None and ollama_is_reachable():
        console.print(f"[dim]  Pulling {model} into Ollama (127.0.0.1:11434)...[/dim]")
        try:
            pull_ollama_model_http(model)
        except Exception as e:
            _error(f"Failed to pull Ollama model {model}: {e}")
        console.print(f"[green]  ✓ Ollama model {model} ready[/green]")
        return

    _pull_ollama_model_in_container(model)


def _pull_ollama_model_in_container(model: str) -> None:
    """Pull an Ollama model inside the bundled Ollama container via
    ``docker exec`` (fallback when the host HTTP API is not reachable).

    Looks for a running container with image ``ollama/ollama``; falls back to
    name-match. Errors clearly with a manual command if we can't locate it.
    """
    container_id = ""
    for filter_flag in ("ancestor=ollama/ollama", "name=ollama"):
        try:
            out = subprocess.check_output(
                ["docker", "ps", "--filter", filter_flag, "--format", "{{.ID}}"],
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            out = ""
        if out:
            container_id = out.splitlines()[0]
            break

    if not container_id:
        _error(
            "Could not find a running Ollama container after `moorcheh up`.",
            hint=(
                "Run `docker ps` to find it, then: "
                f"docker exec <id> ollama pull {model}"
            ),
        )

    console.print(
        f"[dim]  Pulling {model} inside Ollama container {container_id[:12]}...[/dim]"
    )
    try:
        subprocess.check_call(["docker", "exec", container_id, "ollama", "pull", model])
    except subprocess.CalledProcessError as e:
        _error(f"Failed to pull model {model} inside container: {e}")
    console.print(f"[green]  ✓ Ollama model {model} ready in container[/green]")


def _moorcheh_up_and_wait(provider: str, model: str, key: str) -> None:
    """Run ``moorcheh up`` (with non-interactive embedding flags) and poll /health.

    The documented non-interactive setup passes embedding settings to
    ``moorcheh up`` directly via ``--embedding-provider``, ``--embedding-model``,
    and ``--embedding-api-key``; ``moorcheh configure`` only supports
    interactive prompts plus ``--force``, so we skip it.
    """
    args = [
        "moorcheh",
        "up",
        "--embedding-provider",
        provider,
        "--embedding-model",
        model,
    ]
    if key:
        args.extend(["--embedding-api-key", key])

    console.print("[dim]  Starting Moorcheh server (`moorcheh up`)...[/dim]")
    try:
        subprocess.check_call(args)
    except FileNotFoundError:
        _error(
            "`moorcheh` CLI not found on PATH.",
            hint="Re-open your terminal so pip's scripts directory is on PATH, "
            "or run: python -m moorcheh up",
        )
    except subprocess.CalledProcessError as e:
        _error(f"`moorcheh up` failed: {e}")

    url = "http://localhost:8080/health"
    console.print(f"[dim]  Waiting for {url}...[/dim]")
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                console.print("[green]  ✓ Moorcheh server online[/green]")
                return
        except Exception:
            pass
        time.sleep(1.0)
    _error(
        f"Moorcheh server did not become healthy at {url} within 60s.",
        hint="Check `moorcheh status` and Docker logs.",
    )


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
    """MEMANTO CLI - Your agents focus. Memanto remembers."""
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
            f"Your agents focus. Memanto remembers.  •  v{memanto_version}",
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

    backend = config_manager.get_backend()
    cfg_table.add_row("Backend", backend.value)
    if backend == Backend.ON_PREM:
        op = config_manager.get_onprem_config()
        cfg_table.add_row("On-Prem URL", op.get("url", ""))
        cfg_table.add_row("Embedding", op.get("embedding_provider") or "—")
        # Probe on-prem server health
        try:
            r = httpx.get(f"{op.get('url', '').rstrip('/')}/health", timeout=2.0)
            if r.status_code == 200:
                cfg_table.add_row("On-Prem Server", "[green]● online[/green]")
            else:
                cfg_table.add_row(
                    "On-Prem Server", f"[yellow]● status {r.status_code}[/yellow]"
                )
        except Exception:
            cfg_table.add_row("On-Prem Server", "[red]● offline[/red]")

    server_url = f"http://{server_cfg['url']}:{server_cfg['port']}"
    if is_configured:
        cfg_table.add_row("Local REST API URL", server_url)
        if backend == Backend.CLOUD:
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
    backend = config_manager.get_backend()
    if backend == Backend.ON_PREM:
        op = config_manager.get_onprem_config()
        console.print(
            f"\n[dim]Backend: on-prem at {op.get('url', 'http://localhost:8080')}[/dim]"
        )
        os.environ["MEMANTO_BACKEND"] = "on-prem"
    else:
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
    if config_manager.get_backend() == Backend.ON_PREM:
        os.environ["MEMANTO_BACKEND"] = "on-prem"
    else:
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
