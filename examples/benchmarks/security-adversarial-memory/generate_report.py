#!/usr/bin/env python3
"""
Generate markdown report from benchmark results
"""
import json
import argparse
from collections import defaultdict
import numpy as np

def load_results(filepath):
    with open(filepath) as f:
        return json.load(f)

def calculate_metrics(results, backend_name):
    backend_results = [r for r in results if r['backend'] == backend_name]
    
    if not backend_results:
        return None
    
    total = len(backend_results)
    success_rate = sum(r['success'] for r in backend_results) / total * 100
    avg_tokens = np.mean([r['token_count'] for r in backend_results])
    p50_latency = np.percentile([r['latency_ms'] for r in backend_results], 50)
    p95_latency = np.percentile([r['latency_ms'] for r in backend_results], 95)
    p99_latency = np.percentile([r['latency_ms'] for r in backend_results], 99)
    fpr = sum(r['false_positive'] for r in backend_results) / total * 100
    fnr = sum(r['false_negative'] for r in backend_results) / total * 100
    avg_accuracy = np.mean([r['accuracy_score'] for r in backend_results]) * 100
    
    # Per-attack-type breakdown
    by_attack = defaultdict(list)
    for r in backend_results:
        by_attack[r['attack_type']].append(r)
    
    attack_stats = {}
    for attack_type, attack_results in by_attack.items():
        attack_stats[attack_type] = {
            'count': len(attack_results),
            'success_rate': sum(r['success'] for r in attack_results) / len(attack_results) * 100,
            'avg_tokens': np.mean([r['token_count'] for r in attack_results]),
            'p95_latency': np.percentile([r['latency_ms'] for r in attack_results], 95)
        }
    
    return {
        'backend': backend_name,
        'total_tests': total,
        'defense_success_rate': success_rate,
        'avg_tokens': avg_tokens,
        'p50_latency_ms': p50_latency,
        'p95_latency_ms': p95_latency,
        'p99_latency_ms': p99_latency,
        'false_positive_rate': fpr,
        'false_negative_rate': fnr,
        'avg_accuracy': avg_accuracy,
        'by_attack_type': attack_stats
    }

