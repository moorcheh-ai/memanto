"""Run the real cloud round trip and render its terminal output to MP4."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

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
    label: str
    argv: list[str]
    cwd: Path


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


def _clean(line: str) -> str:
    line = ANSI.sub("", line).replace("\r", "").translate(BOX_DRAWING).strip()
    home = str(Path.home())
    replacements = [
        (str(REPOSITORY), "<repo>"),
        (home, "~"),
        (str(REPOSITORY).replace("\\", "/"), "<repo>"),
        (home.replace("\\", "/"), "~"),
    ]
    for source, replacement in replacements:
        line = line.replace(source, replacement)
    return line


def _append(events: list[Event], started: float, text: str, color: str = WHITE) -> None:
    for line in textwrap.wrap(
        _clean(text), width=94, replace_whitespace=False, drop_whitespace=False
    ) or [""]:
        events.append(Event(time.monotonic() - started, line.rstrip(), color))


def _run(commands: list[Command]) -> list[Event]:
    started = time.monotonic()
    events = [Event(0.0, "LIVE TERMINAL  |  real commands, local paths redacted", CYAN)]
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "COLUMNS": "100", "TERM": "xterm-256color"})
    for command in commands:
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
            _append(events, started, line)
        status = process.wait()
        if status:
            _append(events, started, f"command failed with exit code {status}", RED)
            raise RuntimeError(f"Live demo command failed: {command.label}")
        _append(events, started, "OK", GREEN)
        time.sleep(0.7)
    events.append(
        Event(time.monotonic() - started + 2.0, "Round trip complete.", GREEN)
    )
    return events


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


def _commands(agent: str, roundtrip: Path, recall_report: Path) -> list[Command]:
    example_python = ROOT / ".venv" / "Scripts" / "python.exe"
    repository_python = REPOSITORY / ".venv" / "Scripts" / "python.exe"
    if not example_python.is_file() or not repository_python.is_file():
        raise FileNotFoundError(
            "Install both example and repository virtual environments"
        )
    bundle = ROOT / "artifacts" / "langgraph-okf"
    preference = (
        bundle / "memories" / "preference" / "report-format-preference-markdown.md"
    )
    golden = ROOT / "golden_qa.json"
    cli = [str(repository_python), "-m", "memanto.cli.main"]
    return [
        Command("python run_demo.py", [str(example_python), "run_demo.py"], ROOT),
        Command(
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
            f"memanto migrate okf ./artifacts/langgraph-okf --agent {agent}",
            cli + ["migrate", "okf", str(bundle), "--agent", agent],
            REPOSITORY,
        ),
        Command(
            "python show_preference.py  # readable OKF",
            [
                str(example_python),
                "-c",
                f"from pathlib import Path; print(Path({str(preference)!r}).read_text())",
            ],
            ROOT,
        ),
        Command(
            "memanto answer 'Which report format is current?'",
            cli
            + [
                "answer",
                (
                    "Which format should Atlas launch reports use now? "
                    "Answer in one short sentence without em dashes."
                ),
                "--limit",
                "5",
            ],
            REPOSITORY,
        ),
        Command(
            f"memanto memory export --agent {agent} --okf",
            cli
            + [
                "memory",
                "export",
                "--agent",
                agent,
                "--okf",
                "--output",
                str(roundtrip),
            ],
            REPOSITORY,
        ),
        Command(
            "python validate_bundle.py <roundtrip-okf>",
            [
                str(example_python),
                "validate_bundle.py",
                str(roundtrip),
                str(golden),
                "--report",
                str(recall_report),
            ],
            ROOT,
        ),
        Command(
            "python build_evidence_report.py <roundtrip-okf>",
            [
                str(example_python),
                "build_evidence_report.py",
                "--roundtrip-bundle",
                str(roundtrip),
                "--roundtrip-recall",
                str(recall_report),
            ],
            ROOT,
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts" / "live-terminal-demo.mp4"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="memanto-live-demo-") as temp_dir:
        temp = Path(temp_dir)
        events = _run(
            _commands(
                args.agent,
                Path.home() / ".memanto" / f"{args.agent}-roundtrip-okf",
                temp / "roundtrip-recall.json",
            )
        )
    cast = args.output.with_suffix(".json").resolve()
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
    _render(events, args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
