"""Stress deck 1: a results talk -- matplotlib plots, a saved SVG plot, a PNG,
maths in bullets, a long title, and a slide with too many words."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt
import numpy as np

from flexo_talk import Deck

HERE = Path(__file__).resolve().parent


def curves(deck: Deck):
    with deck.plotting():
        figure, axes = plt.subplots()
        steps = np.linspace(0, 50, 200)
        for rate, name in ((0.08, "Adam"), (0.05, "SGD + momentum"), (0.03, "SGD")):
            axes.plot(steps, 2.2 * np.exp(-rate * steps) + 0.15, label=name)
        axes.set_xlabel("Epoch")
        axes.set_ylabel(r"Loss $\mathcal{L}_\theta$")
        axes.set_ylim(0, 2.5)
        axes.legend()
    return figure


def bars(deck: Deck):
    with deck.plotting():
        figure, axes = plt.subplots()
        models = ["MLP", "CNN", "ViT-S", "ViT-B"]
        accuracy = [71.2, 84.5, 88.1, 90.3]
        errors = [1.1, 0.8, 0.6, 0.5]
        axes.bar(models, accuracy, yerr=errors, capsize=4)
        axes.set_ylabel("Top-1 accuracy (%)")
        axes.set_ylim(60, 95)
        for x, value in enumerate(accuracy):
            axes.annotate(f"{value:.1f}", (x, value + 1.5), ha="center")
    return figure


def heatmap(deck: Deck):
    with deck.plotting():
        figure, axes = plt.subplots()
        rng = np.random.default_rng(0)
        data = rng.random((8, 8))
        image = axes.imshow(data, cmap="viridis")
        figure.colorbar(image, ax=axes, label="attention weight")
        axes.set_title("Head 3, layer 6")
    return figure


def saved_svg() -> Path:
    """A plot saved to SVG by someone else, in matplotlib's default look."""

    target = HERE / "build" / "scatter.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    figure, axes = plt.subplots(figsize=(4, 3))
    points = rng.normal(size=(2, 120))
    axes.scatter(points[0], points[1] * 0.5 + points[0] * 0.8, s=12, alpha=0.7)
    axes.set_xlabel("latent $z_1$")
    axes.set_ylabel("latent $z_2$")
    axes.set_title("Posterior samples")
    figure.tight_layout()
    figure.savefig(target)
    plt.close(figure)
    return target


def saved_png() -> Path:
    target = HERE / "build" / "samples.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    matplotlib.use("agg")
    rng = np.random.default_rng(2)
    figure, axes = plt.subplots(2, 4, figsize=(4, 2))
    for axis in axes.flat:
        axis.imshow(rng.random((12, 12)), cmap="gray")
        axis.axis("off")
    figure.savefig(target, dpi=150)
    plt.close(figure)
    matplotlib.use("svg")
    return target


def talk(theme: str = "paper") -> Deck:
    with Deck("results", theme=theme, footer="Stress test · results") as deck:
        deck.title(
            "What we learned from training forty thousand small transformers",
            subtitle="A results talk with plots, maths, and too many words",
            author="A. Researcher",
            date="2026",
        )
        with deck.slide("Training curves") as slide:
            slide.plot(curves(deck))
        with deck.slide("Accuracy against model size", layout="two-columns") as slide:
            slide.left.bullets(
                "Accuracy rises with size: $\\Delta = +19.1$ points",
                "ViT-B beats CNN by **5.8** points",
                ["error bars: $\\pm 1\\sigma$ over 5 seeds"],
            )
            slide.right.plot(bars(deck))
        with deck.slide("Where attention goes", layout="two-columns") as slide:
            slide.left.plot(heatmap(deck))
            slide.right.bullets("Heads specialise early", "Diagonal: *local* attention", "Off-diagonal: copying")
        with deck.slide("A plot someone saved as SVG") as slide:
            slide.image(saved_svg())
        with deck.slide("Samples (a PNG)") as slide:
            slide.image(saved_png())
            slide.text("Eight samples from the model at epoch 50.", align="middle", muted=True)
        with deck.slide("Results on ImageNet") as slide:
            slide.table(
                [
                    ["Model", "Params", "FLOPs", "Top-1 (%)", "Top-5 (%)"],
                    ["ResNet-50", "25.6M", "4.1G", "76.1", "92.9"],
                    ["ViT-S/16", "22.1M", "4.6G", "79.9 $\\pm$ 0.2", "95.0"],
                    ["ViT-B/16", "86.6M", "17.6G", "**81.8**", "**95.9**"],
                    ["Ours ($\\lambda = 0.1$)", "24.0M", "4.3G", "81.2", "95.6"],
                ]
            )
            slide.text("Mean of three seeds; best in **bold**.", muted=True, size=14)
        with deck.slide("Uneven columns", layout="two-columns", split=0.35) as slide:
            slide.left.bullets("A narrow column of words", "and a wide plot")
            slide.right.plot(curves(deck))
        with deck.slide("The objective") as slide:
            slide.bullets(
                "We minimise $\\mathcal{L}(\\theta) = \\mathbb{E}_{x \\sim p}[-\\log q_\\theta(x)]$",
                "with $q_\\theta(x) = \\prod_{t=1}^{T} q_\\theta(x_t \\mid x_{<t})$",
                "Gradient: $\\nabla_\\theta \\mathcal{L} = -\\mathbb{E}[\\nabla_\\theta \\log q_\\theta]$",
                "Temperature $\\tau \\in \\{0.5, 1, 2\\}$; $\\beta_1 = 0.9$, $\\beta_2 = 0.999$",
            )
        with deck.slide("A slide with far too many words on it for anyone to read") as slide:
            slide.bullets(
                *(
                    f"Point {index}: a sentence long enough that it has to wrap onto a second line "
                    "because nobody edits their slides before the talk"
                    for index in range(1, 9)
                )
            )
    return deck


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else "paper"
    result = talk(theme).build(HERE / "build" / f"results-{theme}")
    print(result.summary())
