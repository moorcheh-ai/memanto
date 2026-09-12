#!/usr/bin/env python3
"""Run the guarded cloud half of the Antigravity migration showcase.

The default invocation is a side-effect-free preview. ``--execute`` creates or
reuses a dedicated Memanto agent, imports the sample, validates live recall and
answers, exports OKF, and verifies that every source artifact still rebuilds
byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_round_trip import validate

from memanto.cli.config.manager import ConfigManager

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class LiveCommand:
    label: str
    argv: tuple[str, ...]
    expected_phrases: tuple[str, ...] = ()


def _memanto_executable() -> Path:
    sibling = Path(sys.executable).with_name(
        "memanto.exe" if sys.platform == "win32" else "memanto"
    )
    if sibling.is_file():
        return sibling
    discovered = shutil.which("memanto")
    if discovered is None:
        raise RuntimeError("Memanto CLI not found; install the repository first")
    return Path(discovered)


def _golden_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Golden validation file must contain a JSON list")
    cases: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            raise ValueError("Malformed golden validation case")
        phrases = item.get("expected_phrases")
        if not isinstance(phrases, list) or not all(
            isinstance(phrase, str) and phrase for phrase in phrases
        ):
            raise ValueError("Malformed expected_phrases")
        cases.append(item)
    return cases


def build_commands(
    executable: Path,
    *,
    agent: str,
    okf_path: Path,
    export_path: Path,
    cases: list[dict[str, Any]],
    reuse_agent: bool,
    include_answers: bool,
) -> list[LiveCommand]:
    commands: list[LiveCommand] = []
    exe = str(executable)
    if not reuse_agent:
        commands.append(
            LiveCommand(
                "create-agent",
                (
                    exe,
                    "agent",
                    "create",
                    agent,
                    "--pattern",
                    "project",
                    "--description",
                    "Live Antigravity brain to portable OKF migration demo",
                ),
            )
        )
    commands.extend(
        [
            LiveCommand(
                "import-okf",
                (exe, "migrate", "okf", str(okf_path), "--agent", agent),
            ),
            LiveCommand(
                "activate-agent", (exe, "agent", "activate", agent, "--hours", "6")
            ),
        ]
    )
    for index, case in enumerate(cases, start=1):
        question = str(case["question"])
        recall_phrases = case.get("recall_expected_phrases", case["expected_phrases"])
        expected = tuple(str(phrase) for phrase in recall_phrases)
        commands.append(
            LiveCommand(
                f"recall-{index}",
                (exe, "recall", question, "--limit", "3"),
                expected,
            )
        )
        if include_answers:
            commands.append(
                LiveCommand(
                    f"answer-{index}",
                    (exe, "answer", question, "--limit", "5"),
                )
            )
    commands.append(
        LiveCommand(
            "export-okf",
            (
                exe,
                "memory",
                "export",
                "--agent",
                agent,
                "--okf",
                "--split",
                "file",
                "--output",
                str(export_path),
            ),
        )
    )
    return commands


def staging_export_path(agent: str, evidence_path: Path, data_dir: Path) -> Path:
    digest = hashlib.sha256(str(evidence_path).encode("utf-8")).hexdigest()[:12]
    return data_dir / "exports" / f"{agent}_live_{digest}_okf"


def display_argv(argv: tuple[str, ...]) -> str:
    """Render a shareable command without exposing absolute home paths."""
    cwd = Path.cwd().resolve()
    memanto_data = (Path.home() / ".memanto").resolve()
    rendered: list[str] = []
    for index, value in enumerate(argv):
        path = Path(value)
        if index == 0 and path.name.lower() in {"memanto", "memanto.exe"}:
            rendered.append("memanto")
            continue
        if path.is_absolute():
            resolved = path.resolve()
            try:
                rendered.append(str(resolved.relative_to(cwd)))
                continue
            except ValueError:
                pass
            try:
                relative = resolved.relative_to(memanto_data)
                rendered.append(str(Path("~/.memanto") / relative))
                continue
            except ValueError:
                pass
            rendered.append("<absolute-path-redacted>")
            continue
        rendered.append(value)
    return shlex.join(rendered)


def _run_commands(
    commands: list[LiveCommand], transcript_path: Path
) -> list[dict[str, Any]]:
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    transcript: list[str] = []
    results: list[dict[str, Any]] = []
    for command in commands:
        heading = f"$ {display_argv(command.argv)}"
        print(f"\n[{command.label}]\n{heading}")
        completed = subprocess.run(
            command.argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=child_env,
        )
        output = completed.stdout or ""
        print(output, end="" if output.endswith("\n") else "\n")
        transcript.extend([f"## {command.label}", heading, output.rstrip(), ""])
        result: dict[str, Any] = {
            "label": command.label,
            "exit_code": completed.returncode,
        }
        if command.expected_phrases:
            folded = output.casefold()
            found = [
                phrase
                for phrase in command.expected_phrases
                if phrase.casefold() in folded
            ]
            result["expected_phrases"] = list(command.expected_phrases)
            result["expected_phrases_found"] = found
            result["recall_parity"] = len(found) == len(command.expected_phrases)
        results.append(result)
        transcript_path.write_text("\n".join(transcript), encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"{command.label} failed with exit code {completed.returncode}; "
                f"see {transcript_path}"
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="antigravity-memory-escape-demo")
    parser.add_argument("--source", type=Path, default=ROOT / "sample" / "source")
    parser.add_argument("--okf", type=Path, default=ROOT / "sample" / "okf")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reuse-agent", action="store_true")
    parser.add_argument("--skip-answers", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    try:
        executable = _memanto_executable()
        source = args.source.resolve()
        okf_path = args.okf.resolve()
        output = (
            args.output.resolve()
            if args.output
            else Path(tempfile.gettempdir()) / f"memanto-{args.agent}-evidence"
        )
        exported_evidence = output / "exported-okf"
        config = ConfigManager()
        staged_export = staging_export_path(args.agent, output, config.get_data_dir())
        golden_path = ROOT / "sample" / "golden_qa.json"
        cases = _golden_cases(golden_path)
        commands = build_commands(
            executable,
            agent=args.agent,
            okf_path=okf_path,
            export_path=staged_export,
            cases=cases,
            reuse_agent=args.reuse_agent,
            include_answers=not args.skip_answers,
        )

        print("Live showcase command plan:")
        for command in commands:
            print(f"- {command.label}: {display_argv(command.argv)}")
        print(f"- copy staged export into evidence: {exported_evidence}")
        print("- reconstruct all source artifacts from the exported OKF")
        print(f"- evidence directory: {output}")
        if not args.execute:
            print(
                "\nPreview only. Configure MOORCHEH_API_KEY locally, then rerun "
                "with --execute."
            )
            return 0

        if not config.is_configured():
            raise RuntimeError(
                "Memanto is not configured. Set MOORCHEH_API_KEY locally; never "
                "paste it into source or commit it."
            )
        if output.exists():
            raise RuntimeError(f"Evidence directory already exists: {output}")
        if staged_export.exists():
            raise RuntimeError(f"Staged export already exists: {staged_export}")

        output.mkdir(parents=True)
        try:
            command_results = _run_commands(
                commands, output / "live-cli-transcript.txt"
            )
            shutil.copytree(staged_export, exported_evidence)
            validation = validate(source, exported_evidence, golden_path)
            recall_results = [
                result
                for result in command_results
                if result["label"].startswith("recall-")
            ]
            parity_count = sum(
                bool(result.get("recall_parity")) for result in recall_results
            )
            report = {
                "agent": args.agent,
                "imported_memories": validation["memanto_okf_entries"],
                "exported_source_files_reconstructed": validation[
                    "files_reconstructed_exactly"
                ],
                "lossless_live_round_trip": validation["byte_exact"],
                "source_tree_sha256": validation["source_tree_sha256"],
                "exported_tree_sha256": validation["reconstructed_tree_sha256"],
                "recall_commands_run": len(recall_results),
                "recall_commands_with_full_phrase_parity": parity_count,
                "answer_commands_run": sum(
                    1
                    for result in command_results
                    if result["label"].startswith("answer-")
                ),
                "commands": command_results,
                "exported_okf": "exported-okf",
            }
            (output / "live-cloud-validation.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        finally:
            shutil.rmtree(staged_export, ignore_errors=True)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
