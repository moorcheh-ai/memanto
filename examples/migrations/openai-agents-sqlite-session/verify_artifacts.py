#!/usr/bin/env python3
"""
Verify the committed sample artifacts against the committed source snapshot.

Rebuilds a SQLite database from ``sample/source/session_snapshot.json`` (the raw
rows the OpenAI Agents SDK wrote), re-runs the adapter, and proves:

1. the committed OKF bundle is byte-for-byte what the adapter produces;
2. the adapter is deterministic (two runs, identical bytes);
3. the committed report's counts and source hash match reality;
4. Memanto's own OKF loader + mapper accept the bundle (skipped when the
   ``memanto`` package is not importable).

Standard library only, apart from the optional Memanto import in step 4.

    python verify_artifacts.py
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import okf_adapter  # noqa: E402
import parity_check  # noqa: E402

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "sample" / "source" / "session_snapshot.json"
BUNDLE = HERE / "sample" / "okf"
REPORT = HERE / "sample" / "evidence" / "adapter-report.json"
SESSION_ID = "workspace-buddy-demo"


class VerificationError(AssertionError):
    pass


def _restore_snapshot(snapshot: dict, db_path: Path) -> None:
    """Rebuild the SDK's database from the snapshot (schema + rows verbatim)."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        for sql in snapshot["schema"].values():
            conn.execute(sql)
        conn.executemany(
            "INSERT INTO agent_sessions (session_id, created_at, updated_at) "
            "VALUES (:session_id, :created_at, :updated_at)",
            snapshot["agent_sessions"],
        )
        conn.executemany(
            "INSERT INTO agent_messages (id, session_id, message_data, created_at) "
            "VALUES (:id, :session_id, :message_data, :created_at)",
            snapshot["agent_messages"],
        )
        conn.commit()
    finally:
        conn.close()


def _relative_files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _compare_trees(expected: Path, actual: Path) -> list[str]:
    problems: list[str] = []
    expected_files = _relative_files(expected)
    actual_files = _relative_files(actual)

    for missing in sorted(expected_files - actual_files):
        problems.append(f"committed file not reproduced: {missing}")
    for extra in sorted(actual_files - expected_files):
        problems.append(f"regenerated file is not committed: {extra}")
    for name in sorted(expected_files & actual_files):
        if not filecmp.cmp(expected / name, actual / name, shallow=False):
            problems.append(f"content differs: {name}")
    return problems


