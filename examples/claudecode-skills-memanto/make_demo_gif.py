"""Generate a compact GIF for the Claude Code skills memory demo."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1040
HEIGHT = 640
BG = (15, 19, 27)
PANEL = (27, 34, 45)
TEXT = (238, 244, 250)
MUTED = (149, 166, 184)
GREEN = (91, 205, 149)
BLUE = (112, 177, 255)


STEPS = [
    (
        "Skill run 1: /grill-with-docs",
        [
            "Decision: Keep billing writes idempotent by Stripe event id.",
            "Preference: Add replay tests before webhook changes.",
            "Quirk: Billing timestamps are UTC ISO strings.",
        ],
    ),
    (
        "after_skill hook",
        [
            "Extract durable engineering memory.",
            "Store only decisions, preferences, quirks, constraints.",
            "Skip full prompts, secrets, and noisy logs.",
        ],
    ),
    (
        "Skill run 2: /tdd starts fresh",
        [
            "Task: add tests for Stripe webhook replay.",
            "Files: stripe.ts, stripe.test.ts",
            "Graph state is new; Memanto memory persists.",
        ],
    ),
    (
        "before_skill hook",
        [
            "MEMANTO ENGINEERING MEMORY",
            "- Keep billing writes idempotent by Stripe event id.",
            "- Add replay tests before changing webhook behavior.",
            "- Billing timestamps are stored as UTC ISO strings.",
        ],
    ),
    (
        "Prompt injection",
        [
            "Append compact memory block to the next skill prompt.",
            "The /tdd skill now sees the prior review decisions.",
            "No manual context shoving between sessions.",
        ],
    ),
]


def main() -> None:
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    output = assets_dir / "demo.gif"
    frames: list[Image.Image] = []
    font = _font(30)
    small = _font(23)
    tiny = _font(20)

    for index, (title, lines) in enumerate(STEPS, start=1):
        for _ in range(6):
            image = Image.new("RGB", (WIDTH, HEIGHT), BG)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((44, 44, WIDTH - 44, HEIGHT - 44), radius=18, fill=PANEL)
            draw.text((82, 82), "Claude Code Skills + Memanto", font=font, fill=GREEN)
            draw.text((82, 126), f"Step {index}/5: {title}", font=small, fill=TEXT)
            draw.line((82, 174, WIDTH - 82, 174), fill=(63, 77, 94), width=2)

            y = 218
            for line in lines:
                color = BLUE if line.startswith("MEMANTO") else TEXT
                draw.text((104, y), line, font=small, fill=color)
                y += 50

            draw.text(
                (82, HEIGHT - 96),
                "Global active memory across isolated developer skills",
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

