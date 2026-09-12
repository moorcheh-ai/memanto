"""Optional live validation for a LangMem OKF migration.

This runner deliberately does not create, activate, or delete agents. Prepare
and activate a uniquely named demo agent first, then pass its id explicitly.
The import and export steps go through the shipped Memanto CLI; recall uses
the same SDK client underneath the CLI so scores and hit ids are measurable.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.config.manager import ConfigManager
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

HERE = Path(__file__).resolve().parent

try:
    from run import canonical, decode_snapshots, identity, validate_export
except ModuleNotFoundError:  # Loading this file directly from a test runner.
    _run_spec = importlib.util.spec_from_file_location("langmem_run", HERE / "run.py")
    if not _run_spec or not _run_spec.loader:
        raise ImportError("could not load sibling run.py")
    _run = importlib.util.module_from_spec(_run_spec)
    _run_spec.loader.exec_module(_run)
    canonical = _run.canonical
    decode_snapshots = _run.decode_snapshots
    identity = _run.identity
    validate_export = _run.validate_export


def file_bytes(path: Path) -> int:
    """Return bytes for one file or all files in a bundle directory."""
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def compare_records(
    source: list[dict[str, Any]], target: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare exact source snapshots, reporting missing and unexpected ids."""
    source_ids = [identity(row) for row in source]
    target_ids = [identity(row) for row in target]
    if len(set(source_ids)) != len(source_ids) or len(set(target_ids)) != len(
        target_ids
    ):
        raise ValueError("duplicate snapshot identity")
    source_by_id = dict(zip(source_ids, source, strict=True))
    target_by_id = dict(zip(target_ids, target, strict=True))
    mismatches = [
        key
        for key in sorted(source_by_id.keys() & target_by_id.keys())
        if canonical(source_by_id[key]) != canonical(target_by_id[key])
    ]
    return {
        "source_count": len(source),
        "target_snapshot_count": len(target),
        "missing": sorted(source_by_id.keys() - target_by_id.keys()),
        "unexpected": sorted(target_by_id.keys() - source_by_id.keys()),
        "changed": mismatches,
        "exact_match": not (source_by_id.keys() ^ target_by_id.keys())
        and not mismatches,
    }


def recall_report(
    client: SdkClient, agent: str, queries: list[tuple[str, str | None]]
) -> list[dict[str, Any]]:
    """Run target recall and retain raw scores/hits without inventing thresholds."""
    reports: list[dict[str, Any]] = []
    for query, expected in queries:
        started = time.perf_counter()
        result = client.recall(agent_id=agent, query=query, limit=5)
        elapsed_ms = (time.perf_counter() - started) * 1000
        memories = result.get("memories", [])
        hits = [
            {
                "id": memory.get("id"),
                "score": memory.get("score"),
                "content": memory.get("content"),
            }
            for memory in memories
        ]
        reports.append(
            {
                "query": query,
                "expected_phrase": expected,
                "score": hits[0]["score"] if hits else None,
                "hits": hits,
                "positive_top1_match": bool(
                    expected
                    and hits
                    and expected.lower() in str(hits[0]["content"]).lower()
                ),
                "negative_control": expected is None,
                "elapsed_ms": round(elapsed_ms, 3),
            }
        )
    return reports


def bind_client_session(
    client: SdkClient, active_agent: str | None, active_token: str | None, target: str
) -> None:
    """Bind the SDK to the already activated target without changing config."""
    if active_agent != target or not active_token:
        raise RuntimeError(
            f"target agent is not the active agent; activate {target} before running"
        )
    client.agent_id = active_agent
    client.session_token = active_token


