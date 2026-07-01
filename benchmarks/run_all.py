#!/usr/bin/env python3
"""
Run all benchmarks and generate final report
"""

import json
import os
import subprocess
import sys
from datetime import datetime


def run_benchmark(script_name):
    """Run benchmark and capture output."""
    print(f"\n{'='*60}")
    print(f"Running {script_name}...")
    print(f"{'='*60}")
    
    result = subprocess.run(
        [sys.executable, script_name],
        capture_output=True, text=True, timeout=60
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    
    return result.returncode == 0


def generate_report():
    """Generate final comparison report from saved results."""
    os.makedirs("results", exist_ok=True)
    
    report = []
    report.append("# Memanto vs Mem0 — Benchmark Report")
    report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append("\n---\n")
    
    # Scenario A
    report.append("## Scenario A: Context-Overhead & Latency Sprint")
    try:
        with open("results/scenario_a_results.json") as f:
            a = json.load(f)
        
        manto = a["memanto"]
        m0 = a["mem0"]
        
        report.append("\n| Metric | Memanto | Mem0 |")
        report.append("|---|---|---|")
        report.append(f"| Total Input Tokens | {manto['total_input_tokens']} | {m0['total_input_tokens']} |")
        report.append(f"| Total Retrieved Tokens | {manto['total_retrieved_tokens']} | {m0['total_retrieved_tokens']} |")
        report.append(f"| Mean Latency (s) | {manto['mean_latency']} | {m0['mean_latency']} |")
        report.append(f"| p95 Latency (s) | {manto['p95_latency']} | {m0['p95_latency']} |")
        report.append(f"| Avg Results/Query | {manto['avg_results_per_query']} | {m0['avg_results_per_query']} |")
        report.append("\n")
    except FileNotFoundError:
        report.append("\n⚠️ Scenario A results not found.\n")
    
    # Scenario B
    report.append("## Scenario B: Shifting Persona & Temporal Tracking")
    try:
        with open("results/scenario_b_results.json") as f:
            b = json.load(f)
        
        manto = b["memanto"]
        m0 = b["mem0"]
        
        report.append("\n| Metric | Memanto | Mem0 |")
        report.append("|---|---|---|")
        report.append(f"| Sessions Completed | {manto['sessions_completed']} | {m0['sessions_completed']} |")
        report.append(f"| Total Preferences Stored | {manto['total_preferences_stored']} | {m0['total_preferences_stored']} |")
        report.append(f"| Mean Latency (s) | {manto['mean_latency']} | {m0['mean_latency']} |")
        report.append(f"| Accuracy | {manto['accuracy_score']} ({manto['accuracy_percent']}%) | {m0['accuracy_score']} ({m0['accuracy_percent']}%) |")
        report.append("\n")
    except FileNotFoundError:
        report.append("\n⚠️ Scenario B results not found.\n")
    
    # Write report
    report_text = "\n".join(report)
    with open("results/final_report.md", "w") as f:
        f.write(report_text)
    
    print(report_text)
    print(f"\n✅ Final report saved to results/final_report.md")


def main():
    print("=" * 60)
    print("Memanto vs Mem0 — Full Benchmark Suite")
    print("=" * 60)
    
    # Run benchmarks
    success_a = run_benchmark("benchmark_a_context_latency.py")
    success_b = run_benchmark("benchmark_b_persona_tracking.py")
    
    # Generate report
    generate_report()
    
    if success_a and success_b:
        print("\n✅ All benchmarks completed successfully!")
    else:
        print("\n⚠️ Some benchmarks had issues. Check output above.")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
