#!/usr/bin/env python3
"""
Multi-Agent Shared Memory Benchmark
====================================
Tests how memory frameworks handle CONSISTENCY across multiple concurrent
agent sessions sharing the same user context.

The Problem:
When a coding agent, research agent, and writing agent all access the same
user's memory, they must see the SAME current state — not stale preferences
from 3 sessions ago. This benchmark stress-tests that consistency.

Scenarios:
- 3 agents (coder, researcher, writer) share one user memory
- 10 sessions with evolving, sometimes conflicting preferences
- Measures: accuracy, consistency, token footprint, latency

Competitors: Memanto vs Mem0 vs raw_context_baseline

Usage:
    python run_benchmark.py
    python run_benchmark.py --output results/sample_results.json --markdown results/sample_results.md
    python run_benchmark.py --mock  # Run without API keys (mock mode)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ── Dataset ──────────────────────────────────────────────────────

SESSIONS = [
    {
        "session_id": 1,
        "agent": "coder",
        "content": "I prefer Python over JavaScript. Use pytest for testing. My code style: 4-space indent, max 88 chars.",
        "is_update": True,
    },
    {
        "session_id": 2,
        "agent": "researcher",
        "content": "I'm interested in AI safety research. Focus on alignment and interpretability papers.",
        "is_update": True,
    },
    {
        "session_id": 3,
        "agent": "writer",
        "content": "Write in formal academic tone. Use APA citations. Max 500 words per section.",
        "is_update": True,
    },
    {
        "session_id": 4,
        "agent": "coder",
        "content": "Switching to Rust for performance-critical code. Still use Python for prototyping.",
        "is_update": True,
    },
    {
        "session_id": 5,
        "agent": "researcher",
        "content": "Now focusing on AI agent frameworks and tool-use patterns. Less alignment, more practical.",
        "is_update": True,
    },
    {
        "session_id": 6,
        "agent": "writer",
        "content": "Changed mind — use casual blog tone now, not academic. Include code snippets in articles.",
        "is_update": True,
    },
    {
        "session_id": 7,
        "agent": "coder",
        "content": "Back to Python. Rust was too slow for iteration. Using ruff for linting now.",
        "is_update": True,
    },
    {
        "session_id": 8,
        "agent": "researcher",
        "content": "New focus: multi-agent systems and orchestration patterns. Memory management is key.",
        "is_update": True,
    },
    {
        "session_id": 9,
        "agent": "writer",
        "content": "Writing style: technical tutorials with step-by-step examples. Target audience: intermediate devs.",
        "is_update": True,
    },
    {
        "session_id": 10,
        "agent": "coder",
        "content": "Final preference: Python with type hints. Use uv for package management. Test with pytest + coverage.",
        "is_update": True,
    },
]

PROBES = [
    {
        "probe_id": 1,
        "agent": "coder",
        "question": "What programming language does the user prefer?",
        "expected": "Python",
        "keywords": ["python"],
    },
    {
        "probe_id": 2,
        "agent": "coder",
        "question": "What testing framework does the user use?",
        "expected": "pytest",
        "keywords": ["pytest"],
    },
    {
        "probe_id": 3,
        "agent": "researcher",
        "question": "What is the user's current research focus?",
        "expected": "multi-agent systems and orchestration patterns",
        "keywords": ["multi-agent", "orchestration", "agent"],
    },
    {
        "probe_id": 4,
        "agent": "researcher",
        "question": "Is the user still focused on AI alignment?",
        "expected": "No, moved to practical agent frameworks",
        "keywords": ["no", "moved", "practical", "less"],
    },
    {
        "probe_id": 5,
        "agent": "writer",
        "question": "What writing style does the user prefer?",
        "expected": "technical tutorials with step-by-step examples",
        "keywords": ["technical", "tutorial", "step-by-step", "example"],
    },
    {
        "probe_id": 6,
        "agent": "writer",
        "question": "Should articles use academic citations?",
        "expected": "No, casual blog tone with code snippets",
        "keywords": ["no", "casual", "blog", "code"],
    },
    {
        "probe_id": 7,
        "agent": "coder",
        "question": "What package manager does the user use?",
        "expected": "uv",
        "keywords": ["uv"],
    },
    {
        "probe_id": 8,
        "agent": "researcher",
        "question": "What does the user consider key in multi-agent systems?",
        "expected": "memory management",
        "keywords": ["memory"],
    },
    {
        "probe_id": 9,
        "agent": "writer",
        "question": "Who is the target audience for the user's articles?",
        "expected": "intermediate developers",
        "keywords": ["intermediate", "developer"],
    },
    {
        "probe_id": 10,
        "agent": "coder",
        "question": "What linter does the user use?",
        "expected": "ruff",
        "keywords": ["ruff"],
    },
]


# ── Memory Backend Abstractions ──────────────────────────────────

@dataclass
class MemoryResult:
    text: str
    tokens_used: int
    latency_ms: float
    source: str


class MemoryBackend:
    """Base class for memory backends."""

    def __init__(self, name: str):
        self.name = name
        self.total_tokens_written: int = 0
        self.total_tokens_read: int = 0

    def write(self, session_id: int, agent: str, content: str) -> MemoryResult:
        raise NotImplementedError

    def read(self, agent: str, question: str) -> MemoryResult:
        raise NotImplementedError

    def consistency_check(self, agents: list[str], question: str) -> float:
        """Check if all agents get consistent answers. Returns 0.0-1.0."""
        answers = []
        for agent in agents:
            result = self.read(agent, question)
            answers.append(result.text.lower())
        if not answers:
            return 0.0
        if len(answers) < 2:
            return 1.0
        # Pairwise token-set overlap to avoid first-answer bias
        total_pairs = 0
        matching_pairs = 0
        for i in range(len(answers)):
            for j in range(i + 1, len(answers)):
                total_pairs += 1
                words_i = set(answers[i].split()[:10])
                words_j = set(answers[j].split()[:10])
                overlap = len(words_i & words_j)
                if overlap >= 3:
                    matching_pairs += 1
        return matching_pairs / max(total_pairs, 1)

    def close(self):
        pass


class RawContextBaseline(MemoryBackend):
    """Baseline: just concatenates all past messages. No memory system."""

    def __init__(self):
        super().__init__("raw_context_baseline")
        self.history: list[dict] = []

    def write(self, session_id: int, agent: str, content: str) -> MemoryResult:
        start = time.perf_counter()
        tokens = len(content.split())
        self.history.append({"session_id": session_id, "agent": agent, "content": content})
        self.total_tokens_written += tokens
        latency = (time.perf_counter() - start) * 1000
        return MemoryResult(content, tokens, latency, "append")

    def read(self, agent: str, question: str) -> MemoryResult:
        start = time.perf_counter()
        # Return ALL history (simulates context window bloat)
        full_context = "\n".join(h["content"] for h in self.history)
        tokens = len(full_context.split())
        self.total_tokens_read += tokens
        latency = (time.perf_counter() - start) * 1000
        return MemoryResult(full_context, tokens, latency, "full_history")


class MockMemanto(MemoryBackend):
    """Mock Memanto: simulates active compression + preference tracking."""

    def __init__(self):
        super().__init__("memanto")
        self.compressed_state: dict[str, dict] = {}  # agent -> latest state

    def write(self, session_id: int, agent: str, content: str) -> MemoryResult:
        start = time.perf_counter()
        tokens = len(content.split())
        # Simulate compression: store only latest per agent
        self.compressed_state[agent] = {
            "session_id": session_id,
            "content": content,
            "timestamp": time.time(),
        }
        # Memanto uses ~30% tokens for storage (compression)
        stored_tokens = max(1, int(tokens * 0.3))
        self.total_tokens_written += stored_tokens
        latency = (time.perf_counter() - start) * 1000 + 50  # Simulated API latency
        return MemoryResult(content, stored_tokens, latency, "compressed")

    def read(self, agent: str, question: str) -> MemoryResult:
        start = time.perf_counter()
        # Return compressed state for this agent
        state = self.compressed_state.get(agent, {})
        content = state.get("content", "")
        # Also get cross-agent context (compressed)
        other_context = " ".join(
            s["content"][:50] for a, s in self.compressed_state.items() if a != agent
        )
        full = f"{content}\n{other_context}".strip()
        tokens = len(full.split())
        self.total_tokens_read += tokens
        latency = (time.perf_counter() - start) * 1000 + 80  # Simulated retrieval
        return MemoryResult(full, tokens, latency, "memanto_compressed")


class MockMem0(MemoryBackend):
    """Mock Mem0: simulates graph-based memory with retrieval."""

    def __init__(self):
        super().__init__("mem0")
        self.facts: list[dict] = []

    def write(self, session_id: int, agent: str, content: str) -> MemoryResult:
        start = time.perf_counter()
        tokens = len(content.split())
        # Simulate graph extraction: stores facts
        self.facts.append({
            "session_id": session_id,
            "agent": agent,
            "content": content,
        })
        self.total_tokens_written += tokens
        latency = (time.perf_counter() - start) * 1000 + 100  # Graph extraction
        return MemoryResult(content, tokens, latency, "graph_stored")

    def read(self, agent: str, question: str) -> MemoryResult:
        start = time.perf_counter()
        # Simulate graph retrieval: returns relevant facts
        relevant = [f["content"] for f in self.facts if f["agent"] == agent]
        if not relevant:
            relevant = [f["content"] for f in self.facts[-3:]]
        content = "\n".join(relevant)
        tokens = len(content.split())
        self.total_tokens_read += tokens
        latency = (time.perf_counter() - start) * 1000 + 150  # Graph retrieval
        return MemoryResult(content, tokens, latency, "graph_retrieved")


# ── Scoring ──────────────────────────────────────────────────────

def score_answer(answer: str, expected: str, keywords: list[str]) -> float:
    """Score answer 0.0-1.0 based on keyword presence."""
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / max(len(keywords), 1)


# ── Benchmark Runner ─────────────────────────────────────────────

@dataclass
class ProbeResult:
    probe_id: int
    agent: str
    question: str
    expected: str
    answer: str
    accuracy: float
    tokens_read: int
    latency_ms: float


@dataclass
class BackendResult:
    name: str
    total_tokens_written: int
    total_tokens_read: int
    avg_accuracy: float
    avg_latency_ms: float
    consistency_score: float
    probe_results: list[ProbeResult] = field(default_factory=list)


def run_benchmark(backend: MemoryBackend, mock: bool = False) -> BackendResult:
    """Run the full benchmark on a single backend."""
    print(f"\n{'='*60}")
    print(f"Running benchmark: {backend.name}")
    print(f"{'='*60}")

    # Phase 1: Write all sessions
    print(f"\n--- Phase 1: Writing {len(SESSIONS)} sessions ---")
    for session in SESSIONS:
        result = backend.write(session["session_id"], session["agent"], session["content"])
        print(f"  Session {session['session_id']:2d} [{session['agent']:10s}] "
              f"→ {result.tokens_used:3d} tokens, {result.latency_ms:.1f}ms")

    # Phase 2: Read probes
    print(f"\n--- Phase 2: Reading {len(PROBES)} probes ---")
    probe_results = []
    for probe in PROBES:
        result = backend.read(probe["agent"], probe["question"])
        accuracy = score_answer(result.text, probe["expected"], probe["keywords"])
        pr = ProbeResult(
            probe_id=probe["probe_id"],
            agent=probe["agent"],
            question=probe["question"],
            expected=probe["expected"],
            answer=result.text[:200],
            accuracy=accuracy,
            tokens_read=result.tokens_used,
            latency_ms=result.latency_ms,
        )
        probe_results.append(pr)
        status = "✓" if accuracy >= 0.5 else "✗"
        print(f"  {status} Probe {probe['probe_id']:2d} [{probe['agent']:10s}] "
              f"accuracy={accuracy:.1%} tokens={result.tokens_used:3d} latency={result.latency_ms:.0f}ms")

    # Phase 3: Consistency check
    print(f"\n--- Phase 3: Consistency check ---")
    agents = ["coder", "researcher", "writer"]
    # Use a probe question from the dataset for reproducibility
    consistency_question = PROBES[0]["question"]
    consistency = backend.consistency_check(agents, consistency_question)
    print(f"  Consistency score: {consistency:.1%}")

    # Aggregate
    avg_accuracy = sum(p.accuracy for p in probe_results) / max(len(probe_results), 1)
    avg_latency = sum(p.latency_ms for p in probe_results) / max(len(probe_results), 1)

    result = BackendResult(
        name=backend.name,
        total_tokens_written=backend.total_tokens_written,
        total_tokens_read=backend.total_tokens_read,
        avg_accuracy=avg_accuracy,
        avg_latency_ms=avg_latency,
        consistency_score=consistency,
        probe_results=probe_results,
    )

    print(f"\n  Summary for {backend.name}:")
    print(f"    Avg Accuracy:    {avg_accuracy:.1%}")
    print(f"    Tokens Written:  {backend.total_tokens_written}")
    print(f"    Tokens Read:     {backend.total_tokens_read}")
    print(f"    Avg Latency:     {avg_latency:.0f}ms")
    print(f"    Consistency:     {consistency:.1%}")

    backend.close()
    return result


def generate_report(results: list[BackendResult], output_json: Optional[str] = None,
                    output_md: Optional[str] = None) -> str:
    """Generate comparison report."""
    lines = []
    lines.append("# Multi-Agent Shared Memory Benchmark Results\n")
    lines.append("## Scenario")
    lines.append("3 agents (coder, researcher, writer) share one user memory.")
    lines.append("10 sessions with evolving, sometimes conflicting preferences.\n")

    lines.append("## Results\n")
    lines.append("| Metric | " + " | ".join(r.name for r in results) + " |")
    lines.append("|--------|" + "|".join("---" for _ in results) + "|")
    lines.append("| Avg Accuracy | " + " | ".join(f"{r.avg_accuracy:.1%}" for r in results) + " |")
    lines.append("| Tokens Written | " + " | ".join(f"{r.total_tokens_written}" for r in results) + " |")
    lines.append("| Tokens Read | " + " | ".join(f"{r.total_tokens_read}" for r in results) + " |")
    lines.append("| Avg Latency (ms) | " + " | ".join(f"{r.avg_latency_ms:.0f}" for r in results) + " |")
    lines.append("| Consistency | " + " | ".join(f"{r.consistency_score:.1%}" for r in results) + " |")

    lines.append("\n## Probe Details\n")
    for result in results:
        lines.append(f"### {result.name}\n")
        lines.append("| # | Agent | Question | Expected | Accuracy | Tokens | Latency |")
        lines.append("|---|-------|----------|----------|----------|--------|---------|")
        for p in result.probe_results:
            lines.append(
                f"| {p.probe_id} | {p.agent} | {p.question[:40]}... | "
                f"{p.expected[:30]}... | {p.accuracy:.0%} | {p.tokens_read} | {p.latency_ms:.0f}ms |"
            )
        lines.append("")

    report = "\n".join(lines)

    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(report)
        print(f"\nMarkdown report: {output_md}")

    if output_json:
        json_data = [asdict(r) for r in results]
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(json_data, indent=2))
        print(f"JSON report: {output_json}")

    return report


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Shared Memory Benchmark")
    parser.add_argument("--output", help="JSON output path")
    parser.add_argument("--markdown", help="Markdown output path")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no API keys needed)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Multi-Agent Shared Memory Benchmark")
    print("  Memanto vs Mem0 vs Raw Context Baseline")
    print("=" * 60)

    backends = [RawContextBaseline()]

    if args.mock:
        print("  Mode: MOCK (simulated backends)")
    else:
        print("  Mode: LIVE — real API backends not yet implemented, using mocks")
        print("  (Install moorcheh-sdk/mem0ai and set API keys when available)")

    backends += [MockMemanto(), MockMem0()]

    results = []
    for backend in backends:
        result = run_benchmark(backend, mock=args.mock)
        results.append(result)

    report = generate_report(results, args.output, args.markdown)
    print("\n" + report)

    # Print winner
    best = max(results, key=lambda r: r.avg_accuracy)
    print(f"\n🏆 Winner: {best.name} (accuracy: {best.avg_accuracy:.1%})")


if __name__ == "__main__":
    main()
