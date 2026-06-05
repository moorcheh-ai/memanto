#!/usr/bin/env python3
"""Benchmark Memanto on the LongMemEval dataset.

Usage:
    python long_mem_eval.py --agent-id bench-longmem --num-samples 100

Requires environment variable MOORCHEH_API_KEY.

Install benchmark dependencies:
    pip install -e ".[benchmark]"
"""

import argparse
import json
import os
import sys
import time
from typing import Any

import numpy as np
from datasets import load_dataset
from tqdm import tqdm

from memanto.cli.client.sdk_client import SdkClient


def setup_client(agent_id: str) -> SdkClient:
    """Initialize SdkClient and ensure the agent exists with an active session."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise ValueError("MOORCHEH_API_KEY environment variable not set")
    client = SdkClient(api_key=api_key)
    # Create agent if not exists
    client.post(f"/api/v2/agents/{agent_id}")
    # Activate session
    client.post(f"/api/v2/agents/{agent_id}/activate")
    return client


def load_long_mem_eval(split: str = "test", num_samples: int | None = None) -> list[dict[str, Any]]:
    """Load LongMemEval dataset from Hugging Face.

    Expected format (per example):
    {
        "id": str,
        "conversation": [  # list of turns
            {"role": "user" | "assistant", "content": str}
        ],
        "question": str,
        "expected_answer": str,
    }
    """
    try:
        dataset = load_dataset("moorcheh/long_mem_eval", split=split, streaming=False)
    except Exception as e:
        print(f"Failed to load dataset: {e}", file=sys.stderr)
        print("Make sure you have the `datasets` library installed and internet access.", file=sys.stderr)
        sys.exit(1)

    data = list(dataset)
    if num_samples is not None:
        data = data[:num_samples]
    return data


def evaluate_example(client: SdkClient, agent_id: str, example: dict[str, Any]) -> dict[str, Any]:
    """Run evaluation on a single LongMemEval example.

    Procedure:
    1. Remember each assistant turn as a memory (type='context').
    2. Ask the question via `answer`.
    3. Compare the answer to the expected answer (exact match after normalization).
    """
    example_id = example["id"]
    conversation = example["conversation"]
    question = example["question"]
    expected = example["expected_answer"]

    # Step 1: Store each assistant message as a memory (context type)
    for turn in conversation:
        if turn["role"] == "assistant":
            content = turn["content"]
            # Use remember endpoint
            try:
                resp = client.post(
                    f"/api/v2/agents/{agent_id}/remember",
                    json={
                        "text": content,
                        "type": "context",
                        "provenance": "observed",
                    },
                )
                if resp.status_code not in (200, 201):
                    print(f"Warning: remember failed for turn: {resp.text}", file=sys.stderr)
            except Exception as e:
                print(f"Error remembering turn: {e}", file=sys.stderr)

    # Step 2: Ask the question
    try:
        answer_resp = client.post(
            f"/api/v2/agents/{agent_id}/answer",
            json={
                "question": question,
            },
        )
        if answer_resp.status_code != 200:
            return {
                "id": example_id,
                "question": question,
                "expected": expected,
                "got": None,
                "error": f"Answer endpoint returned {answer_resp.status_code}: {answer_resp.text}",
                "correct": False,
            }
        answer_data = answer_resp.json()
        generated_answer = answer_data.get("answer", "").strip()
    except Exception as e:
        return {
            "id": example_id,
            "question": question,
            "expected": expected,
            "got": None,
            "error": str(e),
            "correct": False,
        }

    # Step 3: Compare (simple exact match, we can improve later)
    correct = _normalize(generated_answer) == _normalize(expected)

    return {
        "id": example_id,
        "question": question,
        "expected": expected,
        "got": generated_answer,
        "error": None,
        "correct": correct,
    }


def _normalize(text: str) -> str:
    """Normalize text for comparison: lower, strip punctuation etc."""
    return text.strip().lower().rstrip(".!?").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Memanto on LongMemEval")
    parser.add_argument(
        "--agent-id",
        default="bench-longmem",
        help="Memanto agent ID to use (created if not exists)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=None,
        help="Number of test samples to evaluate (default: all)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="Maximum number of conversation turns to process per example",
    )
    parser.add_argument(
        "--output",
        default="results_long_mem_eval.json",
        help="Path to output JSON results file",
    )
    args = parser.parse_args()

    print("Setting up Memanto client...")
    client = setup_client(args.agent_id)

    print("Loading LongMemEval dataset (test split)...")
    data = load_long_mem_eval(split="test", num_samples=args.num_samples)
    print(f"Loaded {len(data)} examples.")

    results = []
    print("Running evaluation...")
    for example in tqdm(data, desc="Evaluating examples"):
        # Truncate conversation to max_turns if set
        if args.max_turns and len(example.get("conversation", [])) > args.max_turns:
            example = dict(example)
            example["conversation"] = example["conversation"][: args.max_turns]

        result = evaluate_example(client, args.agent_id, example)
        results.append(result)

    # Compute statistics
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    error_count = sum(1 for r in results if r["error"] is not None)
    accuracy = correct_count / total * 100 if total > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"Results on LongMemEval ({total} samples)")
    print(f"Accuracy: {accuracy:.1f}% ({correct_count}/{total})")
    print(f"Errors: {error_count}")
    print(f"{'='*60}")

    # Save results
    output = {
        "dataset": "moorcheh/long_mem_eval",
        "split": "test",
        "num_samples": total,
        "accuracy": accuracy,
        "correct": correct_count,
        "errors": error_count,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results,
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Detailed results saved to {args.output}")


if __name__ == "__main__":
    main()
