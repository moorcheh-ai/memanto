#!/usr/bin/env python3
"""Generate a genuine multi-run PydanticAI message-history archive.

The scenario records decisions made while building this migration example.  A
deterministic FunctionModel keeps reproduction free of API keys, but the Agent
run loop, tool dispatch, run/conversation identifiers, usage accounting, and
serialized ``ModelMessage`` objects all come from PydanticAI. Timestamps are
normalized after the run through the public message dataclasses so repeated
generation is byte-reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

CONVERSATION_ID = "memanto-bounty-1609-pydanticai"
MODEL_NAME = "pydanticai-migration-evidence-model"
FIXED_TIMESTAMP = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

PROMPTS = (
    "For this PydanticAI migration adapter, keep bundles deterministic and fail closed on secrets.",
    "The source is pydantic-ai-slim 2.27.1 and Memanto's current shipped OKF importer uses OKF v0.1.",
    "Look up the submission deadline and prize for the memory portability bounty.",
    "Correction: the merge-ready folder is examples/migrations/pydanticai-history-okf, not pydanticai-to-okf.",
    "I commit to include a real framework run, mapping table, CLI dry run, recall parity, and a sample OKF bundle.",
    "Record a validation milestone for the adapter test suite.",
    "Do not claim a live Moorcheh import unless MOORCHEH_API_KEY was actually used.",
    "Summarize the current migration plan, deadline, and correction.",
)


def _last_user_prompt(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        for part in reversed(message.parts):
            if isinstance(part, UserPromptPart):
                return str(part.content)
    return ""


def model_function(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    last = messages[-1]
    for part in last.parts:
        if isinstance(part, ToolReturnPart):
            if part.tool_name == "lookup_bounty":
                return ModelResponse(
                    parts=[
                        TextPart(
                            "The deadline is August 31, 2026 at 11:59 PM UTC, "
                            "and the top submission earns USD 200."
                        )
                    ]
                )
            if part.tool_name == "record_validation":
                return ModelResponse(
                    parts=[
                        TextPart(
                            "Recorded validation milestone migration-adapter: "
                            "adapter, reconstruction, privacy, and parity tests required."
                        )
                    ]
                )

    prompt = _last_user_prompt(messages)
    lower = prompt.casefold()
    if "look up" in lower and "deadline" in lower:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="lookup_bounty",
                    args={"issue": 1609},
                    tool_call_id="lookup-bounty-1609",
                )
            ]
        )
    if "record a validation milestone" in lower:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="record_validation",
                    args={"name": "migration-adapter", "status": "required"},
                    tool_call_id="record-validation-1",
                )
            ]
        )
    if "summarize" in lower:
        return ModelResponse(
            parts=[
                TextPart(
                    "Use PydanticAI 2.27.1 ModelMessage JSON, migrate it into "
                    "examples/migrations/pydanticai-history-okf, preserve canonical "
                    "sidecars, fail closed on secrets, validate recall parity, and use "
                    "Memanto's shipped OKF v0.1 importer. The bounty deadline is "
                    "August 31, 2026 at 11:59 PM UTC and the prize is USD 200."
                )
            ]
        )
    return ModelResponse(parts=[TextPart("Recorded project memory: " + prompt)])


def normalize_timestamps(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Copy framework messages with deterministic message and part timestamps."""
    normalized: list[ModelMessage] = []
    for index, message in enumerate(messages):
        timestamp = FIXED_TIMESTAMP + timedelta(seconds=index)
        normalized_parts = []
        for part in message.parts:
            part_fields = {field.name for field in fields(part)}
            normalized_parts.append(
                replace(cast(Any, part), timestamp=timestamp)
                if "timestamp" in part_fields
                else part
            )
        normalized.append(
            cast(
                ModelMessage,
                replace(
                    cast(Any, message),
                    parts=normalized_parts,
                    timestamp=timestamp,
                ),
            )
        )
    return normalized


def generate(output: Path, report_path: Path) -> dict[str, Any]:
    model = FunctionModel(model_function, model_name=MODEL_NAME)
    agent = Agent(
        model,
        instructions=(
            "Maintain accurate migration-project context. Preserve corrections and "
            "never invent validation evidence."
        ),
    )

    @agent.tool_plain
    def lookup_bounty(issue: int) -> dict[str, Any]:
        """Return public acceptance facts captured from the bounty issue."""
        return {
            "issue": issue,
            "deadline": "2026-08-31T23:59:00Z",
            "prize_usd": 200,
            "selection": "top submission by the success matrix",
        }

    @agent.tool_plain
    def record_validation(name: str, status: str) -> dict[str, str]:
        """Record a public demo validation milestone."""
        return {"name": name, "status": status, "scope": "public demo data"}

    history: list[ModelMessage] = []
    outputs: list[str] = []
    run_ids: list[str] = []
    for index, prompt in enumerate(PROMPTS, start=1):
        result = agent.run_sync(
            prompt,
            message_history=history,
            conversation_id=CONVERSATION_ID,
            run_id=f"memanto-pydanticai-run-{index:02d}",
        )
        history = result.all_messages()
        outputs.append(str(result.output))
        run_ids.append(result.run_id)

    history = normalize_timestamps(history)
    data = ModelMessagesTypeAdapter.dump_json(history)
    validated_messages = ModelMessagesTypeAdapter.validate_json(data)
    if ModelMessagesTypeAdapter.dump_json(validated_messages) != data:
        raise RuntimeError("PydanticAI schema round-trip changed the source archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data + b"\n")
    report = {
        "generator": "generate_source.py",
        "source_framework": "pydantic-ai-slim",
        "source_framework_version": version("pydantic-ai-slim"),
        "model": MODEL_NAME,
        "model_kind": "FunctionModel",
        "api_key_required": False,
        "conversation_id": CONVERSATION_ID,
        "turns": len(PROMPTS),
        "messages": len(history),
        "run_ids": run_ids,
        "tool_names": ["lookup_bounty", "record_validation"],
        "tool_dispatches": 2,
        "official_schema_round_trip": True,
        "timestamp_policy": (
            "Framework messages normalized from 2026-08-11T12:00:00Z at "
            "one-second intervals"
        ),
        "source_sha256": hashlib.sha256(data + b"\n").hexdigest(),
        "outputs": outputs,
        "honesty_note": (
            "The archive comes from real PydanticAI Agent runs and tool dispatch. "
            "The deterministic FunctionModel supplies scripted public demo prose; "
            "timestamps are normalized after the run for byte reproduction; no "
            "live LLM generation is claimed."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = generate(args.output, args.report)
    print(
        f"Framework : {report['source_framework']} {report['source_framework_version']}"
    )
    print(f"Turns     : {report['turns']}")
    print(f"Messages  : {report['messages']}")
    print(f"Source    : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
