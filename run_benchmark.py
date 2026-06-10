#!/usr/bin/env python3
"""
The Great Agentic Memory Showdown — Main Benchmark Runner

Compares Memanto vs Mem0 across two scenarios:
  A) Context-Overhead & Latency Sprint (technical logs)
  B) Shifting Persona & Temporal Tracking (evolving preferences)

Usage:
    python run_benchmark.py                 # Full benchmark (requires API keys)
    python run_benchmark.py --dry-run       # Dry run with mock data (no API keys needed)
    python run_benchmark.py --scenario a    # Run only Scenario A
    python run_benchmark.py --scenario b    # Run only Scenario B
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from benchmarks.base import BenchmarkMetric
from benchmarks.memanto_adapter import MemantoAdapter
from benchmarks.mem0_adapter import Mem0Adapter
from benchmarks.evaluator import LLMEvaluator
from benchmarks.scenario_a import run_scenario_a
from benchmarks.scenario_b import run_scenario_b


REPORTS_DIR = Path(__file__).parent / "reports"


def run_benchmark(
    scenario: str = "all",
    num_runs: int = 3,
    dry_run: bool = False,
) -> list[dict]:
    """Run the full benchmark suite.

    Args:
        scenario: "a", "b", or "all"
        num_runs: Number of runs per scenario for statistical aggregation
        dry_run: If True, use mock data

    Returns:
        List of result dicts for all runs.
    """
    evaluator = LLMEvaluator()
    adapters = [MemantoAdapter(), Mem0Adapter()]

    scenarios = []
    if scenario in ("a", "all"):
        scenarios.append(("a", run_scenario_a))
    if scenario in ("b", "all"):
        scenarios.append(("b", run_scenario_b))

    all_results = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for run_idx in range(num_runs):
        for scenario_key, run_fn in scenarios:
            for adapter in adapters:
                user_id = f"bench_{adapter.name}_{scenario_key}_run{run_idx}"
                print(
                    f"  [{run_idx+1}/{num_runs}] {adapter.name} — "
                    f"Scenario {scenario_key.upper()}...",
                    end=" ",
                    flush=True,
                )

                start = time.perf_counter()
                try:
                    metrics = run_fn(adapter, evaluator, user_id, dry_run=dry_run)
                    elapsed = time.perf_counter() - start
                    print(f"✓ ({elapsed:.1f}s)")
                except Exception as e:
                    print(f"✗ Error: {e}")
                    metrics = BenchmarkMetric(
                        framework=adapter.name,
                        scenario=f"{scenario_key}: Error",
                    )
                    metrics.errors += 1

                result = metrics.to_dict()
                result["run_index"] = run_idx
                result["timestamp"] = timestamp
                all_results.append(result)

    return all_results


def generate_console_report(results: list[dict]) -> None:
    """Print a comparison table to the console."""
    from tabulate import tabulate

    # Group by scenario, aggregate across runs
    aggregated = {}
    for r in results:
        key = (r["framework"], r["scenario"])
        if key not in aggregated:
            aggregated[key] = {
                "framework": r["framework"],
                "scenario": r["scenario"],
                "store_tokens": [],
                "retrieve_tokens": [],
                "store_p95": [],
                "retrieve_p95": [],
                "accuracy": [],
                "errors": [],
            }
        agg = aggregated[key]
        agg["store_tokens"].append(r["total_store_tokens"])
        agg["retrieve_tokens"].append(r["total_retrieve_tokens"])
        agg["store_p95"].append(r["store_p95_latency_ms"])
        agg["retrieve_p95"].append(r["retrieve_p95_latency_ms"])
        agg["accuracy"].append(r["retrieval_accuracy"])
        agg["errors"].append(r["errors"])

    import numpy as np

    table = []
    for key, agg in aggregated.items():
        table.append([
            agg["framework"],
            agg["scenario"],
            f"{int(np.mean(agg['store_tokens'])):,}",
            f"{int(np.mean(agg['retrieve_tokens'])):,}",
            f"{np.mean(agg['store_p95']):.1f}",
            f"{np.mean(agg['retrieve_p95']):.1f}",
            f"{np.mean(agg['accuracy']):.3f}",
            sum(agg["errors"]),
        ])

    headers = [
        "Framework", "Scenario", "Store Tokens", "Retrieve Tokens",
        "Store p95 (ms)", "Retrieve p95 (ms)", "Accuracy", "Errors",
    ]
    print("\n" + "=" * 100)
    print("  THE GREAT AGENTIC MEMORY SHOWDOWN — BENCHMARK RESULTS")
    print("=" * 100)
    print(tabulate(table, headers=headers, tablefmt="grid"))
    print()


def generate_json_report(results: list[dict], output_path: Path) -> None:
    """Save results to JSON."""
    report = {
        "title": "The Great Agentic Memory Showdown — Benchmark Results",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version,
            "platform": sys.platform,
            "judge_model": os.environ.get("JUDGE_MODEL", "gpt-4o"),
            "benchmark_runs": len(set(r["run_index"] for r in results)),
        },
        "results": results,
    }
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"JSON report saved: {output_path}")


def generate_html_report(results: list[dict], output_path: Path) -> None:
    """Generate an HTML report with embedded charts."""
    from jinja2 import Template

    template = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
  h1 { color: #333; } h2 { color: #555; margin-top: 40px; }
  .card { background: white; border-radius: 8px; padding: 20px; margin: 16px 0;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #f8f9fa; font-weight: 600; }
  .chart-container { width: 100%; max-width: 700px; margin: 20px auto; }
  .highlight { color: #2563eb; font-weight: bold; }
  .meta { color: #888; font-size: 0.9em; }
</style>
</head>
<body>
<h1>🐜 The Great Agentic Memory Showdown</h1>
<p class="meta">Generated: {{ generated_at }} | Judge Model: {{ judge_model }}</p>

<h2>📊 Results Summary</h2>
<div class="card">
<table>
<tr><th>Framework</th><th>Scenario</th><th>Store Tokens</th><th>Retrieve Tokens</th>
    <th>Store p95 (ms)</th><th>Retrieve p95 (ms)</th><th>Accuracy</th><th>Errors</th></tr>
{% for r in summary %}
<tr><td>{{ r.framework }}</td><td>{{ r.scenario }}</td>
    <td>{{ r.store_tokens }}</td><td>{{ r.retrieve_tokens }}</td>
    <td>{{ r.store_p95 }}</td><td>{{ r.retrieve_p95 }}</td>
    <td class="highlight">{{ r.accuracy }}</td><td>{{ r.errors }}</td></tr>
{% endfor %}
</table>
</div>

<h2>📈 Token Efficiency</h2>
<div class="card chart-container">
<canvas id="tokenChart"></canvas>
</div>

<h2>⏱️ Latency (p95)</h2>
<div class="card chart-container">
<canvas id="latencyChart"></canvas>
</div>

<h2>🎯 Retrieval Accuracy</h2>
<div class="card chart-container">
<canvas id="accuracyChart"></canvas>
</div>

<script>
const labels = {{ labels | tojson }};
const storeTokens = {{ store_tokens | tojson }};
const retrieveTokens = {{ retrieve_tokens | tojson }};
const storeP95 = {{ store_p95 | tojson }};
const retrieveP95 = {{ retrieve_p95 | tojson }};
const accuracy = {{ accuracy | tojson }};

new Chart(document.getElementById('tokenChart'), {
  type: 'bar', data: {
    labels: labels,
    datasets: [
      {label: 'Store Tokens', data: storeTokens, backgroundColor: '#3b82f6'},
      {label: 'Retrieve Tokens', data: retrieveTokens, backgroundColor: '#10b981'}
    ]
  }, options: {responsive: true, plugins: {title: {display: true, text: 'Total Tokens Used'}}}
});

new Chart(document.getElementById('latencyChart'), {
  type: 'bar', data: {
    labels: labels,
    datasets: [
      {label: 'Store p95 (ms)', data: storeP95, backgroundColor: '#f59e0b'},
      {label: 'Retrieve p95 (ms)', data: retrieveP95, backgroundColor: '#ef4444'}
    ]
  }, options: {responsive: true, plugins: {title: {display: true, text: 'p95 Latency (ms)'}}}
});

new Chart(document.getElementById('accuracyChart'), {
  type: 'bar', data: {
    labels: labels,
    datasets: [{label: 'Retrieval Accuracy', data: accuracy, backgroundColor: '#8b5cf6'}]
  }, options: {responsive: true, scales: {y: {min: 0, max: 1}},
    plugins: {title: {display: true, text: 'Retrieval Accuracy (0-1)'}}}
});
</script>
</body></html>""")

    # Aggregate results
    import numpy as np
    aggregated = {}
    for r in results:
        key = (r["framework"], r["scenario"])
        if key not in aggregated:
            aggregated[key] = {"store_t": [], "retrieve_t": [], "store_p": [],
                               "retrieve_p": [], "acc": [], "err": []}
        a = aggregated[key]
        a["store_t"].append(r["total_store_tokens"])
        a["retrieve_t"].append(r["total_retrieve_tokens"])
        a["store_p"].append(r["store_p95_latency_ms"])
        a["retrieve_p"].append(r["retrieve_p95_latency_ms"])
        a["acc"].append(r["retrieval_accuracy"])
        a["err"].append(r["errors"])

    summary = []
    labels = []
    store_tokens = []
    retrieve_tokens = []
    store_p95 = []
    retrieve_p95 = []
    accuracy = []

    for (fw, sc), a in aggregated.items():
        label = f"{fw} — {sc[:20]}"
        labels.append(label)
        st = int(np.mean(a["store_t"]))
        rt = int(np.mean(a["retrieve_t"]))
        sp = round(np.mean(a["store_p"]), 1)
        rp = round(np.mean(a["retrieve_p"]), 1)
        ac = round(np.mean(a["acc"]), 3)
        er = sum(a["err"])
        store_tokens.append(st)
        retrieve_tokens.append(rt)
        store_p95.append(sp)
        retrieve_p95.append(rp)
        accuracy.append(ac)
        summary.append({
            "framework": fw, "scenario": sc,
            "store_tokens": f"{st:,}", "retrieve_tokens": f"{rt:,}",
            "store_p95": str(sp), "retrieve_p95": str(rp),
            "accuracy": str(ac), "errors": er,
        })

    html = template.render(
        title="The Great Agentic Memory Showdown",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        judge_model=os.environ.get("JUDGE_MODEL", "gpt-4o"),
        summary=summary, labels=labels, store_tokens=store_tokens,
        retrieve_tokens=retrieve_tokens, store_p95=store_p95,
        retrieve_p95=retrieve_p95, accuracy=accuracy,
    )
    with open(output_path, "w") as f:
        f.write(html)
    print(f"HTML report saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="The Great Agentic Memory Showdown — Benchmark Runner"
    )
    parser.add_argument(
        "--scenario", choices=["a", "b", "all"], default="all",
        help="Which scenario to run (default: all)",
    )
    parser.add_argument(
        "--runs", type=int, default=3,
        help="Number of runs per scenario (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run with mock data (no API keys needed)",
    )
    args = parser.parse_args()

    load_dotenv()

    print("=" * 60)
    print("  🐜 THE GREAT AGENTIC MEMORY SHOWDOWN")
    print("=" * 60)
    print(f"  Scenario: {args.scenario.upper()}")
    print(f"  Runs: {args.runs}")
    print(f"  Dry Run: {args.dry_run}")
    print(f"  Judge Model: {os.environ.get('JUDGE_MODEL', 'gpt-4o')}")
    print()

    REPORTS_DIR.mkdir(exist_ok=True)

    results = run_benchmark(
        scenario=args.scenario,
        num_runs=args.runs,
        dry_run=args.dry_run,
    )

    generate_console_report(results)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_DIR / f"benchmark_results_{timestamp}.json"
    html_path = REPORTS_DIR / f"benchmark_report_{timestamp}.html"

    generate_json_report(results, json_path)
    generate_html_report(results, html_path)

    print("\n✅ Benchmark complete!")
    print(f"   JSON: {json_path}")
    print(f"   HTML: {html_path}")


if __name__ == "__main__":
    main()
