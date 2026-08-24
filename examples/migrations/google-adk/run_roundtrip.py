#!/usr/bin/env python3
"""Run OKF import → Memanto recall → OKF export with a real cloud key."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import adapter
from scenario import GOLDEN_QUESTIONS

from memanto.app.config import get_data_dir

HERE = Path(__file__).resolve().parent
DEFAULT_BUNDLE = HERE / "artifacts" / "adk-live-run" / "google-adk-okf"
DEFAULT_ARTIFACTS = HERE / "artifacts" / "adk-live-run"
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
COMMAND_TIMEOUT_SECONDS = 180
OKF_RESOURCE_RE = re.compile(r"OKF resource:\s*`?([^`\s]+)")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_markdown_tree(root: Path) -> None:
    """Keep generated cloud evidence portable and free of diff-only whitespace."""
    for path in root.rglob("*.md"):
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(
            "\n".join(line.rstrip() for line in lines).rstrip() + "\n",
            encoding="utf-8",
        )


def _source_session_dates(session: dict[str, Any]) -> list[str]:
    """Return every persisted event date, falling back only when none exist."""
    dates = sorted(
        {
            str(event["timestamp"])[:10]
            for event in (session.get("events") or [])
            if event.get("timestamp")
        }
    )
    if not dates and session.get("create_time"):
        dates.append(str(session["create_time"])[:10])
    return dates or ["unknown"]


def _clear_stale_session_summaries(
    agent_id: str, sessions_dir: Path | None = None
) -> int:
    """Remove local derived summaries before importing into a newly created agent."""
    root = sessions_dir or (get_data_dir() / "sessions")
    if not root.is_dir():
        return 0
    removed = 0
    prefix = f"{agent_id}_"
    for path in root.glob("*_summary.md"):
        if path.name.startswith(prefix):
            path.unlink()
            removed += 1
    return removed


def _assert_unique_summary_resources(root: Path) -> int:
    """Reject round-trip evidence containing duplicate active OKF resources."""
    seen: dict[str, Path] = {}
    count = 0
    for path in sorted((root / "sessions").glob("*_summary.md")):
        resources = OKF_RESOURCE_RE.findall(path.read_text(encoding="utf-8"))
        for resource in resources:
            if resource in seen:
                first = seen[resource].relative_to(root).as_posix()
                duplicate = path.relative_to(root).as_posix()
                raise adapter.AdapterError(
                    "Duplicate active OKF resource in session summaries: "
                    f"{resource} ({first}, {duplicate})"
                )
            seen[resource] = path
            count += 1
    return count


def _repair_export_context(root: Path, source_bundle: Path, agent_id: str) -> None:
    """Keep audit links resolvable and account for ADK-to-summary grouping."""
    source_archive = source_bundle / "archive"
    export_archive = root / "archive"
    if source_archive.is_dir():
        shutil.copytree(source_archive, export_archive, dirs_exist_ok=True)

    for section in ("sessions", "daily-summaries"):
        for path in (root / section).glob("*.md"):
            value = path.read_text(encoding="utf-8")
            path.write_text(
                value.replace("](../../archive/", "](../archive/"),
                encoding="utf-8",
            )

    snapshot = adapter.load_snapshot(
        source_bundle / "source" / "google-adk-sqlite-snapshot.json"
    )
    summary_files = sorted((root / "sessions").glob("*_summary.md"))
    summaries_by_date: dict[str, list[Path]] = {}
    for path in summary_files:
        match = re.search(r"_(\d{4}-\d{2}-\d{2})_.*_summary\.md$", path.name)
        if match:
            summaries_by_date.setdefault(match.group(1), []).append(path)

    rows = []
    mapped_summary_names: set[str] = set()
    for session in snapshot.get("sessions", []):
        for source_date in _source_session_dates(session):
            matched = summaries_by_date.get(source_date, [])
            for path in matched:
                mapped_summary_names.add(path.name)
            links = (
                ", ".join(f"[{path.name}](sessions/{path.name})" for path in matched)
                or "No date-grouped summary emitted"
            )
            rows.append(
                f"| `{session.get('session_id', 'unknown')}` | `{source_date}` | "
                f"{links} |"
            )

    unmatched = [
        path for path in summary_files if path.name not in mapped_summary_names
    ]
    mapping_lines = [
        "# Source-session accounting",
        "",
        f"The source bundle contains **{len(snapshot.get('sessions', []))} Google ADK "
        "sessions**. Memanto's OKF export contains "
        f"**{len(summary_files)} date-grouped session summaries** for agent "
        f"`{agent_id}`. These are derived activity views, not a one-to-one rewrite "
        "of source session identifiers; `session_id=unknown` in their filenames is "
        "therefore not presented as source identity.",
        "",
        "| Google ADK source session | Persisted event date (UTC) | Memanto derived summary |",
        "|---|---|---|",
        *rows,
    ]
    if unmatched:
        mapping_lines.extend(
            [
                "",
                "Derived summaries without a same-date source session:",
                *[f"- [{path.name}](sessions/{path.name})" for path in unmatched],
            ]
        )
    mapping_lines.append("")
    (root / "SOURCE_SESSION_MAPPING.md").write_text(
        "\n".join(mapping_lines), encoding="utf-8"
    )

    index_path = root / "index.md"
    index = index_path.read_text(encoding="utf-8").rstrip()
    index_path.write_text(
        index
        + "\n- [Source-session accounting](SOURCE_SESSION_MAPPING.md) — ADK source "
        "sessions mapped to Memanto's date-grouped summaries\n",
        encoding="utf-8",
    )


def _redact_secret_text(value: str, env: dict[str, str]) -> str:
    """Remove the exact configured API key from captured command output."""
    secret = env.get("MOORCHEH_API_KEY", "").strip()
    return value.replace(secret, "<redacted>") if secret else value


def _executable() -> Path:
    name = "memanto.exe" if os.name == "nt" else "memanto"
    sibling = Path(sys.executable).parent / name
    found = sibling if sibling.is_file() else shutil.which("memanto")
    if not found:
        raise adapter.AdapterError(
            "Memanto CLI not found. Run `uv sync --group dev` from the repo root."
        )
    return Path(found)


def _run(
    executable: Path,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    allow_failure: bool = False,
) -> dict[str, Any]:
    command = [str(executable), *args]
    display_command = _redact_secret_text("memanto " + " ".join(args), env)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        partial = str(exc.stdout or "") + str(exc.stderr or "")
        partial = _redact_secret_text(ANSI_RE.sub("", partial), env)
        raise adapter.AdapterError(
            f"Command timed out after {COMMAND_TIMEOUT_SECONDS}s "
            f"({display_command}): {partial[-800:]}"
        ) from exc
    output = _redact_secret_text(
        ANSI_RE.sub(
            "", result.stdout + ("\n" + result.stderr if result.stderr else "")
        ),
        env,
    )
    record = {
        "command": display_command,
        "returncode": result.returncode,
        "output": output.strip(),
    }
    if result.returncode != 0 and not allow_failure:
        raise adapter.AdapterError(
            f"Command failed ({record['command']}): {output[-800:]}"
        )
    return record


def _score(output: str, groups: tuple[tuple[str, ...], ...]) -> float:
    # Rich wraps table cells with ``|`` at terminal boundaries. Normalize the
    # rendered output so a phrase split across lines is still scored intact.
    folded = output.casefold().replace("|", " ")
    folded = re.sub(r"\s+", " ", folded)
    return sum(
        any(alias.casefold() in folded for alias in group) for group in groups
    ) / len(groups)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--agent", help="New Memanto agent id (default: timestamped)")
    parser.add_argument(
        "--reuse-agent",
        action="store_true",
        help="Reuse an already imported agent instead of creating and importing again",
    )
    parser.add_argument("--recall-attempts", type=int, default=6)
    parser.add_argument("--recall-delay", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    if not api_key:
        print(
            "error: MOORCHEH_API_KEY is required for the real cloud round trip; "
            "it is read from the environment and never written to artifacts"
        )
        return 2
    bundle = args.bundle.expanduser().resolve()
    artifacts = args.artifacts.expanduser().resolve()
    if not (bundle / "migration-manifest.json").is_file():
        print(f"error: generated bundle not found: {bundle}")
        return 2
    agent_id = args.agent or datetime.now(timezone.utc).strftime(
        "google-adk-okf-%Y%m%d%H%M%S"
    )
    repo_root = HERE.parents[2]
    try:
        bundle_argument = bundle.relative_to(repo_root).as_posix()
    except ValueError:
        bundle_argument = str(bundle)
    executable = _executable()
    env = {**os.environ, "NO_COLOR": "1", "TERM": "dumb"}
    records = []
    stale_session_summaries_removed = 0

    try:
        if args.reuse_agent:
            records.append(
                _run(
                    executable,
                    ["agent", "activate", agent_id],
                    cwd=repo_root,
                    env=env,
                )
            )
        else:
            records.append(
                _run(
                    executable,
                    [
                        "agent",
                        "create",
                        agent_id,
                        "--pattern",
                        "project",
                        "--description",
                        "Google ADK portable-memory round trip",
                    ],
                    cwd=repo_root,
                    env=env,
                )
            )
            stale_session_summaries_removed = _clear_stale_session_summaries(agent_id)
            records.append(
                _run(
                    executable,
                    ["migrate", "okf", bundle_argument, "--agent", agent_id],
                    cwd=repo_root,
                    env=env,
                )
            )

        recall_results = []
        for question in GOLDEN_QUESTIONS:
            best: dict[str, Any] | None = None
            for attempt in range(1, max(1, args.recall_attempts) + 1):
                record = _run(
                    executable,
                    ["recall", question["question"], "--limit", "5"],
                    cwd=repo_root,
                    env=env,
                    allow_failure=True,
                )
                score = _score(record["output"], question["expected_groups"])
                candidate = {
                    "id": question["id"],
                    "question": question["question"],
                    "attempt": attempt,
                    "score": score,
                    "output": record["output"],
                    "returncode": record["returncode"],
                }
                if best is None or candidate["score"] > best["score"]:
                    best = candidate
                if score == 1.0:
                    break
                if attempt < args.recall_attempts:
                    time.sleep(max(0.0, args.recall_delay))
            assert best is not None
            recall_results.append(best)

        recall_average = sum(item["score"] for item in recall_results) / len(
            recall_results
        )
        _write_json(
            artifacts / "evidence" / "cloud-recall-validation.json",
            {
                "schema": "google-adk-memanto-cloud-recall/v1",
                "agent_id": agent_id,
                "questions": len(recall_results),
                "passed": sum(item["score"] == 1.0 for item in recall_results),
                "average_score": round(recall_average, 4),
                "results": recall_results,
            },
        )

        export_dir = artifacts / "memanto-roundtrip-export"
        cached_export_dir = get_data_dir() / "exports" / f"{agent_id}_okf"
        records.append(
            _run(
                executable,
                [
                    "memory",
                    "export",
                    "--okf",
                    "--agent",
                    agent_id,
                    "--limit",
                    "100",
                    "--split",
                    "file",
                ],
                cwd=repo_root,
                env=env,
            )
        )
        if not cached_export_dir.is_dir():
            raise adapter.AdapterError(
                f"Memanto reported success but export is missing: {cached_export_dir}"
            )
        if export_dir.exists():
            shutil.rmtree(export_dir)
        shutil.copytree(cached_export_dir, export_dir)
        _repair_export_context(export_dir, bundle, agent_id)
        _normalize_markdown_tree(export_dir)
        exported_resources = _assert_unique_summary_resources(export_dir)
        try:
            bundle_label = bundle.relative_to(artifacts).as_posix()
        except ValueError:
            bundle_label = bundle.name
        summary = {
            "schema": "google-adk-memanto-roundtrip/v1",
            "completed_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "agent_id": agent_id,
            "bundle": bundle_label,
            "imported_via": "memanto migrate okf",
            "queried_via": "memanto recall",
            "exported_via": "memanto memory export --okf",
            "questions": len(recall_results),
            "passed": sum(item["score"] == 1.0 for item in recall_results),
            "average_score": round(recall_average, 4),
            "results": recall_results,
            "commands": [
                {
                    "command": record["command"],
                    "returncode": record["returncode"],
                }
                for record in records
            ],
            "stale_session_summaries_removed": stale_session_summaries_removed,
            "unique_exported_resources": exported_resources,
            "export_path": export_dir.name,
            "api_key_persisted_in_artifacts": False,
        }
        _write_json(artifacts / "roundtrip-summary.json", summary)
    except (OSError, adapter.AdapterError) as exc:
        print(f"error: {exc}")
        return 2

    print(
        f"OK: cloud round trip completed for {agent_id}; "
        f"recall parity {summary['average_score']:.0%}"
    )
    return 0 if summary["average_score"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
