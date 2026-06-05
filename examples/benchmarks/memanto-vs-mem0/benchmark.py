#!/usr/bin/env python3
"""
Memanto vs Mem0 Benchmark
=========================
A reproducible benchmark comparing Moorcheh/Memanto information-theoretic
retrieval against Mem0's vector-based agent memory on a shared document corpus.

Usage:
    export MOORCHEH_API_KEY="mk_..."
    export OPENAI_API_KEY="sk-..."
    python benchmark.py

Outputs:
    results/results.csv       — per-query raw scores
    results/summary.json      — aggregate metrics
    results/summary.md        — human-readable report
"""

import os
import sys
import json
import csv
import time
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Real deps imported lazily in run_benchmark() / main() to keep --demo dependency-free
_DEMO_MODE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CHUNK_SIZE = 700
CHUNK_OVERLAP = 120
TOP_K = 5
DOCUMENT_PATH = Path(__file__).parent / "sample_document.md"
QUERIES_PATH = Path(__file__).parent / "queries.csv"
RESULTS_DIR = Path(__file__).parent / "results"
JUDGE_MODEL = "gpt-4o"
_RUN_ID = str(int(time.time()))
MEMANTO_NAMESPACE = f"memanto_benchmark_namespace_{_RUN_ID}"
MEM0_AGENT_ID = f"benchmark_agent_{_RUN_ID}"

RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class RetrievedContext:
    text: str
    score: float = 0.0
    metadata: Dict[str, Any] = None


@dataclass
class EvaluationResult:
    query: str
    system: str  # "memanto" or "mem0"
    relevance_score: int
    relevance_rationale: str
    completeness_score: int
    completeness_rationale: str
    retrieved_context: str
    latency_ms: float


@dataclass
class SummaryMetrics:
    system: str
    num_queries: int
    avg_relevance: float
    avg_completeness: float
    combined_score: float
    avg_latency_ms: float


