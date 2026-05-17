from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "demo.gif"

FRAMES = [
    [
        "$ python run_demo.py --backend local --reset-local",
        "",
        "LangGraph + Memanto cross-session recall demo",
        "Backend: local",
    ],
    [
        "SESSION 1 - yesterday",
        "thread_id=intake-2026-05-17",
        "",
        "User records Maya Chen's role, preferred interview style,",
        "availability after 14:00 UTC, and Friday take-home promise.",
    ],
    [
        "LangGraph node: recall_context",
        "",
        "No prior memories found in this brand-new thread.",
    ],
    [
        "LangGraph node: write_followup_memory",
        "",
        "Memanto stores 4 typed memories:",
        "- fact: role",
        "- preference: interview style",
        "- fact: availability",
        "- commitment: take-home by Friday",
    ],
    [
        "SESSION 2 - today",
        "thread_id=briefing-2026-05-18",
        "",
        "The user message says only:",
        "\"Prepare my reminder for today's Maya interview.\"",
    ],
    [
        "LangGraph checkpoint state is empty for this new thread.",
        "",
        "Memanto recall searches durable memory outside graph state.",
    ],
    [
        "Agent:",
        "This is a fresh LangGraph thread, but Memanto recalled",
        "yesterday's durable context:",
        "- Maya Chen role: Staff AI Platform",
        "- Maya Chen availability: after 14:00 UTC",
        "- take-home exercise by Friday",
    ],
    [
        "Proof",
        "",
        "intake-2026-05-17 != briefing-2026-05-18",
        "Session 2 did not include Maya's facts in state.",
        "The details came from Memanto long-term memory.",
    ],
]


def main() -> None:
    font = _load_font(22)
    small_font = _load_font(17)
    images = []
    for index, lines in enumerate(FRAMES, 1):
        image = Image.new("RGB", (960, 540), "#0f172a")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((34, 34, 926, 506), radius=18, fill="#111827")
        draw.rectangle((34, 34, 926, 82), fill="#1f2937")
        draw.text((58, 50), "Memanto + LangGraph demo", fill="#f8fafc", font=small_font)
        draw.text((816, 50), f"{index}/8", fill="#93c5fd", font=small_font)

        y = 116
        for line in lines:
            color = "#e5e7eb"
            if line.startswith("$"):
                color = "#86efac"
            elif line.endswith(":") or line.startswith("SESSION") or line == "Proof":
                color = "#93c5fd"
            elif line.startswith("-"):
                color = "#facc15"
            draw.text((64, y), line, fill=color, font=font)
            y += 42
        images.append(image)

    images[0].save(
        OUT,
        save_all=True,
        append_images=images[1:],
        duration=4000,
        loop=0,
        optimize=True,
    )
    print(f"wrote {OUT}")


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


if __name__ == "__main__":
    main()
