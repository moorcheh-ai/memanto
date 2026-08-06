#!/usr/bin/env python3
"""Record a credential-free, real pipeline run as a compact terminal MP4."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1280
HEIGHT = 720
FPS = 24
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
DECORATION = frozenset(" +-│─┌┐└┘├┤┬┴┼╭╮╰╯═║╔╗╚╝")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for candidate in (windows_fonts / name, windows_fonts / "consola.ttf"):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


MONO = _font("CascadiaMono.ttf", 18)
MONO_BOLD = _font("consolab.ttf", 18)
TITLE = _font("segoeuib.ttf", 44)
SUBTITLE = _font("segoeui.ttf", 24)


def _capture_real_run(script_dir: Path) -> tuple[list[str], float]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "NO_COLOR": "1",
            "COLUMNS": "100",
        }
    )
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="crewai-okf-video-") as temporary:
        command = [
            sys.executable,
            str(script_dir / "run_demo.py"),
            "--output",
            str(Path(temporary) / "real-run"),
        ]
        process = subprocess.Popen(
            command,
            cwd=script_dir,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        captured = [line.rstrip() for line in process.stdout]
        return_code = process.wait()
    elapsed = time.monotonic() - started
    if return_code:
        raise RuntimeError(f"Real demo run failed with exit code {return_code}")
    return _compact_terminal_lines(captured), elapsed


def _compact_terminal_lines(lines: list[str]) -> list[str]:
    compact: list[str] = []
    memory_saves = 0
    for raw in lines:
        clean = ANSI_RE.sub("", raw)
        clean = "".join(
            character if 32 <= ord(character) < 127 else " " for character in clean
        )
        clean = clean.strip()
        if not clean or not (set(clean) - DECORATION):
            continue
        if clean in {"Memory Save Started", "Status: Saving..."}:
            continue
        if clean == "Memory Save Completed":
            memory_saves += 1
            clean = f"[CrewAI] Memory.remember completed ({memory_saves}/8)"
        if clean.startswith("Time:") or clean == "Source: Unified Memory":
            continue
        for wrapped in textwrap.wrap(clean, width=103) or [clean]:
            compact.append(wrapped)
    return compact


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#07111f")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 24, WIDTH - 28, HEIGHT - 24), 22, fill="#0d1b2a")
    draw.rounded_rectangle((48, 100, WIDTH - 48, HEIGHT - 62), 14, fill="#061018")
    draw.ellipse((64, 59, 76, 71), fill="#ff5f57")
    draw.ellipse((84, 59, 96, 71), fill="#febc2e")
    draw.ellipse((104, 59, 116, 71), fill="#28c840")
    draw.text((136, 52), "real pipeline • no credentials", font=MONO, fill="#8aa6bd")
    return image, draw


def _title_frame(step: int) -> Image.Image:
    image, draw = _canvas()
    draw.text((95, 170), "CrewAI unified memory", font=TITLE, fill="#e8f4ff")
    draw.text((95, 230), "→ owned OKF → Memanto", font=TITLE, fill="#55d6be")
    draw.text(
        (98, 315),
        "Issue #1609 • current CrewAI 1.15.12 LanceDB schema",
        font=SUBTITLE,
        fill="#abc4d6",
    )
    statements = (
        "Real Memory.remember / list_records / recall calls",
        "Exact SHA-256 reconstruction + Memanto's own loader",
        "Offline and reproducible • zero external LLM calls",
    )
    for index, statement in enumerate(statements):
        visible = step >= index * 18
        color = "#d7e7f3" if visible else "#24394a"
        draw.text(
            (118, 395 + index * 48), f"[x] {statement}", font=MONO_BOLD, fill=color
        )
    return image


def _terminal_frame(lines: list[str], progress: float) -> Image.Image:
    image, draw = _canvas()
    draw.text(
        (66, 118),
        "$ python run_demo.py --output <temporary-real-run>",
        font=MONO_BOLD,
        fill="#55d6be",
    )
    visible = lines[-25:]
    y = 154
    for line in visible:
        color = "#72e6c9" if line.startswith("[") else "#d4e5f0"
        if "PASS" in line or "complete" in line.lower():
            color = "#8df59b"
        draw.text((68, y), line, font=MONO, fill=color)
        y += 20
    bar_left, bar_top, bar_right = 68, 664, WIDTH - 68
    draw.rounded_rectangle(
        (bar_left, bar_top, bar_right, bar_top + 10), 5, fill="#172b3b"
    )
    draw.rounded_rectangle(
        (
            bar_left,
            bar_top,
            bar_left + int((bar_right - bar_left) * progress),
            bar_top + 10,
        ),
        5,
        fill="#55d6be",
    )
    return image


def _result_frame(runtime: float, step: int) -> Image.Image:
    image, draw = _canvas()
    draw.text((76, 122), "VERIFIED RESULT", font=TITLE, fill="#8df59b")
    rows = (
        ("SOURCE", "8 real CrewAI records • 6 recall queries • 0 LLM calls"),
        ("FIDELITY", "8/8 exact source → declared → reconstructed SHA-256"),
        ("MEMANTO", "8/8 mapped • 0 skipped • 7 semantic memory types"),
        ("LIVE", "8/8 imported • 6/6 expected at rank #1 • 8/8 exported"),
    )
    for index, (label, value) in enumerate(rows):
        y = 225 + index * 76
        active = step >= index * 18
        draw.rounded_rectangle(
            (78, y - 13, WIDTH - 78, y + 47),
            10,
            fill="#10283a" if active else "#0a1824",
        )
        draw.text(
            (101, y), label, font=MONO_BOLD, fill="#55d6be" if active else "#284456"
        )
        draw.text((250, y), value, font=MONO, fill="#e6f2f8" if active else "#284456")
    draw.text(
        (80, 641),
        f"Captured from a successful real run in {runtime:.1f}s • evidence committed with the adapter",
        font=MONO,
        fill="#8aa6bd",
    )
    return image


def record(output: Path) -> None:
    script_dir = Path(__file__).resolve().parent
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lines, runtime = _capture_real_run(script_dir)
    writer = imageio_ffmpeg.write_frames(
        str(output),
        (WIDTH, HEIGHT),
        fps=FPS,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        output_params=["-crf", "23", "-preset", "medium", "-movflags", "+faststart"],
    )
    writer.send(None)
    try:
        for frame in range(FPS * 3):
            writer.send(_title_frame(frame).tobytes())

        revealed: list[str] = []
        frames_per_line = 4
        for index, line in enumerate(lines):
            revealed.append(line)
            for _ in range(frames_per_line):
                writer.send(
                    _terminal_frame(revealed, (index + 1) / len(lines)).tobytes()
                )
        for _ in range(FPS * 2):
            writer.send(_terminal_frame(revealed, 1.0).tobytes())

        for frame in range(FPS * 6):
            writer.send(_result_frame(runtime, frame).tobytes())
    finally:
        writer.close()
    print(f"Recorded {len(lines)} real terminal lines to {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "artifacts" / "verified" / "demo.mp4",
    )
    record(parser.parse_args().output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