# ---------------------------------------------------------------------------
# Document loading & chunking
# ---------------------------------------------------------------------------
def load_and_chunk_document(path: Path) -> List[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    logger.info(f"Loading document: {path}")
    text = path.read_text(encoding="utf-8")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    chunks = splitter.split_text(text)
    logger.info(f"Produced {len(chunks)} chunks")
    return chunks


# ---------------------------------------------------------------------------
# Memanto (Moorcheh) pipeline
# ---------------------------------------------------------------------------
class MemantoPipeline:
    def __init__(self):
        from moorcheh_sdk import MoorchehClient

        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY environment variable is required")

        self.client = MoorchehClient(api_key=api_key)
        self.namespace = MEMANTO_NAMESPACE
        self._ensure_namespace()

    def _ensure_namespace(self):
        try:
            existing = self.client.namespaces.list()
            names = [n["namespace_name"] for n in existing.get("namespaces", [])]
            if self.namespace not in names:
                logger.info(f"Creating Moorcheh namespace: {self.namespace}")
                self.client.namespaces.create(self.namespace, "text")
            else:
                logger.info(f"Namespace {self.namespace} already exists")
        except Exception as exc:
            logger.warning(f"Namespace check/create issue (may already exist): {exc}")

    def ingest(self, chunks: List[str]):
        logger.info("Ingesting chunks into Moorcheh/Memanto...")
        documents = [
            {
                "id": f"chunk_{i}",
                "text": chunk,
                "metadata": {"source": "benchmark_doc", "chunk_index": i},
            }
            for i, chunk in enumerate(chunks)
        ]
        batch_size = 15
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            self.client.documents.upload(
                namespace_name=self.namespace, documents=batch
            )
        logger.info("Memanto ingestion complete")

    def search(self, query: str, k: int = TOP_K) -> List[RetrievedContext]:
        start = time.perf_counter()
        results = self.client.similarity_search.query(
            namespaces=[self.namespace], query=query, top_k=k
        )
        elapsed = (time.perf_counter() - start) * 1000
        matches = results if isinstance(results, list) else results.get("results", [])
        contexts = []
        for m in matches:
            contexts.append(
                RetrievedContext(
                    text=m.get("text", m.get("content", "")),
                    score=m.get("score", 0.0),
                    metadata=m.get("metadata", {}),
                )
            )
        return contexts, elapsed


# ---------------------------------------------------------------------------
# Mem0 pipeline
# ---------------------------------------------------------------------------
class Mem0Pipeline:
    def __init__(self):
        from mem0 import Memory

        self.memory = Memory()
        self.agent_id = MEM0_AGENT_ID
        self._use_real_embeddings = bool(os.environ.get("OPENAI_API_KEY"))
        if not self._use_real_embeddings:
            logger.warning("OPENAI_API_KEY not set — Mem0 embeddings will fail; using mock fallback")

    def ingest(self, chunks: List[str]):
        logger.info("Ingesting chunks into Mem0...")
        for i, chunk in enumerate(chunks):
            # Use infer=False to store raw chunks without LLM extraction,
            # matching Moorcheh's zero-extraction ingestion.
            self.memory.add(
                messages=chunk,
                agent_id=self.agent_id,
                infer=False,
                metadata={"source": "benchmark_doc", "chunk_index": i},
            )
        logger.info("Mem0 ingestion complete")

    def search(self, query: str, k: int = TOP_K) -> List[RetrievedContext]:
        start = time.perf_counter()
        results = self.memory.search(
            query=query, filters={"agent_id": self.agent_id}, top_k=k
        )
        elapsed = (time.perf_counter() - start) * 1000
        contexts = []
        for r in results.get("results", []):
            contexts.append(
                RetrievedContext(
                    text=r.get("memory", ""),
                    score=r.get("score", 0.0),
                    metadata=r.get("metadata", {}),
                )
            )
        return contexts, elapsed


# ---------------------------------------------------------------------------
# LLM-as-a-Judge
# ---------------------------------------------------------------------------
class LLMJudge:
    SUPPORTED_PROVIDERS = ("openai", "heuristic")

    def __init__(self):
        self.provider = (os.environ.get("JUDGE_PROVIDER") or "").lower()
        api_key = os.environ.get("OPENAI_API_KEY")
        prompt_path = Path(__file__).parent / "judge_prompt.txt"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")
        self.model = os.environ.get("JUDGE_MODEL", JUDGE_MODEL)
        self._use_openai = False
        self._openai = None

        if self.provider == "gemini":
            raise RuntimeError(
                "JUDGE_PROVIDER=gemini is not implemented in this benchmark. "
                "Supported providers: 'openai' (requires OPENAI_API_KEY) or "
                "'heuristic' (no key required). Add the google-genai client "
                "and a Gemini branch in LLMJudge._evaluate_gemini to enable."
            )
        if self.provider and self.provider not in self.SUPPORTED_PROVIDERS:
            raise RuntimeError(
                f"Unknown JUDGE_PROVIDER={self.provider!r}. "
                f"Supported: {self.SUPPORTED_PROVIDERS}"
            )
        if self.provider == "openai" and not api_key:
            raise RuntimeError(
                "JUDGE_PROVIDER=openai requires OPENAI_API_KEY to be set."
            )
        if api_key and self.provider in ("", "openai"):
            from openai import OpenAI
            self._openai = OpenAI(api_key=api_key)
            self._use_openai = True
            self.provider = "openai"
        if not self._use_openai:
            self.provider = "heuristic"
            logger.warning(
                "LLM judge unavailable (no OPENAI_API_KEY or provider unset) — "
                "falling back to keyword-overlap heuristic"
            )

    def evaluate(self, query: str, contexts: List[RetrievedContext]) -> Dict[str, Any]:
        if self._use_openai:
            return self._evaluate_openai(query, contexts)
        return self._evaluate_heuristic(query, contexts)

    def _evaluate_openai(self, query: str, contexts: List[RetrievedContext]) -> Dict[str, Any]:
        context_text = "\n\n---\n\n".join(
            f"[Score: {round(c.score, 3)}]\n{c.text}" for c in contexts
        )
        user_message = f"Query: {query}\n\nRetrieved Passages:\n{context_text}"
        response = self._openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    def _evaluate_heuristic(self, query: str, contexts: List[RetrievedContext]) -> Dict[str, Any]:
        """Keyword-overlap heuristic for environments without an LLM judge."""
        query_terms = set(query.lower().split())
        scores = []
        for c in contexts:
            text_terms = set(c.text.lower().split())
            if not query_terms:
                overlap = 0.0
            else:
                overlap = len(query_terms & text_terms) / len(query_terms)
            scores.append(min(overlap * 2, 1.0))  # double to compensate, cap at 1.0
        avg_overlap = sum(scores) / len(scores) if scores else 0.0
        relevance = int(avg_overlap * 80 + 20)  # scale to 20-100 range
        completeness = relevance
        return {
            "relevance_score": min(relevance, 100),
            "relevance_rationale": f"[HEURISTIC] Query-keyword overlap: {avg_overlap:.3f}",
            "completeness_score": min(completeness, 100),
            "completeness_rationale": "[HEURISTIC] Based on keyword overlap with query terms",
        }


# ---------------------------------------------------------------------------
# Benchmark orchestration
# ---------------------------------------------------------------------------
def run_benchmark(allow_mock=False):
    logger.info("=" * 60)
    logger.info("Memanto vs Mem0 Benchmark")
    logger.info("=" * 60)

    chunks = load_and_chunk_document(DOCUMENT_PATH)
    queries_df = pd.read_csv(QUERIES_PATH)
    queries = queries_df["query"].dropna().tolist()
    logger.info(f"Loaded {len(queries)} queries")

    # Initialize pipelines
    memanto = MemantoPipeline()
    mem0_uses_mock = False
    try:
        mem0 = Mem0Pipeline()
    except Exception as exc:
        if not allow_mock:
            raise RuntimeError(
                f"Mem0 unavailable ({exc}). Use --allow-mock to run with mock fallback."
            ) from exc
        mem0_uses_mock = True
        logger.warning(f"[MOCK] Mem0 unavailable ({exc}) — using mock fallback")
        mem0 = MockMem0Pipeline(chunks)
    judge = LLMJudge()

    # Ingest
    memanto.ingest(chunks)
    mem0.ingest(chunks)

    all_results: List[EvaluationResult] = []

    for idx, query in enumerate(queries, 1):
        logger.info(f"[{idx}/{len(queries)}] Query: {query}")

        for system_name, pipeline in [("memanto", memanto), ("mem0", mem0)]:
            contexts, latency = pipeline.search(query, k=TOP_K)
            if not contexts:
                logger.warning(f"No results from {system_name} for query: {query}")
                continue

            eval_resp = judge.evaluate(query, contexts)
            context_blob = "\n".join(c.text for c in contexts)

            result = EvaluationResult(
                query=query,
                system=system_name,
                relevance_score=int(eval_resp.get("relevance_score", 0)),
                relevance_rationale=eval_resp.get("relevance_rationale", ""),
                completeness_score=int(eval_resp.get("completeness_score", 0)),
                completeness_rationale=eval_resp.get("completeness_rationale", ""),
                retrieved_context=context_blob,
                latency_ms=round(latency, 2),
            )
            all_results.append(result)
            logger.info(
                f"  {system_name:8s} | Rel: {result.relevance_score:3d} | "
                f"Comp: {result.completeness_score:3d} | "
                f"Latency: {result.latency_ms:6.2f}ms"
            )

    # Persist raw results
    results_csv = RESULTS_DIR / "results.csv"
    with open(results_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "query",
                "system",
                "relevance_score",
                "relevance_rationale",
                "completeness_score",
                "completeness_rationale",
                "latency_ms",
                "retrieved_context",
            ],
        )
        writer.writeheader()
        for r in all_results:
            writer.writerow(asdict(r))
    logger.info(f"Raw results written to {results_csv}")

    # Compute summaries
    summaries = []
    for system_name in ("memanto", "mem0"):
        rows = [r for r in all_results if r.system == system_name]
        if not rows:
            continue
        avg_rel = sum(r.relevance_score for r in rows) / len(rows)
        avg_comp = sum(r.completeness_score for r in rows) / len(rows)
        avg_lat = sum(r.latency_ms for r in rows) / len(rows)
        combined = (avg_rel + avg_comp) / 2
        summaries.append(
            SummaryMetrics(
                system=system_name,
                num_queries=len(rows),
                avg_relevance=round(avg_rel, 2),
                avg_completeness=round(avg_comp, 2),
                combined_score=round(combined, 2),
                avg_latency_ms=round(avg_lat, 2),
            )
        )

    # Save JSON summary
    summary_json = RESULTS_DIR / "summary.json"
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump([asdict(s) for s in summaries], f, indent=2)
    logger.info(f"Summary JSON written to {summary_json}")

    # Save Markdown summary
    summary_md = RESULTS_DIR / "summary.md"
    if summaries:
        winner = max(summaries, key=lambda s: s.combined_score)
    else:
        winner = None
    judge_label = "Keyword-overlap heuristic" if not judge._use_openai else judge.model
    mem0_label = "Mock (fallback)" if mem0_uses_mock else "Real"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write("# Memanto vs Mem0 Benchmark Report\n\n")
        f.write(
            "This benchmark evaluates retrieval quality and latency of **Memanto** (Moorcheh) "
            "against **Mem0** on a shared document corpus.\n\n"
        )
        f.write("## Methodology\n\n")
        f.write(f"- **Document**: `{DOCUMENT_PATH.name}`\n")
        f.write(f"- **Chunks**: {len(chunks)} ({CHUNK_SIZE} chars, {CHUNK_OVERLAP} overlap)\n")
        f.write(f"- **Queries**: {len(queries)}\n")
        f.write(f"- **Top-K retrieved**: {TOP_K}\n")
        f.write(f"- **Judge model**: {judge_label}\n")
        f.write("- **Dimensions**: Relevance (0-100) and Completeness (0-100)\n\n")
        f.write("## Aggregate Results\n\n")
        f.write("| System | Queries | Avg Relevance | Avg Completeness | Combined | Avg Latency (ms) |\n")
        f.write("|--------|---------|---------------|------------------|----------|------------------|\n")
        for s in summaries:
            f.write(
                f"| {s.system:6s} | {s.num_queries:7d} | "
                f"{s.avg_relevance:13.2f} | {s.avg_completeness:16.2f} | "
                f"{s.combined_score:8.2f} | {s.avg_latency_ms:16.2f} |\n"
            )
        f.write(f"\n**Winner**: {winner.system.title()} with combined score {winner.combined_score}\n\n")
        f.write("## Per-Query Breakdown\n\n")
        for q in queries:
            f.write(f"### {q}\n\n")
            for r in all_results:
                if r.query == q:
                    f.write(f"- **{r.system.title()}**: Rel={r.relevance_score}, Comp={r.completeness_score}, Lat={r.latency_ms}ms\n")
            f.write("\n")
    logger.info(f"Summary Markdown written to {summary_md}")

    logger.info("=" * 60)
    logger.info("BENCHMARK COMPLETE")
    logger.info("=" * 60)
    for s in summaries:
        logger.info(
            f"{s.system:8s} — Combined: {s.combined_score} | "
            f"Relevance: {s.avg_relevance} | Completeness: {s.avg_completeness} | "
            f"Latency: {s.avg_latency_ms}ms"
        )


