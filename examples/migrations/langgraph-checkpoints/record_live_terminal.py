"""Run the real cloud round trip and render its terminal output to MP4."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[2]
WIDTH, HEIGHT = 1280, 720
FPS = 24
BACKGROUND = "#080C16"
PANEL = "#101827"
WHITE = "#E5E7EB"
MUTED = "#94A3B8"
CYAN = "#22D3EE"
GREEN = "#4ADE80"
RED = "#FB7185"
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
BOX_DRAWING = str.maketrans(dict.fromkeys("┌┐└┘│─┬┴├┤┼╭╮╰╯═╔╗╚╝║╠╣╦╩╬", " "))


@dataclass(frozen=True)
class Event:
    at: float
    text: str
    color: str = WHITE


@dataclass(frozen=True)
class Command:
    key: str
    label: str
    argv: list[str]
    cwd: Path


@dataclass(frozen=True)
class CommandResult:
    key: str
    label: str
    exit_code: int
    output: list[str]


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/CascadiaMono.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


MONO = _font(20)
SMALL = _font(17)


def _path_variants(path: Path | str) -> list[str]:
    text = str(path)
    variants = [
        text,
        text.replace("\\", "/"),
        text.replace("/", "\\"),
        text.replace("\\", "\\\\"),
        text.replace("\\\\", "\\"),
    ]
    # Prefer longer/more-specific forms first so escaped JSON paths redact fully.
    return sorted(dict.fromkeys(variants), key=len, reverse=True)


def _clean(line: str) -> str:
    line = ANSI.sub("", line).replace("\r", "").translate(BOX_DRAWING).strip()
    for source in _path_variants(REPOSITORY):
        line = line.replace(source, "<repo>")
    for source in _path_variants(Path.home()):
        line = line.replace(source, "~")
    # Catch residual absolute Windows home paths that survived escaping quirks.
    line = re.sub(
        r"(?i)(?:[A-Z]:)?(?:\\\\|/)+Users(?:\\\\|/)+[^\\\\/\s\"']+",
        "~",
        line,
    )
    return line


def resolve_venv_python(root: Path) -> Path:
    """Return Scripts/python.exe (Windows) or bin/python (POSIX) under ``root/.venv``."""
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / ".venv" / "bin" / "python3",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No virtualenv Python found under {root / '.venv'} "
        "(expected Scripts/python.exe or bin/python)"
    )


def _append(events: list[Event], started: float, text: str, color: str = WHITE) -> None:
    for line in textwrap.wrap(
        _clean(text), width=94, replace_whitespace=False, drop_whitespace=False
    ) or [""]:
        events.append(Event(time.monotonic() - started, line.rstrip(), color))


def _run(commands: list[Command]) -> tuple[list[Event], list[CommandResult]]:
    started = time.monotonic()
    events = [Event(0.0, "LIVE TERMINAL  |  real commands, local paths redacted", CYAN)]
    results: list[CommandResult] = []
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "COLUMNS": "100", "TERM": "xterm-256color"})
    for command in commands:
        output: list[str] = []
        _append(events, started, "")
        _append(events, started, f"$ {command.label}", CYAN)
        process = subprocess.Popen(
            command.argv,
            cwd=command.cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            output.append(_clean(line))
            _append(events, started, line)
        status = process.wait()
        results.append(CommandResult(command.key, command.label, status, output))
        if status:
            _append(events, started, f"command failed with exit code {status}", RED)
            raise RuntimeError(f"Live demo command failed: {command.label}")
        _append(events, started, "OK", GREEN)
        time.sleep(0.7)
    events.append(
        Event(time.monotonic() - started + 2.0, "Round trip complete.", GREEN)
    )
    return events, results


def _render_frame(events: list[Event], current: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((48, 29), "LANGGRAPH MEMORY ESCAPE", font=SMALL, fill=CYAN)
    draw.text(
        (WIDTH - 48, 29), "LIVE CLOUD ROUND TRIP", font=SMALL, fill=MUTED, anchor="ra"
    )
    draw.rounded_rectangle(
        (42, 76, WIDTH - 42, HEIGHT - 38),
        radius=16,
        fill=PANEL,
        outline="#273550",
        width=2,
    )
    visible = [event for event in events if event.at <= current][-25:]
    y = 103
    for event in visible:
        draw.text((67, y), event.text, font=MONO, fill=event.color)
        y += 23
    return image


def _render(events: list[Event], output: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required on PATH")
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = max(event.at for event in events) + 2.0
    command = [
        ffmpeg,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in range(int(duration * FPS)):
            process.stdin.write(_render_frame(events, frame / FPS).tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("FFmpeg failed to render the live terminal video")


def _commands(agent: str, run_id: str, run_dir: Path) -> list[Command]:
    example_python = resolve_venv_python(ROOT)
    repository_python = resolve_venv_python(REPOSITORY)
    generated_bundle = ROOT / "artifacts" / "langgraph-okf"
    generated_source = ROOT / "artifacts" / "langgraph-checkpoints.sqlite"
    bundle = run_dir / "langgraph-okf"
    golden = ROOT / "golden_qa.json"
    source = run_dir / "langgraph-checkpoints.sqlite"
    roundtrip = run_dir / "memanto-roundtrip-okf"
    export_destination = Path.home() / ".memanto" / f"{agent}-roundtrip-okf"
    source_answers = run_dir / "source-answers.json"
    memanto_answers = run_dir / "memanto-answers.json"
    recall_report = run_dir / "recall-parity.json"
    staged_bundle_label = f"artifacts/runs/{run_id}/langgraph-okf"
    cli = [str(repository_python), "-m", "memanto.cli.main"]
    return [
        Command("source", "python run_demo.py", [str(example_python), "run_demo.py"], ROOT),
        Command(
            "stage_source",
            "python stage_source.py  # freeze source artifacts for this run",
            [
                str(example_python),
                "stage_source.py",
                str(generated_source),
                str(generated_bundle),
                str(run_dir),
            ],
            ROOT,
        ),
        Command(
            "source_questions",
            "python query_source.py  # five source questions",
            [
                str(example_python),
                "query_source.py",
                str(source),
                str(golden),
                "--output",
                str(source_answers),
            ],
            ROOT,
        ),
        Command(
            "dry_run",
            f"memanto migrate okf ./{staged_bundle_label} --dry-run",
            cli + ["migrate", "okf", str(bundle), "--dry-run"],
            REPOSITORY,
        ),
        Command(
            "agent_create",
            f"memanto agent create {agent}",
            cli
            + [
                "agent",
                "create",
                agent,
                "--pattern",
                "project",
                "--description",
                "LangGraph checkpoint migration live demo",
            ],
            REPOSITORY,
        ),
        Command(
            "cloud_import",
            f"memanto migrate okf ./{staged_bundle_label} --agent {agent}",
            cli + ["migrate", "okf", str(bundle), "--agent", agent],
            REPOSITORY,
        ),
        Command(
            "memanto_questions",
            "python query_memanto.py  # same five questions",
            [
                str(repository_python),
                str(ROOT / "query_memanto.py"),
                "--agent",
                agent,
                "--golden",
                str(golden),
                "--output",
                str(memanto_answers),
            ],
            REPOSITORY,
        ),
        Command(
            "parity",
            "python validate_parity.py  # exact question parity",
            [
                str(example_python),
                "validate_parity.py",
                str(source_answers),
                str(memanto_answers),
                "--output",
                str(recall_report),
            ],
            ROOT,
        ),
        Command(
            "okf_export",
            f"memanto memory export --agent {agent} --okf",
            cli
            + [
                "memory",
                "export",
                "--agent",
                agent,
                "--okf",
                "--output",
                str(export_destination),
            ],
            REPOSITORY,
        ),
        Command(
            "stage_export",
            "python stage_bundle.py  # copy export into this evidence run",
            [
                str(example_python),
                "stage_bundle.py",
                str(export_destination),
                str(roundtrip),
            ],
            ROOT,
        ),
        Command(
            "evidence_report",
            "python build_evidence_report.py  # measured run-scoped report",
            [
                str(example_python),
                "build_evidence_report.py",
                "--roundtrip-bundle",
                str(roundtrip),
                "--source",
                str(source),
                "--source-bundle",
                str(bundle),
                "--roundtrip-recall",
                str(recall_report),
                "--source-recall",
                str(source_answers),
                "--run-id",
                run_id,
                "--output-dir",
                str(run_dir),
            ],
            ROOT,
        ),
    ]


def main() -> None:
    from build_evidence_report import (
        merge_import_counts,
        parse_import_counts,
        write_report,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-prefix", default="langgraph-migration")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    run_id = args.run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid4().hex[:8]
    )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("run id may contain only letters, digits, dot, underscore, or dash")
    agent = f"{args.agent_prefix}-{run_id}".lower()
    run_dir = (ROOT / "artifacts" / "runs" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    output = run_dir / "live-terminal-demo.mp4"
    started_at = datetime.now(timezone.utc).isoformat()
    events, command_results = _run(_commands(agent, run_id, run_dir))
    cast = output.with_suffix(".json")
    cast.write_text(
        json.dumps(
            [
                {"at": round(event.at, 3), "text": event.text, "color": event.color}
                for event in events
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _render(events, output)

    def file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    evidence = run_dir / "migration-evidence.json"
    evidence_data = json.loads(evidence.read_text(encoding="utf-8"))
    import_result = next(
        (result for result in command_results if result.key == "cloud_import"),
        None,
    )
    import_counts = (
        parse_import_counts(import_result.output) if import_result is not None else None
    )
    if import_counts is not None:
        evidence_data = merge_import_counts(evidence_data, import_counts)
        write_report(evidence_data, run_dir)

    # Rebuild cast/video hashes after evidence rewrite is already done; evidence
    # itself is hashed after the optional import merge above.
    evidence_md = run_dir / "migration-evidence.md"
    manifest = {
        "run_id": run_id,
        "agent": agent,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "commands": [
            {
                "key": result.key,
                "label": result.label,
                "exit_code": result.exit_code,
                "output": result.output,
            }
            for result in command_results
        ],
        "artifacts": {
            "source_database": {
                "path": "langgraph-checkpoints.sqlite",
                "sha256": file_hash(run_dir / "langgraph-checkpoints.sqlite"),
            },
            "source_okf_bundle": {
                "path": "langgraph-okf",
                "sha256": evidence_data["first_okf_bundle"]["sha256"],
            },
            "source_answers": {
                "path": "source-answers.json",
                "sha256": file_hash(run_dir / "source-answers.json"),
            },
            "memanto_answers": {
                "path": "memanto-answers.json",
                "sha256": file_hash(run_dir / "memanto-answers.json"),
            },
            "recall_parity": {
                "path": "recall-parity.json",
                "sha256": file_hash(run_dir / "recall-parity.json"),
            },
            "roundtrip_okf_bundle": {
                "path": "memanto-roundtrip-okf",
                "sha256": evidence_data["memanto_roundtrip_okf"]["sha256"],
            },
            "evidence": {"path": evidence.name, "sha256": file_hash(evidence)},
            "evidence_markdown": {
                "path": evidence_md.name,
                "sha256": file_hash(evidence_md),
            },
            "cast": {"path": cast.name, "sha256": file_hash(cast)},
            "video": {"path": output.name, "sha256": file_hash(output)},
        },
    }
    manifest_path = run_dir / "run-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(output)
    print(manifest_path)


if __name__ == "__main__":
    main()
