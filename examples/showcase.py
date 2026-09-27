"""One talk in five looks: the same words and figures, a different page each time.

    python examples/showcase.py            # every look, into examples/build/showcase/<look>
    python examples/showcase.py band swiss # one look in one theme

Each look is a ``DeckStyle`` preset (``Deck(look=...)``); each is paired here
with a flexo theme that suits it. The talk uses every kind of slide and block:
an agenda, sections, a statement, numbers to remember, a quotation, a callout,
figures, a plot, a table, and people.
"""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck

HERE = Path(__file__).resolve().parent
FONTS = {"editorial": {"title_font": "Latin Modern Roman"}}
"""An editorial page sets its headings in a serif over sans-serif words."""
PAIRS = {
    "classic": "paper",
    "band": "swiss",
    "editorial": "classic",
    "keynote": "dark",
    "margin": "midcentury",
}


def backdrop() -> Path:
    """A photograph-like picture for the title slide (drawn here, so the example has no files)."""

    from PIL import Image, ImageDraw, ImageFilter

    path = HERE / "build" / "showcase-assets" / "backdrop.jpg"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    picture = Image.new("RGB", (1600, 900), (18, 32, 58))
    draw = ImageDraw.Draw(picture)
    for index in range(40):
        x, y = (index * 397) % 1600, (index * 211) % 900
        radius = 40 + (index * 37) % 160
        colour = (40 + index * 3 % 90, 90 + index * 5 % 100, 150 + index * 7 % 90)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)
    picture.filter(ImageFilter.GaussianBlur(28)).save(path, quality=88)
    return path


def people() -> list[tuple[Path, str]]:
    from PIL import Image, ImageDraw

    folder = HERE / "build" / "showcase-assets"
    folder.mkdir(parents=True, exist_ok=True)
    names = [("Ada Lovelace", "PI"), ("Alan Turing", "Postdoc"), ("Grace Hopper", "PhD"), ("Emmy Noether", "PhD")]
    cells = []
    for index, (name, role) in enumerate(names):
        path = folder / f"person{index}.jpg"
        if not path.exists():
            picture = Image.new("RGB", (400, 400), (190 - 20 * index, 180 + 10 * index, 160 + 15 * index))
            draw = ImageDraw.Draw(picture)
            draw.ellipse((130, 70, 270, 230), fill=(236, 200, 170))
            draw.ellipse((70, 250, 330, 520), fill=(50 + 30 * index, 70, 110))
            picture.save(path, quality=90)
        cells.append((path, f"**{name}**\n[{role}]{{muted}}"))
    return cells


def talk(look: str = "classic", theme: str | None = None) -> Deck:
    sys.path.insert(0, str(HERE.parent.parent / "flexo" / "examples"))
    import literature

    theme = theme or PAIRS[look]
    fonts = FONTS.get(look, {})
    with Deck("showcase", theme=theme, look=look, footer="Folding with diffusion · 2026", **fonts) as deck:
        deck.title(
            "Folding proteins with diffusion",
            subtitle="What a generative model learns about structure",
            author="Ada Lovelace", date="Group meeting, September 2026",
            background=backdrop() if look == "keynote" else None, shade=0.35,
        )
        deck.agenda()
        deck.section("Why structure", subtitle="Cheap to predict, dear to trust")
        deck.statement("Predicting a structure takes seconds. [Trusting it]{accent} takes a lab.")
        with deck.slide("The gap we want to close") as slide:
            slide.stats(
                ("200M", "structures predicted"), ("0.1%", "solved by experiment"), ("~1 yr", "per solved structure")
            )
            slide.callout(
                "A model that knows *how sure it is* tells us which structures to solve first.",
                title="The idea",
            )
            slide.footnote("Numbers rounded; see the AlphaFold database and the PDB.")
        deck.section("How it works", subtitle="A denoiser, conditioned on the sequence")
        with deck.slide("From sequence to structure", layout="two-columns", split=0.45) as slide:
            slide.left.bullets(
                "A language model reads the sequence",
                "A denoiser turns noise into coordinates",
                ["trained on solved structures", "sampled many times"],
                "Their spread is the model's doubt",
            )
            with slide.right.figure() as figure:
                sequence = figure.root.text("s", "Sequence $s$")
                reader = figure.root.block("lm", label="Language model", input=sequence, tone="encoder", badge="frozen")
                denoiser = figure.root.block(
                    "den", label="Denoiser $\\epsilon_\\theta$", input=reader, tone="head", badge="trained"
                )
                figure.root.text("x", "Structure $x_0$", input=denoiser)
        with deck.slide("The reverse process", layout="figure") as slide:
            slide.add(literature.diffusion())
        with deck.slide("Samples agree where the model is sure", layout="two-columns", split=0.58) as slide:
            import matplotlib.pyplot as plt
            import numpy as np

            with deck.plotting():
                plot, axes = plt.subplots()
                confidence = np.linspace(20, 95, 60)
                spread = 14 * np.exp(-(confidence - 20) / 28) + 0.6
                axes.plot(confidence, spread, label="diffusion (ours)")
                axes.plot(confidence, spread * 1.6 + 0.8, label="ensemble")
                axes.set_xlabel("Confidence (pLDDT)")
                axes.set_ylabel("Spread of samples (Å)")
                axes.legend()
            slide.left.plot(plot)
            slide.right.table(
                [
                    ["Method", "RMSD (Å)", "Calibrated"],
                    ["Ensemble", "3.4", "no"],
                    ["Dropout", "3.1", "no"],
                    ["**Ours**", "**2.2**", "**yes**"],
                ]
            )
            slide.right.text("Lower spread, and it tracks the error.", size=16, muted=True)
        deck.section("What next")
        with deck.slide("What people said") as slide:
            slide.quote(
                "The model's doubt was the most useful thing it told us.",
                by="a crystallographer, after the first round",
            )
        with deck.slide("Thanks", layout="columns", widths=(3, 2)) as slide:
            slide.columns[0].gallery(people(), columns=4, crop="circle", height=90)
            slide.columns[1].text("**Funded by** the [Wellcome Trust]{accent}", size=16)
            repository = "[github.com/jamaliki/flexo](https://github.com/jamaliki/flexo)"
            slide.columns[1].text(f"Code and slides: {repository}", size=16)
    return deck


if __name__ == "__main__":
    chosen = sys.argv[1:2] or list(PAIRS)
    for look in chosen:
        theme = sys.argv[2] if len(sys.argv) > 2 else PAIRS[look]
        result = talk(look, theme).build(HERE / "build" / "showcase" / look)
        print(look, theme, result.summary().splitlines()[0])
