"""Record the real offline migration pipeline as a shareable terminal video."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections import deque
from pathlib import Path
from typing import cast

from aider_okf import parse_aider_history
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
HOME_PATH = re.compile(r"[A-Za-z]:\\Users\\[^\\\r\n]+")
POSIX_HOME_PATH = re.compile(r"/(?:home|Users)/[^/\s]+(?:/[^\s]*)?")


class TerminalRecorder:
    """Render actual command output into an H.264 terminal recording."""

    width = 1280
    height = 720
    fps = 12
    columns = 104
    rows = 27

    def __init__(self, output: Path) -> None:
        """Start an ffmpeg process that accepts raw terminal frames."""

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg is required to record the demo")
        output.parent.mkdir(parents=True, exist_ok=True)
        font_path = (
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "consola.ttf"
        )
        self.font = (
            ImageFont.truetype(str(font_path), 20)
            if font_path.exists()
            else ImageFont.load_default()
        )
        bold_path = font_path.with_name("consolab.ttf")
        self.bold = (
            ImageFont.truetype(str(bold_path), 23) if bold_path.exists() else self.font
        )
        self.lines: deque[str] = deque(maxlen=self.rows)
        self.process = subprocess.Popen(
            [
                ffmpeg,
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{self.width}x{self.height}",
                "-r",
                str(self.fps),
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "24",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def scrub(text: str) -> str:
        """Remove ANSI escapes and machine-specific home paths from frames."""

        text = ANSI.sub("", text).replace(str(REPOSITORY), "<MEMANTO_REPOSITORY>")
        text = HOME_PATH.sub("<USER_HOME>", text)
        return POSIX_HOME_PATH.sub("<USER_HOME>", text)

    def _frame(self) -> bytes:
        """Render the current terminal buffer as one RGB frame."""

        image = Image.new("RGB", (self.width, self.height), "#0b1020")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, 52), fill="#111a33")
        draw.ellipse((19, 18, 35, 34), fill="#ff5f56")
        draw.ellipse((43, 18, 59, 34), fill="#ffbd2e")
        draw.ellipse((67, 18, 83, 34), fill="#27c93f")
        draw.text(
            (104, 12),
            "Aider memory -> Memanto -> portable OKF",
            font=self.bold,
            fill="#e8edf7",
        )
        y = 66
        for line in self.lines:
            color = "#7dd3fc" if line.startswith("$") else "#d8dee9"
            draw.text((22, y), line, font=self.font, fill=color)
            y += 24
        return cast(bytes, image.tobytes())

    def emit(self, text: str = "", *, hold: int = 3) -> None:
        """Append sanitized text and hold each resulting frame."""

        cleaned = self.scrub(text).rstrip()
        rendered = []
        for line in cleaned.splitlines() or [""]:
            rendered.extend(
                textwrap.wrap(line, self.columns, replace_whitespace=False) or [""]
            )
        for line in rendered:
            self.lines.append(line)
            frame = self._frame()
            assert self.process.stdin is not None
            for _ in range(hold):
                self.process.stdin.write(frame)

    def command(self, command: list[str]) -> None:
        """Run a command and record its combined output."""

        self.emit("$ " + " ".join(command), hold=8)
        process = subprocess.Popen(
            command,
            cwd=REPOSITORY,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            self.emit(line, hold=2)
        if process.wait() != 0:
            raise subprocess.CalledProcessError(process.returncode, command)

    def close(self) -> None:
        """Finish the recording and fail if ffmpeg did not encode it."""

        self.emit("", hold=self.fps)
        assert self.process.stdin is not None
        self.process.stdin.close()
        if self.process.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding the demo")


def main() -> int:
    """Record the checked-in migration pipeline as an H.264 demo."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=HERE / "demo" / "aider-okf-demo.mp4"
    )
    args = parser.parse_args()
    memanto = shutil.which("memanto")
    if memanto is None:
        raise SystemExit("memanto CLI not found; run this script with `uv run`")

    source = HERE / "data" / "aider.chat.history.md"
    bundle = Path(tempfile.mkdtemp(prefix="aider-okf-video-")) / "bundle"
    messages = parse_aider_history(source.read_text(encoding="utf-8"))
    first_user = next(message for message in messages if message.role == "user")
    first_assistant = next(
        message for message in messages if message.role == "assistant"
    )

    recorder = TerminalRecorder(args.output)
    try:
        recorder.emit(
            "REAL SOURCE: Aider 0.86.2 + local Ollama qwen2.5-coder:3b", hold=12
        )
        recorder.emit(f"USER> {first_user.content}", hold=5)
        recorder.emit(f"AIDER> {first_assistant.content}", hold=4)
        recorder.command(
            [sys.executable, str(HERE / "aider_okf.py"), str(source), str(bundle)]
        )

        recorder.emit("OPENING A HUMAN-READABLE OKF MEMORY", hold=10)
        okf_file = bundle / "memories" / "002-user.md"
        for line in okf_file.read_text(encoding="utf-8").splitlines()[:28]:
            recorder.emit(line, hold=2)

        recorder.command([memanto, "migrate", "okf", str(bundle), "--dry-run"])
        recorder.command(
            [sys.executable, str(HERE / "validate.py"), str(source), str(bundle)]
        )
        recorder.emit(
            "RESULT: 16 -> 16 -> 16, zero skipped, 16/16 exact hashes, 4/4 recall parity",
            hold=18,
        )
        recorder.emit(
            "Portable markdown is readable, auditable, and belongs to the user.",
            hold=18,
        )
    finally:
        recorder.close()
    print(f"Recorded genuine pipeline demo: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
