#!/usr/bin/env python3
"""Run the live Memanto half of the MCP Memory migration showcase.

The default mode is a side-effect-free preview. Pass ``--execute`` only after
configuring a Moorcheh API key; execution creates or reuses a Memanto agent,
imports the sample OKF, runs recall/answer queries, exports OKF again, and
verifies that the MCP graph can still be reconstructed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from migrate_mcp_memory import MigrationError, load_mcp_graph
from reconstruct_mcp_memory import reconstructed_jsonl

from memanto.cli.config.manager import ConfigManager

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class LiveCommand:
    label: str
    argv: tuple[str, ...]


def _memanto_executable() -> Path:
    sibling = Path(sys.executable).with_name("memanto")
    if sibling.is_file():
        return sibling
    discovered = shutil.which("memanto")
    if discovered is None:
        raise RuntimeError(
            "memanto CLI was not found; install the repository before running "
            "the live showcase"
        )
    return Path(discovered)


def _golden_questions(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise MigrationError("golden Q&A file must contain an array")
    questions: list[str] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            raise MigrationError("golden Q&A entry is malformed")
        questions.append(item["question"])
    return questions


def build_commands(
    executable: Path,
    *,
    agent: str,
    okf_path: Path,
    export_path: Path,
    questions: list[str],
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
                    "Live MCP Memory Server to portable OKF migration demo",
                ),
            )
        )
    commands.extend(
        [
            LiveCommand(
                "import-okf",
                (
                    exe,
                    "migrate",
                    "okf",
                    str(okf_path),
                    "--agent",
                    agent,
                ),
            ),
            LiveCommand(
                "activate-agent",
                (exe, "agent", "activate", agent, "--hours", "6"),
            ),
        ]
    )
    for index, question in enumerate(questions, start=1):
        commands.append(
            LiveCommand(
                f"recall-{index}",
                (exe, "recall", question, "--limit", "3"),
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
    """Return a unique export path that satisfies Memanto's write guard.

    Memanto intentionally restricts ``memory export --output`` to its own data
    directory. The digest ties this temporary path to the requested evidence
    directory without exposing that external path to the export command.
    """
    digest = hashlib.sha256(str(evidence_path).encode("utf-8")).hexdigest()[:12]
    return data_dir / "exports" / f"{agent}_live_{digest}_okf"


def display_argv(argv: tuple[str, ...]) -> str:
    """Render a shareable command without exposing the local home path."""
    cwd = Path.cwd().resolve()
    memanto_data = (Path.home() / ".memanto").resolve()
    rendered: list[str] = []
    for index, value in enumerate(argv):
        path = Path(value)
        if index == 0 and path.name == "memanto":
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
        rendered.append(value)
    return shlex.join(rendered)


def _normalized_source(path: Path) -> bytes:
    graph = load_mcp_graph(path)
    records = [entity.raw for entity in graph.entities] + [
        relation.raw for relation in graph.relations
    ]
    return "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    ).encode("utf-8")


def _run_commands(
    commands: list[LiveCommand], transcript_path: Path
) -> list[dict[str, Any]]:
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
        )
        output = completed.stdout or ""
        print(output, end="" if output.endswith("\n") else "\n")
        transcript.extend([f"## {command.label}", heading, output.rstrip(), ""])
        results.append(
            {
                "label": command.label,
                "exit_code": completed.returncode,
            }
        )
        transcript_path.write_text("\n".join(transcript), encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"{command.label} failed with exit code {completed.returncode}; "
                f"see {transcript_path}"
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="mcp-memory-escape-demo",
        help="Dedicated Memanto agent id for the live demo",
    )
    parser.add_argument(
        "--source",
        default=str(ROOT / "sample" / "source" / "memory.jsonl"),
    )
    parser.add_argument(
        "--okf",
        default=str(ROOT / "sample" / "okf"),
    )
    parser.add_argument(
        "--output",
        help="Evidence directory (must not already exist)",
    )
    parser.add_argument(
        "--reuse-agent",
        action="store_true",
        help="Use an existing agent instead of creating one",
    )
    parser.add_argument(
        "--skip-answers",
        action="store_true",
        help="Run retrieval only when the configured answer model is unavailable",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create/import cloud data and run the live showcase",
    )
    args = parser.parse_args()

    try:
        executable = _memanto_executable()
        source = Path(args.source).resolve()
        okf_path = Path(args.okf).resolve()
        output = (
            Path(args.output).resolve()
            if args.output
            else Path(tempfile.gettempdir()) / f"memanto-{args.agent}-evidence"
        )
        export_path = output / "exported-okf"
        staged_export = staging_export_path(
            args.agent, output, ConfigManager().get_data_dir()
        )
        questions = _golden_questions(ROOT / "sample" / "golden_qa.json")
        commands = build_commands(
            executable,
            agent=args.agent,
            okf_path=okf_path,
            export_path=staged_export,
            questions=questions,
            reuse_agent=args.reuse_agent,
            include_answers=not args.skip_answers,
        )

        print("Live showcase command plan:")
        for command in commands:
            print(f"- {command.label}: {display_argv(command.argv)}")
        print(f"- copy staged export into evidence: {export_path}")
        print(f"- reconstruct exported graph from evidence copy: {export_path}")
        print(f"- evidence directory: {output}")
        if not args.execute:
            print(
                "\nPreview only. Configure MOORCHEH_API_KEY locally, then rerun "
                "with --execute."
            )
            return 0

        if not ConfigManager().is_configured():
            raise RuntimeError(
                "Memanto is not configured. Set MOORCHEH_API_KEY in your local "
                "terminal or ~/.memanto/.env; never commit the key."
            )
        if output.exists():
            raise RuntimeError(
                f"evidence directory already exists: {output}; choose a new --output"
            )
        if staged_export.exists():
            raise RuntimeError(
                f"staged export already exists: {staged_export}; choose a new "
                "--output so stale data cannot enter the evidence"
            )
        output.mkdir(parents=True)
        command_results = _run_commands(commands, output / "live-cli-transcript.txt")
        shutil.copytree(staged_export, export_path)

        graph = load_mcp_graph(source)
        source_records = _normalized_source(source)
        exported_records = reconstructed_jsonl(export_path)
        if exported_records != source_records:
            raise MigrationError(
                "live Memanto export did not reconstruct to the source graph"
            )
        report = {
            "agent": args.agent,
            "source_entities": len(graph.entities),
            "source_relations": len(graph.relations),
            "exported_memories_validated": len(graph.entities),
            "source_records_reconstructed": len(graph.entities) + len(graph.relations),
            "source_records_sha256": hashlib.sha256(source_records).hexdigest(),
            "exported_records_sha256": hashlib.sha256(exported_records).hexdigest(),
            "lossless_live_round_trip": True,
            "recall_commands_run": len(questions),
            "golden_questions_recalled": len(questions),
            "answer_commands_run": 0 if args.skip_answers else len(questions),
            "commands": command_results,
            "exported_okf": str(export_path),
        }
        (output / "live-round-trip.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.rmtree(staged_export)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (MigrationError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
