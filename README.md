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
palette's first colour, captions and footers its muted ink.

Type can be set by role: `Deck(font="IBM Plex Sans", title_font="Latin Modern
Roman", figure_font="Figtree")` sets the words, the titles and section headings,
and the figures each in their own family (each falls back to `font`, then the
theme's). `DeckStyle(title_align="middle", title_role="tone-1-stroke",
title_weight=700)` centres titles and paints them in the accent colour.

### Figures are laid out for the slide

A figure on a slide is laid out by flexo for its place -- its width *and* its
height (`flexo.fit_in_box`) -- at a size where its words read at the deck's
figure size: as written, or **turned** (a stack that reads upward laid out left
to right, rows as columns, Q/K/V glyphs lying down), or spaced closer, whichever
lets its words be largest there, never larger than the body text; a figure
still too small is **folded**, its long rows set on two lines (the full
transformer on one slide: encoder above, decoder folded, 7pt words instead of
4pt). The build summary notes a figure it turned or folded;
`slide.add(figure, turn=False)` keeps one as written. Figures sharing a region
take one scale, so their words match. A figure whose words still end up under
7pt is reported with what to do. Laying a figure out can take a while for a large one (the
full transformer, about half a minute), so each is kept in a cache between builds
(`~/Library/Caches/flexo-talk` or `$XDG_CACHE_HOME/flexo-talk`), keyed by the figure,
its place, and flexo's own source: a rebuild after editing words is immediate.
`FLEXO_TALK_CACHE=0` turns the cache off; `FLEXO_TALK_CACHE=dir` moves it.

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
| `deck.slide(title, layout="columns", columns=3)` | Any number of columns, `slide.columns[i]`; `widths=(2, 1, 1)` makes them uneven |
| `deck.slide(title, layout="figure")` | A title over one figure as large as the slide allows |
| `deck.slide(layout="blank")` | The whole slide as one body |

A region takes blocks, set one under the other: `bullets(*items)` (a nested list
is the level below; `numbered=True` numbers the outer level, natively in PowerPoint;
`reveal=True` shows the outer items one click at a time -- PowerPoint builds, and a
PDF page per step unless `deck.build(handout=True)`), `text(words, size=, align=, muted=)`, `figure(**options)`
(a new flexo `Figure`, used as a `with` block), `add(figure)` (an existing one),
`plot(matplotlib_figure)`, `table(rows)`, `gallery(pictures)` (logos or people in a
grid, captions under them, `crop="circle"` for photographs), `code(source)` (a monospace listing
on a tinted panel, comment lines muted), and `image(path)`. Words take the
height they need and pictures share the rest; when a region has more words than
room, its words are set smaller together (down to `DeckStyle.small_size`) and
the build summary says so.

Right-to-left text (Persian, Arabic, Hebrew) is set right to left: a title or
paragraph whose first letter is right to left aligns right, its bullet or number
on the right, and PowerPoint gets right-to-left paragraphs; English words,
numbers, and maths inside it keep their order.

Slide text is flexo markup -- `$...$` is math, `` `code` `` is monospace,
`[words](url)` links (a hyperlink in the PowerPoint, a link in the PDF),
`[words]{accent}` paints words (`accent2`..., `muted`, `#rrggbb`) --
plus `*emphasis*` and `**strong**`. The slide's own methods go to its first
region, so a one-region slide reads simply. `slide.notes(text)` keeps the
speaker notes; `slide.footnote(text)` sets a reference small and muted at the
foot of the slide.

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
PNG and JPEG files, it is a picture.

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
A variable face (IBM Plex Sans in the classic and paper themes) is drawn by slide
programs at regular or bold only; a weight between (a 600 title) comes out as
one of the two. Choose a family with static faces (Figtree has a SemiBold) where
an in-between weight matters. Emoji are pictures, not outlines, and are refused
with a message rather than drawn in a substitute.

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

`examples/stress/` holds decks that push at the edges: `results.py` (matplotlib
plots, a saved SVG and a PNG, a table, maths, an overfull slide), `variety.py`
(`sketchy`, hand-drawn with literature figures; `lab`, a YAML theme file),
`typefaces.py` (a family per role, code), and `edges.py` (4:3 slides, CJK and
Arabic, unbreakable words, deep lists, a JPEG, a gradient SVG). Each is checked
by rendering its PowerPoint file in ONLYOFFICE (its `x2t` converter, to PDF) and
comparing every page with flexo-talk's own PDF of the same deck; they agree to
within antialiasing.
