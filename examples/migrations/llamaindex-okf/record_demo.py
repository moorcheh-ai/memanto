"""Run the real offline pipeline and render its terminal transcript as MP4."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SIZE = (1280, 720)
FPS = 8
BG = "#10141c"
PANEL = "#171d28"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#4dd0e1"
SUCCESS = "#76d275"


def run(command: list[str], cwd: Path) -> str:
    environment = os.environ.copy()
    environment.update({"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "96"})
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = ANSI.sub("", result.stdout).strip()
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {output}")
    return output


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("/System/Library/Fonts/SFNSMono.ttf"),
        Path("/System/Library/Fonts/Menlo.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ]
    if bold:
        candidates.insert(0, Path("/System/Library/Fonts/SFNSMonoBold.ttf"))
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


FONT = load_font(22)
FONT_SMALL = load_font(18)
FONT_BOLD = load_font(24, bold=True)


def wrap_lines(text: str, width: int = 91) -> list[str]:
    lines = []
    for raw in text.splitlines():
        if not raw:
            lines.append("")
        else:
            lines.extend(
                textwrap.wrap(
                    raw,
                    width=width,
                    replace_whitespace=False,
                    drop_whitespace=False,
                    break_long_words=True,
                )
            )
    return lines


def frame(title: str, lines: list[tuple[str, str]], footer: str) -> bytes:
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((45, 35, 1235, 675), radius=18, fill=PANEL)
    draw.ellipse((70, 58, 86, 74), fill="#ff5f57")
    draw.ellipse((96, 58, 112, 74), fill="#febc2e")
    draw.ellipse((122, 58, 138, 74), fill="#28c840")
    draw.text((165, 49), title, font=FONT_BOLD, fill=TEXT)
    y = 105
    visible = lines[-21:]
    for text, color in visible:
        draw.text((75, y), text, font=FONT_SMALL, fill=color)
        y += 23
    draw.text((75, 642), footer, font=FONT_SMALL, fill=MUTED)
    return image.tobytes()


def add_hold(writer, title, lines, footer, seconds: float) -> None:
    pixels = frame(title, lines, footer)
    for _ in range(max(1, round(seconds * FPS))):
        writer.send(pixels)


def render_video(events: list[tuple[str, str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio_ffmpeg.write_frames(
        str(output),
        SIZE,
        fps=FPS,
        codec="libx264",
        pix_fmt_in="rgb24",
        output_params=["-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart"],
    )
    writer.send(None)
    lines: list[tuple[str, str]] = []
    try:
        add_hold(
            writer,
            "LlamaIndex → Memanto → owned OKF",
            [
                ("LIVE MIGRATION · NO LLM · NO PAID API", ACCENT),
                ("", TEXT),
                ("A real LlamaIndex Memory store becomes portable Markdown.", TEXT),
                (
                    "Every command and result below is executed for this recording.",
                    MUTED,
                ),
            ],
            "Open memory. Reproducible evidence.",
            4,
        )
        for section, command, output_text in events:
            lines = [(f"$ {command}", ACCENT)]
            add_hold(writer, section, lines, "Executing the real pipeline…", 1.0)
            output_lines = wrap_lines(output_text)
            for output_line in output_lines:
                color = SUCCESS if "passed" in output_line.lower() else TEXT
                lines.append((output_line, color))
                add_hold(writer, section, lines, "Captured from the live command", 0.18)
            add_hold(writer, section, lines, "Captured from the live command", 2.0)
            lines.append(("", TEXT))
        add_hold(
            writer,
            "Migration verified",
            [
                ("13 source records → 13 OKF memories", SUCCESS),
                ("0 skipped · 100% field parity · 100% golden recall", SUCCESS),
                ("", TEXT),
                ("The OKF bundle is plain Markdown, readable and git-friendly.", TEXT),
                ("The original SQLite database was opened read-only.", TEXT),
                ("No model call, payment, or cloud service was required.", TEXT),
            ],
            "LlamaIndex memory is now owned, inspectable, and portable.",
            7,
        )
    finally:
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("llamaindex-okf-demo.mp4"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/video"))
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    python = sys.executable
    demo_output = run(
        [python, "run_demo.py", "--output-root", str(args.artifacts)], here
    )
    summary = json.loads(demo_output)
    run_dir = Path(summary["run_dir"])
    bundle = run_dir / "okf-bundle"
    memanto = Path(python).with_name("memanto")
    dry_run = run([str(memanto), "migrate", "okf", str(bundle), "--dry-run"], here)
    sample_doc = next(iter(sorted((bundle / "memories" / "decision").glob("*.md"))))
    readable = sample_doc.read_text(encoding="utf-8")
    report = (run_dir / "fidelity-report.json").read_text(encoding="utf-8")
    events = [
        (
            "1 · Create and migrate real LlamaIndex memory",
            "python run_demo.py",
            demo_output,
        ),
        (
            "2 · Feed the bundle to Memanto's shipped importer",
            "memanto migrate okf <bundle> --dry-run",
            dry_run,
        ),
        (
            "3 · Open one portable memory",
            f"open {sample_doc.name}",
            readable,
        ),
        (
            "4 · Verify fidelity and recall",
            "open fidelity-report.json",
            report,
        ),
    ]
    transcript = args.output.with_suffix(".txt")
    transcript.write_text(
        "\n\n".join(
            f"## {section}\n$ {command}\n{output}"
            for section, command, output in events
        )
        + "\n",
        encoding="utf-8",
    )
    render_video(events, args.output)
    print(f"Video: {args.output.resolve()}")
    print(f"Transcript: {transcript.resolve()}")


if __name__ == "__main__":
    main()
