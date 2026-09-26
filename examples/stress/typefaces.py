"""Stress deck 4: type by role -- titles in one family, words in another, figures
in a third -- with centred accent titles, on the dark theme."""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck, DeckStyle

HERE = Path(__file__).resolve().parent


def talk(theme: str = "dark") -> Deck:
    style = DeckStyle(title_align="middle", title_role="tone-1-stroke", title_weight=700)
    with Deck(
        "typefaces", theme=theme, font="IBM Plex Sans", title_font="Latin Modern Roman",
        figure_font="Figtree", footer="Stress test · typefaces", style=style,
    ) as deck:
        deck.title("Three typefaces, one deck", subtitle="Titles, words, and figures each in their own")
        with deck.slide("Words in IBM Plex, titles in Latin Modern") as slide:
            slide.bullets(
                "Titles are set in the *title font*, in the accent colour, centred",
                "Bullets and tables are set in the **words' font**",
                ["maths too: $\\mathcal{L}(\\theta) = -\\log p_\\theta(x)$"],
            )
            slide.table([["Role", "Family"], ["Titles", "Latin Modern Roman"], ["Words", "IBM Plex Sans"],
                         ["Figures", "Figtree"]])
        with deck.slide("Figures in Figtree", layout="two-columns", split=0.4) as slide:
            slide.left.bullets("A figure keeps its own family", "set by `figure_font=`")
            slide.notes("Inline code uses backticks, as in Markdown.")
            with slide.right.figure() as figure:
                x = figure.text("x", "Tokens $x_{1:T}$")
                encoder = figure.block("enc", label="Encoder", input=x, tone="encoder", badge="frozen")
                figure.block("head", label="Classifier", input=encoder, tone="head", badge="trained")
        with deck.slide("Code, inline and as a listing") as slide:
            slide.bullets("Call `flexo.fit_in_box(figure, w, h)` to lay a figure out for a box")
            slide.code(
                """
                import flexo

                # A figure laid out for a 16:9 slide region
                fit = flexo.fit_in_box(figure, 864, 380, words=13)
                print(fit.layout, f"{fit.words:.1f}pt")
                """
            )
            slide.text("Monospace comes from `mono_family`, or the first installed of a list.", muted=True, size=14)
        deck.section("A section heading", subtitle="is a title too")
    return deck


if __name__ == "__main__":
    print(talk(*sys.argv[1:2]).build(HERE / "build" / "typefaces").summary())
