"""
MEMANTO CLI - Analyze external memory providers (export, compare, report).
"""

from datetime import datetime, timezone

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
    _error,
    _warn,
    analyze_app,
    config_manager,
    console,
    get_client,
)


def _resolve_supermemory_api_key(api_key: str | None) -> str:
    if api_key and api_key.strip():
        config_manager.set_supermemory_api_key(api_key.strip())
        resolved = config_manager.get_supermemory_api_key()
        if resolved:
            return resolved

    stored = config_manager.get_supermemory_api_key()
    if stored:
        return stored

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Supermemory API key[/{BOLD_PRIMARY}]\n"
            "[dim]Get yours at https://supermemory.ai/docs[/dim]",
            border_style=PRIMARY,
        )
    )
    entered = typer.prompt("  Enter your Supermemory API key", hide_input=True)
    if not entered or not entered.strip():
        _error(
            "Supermemory API key is required.",
            hint="Pass --api-key or set SUPERMEMORY_API_KEY in ~/.memanto/.env",
        )

    config_manager.set_supermemory_api_key(entered.strip())
    console.print("[green]  ✓ API key saved to ~/.memanto/.env[/green]")
    resolved = config_manager.get_supermemory_api_key()
    if not resolved:
        _error("Failed to save Supermemory API key.")
    return resolved


def _generate_narrative(prompt: str, *, provider: str) -> tuple[str, str, str]:
    """
    Generate the comparison narrative with Memanto's own LLM (Moorcheh answer).

    Returns (narrative_text, llm_model, llm_method). On any failure, returns an
    empty narrative so the deterministic report is still written.
    """
    method = (
        "Moorcheh 'answer' endpoint over the active agent's namespace; "
        "memory retrieval suppressed (top_k=1, high threshold) so the model "
        "writes purely from the supplied metrics."
    )
    active_agent_id, _ = config_manager.get_active_session()
    if not active_agent_id:
        _warn(
            "No active agent — skipping LLM narrative. "
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
                    "brief. "
                    f"Use present tense for the user's current {provider} footprint; "
                    "use future or conditional tense (can/would/could) for Memanto "
                    "benefits. Output clean markdown. Do not fabricate benchmark "
                    "numbers."
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

    if "session" in last_error.lower() or "token" in last_error.lower():
        _warn(
            f"LLM narrative skipped: {last_error}. "
            "Run 'memanto agent activate <agent-id>' and retry."
        )
        return "", "unavailable (session invalid)", method

    _warn(f"LLM narrative generation failed: {last_error}")
    return "", "unavailable (generation failed)", method


def _resolve_mem0_api_key(api_key: str | None) -> str:
    if api_key and api_key.strip():
        config_manager.set_mem0_api_key(api_key.strip())
        resolved = config_manager.get_mem0_api_key()
        if resolved:
            return resolved

    stored = config_manager.get_mem0_api_key()
    if stored:
        return stored

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Mem0 API key[/{BOLD_PRIMARY}]\n"
            "[dim]Get yours at https://app.mem0.ai[/dim]",
            border_style=PRIMARY,
        )
    )
    entered = typer.prompt("  Enter your Mem0 API key", hide_input=True)
    if not entered or not entered.strip():
        _error(
            "Mem0 API key is required.",
            hint="Pass --api-key or set MEM0_API_KEY in ~/.memanto/.env",
        )

    config_manager.set_mem0_api_key(entered.strip())
    console.print("[green]  ✓ API key saved to ~/.memanto/.env[/green]")
    resolved = config_manager.get_mem0_api_key()
    if not resolved:
        _error("Failed to save Mem0 API key.")
    return resolved


def _resolve_letta_api_key(api_key: str | None) -> str:
    if api_key and api_key.strip():
        config_manager.set_letta_api_key(api_key.strip())
        resolved = config_manager.get_letta_api_key()
        if resolved:
            return resolved

    stored = config_manager.get_letta_api_key()
    if stored:
        return stored

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Letta API key[/{BOLD_PRIMARY}]\n"
            "[dim]Get yours at https://docs.letta.com[/dim]",
            border_style=PRIMARY,
        )
    )
    entered = typer.prompt("  Enter your Letta API key", hide_input=True)
    if not entered or not entered.strip():
        _error(
            "Letta API key is required.",
            hint="Pass --api-key or set LETTA_API_KEY in ~/.memanto/.env",
        )

    config_manager.set_letta_api_key(entered.strip())
    console.print("[green]  ✓ API key saved to ~/.memanto/.env[/green]")
    resolved = config_manager.get_letta_api_key()
    if not resolved:
        _error("Failed to save Letta API key.")
    return resolved


