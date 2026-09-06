"""Build a small MP4 demo artifact for the LangGraph -> OKF showcase."""

from __future__ import annotations

import json
from pathlib import Path

import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "submission" / "langgraph-okf-demo.mp4"
SUMMARY = ROOT / "sample_output" / "summary.json"
PARITY = ROOT / "sample_output" / "validation" / "recall-parity-report.md"
DRY_RUN = ROOT / "sample_output" / "memanto_migrate_okf_dry_run.txt"

WIDTH = 1280
HEIGHT = 720
FPS = 12
BG = (15, 18, 24)
PANEL = (25, 30, 39)
TEXT = (229, 232, 239)
MUTED = (151, 161, 177)
ACCENT = (64, 195, 172)
WARN = (255, 205, 97)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    portable_candidates = [
        "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "LiberationMono-Bold.ttf" if bold else "LiberationMono-Regular.ttf",
    ]
    for candidate in portable_candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass

    candidates = [
        "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/CascadiaMono.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


TITLE_FONT = font(36, bold=True)
BODY_FONT = font(24)
SMALL_FONT = font(19)


def wrap(text: str, limit: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        words = raw.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + len(word) + 1 > limit:
                lines.append(current)
                current = word
            else:
                current += " " + word
        lines.append(current)
    return lines


def frame(title: str, body: list[str], footer: str = "") -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((42, 42, WIDTH - 42, HEIGHT - 42), radius=18, fill=PANEL)
    draw.text((76, 72), title, fill=ACCENT, font=TITLE_FONT)
    y = 140
    for line in body:
        color = WARN if line.startswith("$") or line.startswith(">") else TEXT
        draw.text((84, y), line, fill=color, font=BODY_FONT)
        y += 34
    if footer:
        draw.text((76, HEIGHT - 88), footer, fill=MUTED, font=SMALL_FONT)
    return img


def hold(img: Image.Image, seconds: float) -> list[np.ndarray]:
    arr = np.asarray(img)
    return [arr] * int(seconds * FPS)


def load_summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def require_successful_summary(summary: dict) -> tuple[int, int, int]:
    validation = summary.get("validation")
    if not isinstance(validation, dict):
        raise RuntimeError("summary.json is missing validation metrics")

    questions = validation.get("questions")
    source_score = validation.get("source_score")
    okf_score = validation.get("okf_score")
    parity_score = validation.get("parity_score")
    mapped = summary.get("mapped_memories")
    source_memories = (summary.get("source") or {}).get("memories")
    dry_run = summary.get("memanto_migrate_okf_dry_run") or {}

    required_values = [questions, source_score, okf_score, parity_score, mapped, source_memories]
    if not all(isinstance(value, int) for value in required_values):
        raise RuntimeError("summary.json validation metrics must be integer counts")
    if questions <= 0:
        raise RuntimeError("summary.json reports no validation questions")
    if source_score != questions or okf_score != questions or parity_score != questions:
        raise RuntimeError("summary.json validation did not pass all recall checks")
    if mapped != source_memories:
        raise RuntimeError("summary.json mapped memory count does not match source memories")
    if dry_run.get("returncode") != 0:
        raise RuntimeError("summary.json dry-run did not complete successfully")

    return questions, okf_score, mapped


def main() -> None:
    summary = load_summary()
    questions, okf_score, mapped = require_successful_summary(summary)
    parity = PARITY.read_text(encoding="utf-8")
    dry = DRY_RUN.read_text(encoding="utf-8")

    slides = [
        (
            "LangGraph Checkpoint -> OKF",
            [
                "A real LangGraph StateGraph writes durable memory",
                "into langgraph-checkpoint-sqlite.",
                "",
                "The adapter extracts that memory and exports",
                "human-readable Open Knowledge Format markdown.",
            ],
            "Source is generated by generate_langgraph_checkpoint.py",
        ),
        (
            "One Command Reproduction",
            [
                "$ cd examples/migrations/langgraph-checkpoint-okf",
                "$ python run_showcase.py",
                "",
                f"> source turns: {summary['source']['turns']}",
                f"> mapped memories: {summary['mapped_memories']}",
                f"> OKF bundle: {summary['okf_bundle']}",
            ],
            "No hosted LLM or API key required for the offline path",
        ),
        (
            "Readable Portable Memory",
            [
                "sample_output/okf_bundle/memories/preference/",
                "",
                "- concise-executive-summaries.md",
                "- customer-facing-ui-should-be-calm-and-light.md",
                "",
                "Each file has YAML frontmatter, content, tags,",
                "confidence, timestamp, and checkpoint provenance.",
            ],
            "The bundle is importable with memanto migrate okf",
        ),
        (
            "Recall Parity",
            wrap("\n".join(parity.splitlines()[5:12]), 68),
            f"Golden Q&A parity: {questions}/{questions}; OKF recall: {okf_score}/{questions}",
        ),
        (
            "Official CLI Dry Run",
            wrap("\n".join(line.strip() for line in dry.splitlines()[6:17]), 70),
            f"memanto migrate okf mapped {mapped}/{mapped} and performed no writes",
        ),
        (
            "Freedom Loop",
            [
                "LangGraph checkpoint",
                "  -> OKF bundle",
                "  -> memanto migrate okf --dry-run",
                "  -> portable markdown that humans and agents can read",
                "",
                "Memory should be inspectable, versionable, and movable.",
            ],
            "Demo artifact generated by build_demo_video.py",
        ),
    ]

    frames: list[np.ndarray] = []
    for title, body, footer in slides:
        frames.extend(hold(frame(title, body, footer), 3.6))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(OUTPUT, frames, fps=FPS, codec="libx264", quality=7)
    print(OUTPUT.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
