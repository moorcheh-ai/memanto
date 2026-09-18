"""Run the real-service migration after configuring Memanto normally.

This command uploads the public-source selection to two fresh demo agents.
It never deletes the source or claims success from a dry run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adapter import (
    build_bundle,
    digest,
    load_catalog,
    restore_bundle,
    select_catalog,
    unpack,
)

PROBES = [
    ("What is the Attention Display concept?", "attention-display"),
    ("What is AI Fisherman designed to do?", "ai-fisherman"),
    ("What is the Find My Fish concept?", "find-my-fish"),
    ("What is Buildwave intended to build?", "buildwave"),
    ("What is the Picture Us app concept?", "picture-us"),
    ("What is the AquaFlight concept?", "aquaflight"),
    ("What is the Ocean Bubbles proposal?", "ocean-bubbles"),
    ("What is Super Punch intended for?", "super-punch"),
]


def run_cli(output: Path, label: str, *parts: str, key: str | None = None) -> None:
    """Save CLI output and expose redacted failures in the workflow log."""
    proc = subprocess.run(
        [sys.executable, "-m", "memanto.cli.main", *parts],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    transcript = proc.stdout + proc.stderr
    if key:
        transcript = transcript.replace(key, "[REDACTED]")
    (output / f"{label}.txt").write_text(transcript, encoding="utf-8")
    if proc.returncode:
        # Prefix every line so CLI output cannot become a workflow command.
        for line in transcript.splitlines():
            print(f"[{label}] {line}", file=sys.stderr, flush=True)
        raise RuntimeError(f"{label} failed; review its saved log")
    print(f"Completed {label}", flush=True)


def export_and_copy(
    command: Callable[..., None],
    label: str,
    agent: str,
    destination: Path,
    data: dict,
) -> None:
    """Export inside Memanto's approved directory, then collect the bundle."""
    from memanto.app.services.okf_export_service import OkfExportService

    command(
        label,
        "memory",
        "export",
        "--okf",
        "--agent",
        agent,
        "--limit",
        # The CLI limit is per memory type. The entire expected record count
        # (all tiles plus catalogue metadata) covers every type in this fresh
        # demo agent, including catalogues larger than the old fixed limit.
        str(len(data["tiles"]) + 1),
        "--split",
        "file",
    )
    native_bundle = OkfExportService().exports_dir / f"{agent}_okf"
    shutil.copytree(native_bundle, destination, symlinks=True)


def source_recall(data: dict, query: str) -> list[str]:
    terms = set(re.findall(r"\w+", query.lower())) - {
        "what",
        "is",
        "the",
        "to",
        "do",
        "a",
        "for",
        "concept",
        "intended",
        "designed",
        "proposal",
    }
    scored = []
    for tile in data["tiles"]:
        aliases = tile.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        names = " ".join(str(value) for value in [tile["title"], tile["id"], *aliases])
        title = set(re.findall(r"\w+", names.lower()))
        summary = set(re.findall(r"\w+", tile["summary"].lower()))
        scored.append((4 * len(terms & title) + len(terms & summary), tile["id"]))
    return [
        identifier
        for score, identifier in sorted(scored, key=lambda pair: (-pair[0], pair[1]))[
            :5
        ]
        if score > 0
    ]


def remote_recall(agent: str, query: str) -> list[str]:
    from memanto.cli.commands._shared import get_client

    result = get_client().recall(agent_id=agent, query=query, limit=5)
    ids = []
    for memory in result.get("memories", []):
        content = memory.get("content", "")
        if not content:
            continue
        try:
            record = unpack(content)
        except (ValueError, KeyError, TypeError):
            continue
        if record["kind"] == "tile":
            ids.append(record["data"]["id"])
    return ids


