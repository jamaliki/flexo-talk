"""A journal-club talk on the Vision Transformer, made to find what a real talk still asks for.

    python examples/journal_club.py                 # paper theme, into examples/build/journal-club
    python examples/journal_club.py ../design-corner/talks/themes/night.yaml

Dosovitskiy et al., "An Image is Worth 16x16 Words: Transformers for Image
Recognition at Scale", ICLR 2021. The table and the numbers to remember are the
paper's (Table 2); the two plots are redrawn by eye from its Figures 3 and 7, so
their values are approximate. The picture cut into patches is drawn here, so the
example needs no files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import flexo

from flexo_talk import Deck

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "build" / "journal-club-assets"
TIMES = "\N{MULTIPLICATION SIGN}"


def picture() -> Path:
    """A small landscape, and the same picture cut into a 4 by 4 grid of patches."""

    from PIL import Image, ImageDraw

    path = ASSETS / "patches.png"
    if path.exists():
        return path
    size, cut, gap = 480, 4, 10
    scene = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(scene)
    for y in range(size):
        sky = y / size
        draw.line([(0, y), (size, y)], fill=(int(120 + 110 * sky), int(170 + 60 * sky), int(230 - 30 * sky)))
    draw.ellipse((310, 60, 400, 150), fill=(250, 214, 110))
    draw.polygon([(0, 330), (130, 170), (260, 330)], fill=(92, 112, 140))
    draw.polygon([(150, 330), (300, 150), (480, 330)], fill=(70, 90, 120))
    draw.rectangle((0, 320, size, size), fill=(96, 150, 92))
    draw.rectangle((60, 360, 110, 440), fill=(120, 84, 60))
    draw.ellipse((30, 290, 140, 390), fill=(58, 118, 70))
    step = size // cut
    grid = Image.new("RGBA", (size + gap * (cut - 1), size + gap * (cut - 1)), (0, 0, 0, 0))
    for row in range(cut):
        for column in range(cut):
            patch = scene.crop((column * step, row * step, (column + 1) * step, (row + 1) * step))
            grid.paste(patch, (column * (step + gap), row * (step + gap)))
    path.parent.mkdir(parents=True, exist_ok=True)
    grid.save(path)
    return path


def architecture(fig: flexo.Figure) -> None:
    """Figure 1: patches, their embeddings, the encoder, and the head that reads the class token."""

    column = fig.root.column("model", gap=22)
    patches = column.text("patches", "Image, cut into $16 \\times 16$ patches")
    projection = column.block("projection", label="Linear projection of flattened patches", tone="embedding",
                              input=patches)
    tokens = column.block("tokens", label="Prepend a learned [class] token", tone="embedding", input=projection)
    with column.row("positions", gap=18) as row:
        position = row.text("position", "Position embedding")
        total = row.add("sum", inputs=[tokens, position])
    encoder = column.block("encoder", label=f"Transformer encoder  {TIMES}$L$", tone="attention", input=total)
    head = column.mlp("head", label="MLP head", input=encoder)
    column.text("class", "Class: bird, ball, car, ...", input=head)


def encoder_block(fig: flexo.Figure) -> None:
    """Figure 1, right: one pre-norm encoder layer."""

    column = fig.root.column("layer", gap=16)
    tokens = column.text("in", "Embedded patches")
    norm = column.block("norm1", label="Norm", tone="norm", input=tokens)
    attention = column.block("mha", label="Multi-head attention", tone="attention", input=norm)
    first = column.add("add1", inputs=[attention])
    fig.connect(tokens, first, shape="orthogonal", label="residual")
    norm2 = column.block("norm2", label="Norm", tone="norm", input=first)
    mlp = column.block("mlp", label="MLP", tone="mlp", input=norm2)
    second = column.add("add2", inputs=[mlp])
    fig.connect(first, second, shape="orthogonal")
    column.text("out", "To the next layer", input=second)


CODE = '''\
class PatchEmbedding(nn.Module):
    def __init__(self, size=224, patch=16, width=768):
        super().__init__()
        # A convolution whose stride is its kernel: one token per patch
        self.cut = nn.Conv2d(3, width, patch, stride=patch)
        self.cls = nn.Parameter(torch.zeros(1, 1, width))
        self.position = nn.Parameter(torch.zeros(1, (size // patch) ** 2 + 1, width))

    def forward(self, images):
        tokens = self.cut(images).flatten(2).transpose(1, 2)
        cls = self.cls.expand(len(images), -1, -1)
        return torch.cat([cls, tokens], dim=1) + self.position
'''


def talk(theme: str = "paper") -> Deck:
    import matplotlib.pyplot as plt
    import numpy as np

    with Deck("journal-club", theme=theme, footer="Journal club · ViT") as deck:
        deck.title(
            f"An image is worth 16{TIMES}16 words",
            subtitle="Transformers for image recognition at scale",
            author="Dosovitskiy et al., ICLR 2021",
            date="Journal club, October 2026",
        )
        deck.agenda()
        deck.section("The idea", subtitle="Read an image as a sentence")
        deck.statement("Cut the image into patches, and give them to a [plain transformer]{accent}.")
        with deck.slide("Why try it", layout="two-columns", split=0.55) as slide:
            slide.left.bullets(
                "Convolutions build in what images are like",
                ["locality: neighbours matter most", "translation: a cat is a cat anywhere"],
                "Transformers build in almost nothing",
                "In language, that was fine given data enough",
                "*Does vision need the priors, or only the data?*",
            )
            slide.right.image(picture())
            slide.right.text(f"A $224^2$ image is $14 {TIMES} 14 = 196$ patches of $16^2$ pixels", size=14,
                             muted=True, align="middle")
        with deck.slide("The model", layout="figure") as slide:
            with slide.figure() as figure:
                architecture(figure)
            slide.notes("The only image-specific parts: the patch cut and the learned 1-D positions.")
        with deck.slide("One encoder layer", layout="two-columns", split=0.55) as slide:
            slide.left.bullets(
                "The language model's encoder, unchanged",
                "LayerNorm before each block, a residual around it",
                "The MLP: two layers with a GELU between",
                "Base, Large, Huge: 12, 24, 32 layers of width 768, 1024, 1280",
            )
            with slide.right.figure() as figure:
                encoder_block(figure)
        with deck.slide("The only new code", layout="content") as slide:
            slide.code(CODE)
            slide.footnote("Written for this talk after the paper's description; not the authors' code.")
        deck.section("Results", subtitle="Pre-trained on JFT-300M, fine-tuned")
        with deck.slide("Better than the best CNNs, for less compute") as slide:
            slide.table([
                ["", "ViT-H/14", "ViT-L/16", "BiT-L", "Noisy Student"],
                ["ImageNet", "**88.55**", "87.76", "87.54", "88.4"],
                ["CIFAR-100", "**94.55**", "93.90", "93.51", "\u2013"],
                ["Oxford Flowers-102", "99.68", "**99.74**", "99.63", "\u2013"],
                ["VTAB (19 tasks)", "**77.63**", "76.28", "76.29", "\u2013"],
                ["TPUv3-core-days", "2.5k", "**0.68k**", "9.9k", "12.3k"],
            ])
            slide.footnote("Top-1 accuracy (%); Table 2 of the paper.")
        with deck.slide("The numbers to remember") as slide:
            slide.stats(
                ("88.55%", "ImageNet top-1"), ("2.5k", "TPUv3-core-days"), (f"4{TIMES}", "less compute than BiT-L")
            )
        with deck.plotting():
            data, axes = plt.subplots()
            sizes = ["ImageNet\n1.3M", "ImageNet-21k\n14M", "JFT\n300M"]
            where = np.arange(3)
            axes.fill_between(where, [76.0, 83.5, 86.5], [78.0, 85.0, 87.5], alpha=0.25, label="BiT (ResNets)")
            axes.plot(where, [77.9, 81.3, 84.2], marker="o", label="ViT-B/32")
            axes.plot(where, [76.5, 85.2, 87.8], marker="o", label="ViT-L/16")
            axes.plot(where, [74.0, 85.1, 88.5], marker="o", label="ViT-H/14")
            axes.set_xticks(where, sizes)
            axes.set_ylabel("ImageNet top-1 (%)")
            axes.set_xlabel("Pre-training data")
            axes.legend()
        with deck.slide("Data is what the priors were standing in for", layout="two-columns", split=0.6) as slide:
            slide.left.plot(data)
            slide.right.bullets(
                "On ImageNet alone, big ViTs lose to ResNets",
                "With 14M images they draw level",
                "With 300M they win, and keep improving",
            )
            slide.footnote("Values read by eye from the paper's Figure 3.")
        with deck.plotting():
            reach, axes = plt.subplots()
            rng = np.random.default_rng(3)
            for layer in range(24):
                spread = 110 * np.exp(-layer / 7)
                heads = np.clip(120 - spread + rng.uniform(-spread, spread * 0.4, 16), 5, 125)
                axes.scatter(np.full(16, layer + 1), heads, s=10, color="C0", alpha=0.7)
            axes.set_xlabel("Layer")
            axes.set_ylabel("Mean attention distance (pixels)")
        with deck.slide("Some heads look far from the first layer", layout="two-columns", split=0.55) as slide:
            slide.left.plot(reach)
            slide.right.bullets(
                "Each dot is one head of ViT-L/16",
                "Early layers mix near and far heads",
                "Near heads act like a CNN's first layers",
                "Deeper, every head attends across the image",
            )
            slide.footnote("Redrawn by eye after the paper's Figure 7.")
        deck.section("Discussion")
        with deck.slide("What the abstract claims") as slide:
            slide.quote(
                "When pre-trained on large amounts of data and transferred to multiple mid-sized or small image "
                "recognition benchmarks, Vision Transformer attains excellent results compared to "
                "state-of-the-art convolutional networks while requiring substantially fewer computational "
                "resources to train.",
                by="Dosovitskiy et al., 2021",
            )
        with deck.slide("Questions for us", layout="two-columns") as slide:
            slide.left.bullets(
                "Is \u201cfewer resources\u201d fair when JFT-300M is private?",
                "How much of the gain is the data, and how much the recipe?",
                "Would the result hold at ImageNet scale with better training?",
                numbered=True,
            )
            slide.right.callout(
                "DeiT (Touvron et al., 2021) trained ViTs on ImageNet alone, with strong augmentation "
                "and distillation from a CNN teacher.",
                title="What came next",
            )
            slide.right.callout(
                "Swin (Liu et al., 2021) put locality back: attention within shifted windows.",
                colour="accent3",
            )
    return deck


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else "paper"
    name = Path(theme).stem if theme.endswith(".yaml") else theme
    result = talk(theme).build(HERE / "build" / "journal-club" / name)
    print(result.summary())