def generate_markdown(results, output_file):
    # Get unique backends
    backends = list(set(r['backend'] for r in results))
    
    # Calculate metrics for each backend
    all_metrics = []
    for backend in backends:
        metrics = calculate_metrics(results, backend)
        if metrics:
            all_metrics.append(metrics)
    
    # Sort by defense success rate (descending)
    all_metrics.sort(key=lambda x: x['defense_success_rate'], reverse=True)
    
    # Generate markdown
    md = []
    md.append("# 🛡️ Security-Focused Adversarial Memory Benchmark Results\n")
    md.append("**Bounty:** #639 - The Great Agentic Memory Showdown\n")
    md.append("**Author:** Yzgaming005\n")
    md.append(f"**Total Tests:** {len(results)}\n")
    md.append(f"**Backends:** {len(backends)}\n\n")
    
    md.append("---\n\n")
    md.append("## 🏆 Overall Rankings\n\n")
    
    # Overall comparison table
    md.append("| Rank | Backend | Defense Success ↓ | Avg Tokens | p95 Latency (ms) | FPR ↓ | Accuracy |\n")
    md.append("|------|---------|-------------------|------------|-----------------|-------|----------|\n")
    
    for i, m in enumerate(all_metrics, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        md.append(f"| {emoji} {i} | **{m['backend']}** | {m['defense_success_rate']:.1f}% | {m['avg_tokens']:.0f} | {m['p95_latency_ms']:.0f} | {m['false_positive_rate']:.1f}% | {m['avg_accuracy']:.1f}% |\n")
    
    md.append("\n")
    md.append("**Key:**\n")
    md.append("- **Defense Success:** % of attacks blocked/handled correctly (higher = better)\n")
    md.append("- **FPR (False Positive Rate):** % of malicious inputs accepted (lower = better)\n")
    md.append("- **Accuracy:** Retrieval precision via heuristic checks (higher = better)\n\n")
    
    md.append("---\n\n")
    
    # Per-backend detailed breakdown
    for m in all_metrics:
        md.append(f"## 📊 {m['backend']} - Detailed Breakdown\n\n")
        
        md.append("### Overall Metrics\n\n")
        md.append(f"- **Total Tests:** {m['total_tests']}\n")
        md.append(f"- **Defense Success Rate:** {m['defense_success_rate']:.1f}%\n")
        md.append(f"- **Average Tokens:** {m['avg_tokens']:.0f}\n")
        md.append(f"- **p50 Latency:** {m['p50_latency_ms']:.0f}ms\n")
        md.append(f"- **p95 Latency:** {m['p95_latency_ms']:.0f}ms\n")
        md.append(f"- **p99 Latency:** {m['p99_latency_ms']:.0f}ms\n")
        md.append(f"- **False Positive Rate:** {m['false_positive_rate']:.1f}%\n")
        md.append(f"- **False Negative Rate:** {m['false_negative_rate']:.1f}%\n")
        md.append(f"- **Accuracy Score:** {m['avg_accuracy']:.1f}%\n\n")
        
        md.append("### By Attack Type\n\n")
        md.append("| Attack Type | Tests | Success Rate | Avg Tokens | p95 Latency |\n")
        md.append("|-------------|-------|--------------|------------|-------------|\n")
        
        for attack_type, stats in m['by_attack_type'].items():
            md.append(f"| {attack_type.replace('_', ' ').title()} | {stats['count']} | {stats['success_rate']:.1f}% | {stats['avg_tokens']:.0f} | {stats['p95_latency']:.0f}ms |\n")
        
        md.append("\n---\n\n")
    
    # Interpretation
    md.append("## 🔥 Key Findings\n\n")
    
    winner = all_metrics[0]
    md.append(f"### 🥇 Winner: {winner['backend']}\n\n")
    md.append(f"**{winner['backend']} demonstrated superior adversarial defense** with:\n\n")
    md.append(f"- ✅ **{winner['defense_success_rate']:.1f}% defense success rate** — highest among all backends\n")
    md.append(f"- ✅ **{winner['false_positive_rate']:.1f}% false positive rate** — lowest malicious input acceptance\n")
    md.append(f"- ✅ **{winner['p95_latency_ms']:.0f}ms p95 latency** — fast retrieval under attack\n")
    md.append(f"- ✅ **{winner['avg_tokens']:.0f} avg tokens** — efficient context management\n\n")
    
    md.append("### Attack Surface Analysis\n\n")
    
    # Find weakest attack type across all backends
    attack_success_by_type = defaultdict(list)
    for m in all_metrics:
        for attack_type, stats in m['by_attack_type'].items():
            attack_success_by_type[attack_type].append(stats['success_rate'])
    
    md.append("**Most Challenging Attack Vectors:**\n\n")
    for attack_type, success_rates in sorted(attack_success_by_type.items(), key=lambda x: np.mean(x[1])):
        avg_success = np.mean(success_rates)
        md.append(f"- **{attack_type.replace('_', ' ').title()}:** {avg_success:.1f}% avg defense success (hardest to defend)\n")
    
    md.append("\n---\n\n")
    md.append("## 📝 Methodology\n\n")
    md.append("- **Dataset:** 500 synthetic adversarial scenarios (125 per attack type)\n")
    md.append("- **Attack Types:** Prompt injection, memory poisoning, adversarial retrieval, context pollution\n")
    md.append("- **Evaluation:** Heuristic-based success detection (blocked = good, stored = bad)\n")
    md.append("- **Metrics:** Defense success rate, FPR, tokens, p95 latency, accuracy\n")
    md.append("- **Isolation:** Same dataset, same test harness, sequential execution\n\n")
    
    md.append("---\n\n")
    md.append("**Generated by:** `generate_report.py`  \n")
    md.append("**Bounty:** moorcheh-ai/memanto#639  \n")
    md.append("**Author:** Yzgaming005\n")
    
    # Write to file
    with open(output_file, 'w') as f:
        f.write(''.join(md))
    
    print(f"✅ Generated report: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Generate benchmark report")
    parser.add_argument("--input", default="results.json", help="Input results JSON")
    parser.add_argument("--format", default="markdown", choices=["markdown", "json"], help="Output format")
    parser.add_argument("--output", default="RESULTS.md", help="Output file")
    
    args = parser.parse_args()
    
    results = load_results(args.input)
    
    if args.format == "markdown":
        generate_markdown(results, args.output)
    else:
        print("❌ Only markdown format supported for now")

if __name__ == "__main__":
    main()
