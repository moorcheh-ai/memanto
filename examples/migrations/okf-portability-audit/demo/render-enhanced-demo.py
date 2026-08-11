"""Render a continuous, narrated video from the reproducible bounty evidence."""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1280
HEIGHT = 720
FPS = 24
BG = "#07111f"
PANEL = "#0d1b2d"
PANEL_2 = "#101f33"
TEXT = "#edf6ff"
MUTED = "#91a7bd"
CYAN = "#36d7d0"
GREEN = "#7ee787"
AMBER = "#f6c177"
RED = "#ff7b72"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a Windows font with a stable Segoe fallback."""
    fonts = Path("C:/Windows/Fonts")
    choices = {
        "regular": ["segoeui.ttf", "arial.ttf"],
        "bold": ["segoeuib.ttf", "arialbd.ttf"],
        "mono": ["CascadiaMono.ttf", "consola.ttf"],
    }
    for candidate in choices[name]:
        path = fonts / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    raise FileNotFoundError(f"No usable font for {name}")


REG_18 = _font("regular", 18)
REG_22 = _font("regular", 22)
REG_28 = _font("regular", 28)
BOLD_18 = _font("bold", 18)
BOLD_24 = _font("bold", 24)
BOLD_34 = _font("bold", 34)
BOLD_48 = _font("bold", 48)
BOLD_66 = _font("bold", 66)
MONO_17 = _font("mono", 17)
MONO_20 = _font("mono", 20)


def _ease(value: float) -> float:
    """Smooth a zero-to-one animation value."""
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _fade(draw: ImageDraw.ImageDraw, progress: float, start: float, end: float) -> int:
    """Return an eased reveal width for a timeline segment."""
    if progress <= start:
        return 0
    return int(_ease((progress - start) / (end - start)) * 1000)


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    font: ImageFont.FreeTypeFont,
    fill: str = TEXT,
) -> None:
    """Draw text with consistent antialiasing."""
    draw.text(xy, value, font=font, fill=fill)


def _terminal_line(
    draw: ImageDraw.ImageDraw,
    y: int,
    marker: str,
    value: str,
    color: str = TEXT,
) -> None:
    """Draw one terminal row."""
    _text(draw, (516, y), marker, MONO_17, CYAN if marker == "$" else MUTED)
    _text(draw, (540, y), value, MONO_17, color)


def _base_frame(progress: float, seconds: float) -> Image.Image:
    """Render the persistent workspace shared by the entire story."""
    frame = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(frame)

    # Continuous background grid and header.
    for x in range(0, WIDTH, 40):
        draw.line((x, 0, x, HEIGHT), fill="#0a1728", width=1)
    for y in range(0, HEIGHT, 40):
        draw.line((0, y, WIDTH, y), fill="#0a1728", width=1)
    draw.rounded_rectangle((24, 18, 1256, 66), radius=14, fill="#0b1a2b")
    draw.ellipse((44, 35, 56, 47), fill=RED)
    draw.ellipse((66, 35, 78, 47), fill=AMBER)
    draw.ellipse((88, 35, 100, 47), fill=GREEN)
    _text(draw, (124, 31), "MEMANTO / OKF PORTABILITY AUDIT", BOLD_18)
    _text(draw, (1036, 31), f"LIVE EVIDENCE  {seconds:05.1f}s", MONO_17, MUTED)

    # Persistent source and terminal panels establish spatial continuity.
    draw.rounded_rectangle((24, 84, 470, 646), radius=18, fill=PANEL)
    draw.rounded_rectangle((488, 84, 1256, 646), radius=18, fill=PANEL_2)
    _text(draw, (48, 108), "SOURCE", BOLD_18, MUTED)
    _text(draw, (512, 108), "ONE REPRODUCIBLE COMMAND", BOLD_18, MUTED)
    draw.line((48, 140, 446, 140), fill="#203752", width=2)
    draw.line((512, 140, 1232, 140), fill="#203752", width=2)

    # Source card stays visible while the command progresses.
    draw.rounded_rectangle((48, 166, 446, 286), radius=12, fill="#13263d")
    _text(draw, (68, 186), "GitHub", BOLD_18, CYAN)
    _text(draw, (68, 218), "moorcheh-ai / memanto", BOLD_24)
    _text(draw, (68, 254), "Issue #1609  •  31 comments", MONO_17, MUTED)

    # Flow connector has motion but never changes the camera.
    connector_x = 122 + int((progress * 5 % 1) * 250)
    draw.line((92, 334, 400, 334), fill="#274663", width=4)
    draw.ellipse((connector_x, 328, connector_x + 12, 340), fill=CYAN)
    _text(draw, (72, 358), "GitHub archive", REG_18, MUTED)
    _text(draw, (72, 389), "→ plain Markdown", REG_18, TEXT)
    _text(draw, (72, 420), "→ official dry run", REG_18, TEXT)
    _text(draw, (72, 451), "→ production round trip", REG_18, TEXT)
    _text(draw, (72, 482), "→ deterministic audit", REG_18, TEXT)

    # Footer remains honest and visibly discloses assistance.
    draw.rounded_rectangle((24, 662, 1256, 704), radius=12, fill="#0b1a2b")
    _text(draw, (44, 674), "PR #1813  •  current head ef77062", MONO_17, MUTED)
    _text(
        draw, (818, 674), "AI-assisted production • real command output", MONO_17, MUTED
    )
    return frame


def _render_frame(index: int, total_frames: int, duration: float) -> Image.Image:
    """Render one frame of the single-scene evidence story."""
    progress = index / max(1, total_frames - 1)
    seconds = index / FPS
    frame = _base_frame(progress, seconds)
    draw = ImageDraw.Draw(frame)

    # Hook: overlay once, then reveal the command in the same terminal window.
    if progress < 0.13:
        strength = 1.0 if progress < 0.09 else (0.13 - progress) / 0.04
        overlay = Image.new("RGBA", frame.size, (7, 17, 31, int(235 * strength)))
        od = ImageDraw.Draw(overlay)
        _text(od, (94, 238), "YOUR AGENT REMEMBERS EVERYTHING", BOLD_48)
        _text(od, (94, 310), "until the platform changes.", BOLD_48, AMBER)
        _text(od, (98, 390), "One real archive. One portable receipt.", REG_28, MUTED)
        frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
        return frame

    terminal_lines = [
        (0.13, "$", "python run_demo.py", TEXT),
        (0.19, "✓", "Exported 1 issue + 31 comments", GREEN),
        (0.25, "✓", "Created 33 human-readable OKF memories", GREEN),
        (0.34, "$", "memanto migrate okf github-memory --dry-run", TEXT),
        (0.41, "✓", "OKF nodes: 33", GREEN),
        (0.46, "✓", "Mapped memories: 33  •  skipped: 0", GREEN),
        (0.55, "$", "python roundtrip_demo.py source target", TEXT),
        (0.61, "✓", "Round-tripped 33 memories", GREEN),
        (0.67, "$", "python okf_audit.py --fail-on-change", TEXT),
        (0.72, "$", "python recall_parity.py --fail-on-regression", TEXT),
        (0.76, "✓", "Golden recall: 5/5 before  •  5/5 after", GREEN),
    ]
    y = 168
    for start, marker, value, color in terminal_lines:
        if progress >= start:
            visible = len(value)
            if progress < start + 0.035:
                visible = max(1, int(len(value) * (progress - start) / 0.035))
            _terminal_line(draw, y, marker, value[:visible], color)
            y += 40

    if progress >= 0.80:
        # The receipt grows in place from the terminal output.
        receipt_alpha = _ease((progress - 0.80) / 0.05)
        receipt = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        rd = ImageDraw.Draw(receipt)
        rd.rounded_rectangle(
            (518, 440, 1226, 618),
            radius=14,
            fill=(7, 17, 31, int(245 * receipt_alpha)),
            outline=(126, 231, 135, int(255 * receipt_alpha)),
            width=3,
        )
        rd.text((548, 460), "LOSSLESS RECEIPT", font=BOLD_24, fill=GREEN)
        rd.text((548, 504), "33 → 33", font=BOLD_66, fill=TEXT)
        rd.text((846, 520), "0 removed", font=BOLD_24, fill=GREEN)
        rd.text((1010, 520), "0 changed", font=BOLD_24, fill=GREEN)
        rd.text(
            (548, 582),
            "lossless: true  •  recall preserved: true",
            font=MONO_20,
            fill=CYAN,
        )
        frame = Image.alpha_composite(frame.convert("RGBA"), receipt).convert("RGB")

    if progress >= 0.90:
        # Final proof is a readable record, not a marketing slide.
        md_alpha = _ease((progress - 0.90) / 0.04)
        md = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        md_draw = ImageDraw.Draw(md)
        md_draw.rounded_rectangle(
            (42, 92, 1238, 646),
            radius=18,
            fill=(13, 27, 45, int(250 * md_alpha)),
        )
        md_draw.text(
            (72, 122), "memories/artifact/memanto-1609.md", font=MONO_17, fill=CYAN
        )
        markdown = [
            "---",
            'title: "The Great Memory Migration"',
            "type: artifact",
            "resource: github.com/moorcheh-ai/memanto/issues/1609",
            "tags: [migration, okf, portability]",
            "---",
            "Agent memory remains readable, reviewable, and portable.",
        ]
        yy = 174
        for line in markdown:
            md_draw.text(
                (82, yy),
                line,
                font=MONO_20,
                fill=TEXT if not line.startswith("resource") else AMBER,
            )
            yy += 48
        md_draw.text(
            (72, 560), "READ IT  •  VERSION IT  •  CARRY IT", font=BOLD_34, fill=GREEN
        )
        md_draw.text(
            (72, 610), "Deadline: 31 Aug 2026  •  PR #1813", font=REG_22, fill=MUTED
        )
        frame = Image.alpha_composite(frame.convert("RGBA"), md).convert("RGB")

    # Active progress line provides continuous motion and chronology.
    draw = ImageDraw.Draw(frame)
    draw.rectangle((24, 650, 1256, 654), fill="#203752")
    draw.rectangle((24, 650, 24 + int(1232 * progress), 654), fill=CYAN)
    return frame


def render(audio: Path, output: Path) -> None:
    """Stream frames to ffmpeg and mux the clean narration."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg is required to render the demo; install it and ensure the "
            "ffmpeg executable is available on PATH"
        )
    with wave.open(str(audio), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
    total_frames = math.ceil(duration * FPS)
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
        "-i",
        str(audio),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(total_frames):
            process.stdin.write(_render_frame(index, total_frames, duration).tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed")


def main() -> int:
    """Parse paths and render the enhanced demo."""
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.audio.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
