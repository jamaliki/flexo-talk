"""Stress decks 2 and 3: a hand-drawn deck, and a LaTeX-look deck from a theme file.

- ``sketchy``: the sketch theme; literature figures with badges; two figures
  in one region; words, a figure, and bullets stacked; a title long enough to
  wrap; a blank slide; sections.
- ``lab``: a YAML theme file (tikz type, a lab palette, straight lines);
  graphical models, maths everywhere, notes, a figure beside a picture.
"""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck, DeckStyle

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1].parent / "flexo" / "examples"))
import literature  # noqa: E402
import transformer as transformer_example  # noqa: E402


def sketchy(theme: str = "sketch") -> Deck:
    with Deck("sketchy", theme=theme, footer="Stress test · hand-drawn") as deck:
        deck.title("Fine-tuning, sketched", subtitle="Frozen weights, trained adapters", author="Lab meeting")
        with deck.slide("LoRA trains two small matrices beside a frozen one", layout="two-columns") as slide:
            slide.left.bullets(
                "$W$ stays frozen",
                "Train $A$ and $B$ only",
                ["rank $r \\ll d$", "$B = 0$ at the start"],
                "Merge after training: $W + BA$",
            )
            slide.right.add(literature.lora(theme))
        with deck.slide("Two figures, one idea") as slide:
            slide.text("The same encoder, before and after we freeze it.", muted=True)
            with slide.figure() as before:
                x = before.root.text("x", "$x$")
                before.root.block("enc", label="Encoder", input=x, tone="encoder", badge="trained")
            with slide.figure() as after:
                x = after.root.text("x", "$x$")
                encoder = after.root.block("enc", label="Encoder", input=x, tone="encoder", badge="frozen")
                after.root.block("head", label="Head", input=encoder, tone="head", badge="tuned")
            slide.bullets("Only the head learns in the second stage")
        with deck.slide(
            "A title that is long enough that it will certainly need two lines on a slide this wide",
        ) as slide:
            slide.bullets("The title wraps and the body moves down", "Nothing overlaps")
        deck.section("Architectures", subtitle="Straight from the papers")
        with deck.slide("The transformer", layout="figure") as slide:
            slide.add(transformer_example.transformer(theme))
        with deck.slide(layout="blank") as slide:
            slide.text("A blank slide: one line, centred.", align="middle", size=32)
    return deck


THEME = """\
palettes:
  Lab: ["#0b6e4f", "#c84c09", "#3f51b5", "#8e2c5a"]
theme:
  name: lab-latex
  base: tikz
  palette: Lab
  type: {size: 9pt}
  conventions: {lines: straight}
"""


def lab(theme: str | None = None) -> Deck:
    folder = HERE / "build"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lab.yaml").write_text(THEME)
    style = DeckStyle(title_size=28, body_size=19, numbers=True)
    with Deck("lab", theme=theme or str(folder / "lab.yaml"), footer="Stress test · theme file", style=style) as deck:
        deck.title("Latent variable models", subtitle="In the lab's own style", date="Autumn 2026")
        with deck.slide("Mixtures and their plates", layout="two-columns") as slide:
            slide.left.bullets(
                "Draw $z_n \\sim \\mathrm{Cat}(\\pi)$",
                "Then $x_n \\mid z_n \\sim \\mathcal{N}(\\mu_{z_n}, \\Sigma_{z_n})$",
                "Evidence: $\\log p(x) \\geq \\mathbb{E}_q[\\log p(x, z) - \\log q(z)]$",
            )
            figure = slide.right.figure(conventions={"lines": "straight"})
            with figure.plate("n", "$N$") as plate:
                z = plate.circle("z", "$z_n$")
                plate.circle("x", "$x_n$", shaded=True, input=z)
            slide.notes("The plate says: repeat for every data point.")
        with deck.slide("Topic models", layout="figure") as slide:
            slide.add(literature.lda("tikz"))
        with deck.slide("An HMM, and what it means", layout="two-columns") as slide:
            slide.left.add(literature.hidden_markov_model("tikz"))
            slide.right.bullets(
                "Hidden $z_t$, observed $x_t$",
                "$p(z_t \\mid z_{t-1}) = A_{z_{t-1} z_t}$",
                "Forward: $\\alpha_t(j) = \\sum_i \\alpha_{t-1}(i) A_{ij} B_j(x_t)$",
            )
        with deck.slide("The VAE", layout="figure") as slide:
            slide.add(literature.variational_autoencoder("tikz"))
    return deck


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "sketchy"
    deck = sketchy() if which == "sketchy" else lab()
    print(deck.build(HERE / "build" / which).summary())
