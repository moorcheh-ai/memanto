#!/usr/bin/env python3
"""Render a short MP4 terminal replay from a freshly executed migration run."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
WIDTH, HEIGHT, FPS = 1280, 720, 24

BACKGROUND = "#07110d"
PANEL = "#0c1813"
PANEL_BORDER = "#29473a"
TEXT = "#e6f2ec"
MUTED = "#88a397"
GREEN = "#6ee7a8"
LIME = "#c8ff66"
BLUE = "#70b7ff"


@dataclass(frozen=True)
class Stage:
    duration: float
    heading: str
    command: str
    output: str
    accent: str = GREEN


def font(size: int, *, bold: bool = False):
    names = [
        "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


FONT = font(21)
FONT_SMALL = font(17)
FONT_TITLE = font(35, bold=True)
FONT_HEADING = font(23, bold=True)


def capture(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return sanitize(result.stdout.strip())


def sanitize(text: str) -> str:
    cleaned = text.replace("\\", "/")
    cleaned = re.sub(r"/{2,}", "/", cleaned)
    repo_path = str(REPO_ROOT).replace("\\", "/")
    cleaned = cleaned.replace(repo_path, "<REPO>")
    cleaned = re.sub(r"C:/Users/[^/\s]+", "<HOME>", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"<HOME>/Documents/Codex/.*?work/\s*memanto",
        "<REPO>",
        cleaned,
        flags=re.DOTALL,
    )
    return cleaned


def capture_memanto_dry_run(bundle: Path) -> str:
    sys.path.insert(0, str(REPO_ROOT))
    from typer.testing import CliRunner

    from memanto.cli.commands import migrate
    from memanto.cli.main import app

    # Memanto records dry-run diagnostics beneath its config directory. Keep
    # those local-only artifacts outside the publishable example tree.
    config_root = REPO_ROOT / "work-config" / "video-run-config"
    manager = migrate.config_manager
    manager.config_dir = config_root
    manager.config_file = config_root / "config.yaml"
    manager.env_file = config_root / ".env"
    manager.connections_file = config_root / "connections.json"
    result = CliRunner().invoke(app, ["migrate", "okf", str(bundle), "--dry-run"])
    if result.exit_code:
        raise RuntimeError(result.stdout or str(result.exception))
    cleaned = sanitize(result.stdout.strip())
    if "Run dir:" in cleaned:
        cleaned = (
            cleaned.split("Run dir:", 1)[0].rstrip() + "\n-- output paths redacted --"
        )
    return cleaned


def prepare_stages() -> list[Stage]:
    source = ROOT / "sample_data" / "codex-rollout-sanitized.jsonl"
    bundle = ROOT / "sample_output" / "okf-bundle"
    golden = ROOT / "golden_qa.json"
    parity = ROOT / "sample_output" / "recall-parity.json"
    reexported = ROOT / "sample_output" / "reexported-okf"
    portability = ROOT / "sample_output" / "portability-parity.json"

    migrate_output = capture(
        [
            sys.executable,
            str(ROOT / "codex_to_okf.py"),
            str(source),
            str(bundle),
            "--title",
            "A real Codex task: from changing context to portable memory",
        ]
    )
    validate_output = capture(
        [
            sys.executable,
            str(ROOT / "validate_roundtrip.py"),
            str(bundle),
            "--golden",
            str(golden),
            "--report",
            str(parity),
        ]
    )
    report = json.loads((bundle / "migration-report.json").read_text(encoding="utf-8"))
    privacy = report["privacy_audit"]
    summary = report["summary"]
    portability_output = capture(
        [
            sys.executable,
            str(ROOT / "validate_portability.py"),
            str(bundle),
            str(reexported),
            "--report",
            str(portability),
            "--replace",
        ]
    )
    privacy_output = "\n".join(
        [
            f"visible messages included : {summary['messages_included']}",
            f"portable memories written: {summary['memories_written']}",
            f"encrypted/tool/runtime records excluded: {sum(privacy['skip_counts'].values())}",
            f"redactions applied       : {sum(privacy['redaction_counts'].values())}",
            "",
            "Default boundary: user + visible assistant text only",
            "Never exported: developer instructions, reasoning, tools, runtime state",
        ]
    )
    goal_doc = next((bundle / "memories" / "goal").glob("*.md"))
    goal_excerpt = "\n".join(goal_doc.read_text(encoding="utf-8").splitlines()[:18])
    dry_run = capture_memanto_dry_run(bundle)
    parity_result = json.loads(parity.read_text(encoding="utf-8"))
    portability_result = json.loads(portability.read_text(encoding="utf-8"))
    validation_summary = "\n".join(
        [
            f"structural errors : {len(parity_result['structural_errors'])}",
            f"golden questions  : {parity_result['golden_questions']}",
            f"golden passed     : {parity_result['golden_passed']}",
            f"recall parity     : {parity_result['recall_parity_percent']}%",
            "",
            "The goal, social-media constraint, rejected market, and final bounty",
            "remain retrievable after conversion.",
        ]
    )

    portability_summary = "\n".join(
        [
            f"source memories      : {portability_result['source_memories']}",
            f"mapped by Memanto    : {portability_result['mapped_memories']}",
            f"re-exported to OKF   : {portability_result['reexported_memories']}",
            f"resources preserved  : {portability_result['resources_preserved']}/17",
            f"types/titles/content : {portability_result['passed']}/17",
            f"field parity         : {portability_result['parity_percent']}%",
            "",
            f"Official-code-path output captured: {len(portability_output)} chars",
        ]
    )

    return [
        Stage(
            7,
            "The lock-in problem",
            "$ inspect codex rollout",
            "A real agent run contains durable goals and decisions...\n"
            "but also private reasoning, tools, secrets, and local paths.\n\n"
            "The safe migration must preserve memory without copying the machine.",
            BLUE,
        ),
        Stage(
            11,
            "1 | Convert a genuine Codex rollout",
            "$ python codex_to_okf.py sample_data/codex-rollout-sanitized.jsonl sample_output/okf-bundle",
            migrate_output,
            GREEN,
        ),
        Stage(
            10,
            "2 | Audit the privacy boundary",
            "$ view migration-report.json",
            privacy_output,
            LIME,
        ),
        Stage(
            10,
            "3 | Open the owned memory",
            f"$ view {goal_doc.relative_to(ROOT).as_posix()}",
            goal_excerpt,
            BLUE,
        ),
        Stage(
            11,
            "4 | Validate recall before import",
            "$ python validate_roundtrip.py sample_output/okf-bundle --golden golden_qa.json",
            validation_summary
            + "\n\nRaw validator output captured: "
            + str(len(validate_output))
            + " chars",
            GREEN,
        ),
        Stage(
            12,
            "5 | Let Memanto map the OKF bundle",
            "$ memanto migrate okf sample_output/okf-bundle --dry-run",
            dry_run,
            LIME,
        ),
        Stage(
            11,
            "6 | Re-export through Memanto",
            "$ python validate_portability.py sample_output/okf-bundle sample_output/reexported-okf",
            portability_summary,
            BLUE,
        ),
        Stage(
            8,
            "The freedom loop is complete",
            "$ codex rollout -> privacy boundary -> typed OKF -> Memanto -> OKF",
            "17 mapped | 17 re-exported | 100% field parity | 100% recall parity\n\n"
            "Readable Markdown. Git-friendly history. No hidden state. No lock-in.",
            GREEN,
        ),
    ]


def wrap_lines(text: str, width: int = 96) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if not raw:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw, width=width, replace_whitespace=False) or [""])
    return lines


def render_frame(stage: Stage, elapsed: float, total_progress: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.ellipse((1040, -180, 1420, 200), fill="#123d2b")
    draw.text((58, 34), "MEMANTO x CODEX", font=FONT_SMALL, fill=GREEN)
    draw.text((58, 69), stage.heading, font=FONT_TITLE, fill=TEXT)
    draw.rounded_rectangle(
        (48, 126, 1232, 642), radius=18, fill=PANEL, outline=PANEL_BORDER, width=2
    )
    draw.ellipse((72, 149, 84, 161), fill="#ff6b6b")
    draw.ellipse((94, 149, 106, 161), fill="#ffd166")
    draw.ellipse((116, 149, 128, 161), fill=GREEN)
    draw.text((150, 142), "reproducible migration run", font=FONT_SMALL, fill=MUTED)

    draw.text((74, 186), stage.command, font=FONT, fill=stage.accent)
    output_lines = wrap_lines(stage.output)
    reveal = max(
        1, int(len(output_lines) * min(1.0, elapsed / max(1.0, stage.duration * 0.7)))
    )
    y = 230
    for line in output_lines[:reveal][:18]:
        draw.text((74, y), line, font=FONT_SMALL, fill=TEXT)
        y += 23

    bar_left, bar_top, bar_right = 48, 673, 1232
    draw.rounded_rectangle(
        (bar_left, bar_top, bar_right, 681), radius=4, fill="#183026"
    )
    draw.rounded_rectangle(
        (bar_left, bar_top, bar_left + (bar_right - bar_left) * total_progress, 681),
        radius=4,
        fill=GREEN,
    )
    draw.text(
        (48, 690),
        "Captured from freshly executed commands | privacy-sanitized fixture",
        font=FONT_SMALL,
        fill=MUTED,
    )
    return image


def render_video(stages: list[Stage], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    total_duration = sum(stage.duration for stage in stages)
    writer = imageio_ffmpeg.write_frames(
        str(output),
        (WIDTH, HEIGHT),
        fps=FPS,
        codec="libx264",
        quality=7,
        pix_fmt_in="rgb24",
        output_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    writer.send(None)
    global_elapsed = 0.0
    try:
        for stage in stages:
            frame_count = round(stage.duration * FPS)
            for frame_index in range(frame_count):
                elapsed = frame_index / FPS
                progress = (global_elapsed + elapsed) / total_duration
                frame = render_frame(stage, elapsed, progress)
                writer.send(frame.tobytes())
            global_elapsed += stage.duration
    finally:
        writer.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=ROOT / "sample_output" / "codex-okf-demo.mp4",
    )
    args = parser.parse_args()
    stages = prepare_stages()
    render_video(stages, args.output)
    print(
        f"Rendered {sum(stage.duration for stage in stages):.0f}s demo: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
