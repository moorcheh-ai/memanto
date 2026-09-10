#!/usr/bin/env python3
"""Render an asciinema v2 .cast file to PNG frames, then ffmpeg → mp4/gif."""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont


THEME = {
    "bg": (18, 18, 24),
    "fg": (230, 230, 230),
    "cursor": (255, 200, 80),
    "colors": {
        "black": (18, 18, 24),
        "red": (255, 95, 109),
        "green": (80, 250, 123),
        "yellow": (241, 250, 140),
        "blue": (139, 233, 253),
        "magenta": (255, 121, 198),
        "cyan": (80, 200, 220),
        "white": (230, 230, 230),
        "brightblack": (90, 90, 100),
        "brightred": (255, 120, 130),
        "brightgreen": (120, 255, 160),
        "brightyellow": (255, 255, 170),
        "brightblue": (170, 230, 255),
        "brightmagenta": (255, 160, 220),
        "brightcyan": (140, 230, 240),
        "brightwhite": (255, 255, 255),
    },
}


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def parse_cast(path: Path):
    header = None
    events = []
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if i == 0 and isinstance(obj, dict):
                header = obj
            elif isinstance(obj, list) and len(obj) >= 3:
                events.append(obj)
    if header is None:
        raise SystemExit(f"Not a valid asciinema cast: {path}")
    return header, events


def color_of(named: str | None, bold: bool, default):
    if not named:
        return default
    key = named.lower().replace("bright_", "bright")
    palette = THEME["colors"]
    if bold and not key.startswith("bright") and f"bright{key}" in palette:
        return palette[f"bright{key}"]
    return palette.get(key, default)


def render_frame(screen: pyte.Screen, font, cell_w: int, cell_h: int, pad: int) -> Image.Image:
    cols, rows = screen.columns, screen.lines
    img = Image.new("RGB", (cols * cell_w + pad * 2, rows * cell_h + pad * 2), THEME["bg"])
    draw = ImageDraw.Draw(img)
    for y in range(rows):
        for x in range(cols):
            ch = screen.buffer[y][x]
            char = ch.data or " "
            fg = color_of(ch.fg, ch.bold, THEME["fg"])
            bg = color_of(ch.bg, False, THEME["bg"]) if ch.bg else THEME["bg"]
            if ch.reverse:
                fg, bg = bg, fg
            ox = pad + x * cell_w
            oy = pad + y * cell_h
            if bg != THEME["bg"]:
                draw.rectangle([ox, oy, ox + cell_w, oy + cell_h], fill=bg)
            if char != " ":
                draw.text((ox, oy), char, fill=fg, font=font)
    # cursor
    try:
        cx, cy = screen.cursor.x, screen.cursor.y
        if 0 <= cy < rows and 0 <= cx < cols:
            ox = pad + cx * cell_w
            oy = pad + cy * cell_h
            draw.rectangle([ox, oy + cell_h - 2, ox + cell_w, oy + cell_h], fill=THEME["cursor"])
    except Exception:
        pass
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cast", type=Path)
    ap.add_argument("--mp4", type=Path, default=None)
    ap.add_argument("--gif", type=Path, default=None)
    ap.add_argument("--fps", type=float, default=12.0)
    ap.add_argument("--font-size", type=int, default=16)
    ap.add_argument("--pad", type=int, default=12)
    ap.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")
    ap.add_argument("--max-seconds", type=float, default=180.0)
    args = ap.parse_args()

    if not args.mp4 and not args.gif:
        args.mp4 = args.cast.with_suffix(".mp4")

    header, events = parse_cast(args.cast)
    cols = int(header.get("width") or 100)
    rows = int(header.get("height") or 32)
    font = load_font(args.font_size)
    # measure cell
    bbox = font.getbbox("M")
    cell_w = max(bbox[2] - bbox[0], 8) + 1
    cell_h = max(bbox[3] - bbox[1], 12) + 4

    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)

    out_dir = Path(tempfile.mkdtemp(prefix="castframes_"))
    frame_paths: list[Path] = []
    fps = args.fps
    frame_dt = 1.0 / fps
    t = 0.0
    ev_i = 0
    # advance time to end
    end_t = events[-1][0] / args.speed if events else 0.0
    end_t = min(end_t + 1.5, args.max_seconds)

    try:
        while t <= end_t + 1e-9:
            while ev_i < len(events) and (events[ev_i][0] / args.speed) <= t + 1e-9:
                _ts, kind, data = events[ev_i][0], events[ev_i][1], events[ev_i][2]
                if kind == "o":
                    stream.feed(data)
                ev_i += 1
            img = render_frame(screen, font, cell_w, cell_h, args.pad)
            fp = out_dir / f"frame_{len(frame_paths):05d}.png"
            img.save(fp)
            frame_paths.append(fp)
            t += frame_dt

        if not frame_paths:
            raise SystemExit("No frames rendered")

        pattern = str(out_dir / "frame_%05d.png")
        if args.mp4:
            args.mp4.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-framerate", str(fps),
                "-i", pattern,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(args.mp4),
            ]
            subprocess.check_call(cmd)
            print(f"Wrote {args.mp4} ({args.mp4.stat().st_size} bytes, {len(frame_paths)} frames)")

        if args.gif:
            args.gif.parent.mkdir(parents=True, exist_ok=True)
            # palette for nicer gif
            palette = out_dir / "palette.png"
            subprocess.check_call([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-framerate", str(fps), "-i", pattern,
                "-vf", "palettegen=stats_mode=diff", str(palette),
            ])
            subprocess.check_call([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-framerate", str(fps), "-i", pattern, "-i", str(palette),
                "-lavfi", "paletteuse=dither=bayer:bayer_scale=3",
                str(args.gif),
            ])
            print(f"Wrote {args.gif} ({args.gif.stat().st_size} bytes)")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