def collect_agent_evidence(
    command: Callable[..., None],
    label: str,
    agent: str,
    destination: Path,
    data: dict,
    probes: list[dict[str, Any]],
    stage: str,
) -> None:
    """Keep immediate results and make one fixed post-export measurement.

    Full-data verification is independent of the expected probe answers. This
    does not poll until a query passes or replace an earlier unsuccessful result.
    Export visibility alone does not guarantee semantic retrieval readiness.
    """
    started = time.monotonic()

    def measure(field: str) -> None:
        for probe in probes:
            probe[field] = remote_recall(agent, probe["query"])
            print(
                "Recall observation: "
                + json.dumps(
                    {
                        "field": field,
                        "query": probe["query"],
                        "expected_id": probe["expected_id"],
                        "returned_ids": probe[field],
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                ),
                flush=True,
            )

    measure(f"{stage}_memanto_top5")
    checkpoint = destination.parent / f"{stage}_recall.json"
    checkpoint.write_text(
        json.dumps({"probes": probes, "data_round_trip_complete": False}, indent=2),
        encoding="utf-8",
    )
    export_and_copy(command, label, agent, destination, data)
    if digest(restore_bundle(destination)) != digest(data):
        raise AssertionError(
            f"{stage} real-service export did not preserve all selected fields"
        )
    print(f"Verified complete source data for {stage} agent", flush=True)
    measure(f"{stage}_after_verified_export_top5")
    checkpoint.write_text(
        json.dumps({"probes": probes, "agent_export_verified": True}, indent=2),
        encoding="utf-8",
    )


def retrieval_scores(probes: list[dict[str, Any]]) -> dict[str, int]:
    """Require every recorded scoring stage to pass; never replace older scores."""
    return {
        field: sum(p["expected_id"] in p[field] for p in probes)
        for field in (
            "source_top5",
            "first_memanto_top5",
            "second_memanto_top5",
            "first_after_verified_export_top5",
            "second_after_verified_export_top5",
            "first_after_readiness_top5",
            "second_after_readiness_top5",
        )
        if probes and field in probes[0]
    }


def wait_for_complete_export(
    command: Callable[..., None],
    label: str,
    agent: str,
    destination: Path,
    data: dict,
    *,
    max_attempts: int = 8,
    timeout_seconds: float = 90,
    interval_seconds: float = 2,
) -> dict[str, Any]:
    """Require two successive complete exports without using scored questions.

    This is an application-level visibility barrier, not a backend readiness
    promise. Semantic recall still has to pass independently after this gate.
    The time budget is checked between CLI calls; each CLI call also times out.
    """
    if max_attempts < 2 or timeout_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("Readiness requires at least two attempts and positive limits")
    started = time.monotonic()
    expected = digest(data)
    snapshots = destination.parent / f"{destination.name}_readiness"
    snapshots.mkdir(parents=True, exist_ok=False)
    observations: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "criterion": "two successive native exports exactly reconstruct the entire source",
        "expected_source_sha256": expected,
        "max_attempts": max_attempts,
        "timeout_seconds": timeout_seconds,
        "interval_seconds": interval_seconds,
        "ready": False,
        "observations": observations,
        "limitation": "Complete export visibility does not guarantee semantic retrieval quality",
    }
    evidence_path = snapshots / "readiness.json"

    def save() -> None:
        evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    save()
    consecutive = 0
    for attempt in range(1, max_attempts + 1):
        if time.monotonic() - started >= timeout_seconds:
            break
        snapshot = snapshots / f"attempt-{attempt:02d}"
        # CLI/authentication failures propagate immediately; they are not readiness misses.
        export_and_copy(command, f"{label}_ready_{attempt:02d}", agent, snapshot, data)
        observation: dict[str, Any] = {"attempt": attempt, "complete": False}
        try:
            actual = digest(restore_bundle(snapshot))
            observation["source_sha256"] = actual
            observation["complete"] = actual == expected
        except ValueError as exc:
            observation["validation_error"] = str(exc)
        elapsed = time.monotonic() - started
        observation["elapsed_seconds"] = round(elapsed, 3)
        observations.append(observation)
        consecutive = consecutive + 1 if observation["complete"] else 0
        save()
        print("Readiness observation: " + json.dumps(observation), flush=True)
        if elapsed >= timeout_seconds:
            break
        if consecutive >= 2:
            shutil.copytree(snapshot, destination, symlinks=True)
            evidence["ready"] = True
            evidence["elapsed_seconds"] = round(elapsed, 3)
            save()
            return evidence
        if attempt < max_attempts:
            time.sleep(min(interval_seconds, timeout_seconds - elapsed))
    evidence["failure"] = (
        "Complete source visibility was not confirmed within the limits"
    )
    save()
    raise TimeoutError(evidence["failure"])


