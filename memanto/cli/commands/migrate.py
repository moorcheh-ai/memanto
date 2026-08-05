"""
MEMANTO CLI - Migrate from other memory providers into Memanto.

Replaces the old standalone ``analyze`` subcommand. Migrating now does the
full job:

    1. Pull (or load) the provider's export.
    2. Map source rows onto Memanto memory types.
    3. Bulk-write through ``batch_remember`` (chunked to 100/req).
    4. (Optional) Render the same token/storage/latency report the old
       ``analyze`` command produced — so users see the migration upside in
       the same flow.

Use ``--dry-run`` to preview the mapping (no writes) and always get the
savings report. Use ``--report`` on a real run to also write the report.

Outputs live in ``~/.memanto/migrate/<provider>/<timestamp>/`` to keep the
migrate and old analyze artifacts cleanly separated.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import typer
from rich.panel import Panel

from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionError,
    SessionExpiredError,
)
from memanto.cli.analyze.letta_compare import (
    build_llm_prompt as build_letta_llm_prompt,
)
from memanto.cli.analyze.letta_compare import (
    build_report_markdown as build_letta_report_markdown,
)
from memanto.cli.analyze.letta_compare import (
    compute_metrics as compute_letta_metrics,
)
from memanto.cli.analyze.letta_export import run_letta_export
from memanto.cli.analyze.mem0_compare import (
    build_llm_prompt as build_mem0_llm_prompt,
)
from memanto.cli.analyze.mem0_compare import (
    build_report_markdown as build_mem0_report_markdown,
)
from memanto.cli.analyze.mem0_compare import (
    compute_metrics as compute_mem0_metrics,
)
from memanto.cli.analyze.mem0_export import run_mem0_export
from memanto.cli.analyze.supermemory_compare import (
    build_llm_prompt as build_supermemory_llm_prompt,
)
from memanto.cli.analyze.supermemory_compare import (
    build_report_markdown as build_supermemory_report_markdown,
)
from memanto.cli.analyze.supermemory_compare import (
    compute_metrics as compute_supermemory_metrics,
)
from memanto.cli.analyze.supermemory_export import run_supermemory_export
from memanto.cli.commands._shared import (
    BOLD_PRIMARY,
    BRIGHT,
    PRIMARY,
    SUCCESS,
    WARNING,
    _error,
    _warn,
    config_manager,
    console,
    get_client,
    migrate_app,
)
from memanto.cli.migrate.okf_loader import load_okf_bundle
from memanto.cli.migrate.runner import (
    load_export,
    run_migration,
    write_preview,
)

# Per-provider plumbing in one place so each subcommand stays tiny.
_PROVIDER_BUNDLES: dict[str, dict[str, Any]] = {
    "mem0": {
        "label": "Mem0",
        "exporter": run_mem0_export,
        "metrics": compute_mem0_metrics,
        "prompt": build_mem0_llm_prompt,
        "report": build_mem0_report_markdown,
        "export_filename": "mem0_export.json",
    },
    "letta": {
        "label": "Letta",
        "exporter": run_letta_export,
        "metrics": compute_letta_metrics,
        "prompt": build_letta_llm_prompt,
        "report": build_letta_report_markdown,
        "export_filename": "letta_export.json",
    },
    "supermemory": {
        "label": "Supermemory",
        "exporter": run_supermemory_export,
        "metrics": compute_supermemory_metrics,
        "prompt": build_supermemory_llm_prompt,
        "report": build_supermemory_report_markdown,
        "export_filename": "supermemory_export.json",
    },
}


def _resolve_provider_key(
    provider: str,
    api_key: str | None,
) -> str:
    """Prompt-or-fetch the provider API key the same way analyze used to."""
    getters = {
        "mem0": (
            config_manager.get_mem0_api_key,
            config_manager.set_mem0_api_key,
            "https://app.mem0.ai",
            "MEM0_API_KEY",
        ),
        "letta": (
            config_manager.get_letta_api_key,
            config_manager.set_letta_api_key,
            "https://docs.letta.com",
            "LETTA_API_KEY",
        ),
        "supermemory": (
            config_manager.get_supermemory_api_key,
            config_manager.set_supermemory_api_key,
            "https://supermemory.ai/docs",
            "SUPERMEMORY_API_KEY",
        ),
    }
    get_fn, set_fn, docs_url, env_name = getters[provider]
    label = _PROVIDER_BUNDLES[provider]["label"]

    if api_key and api_key.strip():
        set_fn(api_key.strip())
        resolved = get_fn()
        if resolved:
            return resolved

    stored = get_fn()
    if stored:
        return stored

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]{label} API key[/{BOLD_PRIMARY}]\n"
            f"[dim]Get yours at {docs_url}[/dim]",
            border_style=PRIMARY,
        )
    )
    entered = typer.prompt(f"  Enter your {label} API key", hide_input=True)
    if not entered or not entered.strip():
        _error(
            f"{label} API key is required.",
            hint=f"Pass --api-key or set {env_name} in ~/.memanto/.env",
        )
    set_fn(entered.strip())
    console.print("[green]  ✓ API key saved to ~/.memanto/.env[/green]")
    resolved = get_fn()
    if not resolved:
        _error(f"Failed to save {label} API key.")
    return resolved


def _generate_narrative(prompt: str, *, provider_label: str) -> tuple[str, str, str]:
    """Call the active agent's LLM for a comparison narrative (best-effort)."""
    method = (
        "Moorcheh 'answer' endpoint over the active agent's namespace; "
        "memory retrieval suppressed (top_k=1, high threshold) so the model "
        "writes purely from the supplied metrics."
    )
    active_agent_id, _ = config_manager.get_active_session()
    if not active_agent_id:
        _warn(
            "No active agent — skipping LLM narrative for the report. "
            "Run 'memanto agent activate <agent-id>' to include it."
        )
        return "", "none (no active agent)", method

    ans_cfg = config_manager.get_answer_config()
    model = ans_cfg.get("model", "unknown")
    last_error = ""

    for attempt in range(2):
        try:
            client = get_client()
            result = client.answer(
                agent_id=active_agent_id,
                question=prompt,
                limit=1,
                kiosk_mode=True,
                threshold=0.99,
                temperature=0.3,
                header_prompt=(
                    "You are a precise infrastructure analyst writing a migration "
                    f"brief. Use present tense for the user's current {provider_label} "
                    "footprint; use future or conditional tense (can/would/could) for "
                    "Memanto benefits. Output clean markdown. Do not fabricate "
                    "benchmark numbers."
                ),
                footer_prompt="Return only the markdown brief, no preamble.",
            )
            narrative = (result or {}).get("answer", "") or ""
            return narrative, model, method
        except (InvalidSessionTokenError, SessionExpiredError, SessionError) as exc:
            last_error = str(exc)
            if attempt == 0:
                _warn("Memanto session invalid — re-activating agent and retrying...")
                try:
                    get_client().activate_agent(active_agent_id)
                    continue
                except Exception as reactivate_exc:
                    last_error = str(reactivate_exc)
                    break
        except Exception as exc:
            last_error = str(exc)
            break

    _warn(f"LLM narrative skipped: {last_error}")
    return "", "unavailable", method


