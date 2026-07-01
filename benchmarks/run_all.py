#!/usr/bin/env python3
"""Run all benchmarks and generate final report."""
import json, os, subprocess, sys
from datetime import datetime

SCRIPTS = [
    "benchmark_a_context_latency.py",
    "benchmark_b_persona_tracking.py",
]


def run(script):
    print(f"\n{'='*60}\nRunning {script}...\n{'='*60}")
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print(f"⏱️  {script} timed out after 60s")
        return False
    print(r.stdout)
    if r.stderr:
        print(f"STDERR: {r.stderr[:300]}")
    return r.returncode == 0


def report():
    os.makedirs("results", exist_ok=True)
    lines = ["# Memanto vs Mem0 — Benchmark Report",
             f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "\n---\n"]
    for label, key in [("A: Context & Latency","scenario_a_results"),
                       ("B: Temporal Tracking","scenario_b_results")]:
        lines.append(f"\n## {label}\n")
        try:
            with open(f"results/{key}.json") as f:
                d = json.load(f)
            for sys_name in ["memanto","mem0"]:
                s = d[sys_name]
                lines.append(f"\n**{sys_name.title()}** (mode: {s['api_mode']})")
                for k, v in s.items():
                    if k not in ["system","api_mode"]:
                        lines.append(f"- {k}: {v}")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            lines.append("\n⚠️ No results\n")
    report_text = "\n".join(lines)
    with open("results/final_report.md","w") as f:
        f.write(report_text)
    print(report_text)


def main():
    success = True
    for script in SCRIPTS:
        if not run(script):
            success = False
    report()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
