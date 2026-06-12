#!/usr/bin/env python3
"""Claude Code skills memory bridge backed by the Memanto CLI.

This example keeps skill workflows stateless on disk while letting Memanto
persist the engineering decisions that matter across sessions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

CommandRunner = Callable[[list[str]], Any]


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


class SkillMemoryBridge:
    def __init__(
        self,
        runner: CommandRunner = run_command,
        recall_limit: int = 5,
        context_budget: int = 1600,
    ) -> None:
        self.runner = runner
        self.recall_limit = recall_limit
        self.context_budget = context_budget

    def inject_context(self, event: dict[str, Any]) -> dict[str, str]:
        query = self._build_recall_query(event)
        try:
            result = self.runner(
                ["memanto", "recall", query, "--limit", str(self.recall_limit), "--json"]
            )
        except FileNotFoundError:
            return {"additionalContext": ""}

        memories = self._parse_memories(getattr(result, "stdout", ""))
        if not memories:
            return {"additionalContext": ""}

        lines = ["Relevant engineering memory from prior skill runs:"]
        for memory in memories:
            memory_type = memory.get("type", "memory")
            score = memory.get("score")
            score_text = f", score {score:.2f}" if isinstance(score, int | float) else ""
            content = str(memory.get("content", "")).strip()
            if content:
                lines.append(f"- [{memory_type}{score_text}] {content}")

        return {"additionalContext": self._clip("\n".join(lines))}

    def record_completion(self, event: dict[str, Any]) -> dict[str, Any]:
        summary = str(event.get("summary", "")).strip()
        decisions = [
            str(decision).strip()
            for decision in event.get("decisions", [])
            if str(decision).strip()
        ]
        if not summary and not decisions:
            return {"stored": False, "reason": "empty summary"}

        skill = str(event.get("skill", "unknown-skill")).strip() or "unknown-skill"
        task = str(event.get("task", "unspecified task")).strip() or "unspecified task"
        project_path = str(event.get("project_path", "")).strip()
        memory_body = self._format_memory_body(summary, decisions, project_path)
        title = f"Skill {skill} completed: {task}"

        try:
            result = self.runner(
                [
                    "memanto",
                    "remember",
                    title,
                    memory_body,
                    "--type",
                    "decision",
                ]
            )
        except FileNotFoundError:
            return {"stored": False, "reason": "memanto CLI unavailable"}

        return {
            "stored": getattr(result, "returncode", 0) == 0,
            "title": title,
        }

    def _build_recall_query(self, event: dict[str, Any]) -> str:
        skill = str(event.get("skill", "unknown-skill")).strip() or "unknown-skill"
        task = str(event.get("task", "unspecified task")).strip() or "unspecified task"
        project_path = str(event.get("project_path", "unknown project")).strip()
        files = event.get("files", [])
        file_text = ", ".join(str(path) for path in files) if files else "no files"
        return f"Skill {skill} for task {task} in {project_path} touching {file_text}"

    def _parse_memories(self, stdout: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(stdout or "{}")
        except json.JSONDecodeError:
            return []

        if isinstance(payload, dict):
            memories = payload.get("memories", [])
        elif isinstance(payload, list):
            memories = payload
        else:
            memories = []

        return [memory for memory in memories if isinstance(memory, dict)]

    def _format_memory_body(
        self, summary: str, decisions: list[str], project_path: str
    ) -> str:
        parts = []
        if summary:
            parts.append(summary)
        if decisions:
            parts.append("Decisions:\n" + "\n".join(f"- {item}" for item in decisions))
        if project_path:
            parts.append(f"Project path: {project_path}")
        return "\n\n".join(parts)

    def _clip(self, text: str) -> str:
        if len(text) <= self.context_budget:
            return text
        return text[: self.context_budget - 3].rstrip() + "..."


def load_event(raw_event: str | None) -> dict[str, Any]:
    raw = raw_event if raw_event is not None else sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("event JSON must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memanto bridge for Claude Code skills")
    parser.add_argument("mode", choices=["inject", "record"])
    parser.add_argument("--event", help="JSON event payload. Defaults to stdin.")
    args = parser.parse_args(argv)

    bridge = SkillMemoryBridge()
    event = load_event(args.event)
    if args.mode == "inject":
        payload = bridge.inject_context(event)
    else:
        payload = bridge.record_completion(event)

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
