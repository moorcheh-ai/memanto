"""Generate a small demo GIF for the LangGraph + Memanto example README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SLIDES = [
    (
        "Session 1",
        [
            "New LangGraph support ticket",
            "User: keep replies short",
            "User: follow up by email",
            "Memanto stores durable preferences",
        ],
    ),
    (
        "Memory outside graph state",
        [
            "Graph state ends after session 1",
            "Memanto keeps preference memories",
            "No LLM key required for this demo",
            "Adapter can be swapped for SdkClient",
        ],
    ),
    (
        "Session 2",
        [
            "Fresh ticket starts with empty state",
            "Agent recalls prior preferences",
            "Concise tone selected",
            "Email follow-up selected",
        ],
    ),
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def make_frame(title: str, lines: list[str]) -> Image.Image:
    image = Image.new("RGB", (900, 520), "#f6f8fb")
    draw = ImageDraw.Draw(image)
    title_font = load_font(44, bold=True)
    body_font = load_font(28)
    small_font = load_font(20)

    draw.rectangle((0, 0, 900, 14), fill="#2563eb")
    draw.text((54, 52), "LangGraph + Memanto", fill="#111827", font=title_font)
    draw.text((58, 116), title, fill="#2563eb", font=load_font(30, bold=True))

    y = 184
    for line in lines:
        draw.ellipse((62, y + 8, 78, y + 24), fill="#16a34a")
        draw.text((96, y), line, fill="#1f2937", font=body_font)
        y += 62

    draw.rectangle((54, 452, 846, 478), outline="#d0d7de", width=2)
    draw.text(
        (70, 456),
        "Cross-session recall: session 2 uses memories written in session 1",
        fill="#4b5563",
        font=small_font,
    )
    return image


def main() -> None:
    frames = [make_frame(title, lines) for title, lines in SLIDES]
    output = Path(__file__).with_name("demo.gif")
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=1200,
        loop=0,
    )
    print(output)


if __name__ == "__main__":
    main()