@analyze_app.command("supermemory")
def analyze_supermemory(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="SUPERMEMORY_API_KEY",
        help="Supermemory API key (saved to ~/.memanto/.env)",
    ),
):
    """Analyze a Supermemory account and compare it against Memanto.

    Exports all Supermemory data, computes deterministic savings metrics from
    your real data, generates an LLM comparison narrative, and writes a report.

    Output is saved to:
        ~/.memanto/analyze/supermemory/<timestamp>/
            supermemory_export.json
            analyze-report.md

    The Supermemory key is stored in ~/.memanto/.env. The narrative uses your
    active Memanto agent's LLM (run 'memanto agent activate <id>' first).

    Examples:
        memanto analyze supermemory
        memanto analyze supermemory --api-key sm_...
    """
    key = _resolve_supermemory_api_key(api_key)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = config_manager.get_analyze_dir("supermemory") / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Supermemory analyze[/{BOLD_PRIMARY}]\n"
            "Exporting account data and comparing against Memanto...",
            border_style=PRIMARY,
        )
    )

    def on_progress(message: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {message}")

    try:
        export_path, export = run_supermemory_export(
            key,
            run_dir,
            on_progress=on_progress,
        )
    except ImportError as exc:
        _error(str(exc))
    except Exception as exc:
        _error(f"Supermemory export failed: {exc}")

    on_progress("Computing comparison metrics...")
    metrics = compute_supermemory_metrics(export)

    on_progress("Generating comparison narrative...")
    narrative, llm_model, llm_method = _generate_narrative(
        build_supermemory_llm_prompt(metrics),
        provider="Supermemory",
    )

    report_md = build_supermemory_report_markdown(
        metrics=metrics,
        narrative=narrative,
        export_path=str(export_path),
        llm_model=llm_model,
        llm_method=llm_method,
        exported_at=export.get("exported_at"),
    )
    report_path = run_dir / "analyze-report.md"
    report_path.write_text(report_md, encoding="utf-8")

    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]

    console.print()
    console.print(
        Panel(
            f"[bold green]Analysis complete[/bold green]\n\n"
            f"[dim]Report:[/dim] {report_path}\n"
            f"[dim]Export:[/dim] {export_path}\n\n"
            f"[dim]Documents:[/dim] {v['documents']}  "
            f"[dim]Chunks:[/dim] {v['chunks']}  "
            f"[dim]Memories:[/dim] {v['memories']}\n"
            f"[dim]Could save at ingest:[/dim] ~{t['tokens_saved']:,} tokens "
            f"(~${t['supermemory_extraction_cost_usd']})\n"
            f"[dim]Could free storage:[/dim] {s['saved_human']} "
            f"(~{s['compression_ratio']}x smaller)\n"
            f"[dim]Read latency (projected):[/dim] ~{lat['supermemory_read_ms']}ms → "
            f"<{lat['memanto_read_ms']}ms (~{lat['speedup_x']}x faster)",
            border_style=SUCCESS,
        )
    )


