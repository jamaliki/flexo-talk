# flexo-talk

Slide decks written in [flexo](https://github.com/jamaliki/flexo)'s language: a
`with` block, one theme, and figures that are real flexo figures. A deck builds
to a PowerPoint file whose every box, line, and word is a native, editable
shape, to a PDF (one page per slide, real text, embedded fonts), and to an SVG
and a PNG per slide -- all in Python.

```python
from flexo_talk import Deck

with Deck("results", theme="paper", footer="Group meeting") as deck:
    deck.title("Figures that draw themselves", subtitle="One language for papers and slides",
               author="Kiarash Jamali", date="September 2026")
    with deck.slide("Why another figure tool?") as slide:
        slide.bullets(
            "Figures take hours to draw, and minutes to break",
            "Every change to the model means redrawing by hand",
            ["boxes drift out of line", "arrows stop meeting their boxes"],  # a level in
        )
        slide.notes("Everyone here has redrawn a figure at 2 a.m.")
    with deck.slide("The model", layout="two-columns") as slide:
        slide.left.bullets("Write what the model *is*", "flexo lays it out")
        with slide.right.figure() as figure:          # a flexo Figure, in the deck's theme
            x = figure.root.text("x", "Input $x$")
            figure.root.block("encoder", label="Encoder", input=x, tone="encoder")
    deck.section("Part two", subtitle="Figures from the literature")
    with deck.slide("Deep Q-learning", layout="figure") as slide:
        slide.add(my_flexo_figure)                     # any flexo figure, redrawn in the deck's look

result = deck.build("build")        # build/results.pptx, results.pdf, results-01.svg/.png, ...
print(result.summary())
```

## One theme for everything

`Deck(theme=...)` takes any flexo theme (`paper`, `tikz`, `dark`, `sketch`, ...)
or a theme file (`theme="lab.yaml"`), with `palette=`, `font=`, `conventions=`
and `sketch=` exactly as a flexo `Figure` takes them. Titles, bullets, and
figures share its typeface and colours: bullet marks and title rules take the
palette's first colour, captions and footers its muted ink. A figure on a slide
is compiled by flexo at the width of its place -- at a size where its words read
at the deck's figure size -- then cropped to its ink and scaled to fill the place,
never so far that its words outgrow the body text.

The slide's proportions -- sizes of title, body and figure text, margins,
indents, gaps, the title rule, slide numbers -- are `DeckStyle` fields:
`Deck(style=DeckStyle(body_size=22, numbers=False))`.

## Slides

| Call | Makes |
| --- | --- |
| `deck.title(title, subtitle=, author=, date=)` | The opening slide, centred |
| `deck.section(title, subtitle=)` | A divider between parts |
| `deck.slide(title, layout="content")` | A title over one body (`slide.body`) |
| `deck.slide(title, layout="two-columns", split=0.5)` | A title over `slide.left` and `slide.right`; `split` is the left's share |
| `deck.slide(title, layout="figure")` | A title over one figure as large as the slide allows |
| `deck.slide(layout="blank")` | The whole slide as one body |

A region takes blocks, set one under the other: `bullets(*items)` (a nested list
is the level below), `text(words, size=, align=, muted=)`, `figure(**options)`
(a new flexo `Figure`, used as a `with` block), `add(figure)` (an existing one),
`plot(matplotlib_figure)`, `table(rows)`, and `image(path)`. Words take the height they need
and pictures share the rest; when a region has more words than room, its words
are set smaller together (down to `DeckStyle.small_size`) and the build summary
says so.

## Tables

```python
slide.table([
    ["Model", "Params", "Top-1 (%)"],
    ["ResNet-50", "25.6M", "76.1"],
    ["Ours ($\\lambda = 0.1$)", "24.0M", "**81.2**"],
])
```

A table is ruled as in a paper -- a rule above, one under the header, one below,
no grid -- with its header bold and each column as wide as its widest cell.
Columns of numbers are set flush right (`align="lrr"` or a list of
`start`/`middle`/`end` to choose); `header=False` drops the header. In the
PowerPoint it is a native table with the same columns, rows, and rules.

## Plots

```python
import matplotlib.pyplot as plt

with deck.plotting():                      # the deck's font, sizes, inks, and tones
    figure, axes = plt.subplots()
    axes.plot(epochs, loss, label="Adam")
    axes.set_ylabel(r"Loss $\mathcal{L}_\theta$")
with deck.slide("Training curves") as slide:
    slide.plot(figure)
```

`plot()` lays a matplotlib figure out again at the size of its place
(constrained layout), so its words are set at the deck's size rather than
scaled, in the deck's font. It is placed as vectors: in the PowerPoint every
line is a freeform and every tick label live text; in the PDF it is vectors and
real text. `deck.plotting()` gives matplotlib the deck's look (`deck.plot_style()`
is the same settings as a dict). An SVG saved by any program --
`slide.image("plot.svg")` -- is placed as vectors the same way when it holds
only what flexo draws exactly (paths, text, clips, pictures); otherwise, and for
PNG and JPEG files, it is a picture. Slide text is flexo markup -- `$...$` is math -- plus
`*emphasis*` and `**strong**`. The slide's own methods go to its first region, so a
one-region slide reads simply. `slide.notes(text)` keeps the speaker notes.

## PowerPoint

Each slide's SVG is read back with `flexo.drawing` and written as native shapes:
rectangles as (rounded) rectangles, circles as ellipses, lines as freeforms
with the same lines and curves, arrowheads drawn exactly and grouped with their
line, every label an editable text box in its own face and size, and each flexo
component a group named by its id. A bulleted list is one text box of bulleted
paragraphs, so it edits like any PowerPoint list. The slide background, notes,
and 16:9 size are set as PowerPoint sets them.

Dashed lines use PowerPoint's preset dashes (nearest to the figure's pattern),
which every slide program draws; raised and lowered runs are written so they
are drawn at the figure's script size.

The PDF needs no fonts where it is opened: it embeds them. The PowerPoint file's
text is drawn by the program that opens it, in fonts installed there:
install the theme's fonts (flexo bundles them: `flexo.fonts.bundled_font_directory()`)
wherever the deck is opened, or choose a theme font that is already there.

## Command line

```bash
flexo-talk build talk.py              # the deck the function talk() returns
flexo-talk build talk.py:results -o out --formats pptx,pdf --theme dark
```

## Development

```bash
uv sync --all-groups        # uses ../flexo, editable
uv run pytest
uv run python examples/demo.py
```
