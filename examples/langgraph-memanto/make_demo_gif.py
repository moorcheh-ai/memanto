from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FRAMES = [
    [
        "Session 1: support-yesterday",
        "Riley: remember Northstar, Friday invoices, May 28 migration.",
        "LangGraph state contains only this turn.",
    ],
    [
        "Memanto write node",
        "Stored: Dashboard theme preference",
        "Stored: Invoice delivery rule",
        "Stored: Migration launch deadline",
    ],
    [
        "Session 2: support-today",
        "Fresh LangGraph thread. No previous messages passed in.",
        "Question: what should you remember about Riley?",
    ],
    [
        "Memanto recall node",
        "Recovered Northstar from support-yesterday",
        "Recovered Friday invoice rule from support-yesterday",
        "Recovered May 28 deadline from support-yesterday",
    ],
    [
        "Boundary proof",
        "Current state did not contain yesterday's facts.",
        "Durable memory came from Memanto outside graph state.",
    ],
]


FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def main() -> None:
    output = Path(__file__).parent / "assets" / "cross-session-recall.gif"
    output.parent.mkdir(parents=True, exist_ok=True)
    title_font = ImageFont.truetype(FONT, 30)
    body_font = ImageFont.truetype(FONT, 25)
    frames = []
    for lines in FRAMES:
        image = Image.new("RGB", (900, 420), (18, 24, 38))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((40, 40, 860, 380), radius=16, fill=(244, 247, 251))
        draw.rounded_rectangle((40, 40, 860, 104), radius=16, fill=(35, 92, 130))
        draw.rectangle((40, 76, 860, 104), fill=(35, 92, 130))
        draw.text((74, 57), lines[0], font=title_font, fill=(255, 255, 255))
        for index, line in enumerate(lines[1:]):
            y = 138 + index * 62
            draw.rounded_rectangle(
                (74, y - 12, 826, y + 36),
                radius=8,
                fill=(226 - index * 12, 235 - index * 8, 244),
            )
            draw.text((94, y), line, font=body_font, fill=(16, 32, 48))
        frames.append(image.resize((720, 336)))

    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=6000,
        loop=0,
    )
    print(output)


if __name__ == "__main__":
    main()
