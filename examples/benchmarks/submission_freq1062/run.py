#!/usr/bin/env python3
"""Benchmark orchestrator.

python run.py --dry-run --all
python run.py --datasets locomo --adapters memanto mem0
python run.py --datasets locomo --adapters memanto --output results.json
"""

from __future__ import annotations

import argparse
import json
import os
import warnings
from datetime import datetime

from interfaces import (
    BenchmarkDataset,
    Dataset,
    MemorySystem,
    SystemResults,
    evaluate_query,
    format_category_breakdown,
    format_results_table,
)

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, type[MemorySystem]] = {}


def _discover_adapters() -> None:
    import importlib
    import pkgutil
    from pathlib import Path

    adapters_path = str(Path(__file__).resolve().parent / "adapters")
    for _, name, _ in pkgutil.iter_modules([adapters_path]):
        if name.startswith("_"):
            continue
        mod = importlib.import_module(f"adapters.{name}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and obj is not MemorySystem:
                try:
                    if issubclass(obj, MemorySystem):
                        inst = obj()
                        ADAPTERS[inst.name().lower()] = obj
                except (TypeError, Exception):
                    pass

    # Also register mem0-infer variant (LLM extraction enabled)
    if "mem0" in ADAPTERS and "mem0-infer" not in ADAPTERS:
        from examples.benchmarks.submission_freq1062.adapters.mem0 import Mem0Adapter

        ADAPTERS["mem0-infer"] = lambda: Mem0Adapter(infer=True)


def _load_dotenv() -> None:
    """Load .env from the benchmarks directory into os.environ if present."""
    from pathlib import Path

    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_benchmark(
    dataset: BenchmarkDataset,
    ds_impl: Dataset,
    adapter_cls: type[MemorySystem],
    adapter_kwargs: dict | None = None,
    k: int = 10,
    max_queries: int | None = None,
    judge_fn: callable | None = None,
) -> SystemResults:
    print(f"\n{'=' * 60}")
    print(f"Dataset: {dataset.name}")
    print(f"Adapter: {adapter_cls.__name__}")
    print(f"{'=' * 60}")

    a = adapter_cls(**(adapter_kwargs or {}))
    results = SystemResults(
        system_name=a.name(), dataset_name=dataset.name, configured_k=k
    )

    # Checkpoint file: {adapter}_{dataset}_ckpt.json
    ckpt_path = f"{a.name()}_{dataset.name}_ckpt.json"
    completed_ns: set[str] = set()
    saved_queries: list = []
    if os.path.exists(ckpt_path):
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        completed_ns = set(ckpt.get("completed_namespaces", []))
        # Restore previously-computed query results
        saved_queries = ckpt.get("saved_queries", [])
        results.queries = saved_queries
        if completed_ns:
            print(
                f"  Found checkpoint: {len(completed_ns)} namespaces done, {len(saved_queries)} queries restored"
            )

    try:
        print("  Setting up …")
        a.setup()

        from tqdm import tqdm

        qa_count = len(saved_queries)
        pbar = tqdm(
            total=min(dataset.total_qa_pairs, max_queries or 99999),
            desc=f"  {adapter_cls.__name__}",
            unit="q",
            leave=False,
            ncols=80,
        )
        pbar.update(qa_count)  # account for restored queries
        for ci, conv in enumerate(dataset.conversations):
            ns = f"{dataset.name.lower()}-{conv.sample_id}"

            if ns in completed_ns:
                print(f"  Skipping conv {ci + 1} (checkpointed)")
                qa_count += len(conv.qa_pairs)
                pbar.update(len(conv.qa_pairs))
                continue

            pbar.set_description(f"  Store conv {ci + 1}/{len(dataset.conversations)}")
            a.store_turns(conv.turns, ns)

            pbar.set_description("  Querying")
            for qa in conv.qa_pairs:
                if max_queries and qa_count >= max_queries:
                    break
                qr = evaluate_query(a, qa, ds_impl, ns, k=k, judge_fn=judge_fn)
                results.queries.append(qr)
                qa_count += 1
                pbar.update(1)

            if max_queries and qa_count >= max_queries:
                break

            # Save checkpoint after each conversation (queries + namespaces)
            completed_ns.add(ns)
            with open(ckpt_path, "w") as f:
                json.dump(
                    {
                        "completed_namespaces": list(completed_ns),
                        "saved_queries": results.queries,
                    },
                    f,
                )

        pbar.close()

    finally:
        print("  Tearing down …")
        a.teardown()

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    os.environ.setdefault("POSTHOG_DISABLED", "true")
    _load_dotenv()
    _discover_adapters()

    # Import datasets
    from examples.benchmarks.submission_freq1062.datasets import DATASETS

    parser = argparse.ArgumentParser(
        description="Agentic Memory Showdown — Benchmark Runner",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["locomo"],
        choices=list(DATASETS.keys()),
        help="Datasets to run",
    )
    parser.add_argument(
        "--adapters", nargs="+", default=None, help="Adapters to test (default: all)"
    )
    parser.add_argument("--all", action="store_true", help="Run all adapters")
    parser.add_argument(
        "--list-adapters", action="store_true", help="List adapters and exit"
    )
    parser.add_argument("--sanity", type=str, help="Quick sanity check on one adapter")
    parser.add_argument("--limit", type=int, help="Limit conversations")
    parser.add_argument(
        "--samples", type=int, help="Limit turns per conversation (for quick tests)"
    )
    parser.add_argument("--max-queries", type=int, help="Limit total queries")
    parser.add_argument(
        "--k",
        type=int,
        default=50,
        help="Top-k for recall/precision (default: 50 — enables recall curves)",
    )
    parser.add_argument("--output", type=str, help="Output JSON path")
    parser.add_argument(
        "--cleanup", action="store_true", help="Delete all test resources"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Smoke-test adapters + datasets"
    )
    parser.add_argument(
        "--judge",
        type=str,
        default="groq",
        choices=["groq", "gemini", "local"],
        help="LLM judge provider (default: groq)",
    )
    parser.add_argument(
        "--longmemeval-split",
        type=str,
        default="oracle",
        choices=["oracle", "s"],
        help="LongMemEval split",
    )
    parser.add_argument(
        "--mab-split",
        type=str,
        default="Conflict_Resolution",
        choices=["Accurate_Retrieval", "Conflict_Resolution"],
        help="MemoryAgentBench split",
    )
    args = parser.parse_args()

    # Resolve adapter list
    active = list(ADAPTERS.keys())
    if args.adapters:
        active = args.adapters
    elif not args.all and args.datasets == ["locomo"]:
        pass  # keep all by default

    # --list-adapters
    if args.list_adapters:
        print("Adapters:")
        for name, cls in sorted(ADAPTERS.items()):
            print(f"  {name:15s} → {cls.__name__}")
        print(f"\n{len(ADAPTERS)} total")
        return

    # --sanity
    if args.sanity:
        name = args.sanity.lower()
        if name not in ADAPTERS:
            print(f"Unknown: {name}.  Choices: {list(ADAPTERS)}")
            return
        cls = ADAPTERS[name]
        inst = cls()
        print(f"Sanity check: {inst.name()}")
        ok = inst.dry_run()
        print(f"{'SUCCESS' if ok else 'FAILED'}")
        return

    # --dry-run
    if args.dry_run:
        print(f"\n{'=' * 60}")
        print("DRY RUN")
        print(f"{'=' * 60}")

        # Adapters
        for aname in active:
            if aname not in ADAPTERS:
                print(f"\n  {aname}: UNKNOWN")
                continue
            cls = ADAPTERS[aname]
            print(f"\n--- {cls.__name__} ---")
            inst = cls()
            ok = inst.dry_run()
            print(f"  {aname}: {'SUCCESS' if ok else 'FAILED'}")

        # Datasets
        for dname in args.datasets:
            if dname not in DATASETS:
                print(f"\n  {dname}: UNKNOWN")
                continue
            ds_cls = DATASETS[dname]
            print(f"\n--- {ds_cls.__name__} ---")
            try:
                ds_inst = ds_cls()
                ok = ds_inst.dry_run()
                print(f"  {dname}: {'SUCCESS' if ok else 'FAILED'}")
            except Exception as e:
                print(f"  {dname}: FAILED — {e}")

        print(f"\n{'=' * 60}")
        print("Dry run complete.  Run without --dry-run to execute.")
        print(f"{'=' * 60}")
        return

    # --cleanup
    if args.cleanup:
        print(f"\n{'=' * 60}\nCLEANUP\n{'=' * 60}")
        for aname in active:
            if aname not in ADAPTERS:
                continue
            cls = ADAPTERS[aname]
            print(f"\n  {cls.__name__} …")
            try:
                cls().cleanup()
            except Exception as e:
                print(f"    error: {e}")
        print(f"\n{'=' * 60}\nCleanup complete.\n{'=' * 60}")
        return

    # ---- Normal benchmark mode ----

    # Judge function: default is Groq (the dataset handles this internally
    # when compute_metrics is called without an explicit judge_fn).
    # We only pass a judge_fn for datasets that need it (MemoryAgentBench
    # already defaults to Groq).
    judge_fn = None

    all_results: list[SystemResults] = []

    for dname in args.datasets:
        ds_cls = DATASETS[dname]
        ds_inst = ds_cls()

        kwargs: dict = {}
        if dname == "longmemeval":
            kwargs["split"] = args.longmemeval_split
        elif dname == "memoryagentbench":
            kwargs["split"] = args.mab_split

        print(f"\nLoading: {ds_inst.name} …")
        ds = ds_inst.load(limit=args.limit, max_turns_per_conv=args.samples, **kwargs)
        print(
            f"  {ds.total_qa_pairs} QA pairs, {ds.total_turns} turns, "
            f"{len(ds.conversations)} conversations"
        )

        for aname in active:
            if aname not in ADAPTERS:
                print(f"  Skipping unknown: {aname}")
                continue
            res = run_benchmark(
                ds,
                ds_inst,
                ADAPTERS[aname],
                k=args.k,
                max_queries=args.max_queries,
                judge_fn=judge_fn,
            )
            all_results.append(res)

    # ---- Output ----

    # Define tracks
    TRACKS = {
        "Track 1 — Pure Retrieval (evidence matching)": [
            "locomo",
            "longmemeval",
            "agentmemorybench",
        ],
        "Track 2 — LLM-Judged Retrieval (Groq judge)": [
            "memoryagentbench",
        ],
    }

    print(f"\n{'=' * 70}\nBENCHMARK RESULTS\n{'=' * 70}")

    for track_name, dataset_names in TRACKS.items():
        track_results = [
            r
            for r in all_results
            if any(d in r.dataset_name.lower() for d in dataset_names)
        ]
        if not track_results:
            continue
        print(f"\n## {track_name}\n")
        print(format_results_table(track_results))
        print(format_category_breakdown(track_results))

    if args.output:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "k": args.k,
            "results": [
                {
                    "system": r.system_name,
                    "dataset": r.dataset_name,
                    "total_queries": r.total_queries,
                    "avg_recall_at_k": r.avg_recall_at_k,
                    "avg_precision_at_k": r.avg_precision_at_k,
                    "stale_query_ratio": r.stale_query_ratio,
                    "total_tokens_retrieved": r.total_tokens_retrieved,
                    "p95_latency": r.p95_latency,
                    "p50_latency": r.p50_latency,
                    "per_category": {
                        c: {
                            "count": len(qs),
                            "recall": sum(q.recall_at_k for q in qs) / len(qs),
                            "precision": sum(q.precision_at_k for q in qs) / len(qs),
                            "tokens": sum(q.token_count for q in qs),
                            "latency": sum(q.latency_seconds for q in qs) / len(qs),
                        }
                        for c, qs in r.by_category().items()
                    },
                    "queries": [
                        {
                            "query": q.query,
                            "category": q.category,
                            "recall_at_k": q.recall_at_k,
                            "precision_at_k": q.precision_at_k,
                            "has_stale": q.has_stale,
                            "latency": q.latency_seconds,
                            "tokens": q.token_count,
                            "retrieved_dia_ids": [ri.dia_id for ri in q.retrieved],
                            "evidence_turn_ids": list(q.evidence_turn_ids),
                            "ground_truth": q.ground_truth_answer,
                        }
                        for q in r.queries
                    ],
                }
                for r in all_results
            ],
        }
        with open(args.output, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