def _render_savings_report(
    *,
    provider: str,
    export: dict[str, Any],
    export_path: Path,
    run_dir: Path,
) -> Path:
    bundle = _PROVIDER_BUNDLES[provider]
    metrics = bundle["metrics"](export)
    narrative, llm_model, llm_method = _generate_narrative(
        bundle["prompt"](metrics),
        provider_label=bundle["label"],
    )
    report_md = bundle["report"](
        metrics=metrics,
        narrative=narrative,
        export_path=str(export_path),
        llm_model=llm_model,
        llm_method=llm_method,
        exported_at=export.get("exported_at"),
    )
    report_path = run_dir / "migrate-report.md"
    report_path.write_text(report_md, encoding="utf-8")
    return report_path


def _resolve_target_agent(agent: str | None) -> str:
    if agent and agent.strip():
        return agent.strip()
    active_agent_id, active_session_token = config_manager.get_active_session()
    if not active_agent_id or not active_session_token:
        _error(
            "No --agent supplied and no active agent.",
            hint=(
                "Activate an agent first ('memanto agent activate <id>') "
                "or pass --agent <id>."
            ),
        )
    return active_agent_id


def _load_or_export(
    *,
    provider: str,
    file: Path | None,
    api_key: str | None,
    run_dir: Path,
    progress: Callable[[str], None],
) -> tuple[Path, dict[str, Any]]:
    """Either load an existing export JSON or run the live exporter."""
    bundle = _PROVIDER_BUNDLES[provider]
    if file is not None:
        progress(f"Loading export from {file}")
        return file, load_export(file)

    key = _resolve_provider_key(provider, api_key)
    try:
        result = bundle["exporter"](key, run_dir, on_progress=progress)
        return cast(tuple[Path, dict[str, Any]], result)
    except ImportError as exc:
        _error(str(exc))
    except ValueError as exc:
        _error(str(exc))
    except Exception as exc:
        _error(f"{bundle['label']} export failed: {exc}")


