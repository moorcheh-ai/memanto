"""Render a captioned MP4 walkthrough from the real migration artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
OUTPUT = ARTIFACTS / "langgraph-memory-escape.mp4"
WIDTH, HEIGHT = 1280, 720
FPS = 24

BACKGROUND = "#090D18"
PANEL = "#111827"
PANEL_EDGE = "#253047"
WHITE = "#F8FAFC"
MUTED = "#9CA3AF"
GREEN = "#4ADE80"
CYAN = "#22D3EE"
YELLOW = "#FACC15"
RED = "#FB7185"


def _font(size: int, *, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [Path("C:/Windows/Fonts/CascadiaMono.ttf")]
        if mono
        else [Path("C:/Windows/Fonts/segoeui.ttf")]
    )
    candidates.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
            if mono
            else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/System/Library/Fonts/SFNS.ttf"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


TITLE = _font(46)
SUBTITLE = _font(25)
LABEL = _font(19)
MONO = _font(20, mono=True)
MONO_SMALL = _font(17, mono=True)


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    return image, ImageDraw.Draw(image)


def _header(draw: ImageDraw.ImageDraw, step: str) -> None:
    draw.text((54, 34), "MEMORY ESCAPE", font=LABEL, fill=CYAN)
    draw.text((WIDTH - 54, 34), step, font=LABEL, fill=MUTED, anchor="ra")


def _terminal(draw: ImageDraw.ImageDraw, lines: list[tuple[str, str]]) -> None:
    draw.rounded_rectangle(
        (48, 105, WIDTH - 48, HEIGHT - 56),
        radius=18,
        fill=PANEL,
        outline=PANEL_EDGE,
        width=2,
    )
    for x, color in ((76, RED), (100, YELLOW), (124, GREEN)):
        draw.ellipse((x, 129, x + 13, 142), fill=color)
    y = 174
    for text, color in lines:
        draw.text((78, y), text, font=MONO, fill=color)
        y += 34


def _title_scene(progress: float, summary: dict, recall: dict) -> Image.Image:
    image, draw = _canvas()
    draw.text((64, 88), "Your agent remembers.", font=TITLE, fill=WHITE)
    draw.text((64, 151), "You should own those memories.", font=TITLE, fill=CYAN)
    draw.text(
        (64, 245),
        "A real LangGraph checkpoint history escapes SQLite and becomes portable OKF.",
        font=SUBTITLE,
        fill=MUTED,
    )
    cards = [
        ("CHECKPOINTS", str(summary["checkpoints"])),
        ("THREADS", str(summary["threads"])),
        ("PORTABLE MEMORIES", str(summary["memories"])),
        ("CONTENT COVERAGE", f"{recall['content_coverage'] * 100:.0f}%"),
    ]
    for index, (label, value) in enumerate(cards):
        x = 64 + index * 294
        draw.rounded_rectangle((x, 355, x + 260, 515), radius=16, fill=PANEL)
        draw.text((x + 22, 384), label, font=LABEL, fill=MUTED)
        draw.text((x + 22, 427), value, font=TITLE, fill=GREEN)
    draw.text(
        (64, 620),
        "No API key. No hand-written export. No desktop recording.",
        font=SUBTITLE,
        fill=WHITE,
    )
    return image


def _run_scene(progress: float, summary: dict, recall: dict) -> Image.Image:
    image, draw = _canvas()
    _header(draw, "1 / 4  RUN THE SOURCE")
    all_lines = [
        ("$ python run_demo.py", CYAN),
        ("1/3 Running LangGraph and writing real SQLite checkpoints", WHITE),
        (f"    threads discovered: {summary['threads']}", GREEN),
        (f"    checkpoints written: {summary['checkpoints']}", GREEN),
        ("2/3 Converting latest thread state to OKF", WHITE),
        (f"    portable memories: {summary['memories']}", GREEN),
        ("    skipped source records: 0", GREEN),
        ("3/3 Checking expected facts in the OKF bundle", WHITE),
        (f"    questions passed: {recall['passed']}/{recall['questions']}", GREEN),
        (f"    content_coverage: {recall['content_coverage']:.1f}", GREEN),
    ]
    visible = max(1, min(len(all_lines), int(progress * (len(all_lines) + 2))))
    _terminal(draw, all_lines[:visible])
    return image


def _correction_scene(progress: float, summary: dict, recall: dict) -> Image.Image:
    image, draw = _canvas()
    _header(draw, "2 / 4  PRESERVE CORRECTIONS")
    draw.text((64, 100), "The source changed its mind.", font=TITLE, fill=WHITE)
    draw.rounded_rectangle((64, 190, 1216, 310), radius=18, fill=PANEL)
    draw.text((92, 218), "Earlier checkpoint", font=LABEL, fill=MUTED)
    draw.text((92, 258), "Launch report format: PDF", font=SUBTITLE, fill=RED)
    draw.rounded_rectangle(
        (64, 350, 1216, 505), radius=18, fill=PANEL, outline=GREEN, width=2
    )
    draw.text((92, 378), "Latest checkpoint, migrated to OKF", font=LABEL, fill=MUTED)
    draw.text(
        (92, 421), "Report Format Preference: Markdown", font=SUBTITLE, fill=GREEN
    )
    draw.text(
        (92, 467), "type: preference   source: langgraph", font=MONO_SMALL, fill=CYAN
    )
    draw.text(
        (64, 590),
        "The adapter migrates what the live agent recalls now, not stale history.",
        font=SUBTITLE,
        fill=WHITE,
    )
    return image


def _okf_scene(progress: float, summary: dict, recall: dict) -> Image.Image:
    image, draw = _canvas()
    _header(draw, "3 / 4  OPEN THE BUNDLE")
    lines = [
        ("langgraph-okf/", CYAN),
        ("  index.md", WHITE),
        ("  memories/", WHITE),
        ("    artifact/  2 transcripts", MUTED),
        ("    decision/  1 decision", MUTED),
        ("    fact/      2 facts", MUTED),
        ("    goal/      1 goal", MUTED),
        ("    preference/2 preferences", MUTED),
        ("  metrics/migration-summary.md", WHITE),
        ("  migration-summary.json", WHITE),
    ]
    _terminal(draw, lines)
    return image


def _import_scene(progress: float, summary: dict, recall: dict) -> Image.Image:
    image, draw = _canvas()
    _header(draw, "4 / 4  VERIFY MEMANTO")
    lines = [
        ("$ memanto migrate okf ./artifacts/langgraph-okf --dry-run", CYAN),
        ("Loading OKF bundle...", WHITE),
        ("Mapping OKF nodes onto Memanto schema...", WHITE),
        (f"OKF nodes: {summary['memories']}", GREEN),
        (f"Mapped memories: {summary['memories']}  (skipped 0)", GREEN),
        ("artifact: 2  decision: 1  fact: 2", MUTED),
        ("goal: 1  preference: 2", MUTED),
        ("Dry run complete. No writes performed.", GREEN),
    ]
    _terminal(draw, lines)
    return image


def _outro_scene(progress: float, summary: dict, recall: dict) -> Image.Image:
    image, draw = _canvas()
    draw.text((64, 105), "IN", font=LABEL, fill=MUTED)
    draw.text((64, 145), "LangGraph SQLite", font=TITLE, fill=WHITE)
    draw.text((64, 254), "OWNED", font=LABEL, fill=MUTED)
    draw.text((64, 294), "Readable OKF", font=TITLE, fill=CYAN)
    draw.text((64, 403), "PORTABLE", font=LABEL, fill=MUTED)
    draw.text((64, 443), "Memanto-ready", font=TITLE, fill=GREEN)
    draw.text(
        (64, 575),
        f"{summary['checkpoints']} checkpoints. {summary['threads']} threads. "
        f"{summary['memories']} memories. 0 skipped.",
        font=SUBTITLE,
        fill=WHITE,
    )
    draw.text((64, 630), "Own your agentic memory.", font=SUBTITLE, fill=YELLOW)
    return image


def _artifacts() -> tuple[dict, dict]:
    summary_path = ARTIFACTS / "langgraph-okf" / "migration-summary.json"
    recall_path = ARTIFACTS / "content-coverage-report.json"
    if not summary_path.is_file() or not recall_path.is_file():
        raise FileNotFoundError("Run python run_demo.py before building the video")
    return (
        json.loads(summary_path.read_text(encoding="utf-8")),
        json.loads(recall_path.read_text(encoding="utf-8")),
    )


def render_video(output: Path = OUTPUT) -> Path:
    summary, recall = _artifacts()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required on PATH")
    output.parent.mkdir(parents=True, exist_ok=True)
    scenes: list[tuple[float, Callable[[float, dict, dict], Image.Image]]] = [
        (5.0, _title_scene),
        (11.0, _run_scene),
        (7.0, _correction_scene),
        (7.0, _okf_scene),
        (8.0, _import_scene),
        (6.0, _outro_scene),
    ]
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
        for duration, renderer in scenes:
            frame_count = int(duration * FPS)
            for frame in range(frame_count):
                progress = frame / max(1, frame_count - 1)
                process.stdin.write(renderer(progress, summary, recall).tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("FFmpeg failed to render the demo video")
    return output


if __name__ == "__main__":
    print(render_video())
