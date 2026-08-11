#!/usr/bin/env python3
"""One-command, fail-fast reproduction of the PydanticAI freedom loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_COMMAND_TIMEOUT_SECONDS = 120.0


def run(
    command: list[str],
    *,
    cwd: Path,
    transcript: list[str],
    timeout_seconds: float,
) -> str:
    printable = " ".join(command)
    print(f"\n$ {printable}")
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        timeout_message = (
            f"Command timed out after {timeout_seconds:g} seconds: {printable}\n"
        )
        print(partial, end="")
        print(timeout_message, end="")
        transcript.extend([f"$ {printable}\n", partial, timeout_message])
        raise SystemExit(124) from exc
    print(completed.stdout, end="")
    transcript.extend([f"$ {printable}\n", completed.stdout])
    if completed.returncode:
        raise SystemExit(completed.returncode)
    return completed.stdout


def preview_snapshot(run_root: Path) -> dict[Path, tuple[int, int, str]]:
    """Capture preview identity without relying on a timestamp tolerance window."""
    snapshot: dict[Path, tuple[int, int, str]] = {}
    for path in run_root.glob("*/mapped_preview.json"):
        try:
            payload = path.read_bytes()
            stat = path.stat()
        except FileNotFoundError:
            continue
        snapshot[path.resolve()] = (
            stat.st_mtime_ns,
            stat.st_size,
            hashlib.sha256(payload).hexdigest(),
        )
    return snapshot


def select_invocation_preview(
    run_root: Path,
    before: dict[Path, tuple[int, int, str]],
    bundle: Path,
) -> Path:
    """Return the one changed preview after proving it maps the current bundle."""
    after = preview_snapshot(run_root)
    changed = sorted(
        path for path, signature in after.items() if before.get(path) != signature
    )
    if len(changed) != 1:
        raise SystemExit(
            "Memanto dry-run did not produce exactly one identifiable preview "
            f"(found {len(changed)})"
        )

    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    preview = changed[0]
    actual = json.loads(preview.read_text("utf-8"))
    expected = json.loads(
        json.dumps(
            map_okf(load_okf_bundle(bundle)),
            allow_nan=False,
            ensure_ascii=False,
            default=str,
        )
    )

    # The mapper deliberately stamps each preview row with its migration time,
    # so a fresh in-process mapping cannot reproduce only this runtime field.
    # Every source-derived field must still match the bundle exactly.
    def without_runtime_timestamp(
        rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return [
            {key: value for key, value in row.items() if key != "updated_at"}
            for row in rows
        ]

    if without_runtime_timestamp(actual) != without_runtime_timestamp(expected):
        raise SystemExit(
            "Memanto dry-run preview does not match the bundle from this invocation"
        )
    return preview


def portable_text(value: str, repo: Path) -> str:
    """Remove machine-specific paths, including paths Rich wrapped over lines."""

    def replace_path(text: str, path: Path, replacement: str) -> str:
        pattern = re.escape(str(path)).replace(r"\ ", r"\s+")
        return re.sub(pattern, lambda _match: replacement, text)

    value = replace_path(value, repo, "$REPO")
    return replace_path(value, Path.home(), "$HOME")


def reproduce(
    work: Path,
    transcript_path: Path | None,
    skip_cli: bool,
    force: bool,
    timeout_seconds: float,
) -> Path:
    example = Path(__file__).resolve().parent
    repo = example.parents[2]
    source = work / "source" / "history.json"
    source_report = work / "evidence" / "source-run.json"
    bundle = work / "okf"
    validation_report = work / "evidence" / "validation-report.json"
    reconstruction_report = work / "evidence" / "reconstruction-report.json"
    reconstructed = work / "evidence" / "reconstructed-history.json"
    transcript: list[str] = []
    generated_targets = (work / "source", work / "okf", work / "evidence")
    if any(target.exists() for target in generated_targets) and not force:
        raise SystemExit(
            f"generated artifacts already exist under {work}; pass --force to replace them"
        )
    work.mkdir(parents=True, exist_ok=True)

    run(
        [
            sys.executable,
            str(example / "generate_source.py"),
            "--output",
            str(source),
            "--report",
            str(source_report),
        ],
        cwd=repo,
        transcript=transcript,
        timeout_seconds=timeout_seconds,
    )
    adapter_command = [
        sys.executable,
        str(example / "adapter.py"),
        str(source),
        "--output",
        str(bundle),
    ]
    if force:
        adapter_command.append("--force")
    run(
        adapter_command,
        cwd=repo,
        transcript=transcript,
        timeout_seconds=timeout_seconds,
    )
    if not skip_cli:
        from memanto.cli.config.manager import ConfigManager

        run_root = ConfigManager().get_migrate_dir("okf")
        previews_before = preview_snapshot(run_root)
        cli_output = run(
            [
                sys.executable,
                "-m",
                "memanto",
                "migrate",
                "okf",
                str(bundle),
                "--dry-run",
            ],
            cwd=repo,
            transcript=transcript,
            timeout_seconds=timeout_seconds,
        )
        preview = select_invocation_preview(run_root, previews_before, bundle)
        evidence = work / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(preview, evidence / "memanto-mapped-preview.json")
        (evidence / "memanto-dry-run.txt").write_text(
            portable_text(cli_output, repo), encoding="utf-8"
        )
    run(
        [
            sys.executable,
            str(example / "reconstruct.py"),
            str(bundle),
            "--output",
            str(reconstructed),
            "--report",
            str(reconstruction_report),
        ],
        cwd=repo,
        transcript=transcript,
        timeout_seconds=timeout_seconds,
    )
    run(
        [
            sys.executable,
            str(example / "validate.py"),
            "--source",
            str(source),
            "--bundle",
            str(bundle),
            "--questions",
            str(example / "sample" / "golden_qa.json"),
            "--report",
            str(validation_report),
        ],
        cwd=repo,
        transcript=transcript,
        timeout_seconds=timeout_seconds,
    )

    if transcript_path:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        portable_transcript = portable_text("".join(transcript), repo)
        transcript_path.write_text(portable_transcript, encoding="utf-8")
    print(f"\nFreedom loop verified in: {work}")
    return work


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Keep artifacts here; otherwise a temporary directory is removed on exit.",
    )
    parser.add_argument("--transcript", type=Path)
    parser.add_argument(
        "--skip-cli",
        action="store_true",
        help="Skip only the shipped `memanto migrate okf --dry-run` step.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace artifacts previously generated under --work-dir.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        help="Fail a blocked generator, adapter, or CLI child process after this long.",
    )
    args = parser.parse_args()
    if args.command_timeout_seconds <= 0:
        parser.error("--command-timeout-seconds must be greater than zero")
    if args.work_dir:
        reproduce(
            args.work_dir.resolve(),
            args.transcript,
            args.skip_cli,
            args.force,
            args.command_timeout_seconds,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="pydanticai-okf-demo-") as tmp:
            reproduce(
                Path(tmp),
                args.transcript,
                args.skip_cli,
                args.force,
                args.command_timeout_seconds,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
