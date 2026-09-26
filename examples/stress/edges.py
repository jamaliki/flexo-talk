"""Stress deck 5: edge cases -- 4:3 slides, scripts beyond Latin, unbreakable words,
deep lists, empty and title-only slides, a JPEG, and an SVG flexo cannot draw exactly."""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck, DeckStyle

HERE = Path(__file__).resolve().parent

GRADIENT = """<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="120pt" viewBox="0 0 200 120">
 <defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#1f77b4"/>
 <stop offset="1" stop-color="#ff7f0e"/></linearGradient></defs>
 <rect x="10" y="10" width="180" height="100" rx="12" fill="url(#g)"/>
 <text x="100" y="68" font-size="18" text-anchor="middle" fill="white">gradient</text></svg>"""


def assets() -> tuple[Path, Path]:
    folder = HERE / "build"
    folder.mkdir(parents=True, exist_ok=True)
    svg = folder / "gradient.svg"
    svg.write_text(GRADIENT)
    jpeg = folder / "photo.jpg"
    try:
        from PIL import Image

        picture = Image.new("RGB", (320, 200))
        for x in range(320):
            for y in range(200):
                picture.putpixel((x, y), (x * 255 // 320, y * 255 // 200, 160))
        picture.save(jpeg, quality=90)
    except ImportError:
        jpeg = None  # type: ignore[assignment]
    return svg, jpeg  # type: ignore[return-value]


def talk(theme: str = "paper") -> Deck:
    svg, jpeg = assets()
    style = DeckStyle(width=720.0, height=540.0)
    with Deck("edges", theme=theme, footer="Stress test · edges", style=style) as deck:
        deck.title("Edge cases on a 4:3 slide", subtitle="Scripts, long words, deep lists")
        with deck.slide("Scripts beyond Latin") as slide:
            slide.bullets(
                "日本語のスライドも書けます",
                "中文：图表自动排版",  # noqa: RUF001 - a Chinese colon is the point
                "한국어 문장도 됩니다",
                "العربية تُكتب من اليمين إلى اليسار",
            )
        with deck.slide("Words that do not break") as slide:
            slide.bullets(
                "See https://github.com/jamaliki/flexo-talk/blob/main/src/flexo_talk/compose.py",
                "Supercalifragilisticexpialidociousnessesque-and-then-some-more",
            )
        with deck.slide("Deep lists") as slide:
            slide.bullets("One", ["Two", ["Three", ["Four, the deepest level"]]], "Back to one")
        with deck.slide("Numbered steps") as slide:
            slide.bullets(
                "Write the figure once", "Build the deck", ["PowerPoint, PDF, SVG, PNG", "all in Python"],
                "Present", "Answer questions", "Rebuild when the model changes", "Repeat",
                "Profit", "Sleep", "Ten items make the numbers wider",
                numbered=True,
                reveal=True,
            )
        deck.slide("A slide with a title and nothing else")
        deck.slide(layout="blank")
        with deck.slide("Pictures", layout="two-columns") as slide:
            if jpeg is not None:
                slide.left.image(jpeg)
            slide.right.image(svg)
            slide.right.text("An SVG with a gradient is a picture.", muted=True, size=12)
    return deck


if __name__ == "__main__":
    print(talk(*sys.argv[1:2]).build(HERE / "build" / "edges").summary())
