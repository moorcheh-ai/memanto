"""Run the real Agno -> Memanto CLI -> OKF loop inside the demo container."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from adapter import export, read_memories
from answer_checks import ANSWER_MODEL, destination_answers, source_answers
from demo_source import populate

from memanto.app.clients.backend import Backend
from memanto.cli.config.manager import ConfigManager
from memanto.cli.migrate.okf_loader import load_okf_bundle

QUESTIONS = [
    ("When should the weekly report be delivered?", "delivery", "Friday at 16:00 UTC"),
    ("What file formats should the report use?", "format", "Markdown"),
    ("What timezone does the project display?", "locale", "Asia/Kolkata"),
    ("What primary database does the project use?", "storage", "PostgreSQL 16"),
]


def main() -> None:
    if os.environ.get("MEMANTO_DEMO_CONTAINER") != "1":
        raise RuntimeError("Run with the documented isolated Docker Compose service")
    run_id = uuid.uuid4().hex[:12]
    root = Path("/run-artifacts") / run_id
    root.mkdir(parents=True, exist_ok=False)
    timings: list[dict[str, object]] = []

    def command(*args: str) -> None:
        print("\n$ " + " ".join(args), flush=True)
        start = time.perf_counter()
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        text = result.stdout + result.stderr
        print(text, flush=True)
        (root / f"step-{len(timings) + 1}.log").write_text(text, encoding="utf-8")
        timings.append(
            {
                "command": list(args),
                "seconds": time.perf_counter() - start,
                "returncode": result.returncode,
            }
        )
        result.check_returncode()

    try:
        database = root / "agno.db"
        populate(database)
        source = {row["memory_id"]: row for row in read_memories(database, "demo-user")}
        before_answers = source_answers(database)
        (root / "source-answers.json").write_text(
            json.dumps(before_answers, indent=2), encoding="utf-8"
        )
        print(
            f"Agno persisted {len(source)} current memories; the schedule correction replaced its old value."
        )
        summary = export(database, "demo-user", root / "input-okf")
        print(json.dumps(summary, indent=2))
        print("\nReadable OKF sample from the source database:", flush=True)
        sample = next((root / "input-okf" / "memories").glob("*.md"))
        print(sample.read_text(encoding="utf-8"), flush=True)
        config = ConfigManager()
        config.set_backend(Backend.ON_PREM)
        config.set_onprem_config(
            url="http://server:8080",
            embedding_provider="ollama",
            embedding_model="nomic-embed-text",
            llm_provider="ollama",
            llm_model=ANSWER_MODEL,
        )
        agent_id = "agno-demo-" + run_id
        command("memanto", "agent", "create", agent_id, "--pattern", "tool")
        from memanto.cli.commands._shared import get_client

        client = get_client()
        before_import = client.recall(
            agent_id, QUESTIONS[0][0], limit=3, min_similarity=0
        )
        assert before_import.get("count", 0) == 0, (
            "Expected a newly created empty destination"
        )
        print("Before migration: the new Memanto agent has no answer-bearing memories.")
        command("memanto", "migrate", "okf", str(root / "input-okf"), "--dry-run")
        command(
            "memanto", "migrate", "okf", str(root / "input-okf"), "--agent", agent_id
        )
        # SDK recall uses the same live backend as the CLI; no mocked service.
        readiness_start = time.perf_counter()
        readiness_checks = []
        # Moorcheh acknowledges queued writes before the search index is ready.
        # Wait for all four records, independently of the golden answers below.
        while True:
            ready = client.recall(agent_id, "project", limit=100, min_similarity=0)
            readiness_checks.append(ready.get("count", 0))
            if ready.get("count", 0) == len(source):
                break
            if time.perf_counter() - readiness_start > 60:
                raise TimeoutError(
                    "The imported records did not become searchable within 60 seconds"
                )
            time.sleep(0.5)
        readiness_seconds = time.perf_counter() - readiness_start
        answers = destination_answers(client, agent_id, before_answers)
        (root / "generated-answers.json").write_text(
            json.dumps(answers, indent=2, default=str), encoding="utf-8"
        )
        evidence = []
        for question, memory_id, expected in QUESTIONS:
            start = time.perf_counter()
            response = client.recall(agent_id, question, limit=3, min_similarity=0)
            matched = any(
                expected in str(item.get("content", ""))
                for item in response.get("memories", [])
            )
            evidence.append(
                {
                    "question": question,
                    "expected": expected,
                    "source_contains_answer": expected in source[memory_id]["memory"],
                    "destination_retrieved_answer": matched,
                    "recall_seconds": time.perf_counter() - start,
                    "response": response,
                }
            )
            print(
                json.dumps(
                    {
                        key: value
                        for key, value in evidence[-1].items()
                        if key != "response"
                    }
                )
            )
        exported = Path.home() / ".memanto" / "on-prem" / ("export-" + run_id)
        command(
            "memanto",
            "memory",
            "export",
            "--okf",
            "--split",
            "file",
            "--agent",
            agent_id,
            "--output",
            str(exported),
            "--limit",
            "100",
        )
        shutil.copytree(exported, root / "roundtrip-okf")
        roundtrip = load_okf_bundle(root / "roundtrip-okf")
        bodies = [row["body"] for row in roundtrip["memories"]]
        input_bodies = [
            entry["body"] for entry in load_okf_bundle(root / "input-okf")["memories"]
        ]
        intact = len(bodies) == len(source) and all(
            any(original in body for body in bodies) for original in input_bodies
        )
        report = {
            "source": "Agno 3.0.6 SQLite persistence API",
            "scenario": "Scripted demonstration, not a historical personal archive",
            "golden_check": "Answer-bearing retrieval at k=3, not generated-answer quality",
            "questions": evidence,
            "generated_answer_checks": answers,
            "answer_model": ANSWER_MODEL,
            "destination_count_before_import": before_import.get("count", 0),
            "live_import_verified": True,
            "index_readiness_counts": readiness_checks,
            "index_readiness_seconds": readiness_seconds,
            "roundtrip_count": len(bodies),
            "roundtrip_source_text_preserved": intact,
            "savings_report": "The upstream OKF CLI has no savings report or --report option",
        }
        (root / "live-validation.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        assert intact, "Round-trip export lost or changed source memory text"
        assert all(
            item["source_pass"] and item["destination_pass"] for item in answers
        ), "Generated-answer parity check failed; inspect the saved answers"
        assert all(
            row["source_contains_answer"] and row["destination_retrieved_answer"]
            for row in evidence
        ), "At least one golden retrieval check failed"
        print(
            f"Generated answers: {len(answers)}/{len(answers)} pass before and after. "
            f"Round trip: {len(bodies)} complete memory bodies preserved.",
            flush=True,
        )
        print(report["savings_report"], flush=True)
        print(
            "Live import, recall, and OKF export checks passed. Artifacts: " + str(root)
        )
    finally:
        (root / "timings.json").write_text(
            json.dumps(timings, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
