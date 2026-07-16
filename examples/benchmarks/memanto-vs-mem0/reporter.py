"""
Results reporter.

Renders the BenchmarkResult as:
  - A rich terminal table (via the `rich` library)
  - A JSON results file saved to results/
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from harness import BenchmarkResult, SystemResult

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"


def _fmt(val: float, decimals: int = 2) -> str:
    return f"{val:.{decimals}f}"


def print_report(result: BenchmarkResult) -> None:
    """Print a formatted benchmark report to the terminal."""
    try:
        import importlib.util

        _rich = importlib.util.find_spec("rich") is not None
    except ImportError:
        _rich = False

    systems = list(result.systems.values())
    names = [s.system for s in systems]

    print("\n")
    print("=" * 70)
    print(f"  BENCHMARK RESULTS — {result.scenario_title}")
    print(f"  Run: {result.run_timestamp}   Judge: {result.judge_model}")
    print("=" * 70)

    if _rich:
        _print_rich(result, systems, names)
    else:
        _print_plain(result, systems, names)

    # ── Winner ────────────────────────────────────────────────────────────
    if all(len(s.eval_scores) > 0 for s in systems):
        winner = result.winner()
        print(f"\n🏆  Winner (by total eval score): {winner}\n")


def _print_rich(
    result: BenchmarkResult,
    systems: list[SystemResult],
    names: list[str],
) -> None:
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # ── Metric summary table ──────────────────────────────────────────────
    t = Table(title="Performance Metrics", box=box.ROUNDED, show_lines=True)
    t.add_column("Metric", style="bold")
    for name in names:
        t.add_column(name, justify="right")

    rows = []
    for s in systems:
        rows.append(str(s.total_tokens_ingested))
    t.add_row("Tokens ingested", *rows)

    rows = []
    for s in systems:
        rows.append(str(s.total_tokens_recalled))
    t.add_row("Tokens recalled", *rows)

    rows = []
    for s in systems:
        rows.append(str(s.total_tokens))
    t.add_row("Total tokens", *[f"[bold]{r}[/bold]" for r in rows])

    rows = []
    for s in systems:
        rows.append(_fmt(s.p95_ingest_latency) + "s")
    t.add_row("p95 ingest latency", *rows)

    rows = []
    for s in systems:
        rows.append(_fmt(s.p95_recall_latency) + "s")
    t.add_row("p95 recall latency", *rows)

    rows = []
    for s in systems:
        rows.append(_fmt(s.mean_recall_latency) + "s")
    t.add_row("Mean recall latency", *rows)

    console.print(t)

    # ── Accuracy table ────────────────────────────────────────────────────
    if all(len(s.eval_scores) > 0 for s in systems):
        a = Table(
            title="Retrieval Accuracy (LLM Judge — max 15 per query)",
            box=box.ROUNDED,
            show_lines=True,
        )
        a.add_column("Query", style="bold", width=35)
        a.add_column("Type", width=24)
        for name in names:
            a.add_column(f"{name}\n(acc/stale/prec)", justify="center")

        # Collect scores per query_id per system
        scores_by_qid: dict[str, dict[str, object]] = {}
        for s in systems:
            for sc in s.eval_scores:
                if sc.query_id not in scores_by_qid:
                    scores_by_qid[sc.query_id] = {}
                scores_by_qid[sc.query_id][s.system] = sc

        # Load query metadata
        import json as _json

        data_path = Path(__file__).parent / "data" / "executive_shadow.json"
        with open(data_path) as f:
            scenario = _json.load(f)
        qmeta = {eq["id"]: eq for eq in scenario["evaluation_queries"]}

        for qid, by_sys in scores_by_qid.items():
            qm = qmeta.get(qid, {})
            label = qm.get("query", qid)[:34]
            test_type = qm.get("tests", "")
            row = [label, test_type]
            for name in names:
                sc = by_sys.get(name)
                if sc:
                    row.append(
                        f"{sc.accuracy}/{sc.staleness_avoidance}/{sc.precision} = [bold]{sc.total}[/bold]"
                    )
                else:
                    row.append("—")
            a.add_row(*row)

        # Totals row
        totals = []
        for s in systems:
            totals.append(
                f"[bold green]{s.total_eval_score}/{s.max_possible_eval_score} "
                f"({s.eval_score_pct:.0f}%)[/bold green]"
            )
        a.add_row("[bold]TOTAL[/bold]", "", *totals)

        console.print(a)


def _print_plain(
    result: BenchmarkResult,
    systems: list[SystemResult],
    names: list[str],
) -> None:
    """Fallback plain-text output when rich is not installed."""
    col_w = 22
    header = f"{'Metric':<32}" + "".join(f"{n:>{col_w}}" for n in names)
    print(header)
    print("-" * len(header))

    def row(label: str, vals: list[str]) -> None:
        print(f"{label:<32}" + "".join(f"{v:>{col_w}}" for v in vals))

    row("Tokens ingested", [str(s.total_tokens_ingested) for s in systems])
    row("Tokens recalled", [str(s.total_tokens_recalled) for s in systems])
    row("Total tokens", [str(s.total_tokens) for s in systems])
    row("p95 ingest latency", [_fmt(s.p95_ingest_latency) + "s" for s in systems])
    row("p95 recall latency", [_fmt(s.p95_recall_latency) + "s" for s in systems])
    row("Mean recall latency", [_fmt(s.mean_recall_latency) + "s" for s in systems])

    if all(len(s.eval_scores) > 0 for s in systems):
        print()
        row("Accuracy score", [str(s.total_accuracy_score) for s in systems])
        row("Staleness score", [str(s.total_staleness_score) for s in systems])
        row("Precision score", [str(s.total_precision_score) for s in systems])
        row(
            "Total eval score",
            [f"{s.total_eval_score}/{s.max_possible_eval_score}" for s in systems],
        )
        row("Eval score %", [f"{s.eval_score_pct:.1f}%" for s in systems])


def save_results(result: BenchmarkResult) -> Path:
    """Save the full results as a JSON file and return the path."""
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = result.run_timestamp.replace(":", "-").replace("T", "_").replace("Z", "")
    path = RESULTS_DIR / f"benchmark_{ts}.json"

    # Serialise dataclasses
    def _serialise(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: _serialise(v) for k, v in asdict(obj).items()}
        if isinstance(obj, (list, tuple)):
            return [_serialise(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _serialise(v) for k, v in obj.items()}
        return obj

    data = {
        "scenario_title": result.scenario_title,
        "run_timestamp": result.run_timestamp,
        "judge_model": result.judge_model,
        "metadata": result.metadata,
        "systems": {
            name: {
                "metrics": {
                    "total_tokens_ingested": sr.total_tokens_ingested,
                    "total_tokens_recalled": sr.total_tokens_recalled,
                    "total_tokens": sr.total_tokens,
                    "p95_ingest_latency_s": round(sr.p95_ingest_latency, 4),
                    "p95_recall_latency_s": round(sr.p95_recall_latency, 4),
                    "mean_recall_latency_s": round(sr.mean_recall_latency, 4),
                    "total_eval_score": sr.total_eval_score,
                    "max_possible_eval_score": sr.max_possible_eval_score,
                    "eval_score_pct": round(sr.eval_score_pct, 1),
                },
                "ingest_results": _serialise(sr.ingest_results),
                "recall_results": _serialise(sr.recall_results),
                "eval_scores": _serialise(sr.eval_scores),
            }
            for name, sr in result.systems.items()
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info("Results saved to %s", path)
    return path