@analyze_app.command("mem0")
def analyze_mem0(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="MEM0_API_KEY",
        help="Mem0 API key (saved to ~/.memanto/.env)",
    ),
):
    """Analyze a Mem0 account and compare it against Memanto.

    Exports all Mem0 entities and memories, computes deterministic savings
    metrics from your real data, generates an LLM comparison narrative, and
    writes a report.

    Output is saved to:
        ~/.memanto/analyze/mem0/<timestamp>/
            mem0_export.json
            analyze-report.md

    The Mem0 key is stored in ~/.memanto/.env. The narrative uses your active
    Memanto agent's LLM (run 'memanto agent activate <id>' first).

    Examples:
        memanto analyze mem0
        memanto analyze mem0 --api-key m0_...
    """
    key = _resolve_mem0_api_key(api_key)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = config_manager.get_analyze_dir("mem0") / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Mem0 analyze[/{BOLD_PRIMARY}]\n"
            "Exporting account data and comparing against Memanto...",
            border_style=PRIMARY,
        )
    )

    def on_progress(message: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {message}")

    try:
        export_path, export = run_mem0_export(
            key,
            run_dir,
            on_progress=on_progress,
        )
    except ImportError as exc:
        _error(str(exc))
    except Exception as exc:
        _error(f"Mem0 export failed: {exc}")

    on_progress("Computing comparison metrics...")
    metrics = compute_mem0_metrics(export)

    on_progress("Generating comparison narrative...")
    narrative, llm_model, llm_method = _generate_narrative(
        build_mem0_llm_prompt(metrics),
        provider="Mem0",
    )

    report_md = build_mem0_report_markdown(
        metrics=metrics,
        narrative=narrative,
        export_path=str(export_path),
        llm_model=llm_model,
        llm_method=llm_method,
        exported_at=export.get("exported_at"),
    )
    report_path = run_dir / "analyze-report.md"
    report_path.write_text(report_md, encoding="utf-8")

    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]

    console.print()
    console.print(
        Panel(
            f"[bold green]Analysis complete[/bold green]\n\n"
            f"[dim]Report:[/dim] {report_path}\n"
            f"[dim]Export:[/dim] {export_path}\n\n"
            f"[dim]Entities:[/dim] {v['entities']}  "
            f"[dim]Memories:[/dim] {v['memories']}\n"
            f"[dim]Could save at ingest:[/dim] ~{t['tokens_saved']:,} tokens "
            f"(~${t['mem0_extraction_cost_usd']})\n"
            f"[dim]Could free storage:[/dim] {s['saved_human']} "
            f"(~{s['compression_ratio']}x smaller)\n"
            f"[dim]Read latency (projected):[/dim] ~{lat['mem0_read_ms']}ms → "
            f"<{lat['memanto_read_ms']}ms (~{lat['speedup_x']}x faster)",
            border_style=SUCCESS,
        )
    )


@analyze_app.command("letta")
def analyze_letta(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="LETTA_API_KEY",
        help="Letta API key (saved to ~/.memanto/.env)",
    ),
):
    """Analyze your Letta account and compare it against Memanto.

    Lists every agent in the account, exports archival passages from each,
    computes deterministic savings metrics from your real data, generates an
    LLM comparison narrative, and writes a report.

    Output is saved to:
        ~/.memanto/analyze/letta/<timestamp>/
            letta_export.json
            analyze-report.md

    The Letta key is stored in ~/.memanto/.env. The narrative uses your active
    Memanto agent's LLM (run 'memanto agent activate <id>' first).

    Examples:
        memanto analyze letta
        memanto analyze letta --api-key sk-let-...
    """
    key = _resolve_letta_api_key(api_key)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = config_manager.get_analyze_dir("letta") / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Letta analyze[/{BOLD_PRIMARY}]\n"
            "Exporting archival memory and comparing against Memanto...",
            border_style=PRIMARY,
        )
    )

    def on_progress(message: str) -> None:
        console.print(f"  [{BRIGHT}]…[/{BRIGHT}] {message}")

    try:
        export_path, export = run_letta_export(
            key,
            run_dir,
            on_progress=on_progress,
        )
    except ImportError as exc:
        _error(str(exc))
    except ValueError as exc:
        _error(str(exc))
    except Exception as exc:
        _error(f"Letta export failed: {exc}")

    on_progress("Computing comparison metrics...")
    metrics = compute_letta_metrics(export)

    on_progress("Generating comparison narrative...")
    narrative, llm_model, llm_method = _generate_narrative(
        build_letta_llm_prompt(metrics),
        provider="Letta",
    )

    report_md = build_letta_report_markdown(
        metrics=metrics,
        narrative=narrative,
        export_path=str(export_path),
        llm_model=llm_model,
        llm_method=llm_method,
        exported_at=export.get("exported_at"),
    )
    report_path = run_dir / "analyze-report.md"
    report_path.write_text(report_md, encoding="utf-8")

    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]
    console.print()
    console.print(
        Panel(
            f"[bold green]Analysis complete[/bold green]\n\n"
            f"[dim]Report:[/dim] {report_path}\n"
            f"[dim]Export:[/dim] {export_path}\n\n"
            f"[dim]Agents:[/dim] {v['agents']}  "
            f"[dim]Passages:[/dim] {v['passages']}\n"
            f"[dim]Could save at ingest:[/dim] ~{t['tokens_saved']:,} tokens "
            f"(~${t['letta_extraction_cost_usd']})\n"
            f"[dim]Could free storage:[/dim] {s['saved_human']} "
            f"(~{s['compression_ratio']}x smaller)\n"
            f"[dim]Read latency (projected):[/dim] ~{lat['letta_read_ms']}ms → "
            f"<{lat['memanto_read_ms']}ms (~{lat['speedup_x']}x faster)",
            border_style=SUCCESS,
        )
    )