def collect_ready_agent_evidence(
    command: Callable[..., None],
    label: str,
    agent: str,
    destination: Path,
    data: dict,
    probes: list[dict[str, Any]],
    stage: str,
) -> dict[str, Any]:
    readiness = wait_for_complete_export(command, label, agent, destination, data)
    field = f"{stage}_after_readiness_top5"
    for probe in probes:
        probe[field] = remote_recall(agent, probe["query"])
        print(
            "Recall observation: "
            + json.dumps(
                {
                    "field": field,
                    "query": probe["query"],
                    "expected_id": probe["expected_id"],
                    "returned_ids": probe[field],
                }
            ),
            flush=True,
        )
    (destination.parent / f"{stage}_recall.json").write_text(
        json.dumps({"probes": probes, "readiness": readiness}, indent=2),
        encoding="utf-8",
    )
    return readiness


def main() -> int:
    from memanto.cli.config.manager import ConfigManager

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--upload-public-source", action="store_true")
    parser.add_argument(
        "--diagnose-immediate",
        action="store_true",
        help="Reproduce v2 immediate/post-export measurements; early misses still fail",
    )
    args = parser.parse_args()
    if not args.upload_public_source:
        parser.error(
            "Pass --upload-public-source only when ready to upload this selection"
        )
    cfg = ConfigManager()
    if not cfg.get_api_key() and str(cfg.get_backend().value) != "on-prem":
        print(
            "BLOCKED: configure the real Moorcheh service through Memanto first. No upload was attempted."
        )
        return 2
    data = select_catalog(load_catalog(args.source), public_only=True)
    available_ids = {t["id"] for t in data["tiles"]}
    if not all(identifier in available_ids for _, identifier in PROBES):
        raise ValueError(
            "This live probe set requires the supplied Voller public-source snapshot"
        )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    build_bundle(data, output / "source_okf")
    key = cfg.get_api_key()

    def command(label: str, *parts: str) -> None:
        run_cli(output, label, *parts, key=key)

    suffix = uuid.uuid4().hex[:12]
    first, second = f"voller-portable-{suffix}-a", f"voller-portable-{suffix}-b"
    baseline: list[dict[str, Any]] = [
        {"query": q, "expected_id": target, "source_top5": source_recall(data, q)}
        for q, target in PROBES
    ]
    command("01_create_first", "agent", "create", first)
    command("02_preview", "migrate", "okf", str(output / "source_okf"), "--dry-run")
    command("03_import", "migrate", "okf", str(output / "source_okf"), "--agent", first)
    collect = (
        collect_agent_evidence
        if args.diagnose_immediate
        else collect_ready_agent_evidence
    )
    readiness_first = collect(
        command, "04_export", first, output / "first_export", data, baseline, "first"
    )
    command("05_create_second", "agent", "create", second)
    command(
        "06_reimport", "migrate", "okf", str(output / "first_export"), "--agent", second
    )
    readiness_second = collect(
        command,
        "07_export_again",
        second,
        output / "second_export",
        data,
        baseline,
        "second",
    )
    scores = retrieval_scores(baseline)
    report = {
        "agents_created": [first, second],
        "selected_tiles": len(data["tiles"]),
        "data_round_trip_passed": True,
        "retrieval_hits_out_of_8": scores,
        "measurement_protocol": (
            "v2: immediate recall, complete export verification, then one additional pass; early misses still fail"
            if args.diagnose_immediate
            else "v3: two successive complete native exports before one scored pass per agent; no scored-query retries"
        ),
        "readiness": {"first": readiness_first, "second": readiness_second},
        "probes": baseline,
        "probe_limit": "Eight named-record retrieval probes; not a general answer-quality or reasoning benchmark",
        "competition_entry_complete": False,
    }
    (output / "live_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"data_round_trip_passed": True, "retrieval_hits_out_of_8": scores},
            indent=2,
        )
    )
    return 0 if all(value == 8 for value in scores.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