def run_command(command: list[str], cwd: Path) -> tuple[float, str]:
    started = time.perf_counter()
    result = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, timeout=120
    )
    output = result.stdout + result.stderr
    _, token = ConfigManager().get_active_session()
    for secret in (os.environ.get("MOORCHEH_API_KEY"), token):
        if secret:
            output = output.replace(secret, "[REDACTED]")
    output = output.replace(str(Path.home()), "~")
    if result.returncode:
        raise RuntimeError(f"CLI command failed ({result.returncode}):\n{output}")
    return time.perf_counter() - started, output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle", type=Path, required=True, help="Local OKF bundle to import"
    )
    parser.add_argument(
        "--source-export",
        type=Path,
        required=True,
        help="JSON export used to create the bundle",
    )
    parser.add_argument(
        "--source-report", type=Path, help="run-report.json providing source queries"
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Prepared, activated, uniquely named demo agent id",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory for the target OKF re-export and report",
    )
    parser.add_argument(
        "--allow-shared-config",
        action="store_true",
        help="Allow an existing ~/.memanto config after checking the target",
    )
    parser.add_argument(
        "--resume-after-import",
        action="store_true",
        help="Skip import after a previous successful import to this same target",
    )
    args = parser.parse_args()

    if not os.environ.get("MOORCHEH_API_KEY", "").strip():
        raise SystemExit(
            "MOORCHEH_API_KEY must be set; the key is never printed or written"
        )
    args.bundle = args.bundle.resolve()
    args.source_export = args.source_export.resolve()
    args.output = args.output.resolve()
    if args.source_report:
        args.source_report = args.source_report.resolve()
    shared_config = Path.home() / ".memanto"
    if (
        any(
            (shared_config / name).exists()
            for name in (".env", "config.yaml", "connections.json")
        )
        and not args.allow_shared_config
    ):
        raise RuntimeError(
            "shared ~/.memanto config exists; use a clean demo account/config "
            "or pass --allow-shared-config after checking the target"
        )
    for path in (args.bundle, args.source_export):
        if not path.exists():
            raise FileNotFoundError(path)
    active_agent, active_token = ConfigManager().get_active_session()
    if active_agent != args.agent or not active_token:
        raise RuntimeError(
            f"target agent is not the active agent; activate {args.agent} before running"
        )
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")

    source_export = json.loads(args.source_export.read_text(encoding="utf-8"))
    source_records = validate_export(source_export)
    # Reserve one per-type export slot so an unexpected target record is visible.
    export_limit = len(source_records) + 1
    if export_limit > 100:
        raise ValueError(
            "source snapshot requires an export limit of "
            f"{export_limit}, but the CLI maximum is 100; reduce the source "
            "snapshot before running the live workflow"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report_path = args.source_report or args.source_export.with_name("run-report.json")
    if not report_path.exists():
        raise FileNotFoundError(
            f"source report required for recall parity: {report_path}"
        )
    source_report = json.loads(report_path.read_text(encoding="utf-8"))
    queries = [
        (str(item["query"]), item.get("expected_phrase"))
        for item in source_report.get("source_retrieval", [])
    ]
    local_snapshots = decode_snapshots(map_okf(load_okf_bundle(args.bundle)))
    if not compare_records(source_records, local_snapshots)["exact_match"]:
        raise ValueError("source export and import bundle do not match")
    repo_root = Path(__file__).resolve().parents[3]
    # Keep every local artifact in a sibling staging directory. A failed run
    # must not leave a partial report that looks like a successful validation.
    with tempfile.TemporaryDirectory(
        prefix=f".{args.output.name}.staging-", dir=args.output.parent
    ) as staging_dir:
        staging = Path(staging_dir)
        target_bundle = staging / "target-okf"

        import_seconds: float | None = None
        import_log = "Import skipped explicitly; existing target is being validated.\n"
        if not args.resume_after_import:
            import_seconds, import_log = run_command(
                [
                    sys.executable,
                    "-m",
                    "memanto",
                    "migrate",
                    "okf",
                    str(args.bundle),
                    "--agent",
                    args.agent,
                ],
                repo_root,
            )
            print(
                "Import completed; retry this run with --resume-after-import "
                "to avoid importing the bundle again.",
                file=sys.stderr,
            )
        (staging / "cli-import.txt").write_text(import_log, encoding="utf-8")
        client = SdkClient(os.environ["MOORCHEH_API_KEY"])
        bind_client_session(client, active_agent, active_token, args.agent)
        recall = recall_report(
            client,
            args.agent,
            queries,
        )
        (staging / "target-recall.json").write_text(
            json.dumps(recall, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Honor the shipped export path boundary, then copy the resulting bundle.
        staged_export = (
            Path.home() / ".memanto" / "exports" / ("langmem-" + uuid.uuid4().hex)
        )
        export_seconds, export_log = run_command(
            [
                sys.executable,
                "-m",
                "memanto",
                "memory",
                "export",
                "--okf",
                "--agent",
                args.agent,
                "--limit",
                str(export_limit),
                "--split",
                "file",
                "--output",
                str(staged_export),
            ],
            repo_root,
        )
        (staging / "cli-export.txt").write_text(export_log, encoding="utf-8")
        shutil.copytree(staged_export, target_bundle)

        target_rows = load_okf_bundle(target_bundle)
        target_snapshots = decode_snapshots(map_okf(target_rows))
        comparison = compare_records(source_records, target_snapshots)
        report = {
            "agent": args.agent,
            "source_records": len(source_records),
            "import": {
                "seconds": round(import_seconds, 3)
                if import_seconds is not None
                else None,
                "skipped": args.resume_after_import,
                "bundle_bytes": file_bytes(args.bundle),
            },
            "target_reexport": {
                "seconds": round(export_seconds, 3),
                "bundle_bytes": file_bytes(target_bundle),
            },
            "source_retrieval": source_report.get("source_retrieval", []),
            "target_recall": recall,
            "snapshot_comparison": comparison,
            "savings": {
                "cost": None,
                "latency": None,
                "note": "No savings claim is made by this workflow.",
            },
        }
        (staging / "live-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if not comparison["exact_match"]:
            # Keep the diagnostic visible even though the invalid staging tree
            # is removed and therefore cannot be inspected at the output path.
            print(json.dumps(report, indent=2, ensure_ascii=False))
            raise SystemExit(
                "Source snapshot conservation failed; see printed snapshot comparison"
            )
        if args.output.exists():
            raise FileExistsError(
                f"refusing to overwrite existing output: {args.output}"
            )
        staging.rename(args.output)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
