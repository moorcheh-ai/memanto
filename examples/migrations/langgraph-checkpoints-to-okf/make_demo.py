"""Generate demo.mp4: a terminal-style recording of the REAL pipeline.

Runs the actual commands (seed -> migrate -> validate -> memanto dry-run),
captures their genuine stdout, and renders it as a terminal video so reviewers
can watch the real run end-to-end.

Requires: pillow, numpy, imageio, imageio-ffmpeg (pip install).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
OUT = os.path.join(HERE, "demo.mp4")

W, H = 1280, 720
BG = (11, 15, 23)
FG = (229, 231, 235)
DIM = (107, 114, 128)
ACCENT = (34, 211, 238)
GOOD = (163, 230, 53)

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",  # Windows
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
    "/System/Library/Fonts/Menlo.ttc",  # macOS
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """First available monospace font; falls back to Pillow's default."""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT = _load_font(19)
FONT_B = _load_font(21)
LINE_H = 26
PAD = 34
MAX_CHARS = 100
FPS = 30
LINES_PER_SEC = 3


def run_capture(args: list[str]) -> list[str]:
    res = subprocess.run(
        args,
        cwd=HERE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = (res.stdout + res.stderr).splitlines()
    if res.returncode != 0:
        lines.append(f"[exit {res.returncode}] {' '.join(args)}")
    return lines


def collect_transcript() -> list[tuple[str, tuple]]:
    lines: list[tuple[str, tuple]] = []

    def cmd(c: str):
        lines.append((f"$ {c}", ACCENT))

    def out(block: list[str]):
        for ln in block:
            ln = ln.rstrip()
            if not ln:
                lines.append(("", FG))
                continue
            for w in textwrap.wrap(ln, MAX_CHARS) or [""]:
                color = FG
                if "PASS" in w or "parity: 9/9" in w or "DONE" in w:
                    color = GOOD
                elif w.startswith("="):
                    color = DIM
                lines.append((w, color))

    cmd("python run.py --force")
    out(run_capture([PY, "run.py", "--force"]))
    cmd("python -m memanto migrate okf out/okf-bundle --dry-run")
    out(
        run_capture(
            [PY, "-m", "memanto", "migrate", "okf", "out/okf-bundle", "--dry-run"]
        )
    )
    cmd("pytest -c pytest.ini tests/ -q")
    out(run_capture([PY, "-m", "pytest", "-c", "pytest.ini", "tests/", "-q"]))
    return lines


def frame(lines: list[tuple[str, tuple]], title: str | None = None) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 40], fill=(17, 24, 39))
    d.text(
        (PAD, 9),
        title or "langgraph-checkpoints-to-okf — live run",
        font=FONT_B,
        fill=DIM,
    )
    max_lines = (H - 40 - PAD) // LINE_H
    visible = lines[-max_lines:]
    y = 40 + 8
    for text, color in visible:
        d.text((PAD, y), text, font=FONT, fill=color)
        y += LINE_H
    return img


def main() -> None:
    transcript = collect_transcript()
    print(f"transcript: {len(transcript)} lines")

    with imageio.get_writer(OUT, fps=FPS, codec="libx264", quality=8) as writer:
        # title card (2s)
        card = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(card)
        d.text(
            (PAD, H // 2 - 60),
            "Free your LangGraph agent's memory",
            font=_load_font(40),
            fill=FG,
        )
        d.text(
            (PAD, H // 2 + 4),
            "checkpoints.sqlite  ->  OKF bundle  ->  memanto migrate okf",
            font=FONT_B,
            fill=ACCENT,
        )
        d.text((PAD, H // 2 + 44), "real pipeline, zero API keys", font=FONT, fill=DIM)
        for _ in range(FPS * 2):
            writer.append_data(np.asarray(card))

        # progressive line reveal
        shown: list[tuple[str, tuple]] = []
        step = max(1, int(FPS / LINES_PER_SEC))
        for i, ln in enumerate(transcript):
            shown.append(ln)
            if i % step == 0 or i == len(transcript) - 1:
                writer.append_data(np.asarray(frame(shown)))
        # hold on final (4s)
        final = np.asarray(frame(shown))
        for _ in range(FPS * 4):
            writer.append_data(final)
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
