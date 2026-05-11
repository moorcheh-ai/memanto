from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FRAMES = [
    [
        "Day 1: support graph receives Riley's order",
        "write memory: Acme Robotics order AR-8841",
        "write memory: concise answers, no marketing",
        "write memory: refunds > $500 need approval",
    ],
    [
        "Durable memory sits outside LangGraph state",
        "backend: Local JSON for review",
        "backend: Memanto SDK for live Moorcheh storage",
        "graph state can be discarded between sessions",
    ],
    [
        "Day 2: fresh graph invocation",
        "recall query: Riley + Acme refund",
        "recalled: AR-8841",
        "recalled: manager approval rule",
    ],
    [
        "Result",
        "LangGraph handles orchestration",
        "Memanto handles cross-session memory",
        "run: python validate_offline.py",
    ],
]


def main() -> None:
    out_path = Path(__file__).with_name("demo.gif")
    font = ImageFont.load_default()
    frames = []

    for index, lines in enumerate(FRAMES, start=1):
        image = Image.new("RGB", (760, 420), "#101820")
        draw = ImageDraw.Draw(image)
        draw.rectangle((24, 24, 736, 396), outline="#55d6be", width=3)
        draw.text((48, 44), f"LangGraph + Memanto demo  {index}/4", fill="#55d6be", font=font)
        y = 112
        for line in lines:
            draw.text((70, y), f"> {line}", fill="#f7f7f2", font=font)
            y += 58
        frames.append(image)

    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=1800,
        loop=0,
    )
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