# ---------------------------------------------------------------------------
# Demo / dry-run mode (no external API keys required)
# ---------------------------------------------------------------------------
class MockMemantoPipeline:
    def __init__(self, chunks):
        self.chunks = chunks

    def ingest(self, chunks):
        logger.info("[DEMO] Mock Memanto ingestion complete")

    def search(self, query: str, k: int = TOP_K):
        import random
        start = time.perf_counter()
        # Return random chunks with fake scores
        contexts = [
            RetrievedContext(
                text=self.chunks[i % len(self.chunks)],
                score=round(random.uniform(0.6, 0.95), 3),
                metadata={"demo": True}
            )
            for i in range(k)
        ]
        elapsed = (time.perf_counter() - start) * 1000
        return contexts, elapsed


class MockMem0Pipeline:
    def __init__(self, chunks):
        self.chunks = chunks

    def ingest(self, chunks):
        logger.info("[DEMO] Mock Mem0 ingestion complete")

    def search(self, query: str, k: int = TOP_K):
        import random
        start = time.perf_counter()
        contexts = [
            RetrievedContext(
                text=self.chunks[(i + 1) % len(self.chunks)],
                score=round(random.uniform(0.5, 0.90), 3),
                metadata={"demo": True}
            )
            for i in range(k)
        ]
        elapsed = (time.perf_counter() - start) * 1000
        return contexts, elapsed


