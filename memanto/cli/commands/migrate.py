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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import typer
from rich.panel import Panel
from rich.table import Table

from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionError,
    SessionExpiredError,
)
from memanto.cli.analyze.langfuse_export import (
    DEFAULT_WINDOW_DAYS,
    normalize_host,
    run_langfuse_export,
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
from memanto.cli.migrate import langfuse_config, langfuse_discover, langfuse_state
from memanto.cli.migrate.langfuse_rules import CaptureConfig, parse_capture_modes
from memanto.cli.migrate.okf_loader import load_okf_bundle
from memanto.cli.migrate.runner import (
    load_export,
    run_langfuse_sync,
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
    # Langfuse carries no savings report: it is an observability backend, not
    # a memory store to benchmark Memanto against. It also runs its own flow
    # (`_run_langfuse_flow`) because it reconciles against a sync ledger, so
    # only `label` and `exporter` are ever read from this entry.
    "langfuse": {
        "label": "Langfuse",
        "exporter": run_langfuse_export,
        "export_filename": "langfuse_export.json",
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
        "langfuse": (
            config_manager.get_langfuse_api_key,
            config_manager.set_langfuse_api_key,
            "your Langfuse project settings (enter as 'public_key:secret_key')",
            "LANGFUSE_API_KEY",
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
        try:
            return file, load_export(file)
        except (FileNotFoundError, OSError) as exc:
            raise ValueError(f"Export file not found or unreadable: {file} ({exc})")
        except ValueError as exc:
            raise ValueError(f"Export file is not valid JSON: {file} ({exc})")

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


@migrate_app.command("chatgpt")
def migrate_chatgpt(
    file: Path = typer.Argument(
        ...,
        help="Path to the ChatGPT 'conversations.json' from your data export.",
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
    """Import a ChatGPT account export into the active (or selected) agent.

    Like the OKF import, ChatGPT is a local file -- no API key and no savings
    report. The adapter walks the active branch of every conversation and
    imports your own statements (preferences, facts, commitments) as memories.

    Examples:
        memanto migrate chatgpt ./conversations.json --dry-run
        memanto migrate chatgpt ./conversations.json --agent my-agent
    """
    if not file.exists():
        _error(
            f"ChatGPT export not found: {file}",
            hint="Export your data at chatgpt.com -> Settings -> Data controls -> Export.",
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = config_manager.get_migrate_dir("chatgpt") / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    mode = "Dry run" if dry_run else "Migrate"
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]ChatGPT -> Memanto  {mode}[/{BOLD_PRIMARY}]",
            border_style=PRIMARY,
        )
    )

    def progress(msg: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {msg}")

    target_agent = None if dry_run else _resolve_target_agent(agent)

    progress(f"Parsing ChatGPT export from {file}")
    from memanto.cli.migrate.chatgpt_export import (
        export_chatgpt_memories,
        load_conversations,
    )

    try:
        export = export_chatgpt_memories(load_conversations(file))
    except Exception as exc:
        _error(f"Failed to parse ChatGPT export: {exc}")

    progress("Mapping ChatGPT statements onto Memanto schema...")
    client = None if dry_run else get_client()
    summary, rows = run_migration(
        provider="chatgpt",
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
        f"[dim]User statements:[/dim] {summary.source_count}",
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


# --------------------------------------------------------------------------
# Langfuse — a repeatable sync, so it runs its own reconciling flow.
# --------------------------------------------------------------------------


def _parse_capture_modes(raw: list[str] | None) -> frozenset[str]:
    """Normalize ``--capture low-score`` to the internal ``low_score``."""
    try:
        return parse_capture_modes(raw)
    except ValueError as exc:
        _error(str(exc))


def _parse_rules(raw: list[str] | None) -> list[langfuse_config.ScoreRule]:
    """Turn ``--score-fail 'correctness<0.7'`` into rules, or fail loudly."""
    rules = []
    for item in raw or []:
        try:
            rules.append(langfuse_config.parse_score_rule(item))
        except langfuse_config.ScoreRuleError as exc:
            _error(str(exc))
    return rules


def _resolve_langfuse_config(
    *,
    base_dir: Path,
    key: str,
    capture: list[str] | None,
    score_fail: list[str] | None,
    score_pass: list[str] | None,
    latency_ms: float | None,
    latency_percentile: float | None,
    cost_usd: float | None,
    cost_percentile: float | None,
    group_by: str | None,
    save: bool,
) -> langfuse_config.ProjectConfig:
    """Merge stored per-project settings with this run's flags.

    Stored settings are the baseline so a user configures a project once;
    flags override for a single run, and ``--save`` promotes them.
    """
    cfg_path = langfuse_config.config_path(base_dir)
    stored = langfuse_config.load_project(cfg_path, key)

    merged = langfuse_config.ProjectConfig(
        capture=_parse_capture_modes(capture) if capture else stored.capture,
        score_fail_rules=_parse_rules(score_fail) or stored.score_fail_rules,
        score_pass_rules=_parse_rules(score_pass) or stored.score_pass_rules,
        latency_ms=latency_ms if latency_ms is not None else stored.latency_ms,
        latency_percentile=(
            latency_percentile
            if latency_percentile is not None
            else stored.latency_percentile
        ),
        cost_usd=cost_usd if cost_usd is not None else stored.cost_usd,
        cost_percentile=(
            cost_percentile if cost_percentile is not None else stored.cost_percentile
        ),
        group_by=group_by or stored.group_by,
    )

    if save:
        langfuse_config.save_project(cfg_path, key, merged)
        console.print(f"[green]  ✓ Saved capture settings for project '{key}'[/green]")
    return merged


def _render_discovery(report: dict[str, Any]) -> None:
    """Print what's actually in the user's project so they can choose budgets."""
    window = report.get("window", {})
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Langfuse project discovery[/{BOLD_PRIMARY}]\n"
            f"[dim]{window.get('observation_count', 0)} observations, "
            f"{window.get('score_count', 0)} scores[/dim]",
            border_style=PRIMARY,
        )
    )

    scores = report.get("scores") or []
    if scores:
        table = Table(title="Scores", box=None, header_style=BOLD_PRIMARY)
        for col in ("Name", "Type", "Count", "Observed", "Suggested rule"):
            table.add_column(col, overflow="fold")
        for row in scores:
            observed = (
                f"{row.get('min')} … {row.get('max')}"
                if "min" in row
                else ", ".join(row.get("categories") or [])
            )
            table.add_row(
                row["name"],
                row["data_type"],
                str(row["count"]),
                observed,
                row["suggestion"],
            )
        console.print(table)
    else:
        console.print("[dim]  No scores in this window.[/dim]")

    operations = report.get("operations") or []
    if operations:
        table = Table(
            title="Latency & cost by operation", box=None, header_style=BOLD_PRIMARY
        )
        for col in ("Operation", "Count", "p50 ms", "p95 ms", "p99 ms", "cost p95"):
            table.add_column(col, overflow="fold")
        for row in operations:
            table.add_row(
                row["name"],
                str(row["count"]),
                str(row["latency_p50"]),
                str(row["latency_p95"]),
                str(row["latency_p99"]),
                f"${row['cost_p95']}" if report.get("has_cost_data") else "—",
            )
        console.print(table)

    errors = report.get("errors") or {}
    labels = errors.get("labels") or []
    if labels:
        table = Table(
            title=(
                f"Error labels — {errors.get('errored_observations', 0)} errors "
                f"grouped into {errors.get('distinct_signatures', 0)} signatures"
            ),
            box=None,
            header_style=BOLD_PRIMARY,
        )
        table.add_column("Label", overflow="fold")
        table.add_column("Count")
        for row in labels:
            table.add_row(row["label"], str(row["count"]))
        console.print(table)

    for note in report.get("notes") or []:
        _warn(note)

    console.print(
        "\n[dim]Set what you want with --capture / --score-fail / "
        "--latency-percentile etc. and add --save to store it for this "
        "project.[/dim]"
    )


@migrate_app.command("langfuse")
def migrate_langfuse(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="LANGFUSE_API_KEY",
        help="Langfuse keys as 'public_key:secret_key' (saved to ~/.memanto/.env).",
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        envvar="LANGFUSE_HOST",
        help="Langfuse base URL (default https://cloud.langfuse.com).",
    ),
    file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Existing Langfuse export JSON (skip the live pull).",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target Memanto agent id (defaults to the active agent).",
    ),
    capture: list[str] | None = typer.Option(
        None,
        "--capture",
        "-c",
        help=(
            "What to capture; repeatable or comma-separated. "
            "errors | low-score | slow | costly | success  [default: errors]"
        ),
    ),
    since_days: int | None = typer.Option(
        None,
        "--since-days",
        help=(
            "Look back this many days. Defaults to the last sync time, "
            f"or {DEFAULT_WINDOW_DAYS} days on a first run."
        ),
    ),
    score_fail: list[str] | None = typer.Option(
        None,
        "--score-fail",
        help=(
            "Rule marking a score as a failure; repeatable. "
            "e.g. 'correctness<0.7', 'toxicity>0.3', 'thumbs_up=false', "
            "'tone in rude,evasive'. Run --discover to see your score names."
        ),
    ),
    score_pass: list[str] | None = typer.Option(
        None,
        "--score-pass",
        help="Rule marking a score as a success; repeatable. Same syntax.",
    ),
    latency_ms: float | None = typer.Option(
        None,
        "--latency-ms",
        help="Fixed latency budget in ms; slower observations become 'slow'.",
    ),
    latency_percentile: float | None = typer.Option(
        None,
        "--latency-percentile",
        help=(
            "Latency budget as a percentile of each operation's own traffic "
            "(e.g. 95). Self-calibrating alternative to --latency-ms."
        ),
    ),
    cost_usd: float | None = typer.Option(
        None,
        "--cost-usd",
        help="Fixed cost budget in USD; pricier observations become 'costly'.",
    ),
    cost_percentile: float | None = typer.Option(
        None,
        "--cost-percentile",
        help="Cost budget as a percentile of each operation's own traffic.",
    ),
    group_by: str | None = typer.Option(
        None,
        "--group-by",
        help=(
            "Group on a stable field instead of the error message, e.g. "
            "'metadata.error_code'. Use when your messages don't group well."
        ),
    ),
    discover: bool = typer.Option(
        False,
        "--discover",
        help="Report this project's score names, latency/cost spread, and error labels. Writes nothing.",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Store the supplied capture settings for this Langfuse project.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the grouping and the write/update plan without writing.",
    ),
):
    """Sync Langfuse observability signal into the active (or selected) agent.

    Errors, failed evals, and latency/cost anomalies become memories, grouped
    into one memory per *signature* rather than one per occurrence, so a
    thousand identical failures become a single memory whose confidence
    reflects how often it happened.

    Only ``errors`` works out of the box — it is the one signal every Langfuse
    project records identically. Score names, their ranges, and what counts as
    slow or expensive are all project-specific, so those modes stay inert (and
    say so) until you supply a rule or a budget. Start with ``--discover``.

    Settings are stored per Langfuse project in
    ``~/.memanto/migrate/langfuse/config.json`` when you pass ``--save``, and
    the sync ledger beside it is keyed by project *and* target agent, so
    re-running updates existing memories instead of duplicating them.

    Examples:
        memanto migrate langfuse --discover
        memanto migrate langfuse --capture errors,slow --latency-percentile 95 --save
        memanto migrate langfuse --score-fail 'correctness<0.7' --capture low-score
        memanto migrate langfuse --group-by metadata.error_code --dry-run
    """
    base_dir = config_manager.get_migrate_dir("langfuse")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    def progress(msg: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {msg}")

    resolved_host = normalize_host(host or config_manager.get_langfuse_host())
    credential = None
    if file is None:
        credential = _resolve_provider_key("langfuse", api_key)
        if host:
            config_manager.set_langfuse_host(resolved_host)

    key = langfuse_config.project_key(api_key=credential)
    project = _resolve_langfuse_config(
        base_dir=base_dir,
        key=key,
        capture=capture,
        score_fail=score_fail,
        score_pass=score_pass,
        latency_ms=latency_ms,
        latency_percentile=latency_percentile,
        cost_usd=cost_usd,
        cost_percentile=cost_percentile,
        group_by=group_by,
        save=save,
    )
    capture_config = CaptureConfig.from_project(project)

    # ---- Discovery: look, report, write nothing. -------------------------
    if discover:
        if file is not None:
            try:
                export = load_export(file)
            except Exception as exc:
                _error(f"Failed to load Langfuse export: {exc}")
        else:
            progress(f"Sampling {resolved_host}...")
            try:
                _, export = run_langfuse_export(
                    cast(str, credential),
                    run_dir,
                    host=resolved_host,
                    since=(
                        datetime.now(timezone.utc) - timedelta(days=since_days)
                        if since_days
                        else None
                    ),
                    discover=True,
                    on_progress=progress,
                )
            except ValueError as exc:
                _error(str(exc))
            except Exception as exc:
                _error(f"Langfuse discovery failed: {exc}")
        _render_discovery(langfuse_discover.discover(export))
        return

    # A dry run must reconcile against the ledger of the agent it would
    # actually write to, or it reports every already-synced signature as new.
    # It still must not *require* an agent, so resolution is best-effort here.
    if dry_run:
        target_agent = (agent or "").strip() or config_manager.get_active_session()[0]
    else:
        target_agent = _resolve_target_agent(agent)

    ledger_path = langfuse_state.state_path(base_dir)
    scope = langfuse_state.scope_key(key, target_agent or "unknown-agent")
    state = langfuse_state.load_state(ledger_path, scope)

    modes = project.capture
    mode_label = "Dry run" if dry_run else "Sync"
    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Langfuse -> Memanto  {mode_label}[/{BOLD_PRIMARY}]\n"
            f"[dim]Capturing: {', '.join(sorted(m.replace('_', '-') for m in modes))}[/dim]",
            border_style=PRIMARY,
        )
    )

    # Window: an explicit --since-days wins, else resume from the last sync.
    previous_sync = langfuse_state.last_synced_at(state)
    since: datetime | None
    if since_days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
    else:
        since = previous_sync

    if file is not None:
        progress(f"Loading export from {file}")
        try:
            export = load_export(file)
        except Exception as exc:
            _error(f"Failed to load Langfuse export: {exc}")
    else:
        window = (
            f"since {since.isoformat()}"
            if since
            else f"last {DEFAULT_WINDOW_DAYS} days"
        )
        progress(f"Pulling from {resolved_host} ({window})")
        try:
            _, export = run_langfuse_export(
                cast(str, credential),
                run_dir,
                host=resolved_host,
                since=since,
                capture=set(modes),
                config=capture_config,
                on_progress=progress,
            )
        except ValueError as exc:
            _error(str(exc))
        except Exception as exc:
            _error(f"Langfuse export failed: {exc}")

    progress("Grouping observations into signatures...")
    summary, rows, _plan = run_langfuse_sync(
        export=export,
        client=None if dry_run else get_client(),
        agent_id=cast(str, target_agent or ""),
        state=state,
        dry_run=dry_run,
        # Explicit so a --file replay honours these settings rather than
        # whatever the saved export happened to be pulled with.
        config=capture_config,
        on_progress=progress,
    )
    preview_path = write_preview(rows, run_dir / "mapped_preview.json")

    if not dry_run:
        # Saved even when nothing changed, so the cursor still advances — but
        # not past a failure, or the next run's window would skip observations
        # that were never stored.
        langfuse_state.save_state(
            ledger_path, state, scope, advance_cursor=summary.failed == 0
        )

    type_lines = (
        ", ".join(f"{k}: {v}" for k, v in sorted(summary.type_counts.items())) or "—"
    )

    body_lines = [
        f"[dim]Observations pulled:[/dim] {summary.observation_count}",
        f"[dim]Distinct signatures:[/dim] {summary.signature_count}",
        f"[dim]Type breakdown:[/dim] {type_lines}",
        "",
        f"[dim]New:[/dim] {summary.new}  "
        f"[dim]Changed:[/dim] {summary.changed}  "
        f"[dim]Unchanged:[/dim] {summary.unchanged}",
    ]
    if dry_run:
        body_lines.append("")
        body_lines.append("[yellow]Dry run — no writes performed.[/yellow]")
        body_lines.append(
            f"[dim]Would target agent:[/dim] {target_agent or '(none active)'}"
        )
    else:
        body_lines.append(
            f"[dim]Imported:[/dim] {summary.imported}  "
            f"[dim]Updated:[/dim] {summary.updated}  "
            f"[dim]Failed:[/dim] {summary.failed}"
        )
        body_lines.append(f"[dim]Target agent:[/dim] {target_agent}")

    body_lines.append("")
    body_lines.append(f"[dim]Run dir:[/dim] {run_dir}")
    body_lines.append(f"[dim]Mapped preview:[/dim] {preview_path}")
    body_lines.append(f"[dim]Sync ledger:[/dim] {ledger_path}  [dim]({scope})[/dim]")
    if previous_sync:
        body_lines.append(f"[dim]Previous sync:[/dim] {previous_sync.isoformat()}")
    for warning in summary.warnings:
        body_lines.append(f"[yellow]![/yellow] {warning}")
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
                else "[bold green]Sync complete[/bold green]"
            ),
            border_style=border,
        )
    )
