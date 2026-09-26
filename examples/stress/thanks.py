"""Stress deck 8: acknowledgements -- columns, bold and coloured lines, logos, and
people's photographs cropped to circles with their names under them."""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck

HERE = Path(__file__).resolve().parent
PEOPLE = [
    ("Ada Lovelace", "PI"), ("Alan Turing", "Postdoc"), ("Grace Hopper", "PhD student"),
    ("Claude Shannon", "PhD student"), ("Emmy Noether", "Visiting professor"),
    ("John von Neumann", "Engineer"), ("Katherine Johnson", "Postdoc"), ("Tu Youyou", "Collaborator"),
]
LOGO = """<svg xmlns="http://www.w3.org/2000/svg" width="{w}pt" height="40pt" viewBox="0 0 {w} 40">
 <rect x="1" y="1" width="38" height="38" rx="8" fill="{colour}"/>
 <text x="48" y="27" font-family="Figtree" font-weight="700" font-size="20" fill="#333">{name}</text></svg>"""


def assets() -> tuple[list[Path], list[Path]]:
    folder = HERE / "build" / "thanks-assets"
    folder.mkdir(parents=True, exist_ok=True)
    logos = []
    for name, colour in (("NSF", "#1f5fbf"), ("Wellcome", "#c2362b"), ("ERC", "#2f8f3a"), ("CZI", "#7a3fa0")):
        path = folder / f"{name}.svg"
        path.write_text(LOGO.format(w=48 + 13 * len(name), colour=colour, name=name))
        logos.append(path)
    photos = []
    from PIL import Image, ImageDraw

    for index, _ in enumerate(PEOPLE):
        path = folder / f"person{index}.jpg"
        picture = Image.new("RGB", (400, 500), (200 - 15 * index, 170 + 8 * index, 150 + 10 * index))
        draw = ImageDraw.Draw(picture)
        draw.ellipse((120, 90, 280, 270), fill=(236, 200, 170))
        draw.ellipse((70, 280, 330, 560), fill=(60 + 20 * index, 80, 120))
        picture.save(path, quality=90)
        photos.append(path)
    return photos, logos


def talk(theme: str = "paper") -> Deck:
    photos, logos = assets()
    with Deck("thanks", theme=theme or "paper", footer="Stress test · thanks") as deck:
        with deck.slide("Acknowledgements", layout="columns", columns=3) as slide:
            lab, collaborators, funding = slide.columns
            lab.text("**The lab**", colour="accent")
            lab.text("**Ada Lovelace** [— PI]{muted}\n**Alan Turing** [— postdoc]{muted}\n"
                     "**Grace Hopper** [— PhD]{muted}\n**Claude Shannon** [— PhD]{muted}", size=16)
            collaborators.text("**Collaborators**", colour="accent2")
            collaborators.bullets(
                "[Emmy Noether]{accent2}, Göttingen", "[Tu Youyou]{accent3}, Beijing",
                "Katherine Johnson, [NASA Langley](https://www.nasa.gov)", size=16,
            )
            funding.text("**Funding**", colour="accent3")
            funding.gallery(logos, columns=1, height=34)
            funding.text("Compute: [**Frontier**]{#c0392b} at ORNL", size=14, muted=True)
        with deck.slide("The people who did the work") as slide:
            slide.gallery(
                [(photo, f"**{name}**\n[{role}]{{muted}}")
                 for photo, (name, role) in zip(photos, PEOPLE, strict=True)],
                columns=4, height=110, crop="circle",
            )
        with deck.slide("Thank you", layout="columns", widths=(2, 1)) as slide:
            slide.columns[0].text("Questions?", size=40)
            repository = "[github.com/jamaliki/flexo-talk](https://github.com/jamaliki/flexo-talk)"
            slide.columns[0].text(f"Slides and code: {repository}", size=16)
            slide.columns[1].gallery([(photos[0], "**Ada Lovelace**\nada@example.org")], crop="circle", height=150)
    return deck


if __name__ == "__main__":
    print(talk(*sys.argv[1:2]).build(HERE / "build" / "thanks").summary())