def _run_migrate_flow(
    *,
    provider: str,
    api_key: str | None,
    file: Path | None,
    agent: str | None,
    dry_run: bool,
    report: bool,
) -> None:
    """Shared entry point for every migrate subcommand."""
    bundle = _PROVIDER_BUNDLES[provider]
    label = bundle["label"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = config_manager.get_migrate_dir(provider) / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    mode = "Dry run" if dry_run else "Migrate"
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]{label} -> Memanto  {mode}[/{BOLD_PRIMARY}]",
            border_style=PRIMARY,
        )
    )

    def progress(msg: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {msg}")

    # Step 1 — resolve target only if we will actually write.
    target_agent = None if dry_run else _resolve_target_agent(agent)

    # Step 2 — load or live-export.
    export_path, export = _load_or_export(
        provider=provider,
        file=file,
        api_key=api_key,
        run_dir=run_dir,
        progress=progress,
    )

    # Step 3 — map (and optionally write).
    progress("Mapping source records onto Memanto schema...")
    client = None if dry_run else get_client()
    summary, rows = run_migration(
        provider=provider,
        export=export,
        client=client,
        agent_id=target_agent or "",
        dry_run=dry_run,
        on_progress=progress,
    )

    # Step 4 — preview file (dry run) and savings report (dry run OR --report).
    preview_path = write_preview(rows, run_dir / "mapped_preview.json")

    report_path: Path | None = None
    if dry_run or report:
        progress("Rendering savings report...")
        report_path = _render_savings_report(
            provider=provider,
            export=export,
            export_path=export_path,
            run_dir=run_dir,
        )

    # Step 5 — summarize.
    type_lines = (
        ", ".join(f"{k}: {v}" for k, v in sorted(summary.type_counts.items())) or "—"
    )

    body_lines = [
        f"[dim]Source records:[/dim] {summary.source_count}",
        f"[dim]Mapped memories:[/dim] {summary.mapped_count}  "
        f"[dim](skipped {summary.skipped} empty)[/dim]",
        f"[dim]Type breakdown:[/dim] {type_lines}",
    ]
    if dry_run:
        body_lines.append("")
        body_lines.append("[yellow]Dry run — no writes performed.[/yellow]")
    else:
        body_lines.append(
            f"[dim]Imported:[/dim] {summary.imported}  "
            f"[dim]Failed:[/dim] {summary.failed}  "
            f"[dim]Batches:[/dim] {summary.batches}"
        )
        body_lines.append(f"[dim]Target agent:[/dim] {target_agent}")

    body_lines.append("")
    body_lines.append(f"[dim]Run dir:[/dim] {run_dir}")
    body_lines.append(f"[dim]Mapped preview:[/dim] {preview_path}")
    if report_path:
        body_lines.append(f"[dim]Savings report:[/dim] {report_path}")
    if summary.errors:
        sample = summary.errors[0]
        body_lines.append(
            f"[red]First error:[/red] {sample}  [dim](see run dir for more)[/dim]"
        )

    border = WARNING if summary.failed else SUCCESS
    console.print()
    console.print(
        Panel(
            "\n".join(body_lines),
            title=(
                "[bold yellow]Dry run complete[/bold yellow]"
                if dry_run
                else "[bold green]Migration complete[/bold green]"
            ),
            border_style=border,
        )
    )


# --------------------------------------------------------------------------
# Provider subcommands — thin wrappers over _run_migrate_flow.
# --------------------------------------------------------------------------


@migrate_app.command("mem0")
def migrate_mem0(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="MEM0_API_KEY",
        help="Mem0 API key (saved to ~/.memanto/.env)",
    ),
    file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Existing Mem0 export JSON (skip live export).",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target Memanto agent id (defaults to the active agent).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the mapping and savings report without writing.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help="Also write the token/latency/storage savings report on a real run.",
    ),
):
    """Migrate a Mem0 account into the active (or selected) Memanto agent.

    Examples:
        memanto migrate mem0 --dry-run
        memanto migrate mem0 --file ./mem0_export.json
        memanto migrate mem0 --agent my-agent --report
    """
    _run_migrate_flow(
        provider="mem0",
        api_key=api_key,
        file=file,
        agent=agent,
        dry_run=dry_run,
        report=report,
    )


