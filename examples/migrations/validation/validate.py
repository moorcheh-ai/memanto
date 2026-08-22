#!/usr/bin/env python3
"""
Round-trip recall validation for the migration showcase.

Loads validation/golden_qa.json, calls SdkClient.answer for each question
against a migrated agent, and scores each answer with an LLM judge.

Usage:
    python validation/validate.py --agent <agent_id>

Env vars required:
    MOORCHEH_API_KEY      - Memanto API key
    OPENROUTER_API_KEY    - For the LLM judge

Exit codes:
    0  - 8 or more of 10 questions passed
    1  - fewer than 8 passed (or runtime error)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).parent

PASS_THRESHOLD = 8
MIN_SCORE_TO_PASS = 10  # out of 15


def _load_golden(path: Path) -> list[dict]:
    """
    Load golden question-and-answer data from a JSON file.
    
    Parameters:
        path (Path): Path to the JSON file containing the golden data.
    
    Returns:
        list[dict]: Parsed golden question-and-answer records.
    """
    with open(path) as f:
        return json.load(f)


def _build_judge():
    # validate.py lives at examples/migrations/validation/
    # evaluator.py lives at examples/benchmarks/memanto-vs-mem0/
    """Create an LLM judge configured with the validation evaluator model.
    
    Returns:
        LLMJudge: The configured language model judge.
    """
    evaluator_path = _HERE.parent.parent / "benchmarks" / "memanto-vs-mem0" / "evaluator.py"
    if not evaluator_path.exists():
        raise FileNotFoundError(f"evaluator.py not found at {evaluator_path}")
    import importlib.util
    spec = importlib.util.spec_from_file_location("evaluator", evaluator_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["evaluator"] = mod
    spec.loader.exec_module(mod)
    return mod.LLMJudge(model="openai/gpt-4o-mini")


def _print_table(results: list[dict]) -> None:
    """Print validation results in a formatted table.
    
    Parameters:
        results (list[dict]): Validation results to display.
    """
    cols = ["id", "source", "score", "pass", "accuracy", "staleness", "precision"]
    widths = [8, 10, 7, 5, 10, 10, 10]
    header = "  ".join(c.ljust(w) for c, w in zip(cols, widths))
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        row = [
            r["id"].ljust(widths[0]),
            r["source"].ljust(widths[1]),
            str(r["total"]).ljust(widths[2]),
            ("YES" if r["passed"] else "NO ").ljust(widths[3]),
            str(r["accuracy"]).ljust(widths[4]),
            str(r["staleness_avoidance"]).ljust(widths[5]),
            str(r["precision"]).ljust(widths[6]),
        ]
        print("  ".join(row))
    print()


def run(agent_id: str, golden_path: Path) -> int:
    """
    Run round-trip recall validation for an agent against a golden question-and-answer set.
    
    Parameters:
        agent_id (str): Identifier of the agent to activate and evaluate.
        golden_path (Path): Path to the golden question-and-answer JSON file.
    
    Returns:
        int: 0 if the validation meets the pass threshold, otherwise 1.
    """
    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    if not api_key:
        print("ERROR: MOORCHEH_API_KEY is not set", file=sys.stderr)
        return 1

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        print("ERROR: OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    from memanto.cli.client.sdk_client import SdkClient
    from memanto.app.utils.errors import AgentAlreadyExistsError

    client = SdkClient(api_key=api_key)

    try:
        client.create_agent(agent_id, pattern="tool")
    except AgentAlreadyExistsError:
        pass

    client.activate_agent(agent_id, duration_hours=1)

    results = []
    passed = 0

    try:
        golden = _load_golden(golden_path)
        judge = _build_judge()

        for item in golden:
            qid = item["id"]
            question = item["question"]
            golden_answer = item["answer"]
            source = item["source"]

            print(f"  {qid}: {question[:60]}...")

            try:
                resp = client.answer(agent_id, question)
                recalled = resp.get("answer", "") or ""
            except Exception as exc:
                print(f"    answer() failed: {exc}", file=sys.stderr)
                recalled = ""

            try:
                score = judge.score(
                    system_name="memanto",
                    query_id=qid,
                    query=question,
                    golden_answer=golden_answer,
                    stale_signals=[],
                    current_signals=[golden_answer],
                    recalled_answer=recalled,
                )
                ok = score.total >= MIN_SCORE_TO_PASS
                accuracy = score.accuracy
                staleness_avoidance = score.staleness_avoidance
                precision = score.precision
                reasoning = score.reasoning
            except Exception as exc:
                print(f"    judge.score() failed for {qid}: {exc}", file=sys.stderr)
                ok = False
                accuracy = staleness_avoidance = precision = 0
                reasoning = str(exc)

            if ok:
                passed += 1

            results.append({
                "id": qid,
                "source": source,
                "total": accuracy + staleness_avoidance + precision,
                "accuracy": accuracy,
                "staleness_avoidance": staleness_avoidance,
                "precision": precision,
                "passed": ok,
                "reasoning": reasoning,
            })
    finally:
        try:
            client.deactivate_agent(agent_id)
        except Exception as exc:
            print(f"deactivate_agent failed: {exc}", file=sys.stderr)

    _print_table(results)

    print(f"Result: {passed}/{len(golden)} passed  (threshold {PASS_THRESHOLD}/{len(golden)}, min score {MIN_SCORE_TO_PASS}/15)")

    if passed >= PASS_THRESHOLD:
        print("PASS")
        return 0
    else:
        print(f"FAIL  ({PASS_THRESHOLD - passed} more needed)")
        return 1


def main() -> None:
    """Parse command-line arguments and run recall validation for the selected agent."""
    parser = argparse.ArgumentParser(description="Recall validation for migration showcase")
    parser.add_argument("--agent", required=True, help="Agent ID to query")
    parser.add_argument(
        "--golden",
        default=str(_HERE / "golden_qa.json"),
        help="Path to golden_qa.json",
    )
    args = parser.parse_args()
    sys.exit(run(args.agent, Path(args.golden)))


if __name__ == "__main__":
    main()
