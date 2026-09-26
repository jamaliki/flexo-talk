"""A short talk, to show the language: every slide in one theme."""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck

HERE = Path(__file__).resolve().parent


def talk(theme: str = "paper") -> Deck:
    with Deck("demo", theme=theme, footer="flexo-talk · a demo") as deck:
        deck.title(
            "Figures that draw themselves",
            subtitle="One language for papers and slides",
            author="Kiarash Jamali",
            date="September 2026",
        )
        with deck.slide("Why another figure tool?") as slide:
            slide.bullets(
                "Figures take hours to draw, and minutes to break",
                "Every change to the model means redrawing by hand",
                [
                    "boxes drift out of line",
                    "arrows stop meeting their boxes",
                ],
                "Slides and papers drift apart in style",
            )
            slide.notes("Start with the pain: everyone here has redrawn a figure at 2 a.m.")
        with deck.slide("The same model, two ways", layout="two-columns") as slide:
            slide.left.bullets(
                "Write what the model *is*",
                "flexo lays it out and routes every arrow",
                "The theme decides every colour and weight",
            )
            with slide.right.figure() as figure:
                x = figure.root.text("x", "Input $x$")
                encoder = figure.root.block("encoder", label="Encoder", input=x, tone="encoder")
                head = figure.root.block("head", label="Head", input=encoder, tone="head")
                figure.root.text("y", r"$\hat{y}$", input=head)
        deck.section("Part two", subtitle="Figures from the literature")
        with deck.slide("Deep Q-learning", layout="figure") as slide:
            sys.path.insert(0, str(HERE.parent.parent / "flexo" / "examples"))
            import literature

            slide.add(literature.dqn())
    return deck


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else "paper"
    result = talk(theme).build(HERE / "build" / theme)
    print(result.summary())