@migrate_app.command("letta")
def migrate_letta(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="LETTA_API_KEY",
        help="Letta API key (saved to ~/.memanto/.env)",
    ),
    file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Existing Letta export JSON (skip live export).",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target Memanto agent id (defaults to the active agent).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the mapping and savings report without writing.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help="Also write the token/latency/storage savings report on a real run.",
    ),
):
    """Migrate Letta archival passages into the active (or selected) Memanto agent."""
    _run_migrate_flow(
        provider="letta",
        api_key=api_key,
        file=file,
        agent=agent,
        dry_run=dry_run,
        report=report,
    )


@migrate_app.command("okf")
def migrate_okf(
    path: Path = typer.Argument(
        ...,
        help="Path to an OKF bundle directory (or a single .md file).",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target Memanto agent id (defaults to the active agent).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the mapping without writing.",
    ),
):
    """Import an OKF (Open Knowledge Format) bundle into the active (or selected) agent.

    Unlike the provider migrations, OKF is a local file bundle — no API key and
    no savings report. Fields that don't map onto Memanto's schema are preserved
    in a ``[Supporting data]`` footer, and OKF's free-form ``type`` is
    auto-classified.

    Examples:
        memanto migrate okf ./okf-bundle --dry-run
        memanto migrate okf ./okf-bundle --agent my-agent
    """
    if not path.exists():
        _error(
            f"OKF bundle not found: {path}",
            hint="Provide a path to an OKF directory or .md file.",
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = config_manager.get_migrate_dir("okf") / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    mode = "Dry run" if dry_run else "Migrate"
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]OKF -> Memanto  {mode}[/{BOLD_PRIMARY}]",
            border_style=PRIMARY,
        )
    )

    def progress(msg: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {msg}")

    target_agent = None if dry_run else _resolve_target_agent(agent)

    progress(f"Loading OKF bundle from {path}")
    try:
        export = load_okf_bundle(path)
    except Exception as exc:
        _error(f"Failed to load OKF bundle: {exc}")

    progress("Mapping OKF nodes onto Memanto schema...")
    client = None if dry_run else get_client()
    summary, rows = run_migration(
        provider="okf",
        export=export,
        client=client,
        agent_id=target_agent or "",
        dry_run=dry_run,
        on_progress=progress,
    )

    preview_path = write_preview(rows, run_dir / "mapped_preview.json")

    type_lines = (
        ", ".join(f"{k}: {v}" for k, v in sorted(summary.type_counts.items())) or "—"
    )
    body_lines = [
        f"[dim]OKF nodes:[/dim] {summary.source_count}",
        f"[dim]Mapped memories:[/dim] {summary.mapped_count}  "
        f"[dim](skipped {summary.skipped})[/dim]",
        f"[dim]Type breakdown:[/dim] {type_lines}",
    ]
    if dry_run:
        body_lines.append("")
        body_lines.append("[yellow]Dry run — no writes performed.[/yellow]")
    else:
        body_lines.append(
            f"[dim]Imported:[/dim] {summary.imported}  "
            f"[dim]Failed:[/dim] {summary.failed}  "
            f"[dim]Batches:[/dim] {summary.batches}"
        )
        body_lines.append(f"[dim]Target agent:[/dim] {target_agent}")

    body_lines.append("")
    body_lines.append(f"[dim]Run dir:[/dim] {run_dir}")
    body_lines.append(f"[dim]Mapped preview:[/dim] {preview_path}")
    if summary.errors:
        body_lines.append(
            f"[red]First error:[/red] {summary.errors[0]}  "
            "[dim](see run dir for more)[/dim]"
        )

    border = WARNING if summary.failed else SUCCESS
    console.print()
    console.print(
        Panel(
            "\n".join(body_lines),
            title=(
                "[bold yellow]Dry run complete[/bold yellow]"
                if dry_run
                else "[bold green]Import complete[/bold green]"
            ),
            border_style=border,
        )
    )


@migrate_app.command("supermemory")
def migrate_supermemory(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="SUPERMEMORY_API_KEY",
        help="Supermemory API key (saved to ~/.memanto/.env)",
    ),
    file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Existing Supermemory export JSON (skip live export).",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target Memanto agent id (defaults to the active agent).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the mapping and savings report without writing.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help="Also write the token/latency/storage savings report on a real run.",
    ),
):
    """Migrate a Supermemory account into the active (or selected) Memanto agent."""
    _run_migrate_flow(
        provider="supermemory",
        api_key=api_key,
        file=file,
        agent=agent,
        dry_run=dry_run,
        report=report,
    )
