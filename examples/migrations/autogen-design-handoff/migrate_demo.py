"""Run a real AutoGen ListMemory -> OKF -> shipped Memanto CLI handoff.

The source events are synthetic. No LLM is called and no private conversations
are used. ListMemory queries return all records, not ranked search results.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from autogen_core.memory import ListMemory, MemoryContent, MemoryMimeType
from autogen_core.model_context import BufferedChatCompletionContext

PROJECT = "Harbor reading lamp"
TYPE_MAP = {"decision": "decision", "constraint": "fact", "procedure": "instruction"}
QUESTIONS = [
    (
        "finish",
        "What is the approved production finish of the Harbor lamp?",
        "warm white RAL 9001",
    ),
    ("light", "What color temperature must the Harbor reading lamp use?", "2700 K"),
    (
        "material",
        "What material is approved for the Harbor lamp shell?",
        "recycled aluminum",
    ),
    ("control", "How should a user dim the Harbor lamp?", "rotary dimmer on the base"),
    (
        "packaging",
        "What packaging is approved for the Harbor lamp?",
        "plastic-free molded pulp",
    ),
    (
        "review",
        "What must the Harbor lamp team check before design handoff?",
        "verify 3 mm cable clearance",
    ),
]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


async def seed_source(output: Path) -> dict[str, Any]:
    """Record actual add/query/update_context calls and serialize their result."""
    memory = ListMemory(name="harbor-design-decisions")
    events = [
        ("finish", "graphite gray", "decision", "superseded"),
        ("light", "2700 K", "constraint", "current"),
        ("material", "recycled aluminum", "decision", "current"),
        ("finish", "warm white RAL 9001", "decision", "current"),
        ("control", "rotary dimmer on the base", "decision", "current"),
        ("packaging", "plastic-free molded pulp", "decision", "current"),
        ("review", "verify 3 mm cable clearance", "procedure", "current"),
    ]
    for sequence, (key, value, kind, status) in enumerate(events):
        await memory.add(
            MemoryContent(
                content=f"{PROJECT}: {key} = {value}. Status: {status}.",
                mime_type=MemoryMimeType.TEXT,
                metadata={
                    "project": PROJECT,
                    "key": key,
                    "value": value,
                    "kind": kind,
                    "status": status,
                    "sequence": sequence,
                    "synthetic": True,
                },
            )
        )
    # The eighth event exercises structured JSON, not just strings.
    await memory.add(
        MemoryContent(
            content={"component": "base", "diameter_mm": 160, "revision": "B"},
            mime_type=MemoryMimeType.JSON,
            metadata={
                "project": PROJECT,
                "kind": "constraint",
                "sequence": 7,
                "synthetic": True,
            },
        )
    )
    checks = []
    for key, question, expected in QUESTIONS:
        response = await memory.query(question)
        answers = [
            r.metadata["value"]
            for r in response.results
            if r.metadata
            and r.metadata.get("key") == key
            and r.metadata.get("status") == "current"
        ]
        checks.append(
            {
                "question": question,
                "answer": answers,
                "passed": answers == [expected],
                "records_returned": len(response.results),
            }
        )
    context = BufferedChatCompletionContext(buffer_size=10)
    await memory.update_context(context)
    messages = await context.get_messages()
    snapshot = memory.dump_component().model_dump(mode="json")
    write_json(output / "source-component.json", snapshot)
    write_json(
        output / "source-operations.json",
        {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "add_calls": 8,
            "query_calls": 6,
            "update_context_calls": 1,
            "context_messages": len(messages),
            "query_semantics": "ListMemory returns all records; answers use metadata status=current.",
            "checks": checks,
        },
    )
    await memory.clear()
    after_clear = len((await memory.query("finish")).results)
    operations = json.loads((output / "source-operations.json").read_text())
    operations["after_clear_count"] = after_clear
    write_json(output / "source-operations.json", operations)
    assert after_clear == 0
    await memory.close()
    return snapshot


def to_okf(component: dict[str, Any], destination: Path) -> dict[str, Any]:
    """Convert only the documented ListMemory component schema, fail closed.

    Preserve every original content/MIME/metadata field in the body rather than
    putting them in Memanto's bounded supporting-data footer. Ordinal + hash IDs
    preserve duplicate records, source ordering, and deterministic rebuilds.
    """
    if component.get("provider") != "autogen_core.memory.ListMemory":
        raise ValueError("Expected autogen_core.memory.ListMemory component")
    records = component.get("config", {}).get("memory_contents")
    if not isinstance(records, list) or not records:
        raise ValueError("Expected non-empty config.memory_contents")
    prepared = []
    for ordinal, record in enumerate(records):
        if record.get("mime_type") not in ("text/plain", "application/json"):
            raise ValueError(f"Unsupported MIME at record {ordinal}; nothing written")
        metadata = record.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object or null")
        payload = canonical(record)
        if len(payload) > 6000:
            raise ValueError("Record exceeds lossless example limit (6000 characters)")
        digest = hashlib.sha256(payload.encode()).hexdigest()
        identifier = f"{ordinal:04d}-{digest[:12]}"
        memory_type = TYPE_MAP.get(metadata.get("kind"), "observation")
        title = f"AutoGen #{ordinal}: {metadata.get('key', 'structured component')}"
        frontmatter = {
            "type": memory_type,
            "title": title,
            "resource": f"autogen-listmemory:{identifier}",
            "tags": ["autogen", "listmemory"],
            "x_memanto": {
                "type": memory_type,
                "source": "autogen-listmemory",
                "provenance": "imported",
            },
        }
        human = (
            record["content"]
            if isinstance(record["content"], str)
            else canonical(record["content"])
        )
        body = (
            f"{human}\n\nSource order: {ordinal}. SHA256: {digest}\n\n"
            f"```autogen-record\n{payload}\n```\n"
        )
        prepared.append((identifier, memory_type, frontmatter, body))
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Refusing to mix a new conversion with an existing bundle")
    destination.mkdir(parents=True, exist_ok=True)
    for identifier, _, frontmatter, body in prepared:
        (destination / f"{identifier}.md").write_text(
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
            + "---\n"
            + body
        )
    return {
        "source_count": len(records),
        "okf_count": len(prepared),
        "type_counts": dict(Counter(x[1] for x in prepared)),
        "skipped": 0,
    }


def recover_records(content: str) -> list[dict[str, Any]]:
    return [
        json.loads(p)
        for p in re.findall(r"```autogen-record\n(.*?)\n```", content, re.S)
    ]


def cli(output: Path, name: str, arguments: list[str]) -> float:
    command = [shutil.which("memanto") or "memanto", *arguments]
    print("$ memanto " + " ".join(arguments).replace(str(output), "RUN"), flush=True)
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    log = result.stdout + result.stderr
    key = os.environ.get("MOORCHEH_API_KEY")
    if key:
        log = log.replace(key, "[REDACTED]")
    log = log.replace(str(Path.home()), "~")
    (output / f"{name}.txt").write_text(log)
    if result.returncode:
        raise RuntimeError(f"{name} failed: see {output / (name + '.txt')}")
    print(f"{name}: complete", flush=True)
    return round(time.perf_counter() - started, 3)


def validate_checks(report: dict[str, Any], source_checks: list[dict[str, Any]]) -> None:
    """Fail the command when the saved integrity or recall evidence fails."""
    failures = []
    if not source_checks or not all(check.get("passed") is True for check in source_checks):
        failures.append("source recall")
    if report.get("mode") == "live-cloud":
        if report.get("lossless_payload_roundtrip") is not True:
            failures.append("roundtrip integrity")
        if not report.get("recall_total") or report.get("recall_passed") != report["recall_total"]:
            failures.append("target recall")
    if failures:
        raise SystemExit("Validation failed: " + ", ".join(failures) + ". Evidence retained.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("run"))
    parser.add_argument(
        "--live",
        action="store_true",
        help="Create cloud agent, import, query and export",
    )
    parser.add_argument(
        "--agent",
        default="autogen-handoff-"
        + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
    )
    parser.add_argument(
        "--existing-empty-agent",
        action="store_true",
        help="Skip creation for an already created, empty demo agent",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(
            "Choose a new output directory; previous evidence must not be overwritten."
        )
    output.mkdir(parents=True)
    snapshot = asyncio.run(seed_source(output))
    print("AutoGen: 8 real add calls, snapshot saved, source cleared to 0 records.", flush=True)
    source_checks = json.loads((output / "source-operations.json").read_text())["checks"]
    report = to_okf(snapshot, output / "source-okf")
    report["timings_seconds"] = {
        "cli_dry_run": cli(
            output,
            "01-dry-run",
            [
                "migrate",
                "okf",
                str(output / "source-okf"),
                "--agent",
                args.agent,
                "--dry-run",
            ],
        )
    }
    report["savings"] = (
        "N/A: shipped OKF migration has no savings report; AutoGen ListMemory is in-process and no embedding bill was measured."
    )
    report["mode"] = "offline"
    if args.live:
        if not os.environ.get("MOORCHEH_API_KEY"):
            raise SystemExit("Set MOORCHEH_API_KEY privately before --live.")
        from memanto.cli.client.sdk_client import SdkClient

        client = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])
        if not args.existing_empty_agent:
            cli(
                output,
                "02-create-agent",
                ["agent", "create", args.agent, "--pattern", "project"],
            )
        client.activate_agent(args.agent, 6)
        before = client.recall(args.agent, "Harbor lamp", limit=10, min_similarity=0.0)
        if before["memories"]:
            raise SystemExit("Target agent is not empty; use a new demo agent.")
        report["target_before_count"] = before["count"]
        report["timings_seconds"]["cli_import"] = cli(
            output,
            "03-import",
            ["migrate", "okf", str(output / "source-okf"), "--agent", args.agent],
        )
        report["timings_seconds"]["cli_export"] = cli(
            output,
            "04-export",
            [
                "memory",
                "export",
                "--agent",
                args.agent,
                "--okf",
                "--split",
                "file",
            ],
        )
        # Respect the CLI export sandbox: use its default data directory, then
        # copy only this synthetic demo bundle into the reproducible evidence.
        shutil.copytree(
            Path.home() / ".memanto" / "exports" / f"{args.agent}_okf",
            output / "exported-okf",
        )
        from memanto.cli.migrate.okf_loader import load_okf_bundle

        exported = load_okf_bundle(output / "exported-okf")["memories"]
        restored = [record for e in exported for record in recover_records(e["body"])]
        original = snapshot["config"]["memory_contents"]
        report["lossless_payload_roundtrip"] = Counter(
            map(canonical, restored)
        ) == Counter(map(canonical, original))
        report["exported_count"] = len(exported)
        for top_k in (3, len(original)):
            checks = []
            for key, question, expected in QUESTIONS:
                started = time.perf_counter()
                result = client.recall(args.agent, question, limit=top_k, min_similarity=0.0)
                records = [
                    r
                    for item in result["memories"]
                    for r in recover_records(item.get("content", ""))
                ]
                answers = [
                    r["metadata"]["value"]
                    for r in records
                    if r.get("metadata", {}).get("key") == key
                    and r["metadata"].get("status") == "current"
                ]
                checks.append(
                    {
                        "question": question,
                        "expected": expected,
                        "answers": answers,
                        "passed": expected in answers,
                        "top_k": top_k,
                        "retrieved_count": len(result["memories"]),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000),
                        "results": result["memories"],
                    }
                )
            if top_k == 3:
                write_json(output / "ranked-top3.json", checks)
                report["ranked_top3_passed"] = sum(c["passed"] for c in checks)
                report["ranked_top3_total"] = len(checks)
            else:
                write_json(output / "recall-after.json", checks)
                report["recall_passed"] = sum(c["passed"] for c in checks)
                report["recall_total"] = len(checks)
                report["recall_scope"] = "equal context volume: all eight demo records; not ranked-search parity"
        report["mode"] = "live-cloud"
        report["agent"] = args.agent
    write_json(output / "migration-summary.json", report)
    print(json.dumps(report, indent=2))
    validate_checks(report, source_checks)


if __name__ == "__main__":
    main()