def verify(session_id: str = SESSION_ID) -> int:
    checks: list[tuple[str, bool, str]] = []

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    committed_report = json.loads(REPORT.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / snapshot["source"]["db_file"]
        _restore_snapshot(snapshot, db_path)

        # The bundle directory name lands in the report, so mirror the committed
        # layout (``sample/okf``) to keep the comparison exact.
        run_1 = tmp_path / "run-1" / BUNDLE.name
        run_2 = tmp_path / "run-2" / BUNDLE.name
        first = okf_adapter.migrate(
            db_path=db_path,
            session_id=session_id,
            out_dir=run_1,
            source_package_version=snapshot["source"]["package_version"],
            generated_at=committed_report["generated_at"],
        )
        second = okf_adapter.migrate(
            db_path=db_path,
            session_id=session_id,
            out_dir=run_2,
            source_package_version=snapshot["source"]["package_version"],
            generated_at=committed_report["generated_at"],
        )

        # 1. Committed bundle == regenerated bundle.
        problems = _compare_trees(BUNDLE, run_1)
        checks.append(
            (
                f"committed bundle matches a fresh run ({len(_relative_files(BUNDLE))} files)",
                not problems,
                "; ".join(problems[:5]),
            )
        )

        # 2. Determinism.
        drift = _compare_trees(run_1, run_2)
        checks.append(
            (
                "adapter output is deterministic across runs",
                not drift,
                "; ".join(drift[:5]),
            )
        )

        # 3. Report truthfulness. The rebuilt database is logically identical but
        # physically a different file, so its read-snapshot hash legitimately
        # differs from the one the committed report recorded.
        volatile = {"read_snapshot_sha256", "db_file"}
        report_matches = (
            first["counts"] == committed_report["counts"]
            and first["mapped"] == committed_report["mapped"]
            and first["skipped"] == committed_report["skipped"]
            and first["output"] == committed_report["output"]
            # Catches a committed report left behind by an older adapter version.
            and first["adapter"] == committed_report["adapter"]
            and {k: v for k, v in first["source"].items() if k not in volatile}
            == {
                k: v for k, v in committed_report["source"].items() if k not in volatile
            }
        )
        checks.append(
            ("committed report matches a fresh run", report_matches, "report drift")
        )
        checks.append(
            (
                "report read-snapshot hash matches the captured source database",
                committed_report["source"]["read_snapshot_sha256"]
                == snapshot["source"]["read_snapshot_sha256"],
                "read_snapshot_sha256 mismatch between report and capture",
            )
        )
        checks.append(("second run is stable", first["counts"] == second["counts"], ""))

        counts = committed_report["counts"]
        source_rows = [
            row for row in snapshot["agent_messages"] if row["session_id"] == session_id
        ]
        checks.append(
            (
                f"every source item is accounted for ({counts['source_items']} items)",
                counts["source_items"] == len(source_rows)
                and counts["source_items_consumed"] == len(source_rows),
                f"snapshot has {len(source_rows)} rows for {session_id}",
            )
        )

    # 4. Memanto round-trip + 5. query parity (both need the memanto package).
    parity = None
    try:
        from memanto.cli.migrate.mappers import map_okf, type_breakdown
        from memanto.cli.migrate.okf_loader import load_okf_bundle
    except ImportError:
        checks.append(
            ("memanto import check skipped (package not installed)", True, "")
        )
        breakdown = None
    else:
        export = load_okf_bundle(BUNDLE)
        rows = map_okf(export)
        breakdown = type_breakdown(rows)
        checks.append(
            (
                f"memanto load_okf_bundle + map_okf yields {len(rows)} memories",
                len(rows) == counts["mapped_documents"] == len(export["memories"]),
                f"loader saw {len(export['memories'])}, mapper produced {len(rows)}",
            )
        )
        checks.append(
            (
                "every mapped memory keeps its source_ref, timestamp and source",
                all(
                    row["source_ref"]
                    and row["created_at"]
                    and row["source"] == okf_adapter.SOURCE_LABEL
                    for row in rows
                ),
                "missing provenance on at least one row",
            )
        )

        # 5. Offline before/after query parity (needs the Memanto mapper above).
        parity = parity_check.load_parity_report(SNAPSHOT, BUNDLE, REPORT, session_id)
        lost = [r["question"] for r in parity["results"] if not r["passed"]]
        checks.append(
            (
                f"all {parity['questions']} questions keep their answer "
                f"(>={parity['fact_coverage_threshold']:.0%} expected facts each, "
                "offline)",
                parity["meets_threshold"],
                f"lost: {'; '.join(lost)}",
            )
        )

    width = max(len(label) for label, _, _ in checks)
    failures = 0
    for label, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        # Pad only when a detail follows, so passing lines carry no trailing
        # whitespace (this output is committed as evidence).
        line = (
            f"[{mark}] {label.ljust(width)}  <- {detail}"
            if not ok
            else f"[{mark}] {label}"
        )
        print(line.rstrip())
        failures += 0 if ok else 1

    print()
    print(f"source items   : {counts['source_items']}")
    print(f"mapped         : {counts['mapped_documents']} {counts['mapped_by_kind']}")
    print(f"skipped        : {counts['skipped_items']} {counts['skipped_by_reason']}")
    if breakdown is not None:
        print(f"memanto types  : {breakdown}")
    if parity is not None:
        print(
            f"query parity   : {parity['passed']}/{parity['questions']} questions "
            "answered on both sides (offline — not live recall)"
        )
    print(f"\n{len(checks) - failures}/{len(checks)} checks passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--session", default=SESSION_ID, help="Session id to verify.")
    args = parser.parse_args(argv)
    try:
        return verify(args.session)
    except (VerificationError, okf_adapter.AdapterError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
