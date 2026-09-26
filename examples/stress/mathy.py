"""Stress deck 6: maths everywhere -- in titles, footers, table headers, and figures
that embed a picture."""

from __future__ import annotations

import sys
from pathlib import Path

from flexo_talk import Deck

HERE = Path(__file__).resolve().parent

MOLECULE = """<svg xmlns="http://www.w3.org/2000/svg" width="80pt" height="60pt" viewBox="0 0 80 60">
 <line x1="15" y1="30" x2="40" y2="15" stroke="#333" stroke-width="2"/>
 <line x1="40" y1="15" x2="65" y2="30" stroke="#333" stroke-width="2"/>
 <circle cx="15" cy="30" r="8" fill="#e45756"/><circle cx="40" cy="15" r="9" fill="#4c78a8"/>
 <circle cx="65" cy="30" r="8" fill="#e45756"/></svg>"""


def talk(theme: str = "tikz") -> Deck:
    art = HERE / "build" / "molecule.svg"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(MOLECULE)
    with Deck("mathy", theme=theme, footer="Stress test · $\\mathbb{E}[\\text{maths}]$") as deck:
        deck.title("Minimising $\\mathcal{L}(\\theta)$", subtitle="with $\\nabla_\\theta$ and $x^{(i)}_t$")
        with deck.slide("The ELBO: $\\log p(x) \\geq \\mathbb{E}_{q}[\\log p(x,z)] - H$") as slide:
            slide.table(
                [
                    ["$\\beta$", "$\\mathcal{L}_{\\text{rec}}$", "$D_{\\text{KL}}$", "$\\log p(x)$"],
                    ["0.5", "81.2", "12.1", "$-93.3$"],
                    ["1.0", "84.0", "8.4", "$-92.4$"],
                    ["4.0", "91.7", "3.2", "$-94.9$"],
                ]
            )
            slide.footnote("[1] Kingma & Welling, *Auto-Encoding Variational Bayes*, ICLR 2014.")
            slide.footnote("[2] Higgins et al., *$\\beta$-VAE*, ICLR 2017.")
        with deck.slide("A figure with a picture in it", layout="two-columns") as slide:
            slide.left.bullets("A molecule $M$ is embedded", "The encoder reads $\\phi(M)$")
            with slide.right.figure() as figure:
                mol = figure.image("mol", art, label="Molecule $M$")
                enc = figure.block("enc", label="Encoder $\\phi$", input=mol, tone="encoder")
                figure.text("z", "$z \\in \\mathbb{R}^{d}$", input=enc)
    return deck


if __name__ == "__main__":
    print(talk(*sys.argv[1:2]).build(HERE / "build" / "mathy").summary())