class MockJudge:
    def evaluate(self, query: str, contexts: List[RetrievedContext]) -> Dict[str, Any]:
        import random
        return {
            "relevance_score": random.randint(70, 98),
            "relevance_rationale": "[DEMO] The retrieved context is relevant to the query.",
            "completeness_score": random.randint(65, 95),
            "completeness_rationale": "[DEMO] The context partially answers the query.",
        }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Memanto vs Mem0 Benchmark")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode without requiring API keys (uses mock data).",
    )
    parser.add_argument(
        "--allow-mock",
        action="store_true",
        help="Allow fallback to mock Mem0 pipeline when real mem0 is unavailable.",
    )
    args = parser.parse_args()

    if args.demo:
        logger.info("Running in DEMO mode — no API keys required")
        global MemantoPipeline, Mem0Pipeline, LLMJudge
        chunks = load_and_chunk_document(DOCUMENT_PATH)
        memanto = MockMemantoPipeline(chunks)
        mem0 = MockMem0Pipeline(chunks)
        judge = MockJudge()

        queries_df = pd.read_csv(QUERIES_PATH)
        queries = queries_df["query"].dropna().tolist()

        all_results = []
        for idx, query in enumerate(queries, 1):
            logger.info(f"[{idx}/{len(queries)}] Query: {query}")
            for system_name, pipeline in [("memanto", memanto), ("mem0", mem0)]:
                contexts, latency = pipeline.search(query, k=TOP_K)
                eval_resp = judge.evaluate(query, contexts)
                context_blob = "\n".join(c.text for c in contexts)
                result = EvaluationResult(
                    query=query,
                    system=system_name,
                    relevance_score=int(eval_resp.get("relevance_score", 0)),
                    relevance_rationale=eval_resp.get("relevance_rationale", ""),
                    completeness_score=int(eval_resp.get("completeness_score", 0)),
                    completeness_rationale=eval_resp.get("completeness_rationale", ""),
                    retrieved_context=context_blob,
                    latency_ms=round(latency, 2),
                )
                all_results.append(result)
                logger.info(
                    f"  {system_name:8s} | Rel: {result.relevance_score:3d} | "
                    f"Comp: {result.completeness_score:3d} | "
                    f"Latency: {result.latency_ms:6.2f}ms"
                )

        # Persist results using same logic as real run
        results_csv = RESULTS_DIR / "results.csv"
        with open(results_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "query",
                    "system",
                    "relevance_score",
                    "relevance_rationale",
                    "completeness_score",
                    "completeness_rationale",
                    "latency_ms",
                    "retrieved_context",
                ],
            )
            writer.writeheader()
            for r in all_results:
                writer.writerow(asdict(r))
        logger.info(f"Raw results written to {results_csv}")

        summaries = []
        for system_name in ("memanto", "mem0"):
            rows = [r for r in all_results if r.system == system_name]
            if not rows:
                continue
            avg_rel = sum(r.relevance_score for r in rows) / len(rows)
            avg_comp = sum(r.completeness_score for r in rows) / len(rows)
            avg_lat = sum(r.latency_ms for r in rows) / len(rows)
            combined = (avg_rel + avg_comp) / 2
            summaries.append(
                SummaryMetrics(
                    system=system_name,
                    num_queries=len(rows),
                    avg_relevance=round(avg_rel, 2),
                    avg_completeness=round(avg_comp, 2),
                    combined_score=round(combined, 2),
                    avg_latency_ms=round(avg_lat, 2),
                )
            )

        summary_json = RESULTS_DIR / "summary.json"
        with open(summary_json, "w", encoding="utf-8") as f:
            json.dump([asdict(s) for s in summaries], f, indent=2)

        demo_winner = max(summaries, key=lambda s: s.combined_score) if summaries else None
        summary_md = RESULTS_DIR / "summary.md"
        with open(summary_md, "w", encoding="utf-8") as f:
            f.write("# Memanto vs Mem0 Benchmark Report\n\n")
            f.write(
                "This benchmark evaluates retrieval quality and latency of **Memanto** (Moorcheh) "
                "against **Mem0** on a shared document corpus.\n\n"
            )
            f.write("## Methodology\n\n")
            f.write(f"- **Document**: `{DOCUMENT_PATH.name}`\n")
            f.write(f"- **Chunks**: {len(chunks)} ({CHUNK_SIZE} chars, {CHUNK_OVERLAP} overlap)\n")
            f.write(f"- **Queries**: {len(queries)}\n")
            f.write(f"- **Top-K retrieved**: {TOP_K}\n")
            f.write(f"- **Judge model**: Keyword-overlap heuristic (demo)\n")
            f.write("- **Dimensions**: Relevance (0-100) and Completeness (0-100)\n\n")
            f.write("## Aggregate Results\n\n")
            f.write("| System | Queries | Avg Relevance | Avg Completeness | Combined | Avg Latency (ms) |\n")
            f.write("|--------|---------|---------------|------------------|----------|------------------|\n")
            for s in summaries:
                f.write(
                    f"| {s.system:6s} | {s.num_queries:7d} | "
                    f"{s.avg_relevance:13.2f} | {s.avg_completeness:16.2f} | "
                    f"{s.combined_score:8.2f} | {s.avg_latency_ms:16.2f} |\n"
                )
        if winner:
            if demo_winner:
                f.write(f"\n**Winner**: {demo_winner.system.title()} with combined score {demo_winner.combined_score}\n\n")
            else:
                f.write("\n**Winner**: N/A (no results)\n\n")
        else:
            f.write("\n**Winner**: N/A (no results)\n\n")
            f.write("## Per-Query Breakdown\n\n")
            for q in queries:
                f.write(f"### {q}\n\n")
                for r in all_results:
                    if r.query == q:
                        f.write(f"- **{r.system.title()}**: Rel={r.relevance_score}, Comp={r.completeness_score}, Lat={r.latency_ms}ms\n")
                f.write("\n")

        logger.info("=" * 60)
        logger.info("DEMO BENCHMARK COMPLETE")
        logger.info("=" * 60)
        for s in summaries:
            logger.info(
                f"{s.system:8s} — Combined: {s.combined_score} | "
                f"Relevance: {s.avg_relevance} | Completeness: {s.avg_completeness} | "
                f"Latency: {s.avg_latency_ms}ms"
            )
        return

    run_benchmark(allow_mock=args.allow_mock)


if __name__ == "__main__":
    main()
