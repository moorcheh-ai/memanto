#!/usr/bin/env python3
"""Run all benchmarks and generate final report."""
import json, os, subprocess, sys
from datetime import datetime

def run(script):
    print(f"\n{'='*60}\nRunning {script}...\n{'='*60}")
    r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60)
    print(r.stdout)
    if r.stderr: print("STDERR:", r.stderr[:300])
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
        except: lines.append("\n⚠️ No results\n")
    with open("results/final_report.md","w") as f: f.write("\n".join(lines))
    print("\n".join(lines))

run("benchmark_a_context_latency.py") and run("benchmark_b_persona_tracking.py")
report()
