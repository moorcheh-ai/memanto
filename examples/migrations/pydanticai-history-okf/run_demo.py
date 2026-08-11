#!/usr/bin/env python3
"""One-command, fail-fast reproduction of the PydanticAI freedom loop."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(command: list[str], *, cwd: Path, transcript: list[str]) -> str:
    printable = " ".join(command)
    print(f"\n$ {printable}")
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    print(completed.stdout, end="")
    transcript.extend([f"$ {printable}\n", completed.stdout])
    if completed.returncode:
        raise SystemExit(completed.returncode)
    return completed.stdout


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
    )
    if not skip_cli:
        from memanto.cli.config.manager import ConfigManager

        cli_started_ns = time.time_ns()
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
        )
        run_root = ConfigManager().get_migrate_dir("okf")
        previews = [
            path
            for path in run_root.glob("*/mapped_preview.json")
            if path.stat().st_mtime_ns >= cli_started_ns - 1_000_000_000
        ]
        if not previews:
            raise SystemExit("Memanto dry-run preview was not created")
        preview = max(previews, key=lambda path: path.stat().st_mtime_ns)
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
    args = parser.parse_args()
    if args.work_dir:
        reproduce(args.work_dir.resolve(), args.transcript, args.skip_cli, args.force)
    else:
        with tempfile.TemporaryDirectory(prefix="pydanticai-okf-demo-") as tmp:
            reproduce(Path(tmp), args.transcript, args.skip_cli, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
