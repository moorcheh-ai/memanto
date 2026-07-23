"""Answer the golden questions from the latest LangGraph checkpoint state."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402


def _latest_states(database: Path) -> dict[tuple[str, str], dict[str, Any]]:
    states: dict[tuple[str, str], dict[str, Any]] = {}
    with closing(sqlite3.connect(database, check_same_thread=False)) as connection:
        saver = SqliteSaver(connection)
        rows = connection.execute(
            "SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoints "
            "ORDER BY thread_id, checkpoint_ns"
        ).fetchall()
        for thread_id, namespace in rows:
            config = {
                "configurable": {
                    "thread_id": str(thread_id),
                    "checkpoint_ns": str(namespace or ""),
                }
            }
            checkpoints = saver.list(config, limit=1)
            try:
                latest = next(checkpoints, None)
            finally:
                checkpoints.close()
            if latest is not None:
                state = latest.checkpoint.get("channel_values") or {}
                if isinstance(state, dict):
                    states[(str(thread_id), str(namespace or ""))] = state
    return states


def _answer(
    states: dict[tuple[str, str], dict[str, Any]], selector: dict[str, Any]
) -> str:
    thread = states[(selector["thread"], selector.get("namespace", ""))]
    value: Any = thread[selector["channel"]]
    if "key" in selector:
        value = value[selector["key"]]
    if "index" in selector:
        value = value[int(selector["index"])]
    return str(value)


def query_source(database: Path, golden_file: Path) -> dict[str, Any]:
    states = _latest_states(database)
    cases = json.loads(golden_file.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case in cases:
        answer = _answer(states, case["source_selector"])
        expected = [str(term) for term in case["expected_terms"]]
        passed = all(term.casefold() in answer.casefold() for term in expected)
        results.append(
            {
                "question": case["question"],
                "answer": answer,
                "expected_terms": expected,
                "passed": passed,
            }
        )
    passed = sum(result["passed"] for result in results)
    return {
        "system": "LangGraph SqliteSaver latest state",
        "questions": len(results),
        "passed": passed,
        "score": passed / len(results) if results else 1.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("golden", type=Path, nargs="?", default=Path("golden_qa.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = query_source(args.database, args.golden)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["score"] != 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
