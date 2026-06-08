#!/usr/bin/env python3
"""
Memanto Benchmark Showdown - 主运行器
=====================================

对比 Memanto vs Mem0 在两种场景下的表现:
  场景A: 数据密集型 - 上下文开销延迟冲刺
  场景B: 动态偏好 - 时序追踪测试

使用方法:
  1. 复制 .env.example 为 .env 并填写 API key
  2. pip install -r requirements.txt
  3. python run_benchmark.py

环境变量:
  MEMANTO_API_KEY / MOORCHEH_API_KEY - Memanto/Moorcheh API 密钥
  MEM0_API_KEY                       - Mem0 API 密钥
  BENCHMARK_OUTPUT                   - 结果输出路径 (默认: results/)
  BENCHMARK_REPEAT                   - 每场景重复次数 (默认: 3)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 将项目根目录加入路径
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backends.base import BaseMemoryBackend, MemoryEntry
from backends.memanto_backend import MemantoBackend
from backends.mem0_backend import Mem0Backend
from datasets.scenario_a_technical import (
    TECHNICAL_LOGS,
    RETRIEVAL_QUERIES,
    GOLDEN_ANSWERS,
)
from datasets.scenario_b_persona import (
    PREFERENCE_SESSIONS,
    PREFERENCE_QUERIES,
    PREFERENCE_GOLDEN,
)
from metrics.collector import MetricsCollector
from metrics.reporter import print_comparison_table, print_summary


def init_backends() -> list[BaseMemoryBackend]:
    """初始化可用的后端"""
    backends = []
    try:
        m = MemantoBackend()
        m.setup()
        backends.append(m)
        print("[OK] Memanto backend initialized")
    except Exception as e:
        print(f"[SKIP] Memanto backend: {e}")

    try:
        mem0 = Mem0Backend()
        mem0.setup()
        backends.append(mem0)
        print(f"[OK] {mem0.name} backend initialized")
    except Exception as e:
        print(f"[SKIP] Mem0 backend: {e}")

    if len(backends) < 2:
        print("\n[ERROR] 需要至少两个后端才能进行对比测试")
        print("请确保 MEMANTO_API_KEY 和 MEM0_API_KEY 都已设置")
        sys.exit(1)

    return backends


def run_scenario_a(
    backends: list[BaseMemoryBackend],
    collector: MetricsCollector,
    repeat: int = 3,
) -> None:
    """场景A: 数据密集型 - 上下文开销延迟冲刺"""
    print("\n" + "=" * 60)
    print("  SCENARIO A: Context-Overhead Latency Sprint")
    print("=" * 60)

    for iteration in range(repeat):
        print(f"\n  Iteration {iteration + 1}/{repeat}...")
        for backend in backends:
            backend.reset()
            # 存储所有技术日志
            for entry in TECHNICAL_LOGS:
                result = backend.ingest(entry)
                collector.record("scenario_a", result)
            # 执行检索查询
            for query in RETRIEVAL_QUERIES:
                result = backend.retrieve(query, top_k=3)
                collector.record("scenario_a", result)

    # 打印对比结果
    memanto_m = collector.aggregate("scenario_a", "Memanto")
    mem0_m = collector.aggregate("scenario_a", "Mem0")
    print_comparison_table(memanto_m, mem0_m)


def run_scenario_b(
    backends: list[BaseMemoryBackend],
    collector: MetricsCollector,
    repeat: int = 3,
) -> None:
    """场景B: 动态偏好 - 时序追踪测试"""
    print("\n" + "=" * 60)
    print("  SCENARIO B: Shifting Persona Temporal Tracking")
    print("=" * 60)

    for iteration in range(repeat):
        print(f"\n  Iteration {iteration + 1}/{repeat}...")
        for backend in backends:
            backend.reset()
            # 按时序执行会话
            for session in PREFERENCE_SESSIONS:
                print(f"    Session {session.session_id}: {session.description}")
                for entry in session.entries:
                    result = backend.ingest(entry)
                    collector.record("scenario_b", result)
                # 每次会话后检索当前偏好
                for query in PREFERENCE_QUERIES:
                    result = backend.retrieve(query, top_k=3)
                    collector.record("scenario_b", result)

    # 打印对比结果
    memanto_m = collector.aggregate("scenario_b", "Memanto")
    mem0_m = collector.aggregate("scenario_b", "Mem0")
    print_comparison_table(memanto_m, mem0_m)


def main() -> None:
    print("Memanto Benchmark Showdown")
    print("=" * 60)

    repeat = int(os.environ.get("BENCHMARK_REPEAT", "3"))
    output_dir = Path(os.environ.get("BENCHMARK_OUTPUT", str(ROOT / "results")))
    output_dir.mkdir(parents=True, exist_ok=True)

    backends = init_backends()
    collector = MetricsCollector()

    # 运行场景A
    run_scenario_a(backends, collector, repeat)

    # 运行场景B
    run_scenario_b(backends, collector, repeat)

    # 打印总体摘要
    memanto_results = [collector.aggregate(s, "Memanto") for s in ["scenario_a", "scenario_b"]]
    mem0_results = [collector.aggregate(s, "Mem0") for s in ["scenario_a", "scenario_b"]]
    print_summary(memanto_results, mem0_results)

    # 导出 JSON 结果
    json_path = output_dir / "benchmark_results.json"
    collector.export_json(str(json_path))
    print(f"\nDetailed results saved to: {json_path}")

    # 导出 Markdown 报告
    md_path = output_dir / "benchmark_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Memanto Benchmark Showdown Results\n\n")
        f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Repetitions**: {repeat}\n\n")
        f.write("## Scenario A: Context-Overhead Latency Sprint\n\n")
        print_comparison_table(memanto_results[0], mem0_results[0], file=f)
        f.write("\n## Scenario B: Shifting Persona Temporal Tracking\n\n")
        print_comparison_table(memanto_results[1], mem0_results[1], file=f)
        f.write("\n## Overall Summary\n\n")
        print_summary(memanto_results, mem0_results, file=f)
    print(f"Report saved to: {md_path}")


if __name__ == "__main__":
    main()
