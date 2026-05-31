"""Generate a small 30-second GIF for the README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1040
HEIGHT = 640
BG = (18, 24, 32)
PANEL = (28, 36, 48)
TEXT = (235, 242, 248)
MUTED = (143, 164, 182)
GREEN = (87, 201, 142)
BLUE = (105, 171, 255)


STEPS = [
    (
        "Session 1: store yesterday's support handoff",
        [
            "$ python run_cross_session_demo.py --backend file --reset",
            "remembered: Customer Alex is on the enterprise plan.",
            "remembered: Customer Alex prefers email follow-ups before demos.",
            "remembered: Invoices for Alex should stay in GBP.",
        ],
    ),
    (
        "Session 2: LangGraph starts with a fresh state",
        [
            "question: Can we book a demo tomorrow?",
            "question: They prefer email.",
            "question: What invoice currency will we use?",
        ],
    ),
    (
        "Graph node: recall_memory",
        [
            "Memanto recall: Alex demo invoice currency preference",
            "found: enterprise plan",
            "found: email follow-ups",
            "found: GBP invoices",
        ],
    ),
    (
        "Graph node: compose_response",
        [
            "Recommended response:",
            "Keep the answer enterprise-aware.",
            "Offer an email follow-up.",
            "Keep invoice language in GBP.",
        ],
    ),
    (
        "Graph node: store_followup_learning",
        [
            "New preference detected in today's message.",
            "remember: latest message confirms email preference.",
            "The next graph run can recall this too.",
        ],
    ),
]


def main() -> None:
    """Render the README demo GIF frames and write the output asset."""

    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    output = assets_dir / "demo.gif"
    frames: list[Image.Image] = []
    font = _font(30)
    small = _font(24)
    tiny = _font(20)

    for index, (title, lines) in enumerate(STEPS, start=1):
        for _ in range(6):
            image = Image.new("RGB", (WIDTH, HEIGHT), BG)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                (44, 44, WIDTH - 44, HEIGHT - 44), radius=18, fill=PANEL
            )
            draw.text((82, 82), "LangGraph + Memanto", font=font, fill=GREEN)
            draw.text((82, 126), f"Step {index}/5: {title}", font=small, fill=TEXT)
            draw.line((82, 174, WIDTH - 82, 174), fill=(64, 78, 94), width=2)

            y = 218
            for line in lines:
                color = (
                    BLUE if line.startswith("$") or line.startswith("Memanto") else TEXT
                )
                draw.text((104, y), line, font=small, fill=color)
                y += 48

            draw.text(
                (82, HEIGHT - 96),
                "Cross-session recall: durable memory outside the graph state",
                font=tiny,
                fill=MUTED,
            )
            frames.append(image)

    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=1000,
        loop=0,
        optimize=True,
    )
    print(output)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a readable system font, falling back to Pillow's default."""

    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


if __name__ == "__main__":
    main()
