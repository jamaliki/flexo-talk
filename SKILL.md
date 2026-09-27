---
name: flexo-talk
description: Make slide decks with flexo-talk -- titles, bullets, tables, plots, quotes, big numbers, people, and real flexo figures in one theme and one look -- exported to editable PowerPoint (PPTX), PDF, and SVG/PNG per slide. Use when asked for a talk, presentation, slides, a lab-meeting or conference deck, or an acknowledgements slide, especially one that should match a paper's figures.
---

# Making slide decks with flexo-talk

flexo-talk writes a deck the way [flexo](https://github.com/jamaliki/flexo)
writes a figure: a `with` block in one theme, no coordinates. You say what is on
each slide; flexo-talk decides where it goes and how large, and every figure is a
real flexo figure laid out for its place. Every output is written in Python (no
Inkscape, no LibreOffice): a PowerPoint of native, editable shapes and text, a
PDF with embedded fonts, and an SVG and PNG per slide.

## Setup

flexo-talk lives next to flexo (`../flexo`, installed editable by uv).

```bash
uv sync --all-groups                 # in the flexo-talk checkout
uv run python talk.py                # a script that builds its deck
uv run flexo-talk build talk.py      # or: build the deck that talk() returns
uv run flexo-talk build talk.py:results -o out --formats pptx,pdf --theme dark
```

matplotlib is needed only for `slide.plot` (the `plots` extra); Pillow only for
`gallery(..., crop=...)`.

## The loop (do all four, every time)

1. **Write** the deck in a `.py` file as a function returning the `Deck` (below).
2. **Build**: `result = deck.build("build")`, then `print(result.summary())`.
   It writes `build/<id>.pptx`, `build/<id>.pdf`, and `build/<id>-NN.svg`/`.png`.
3. **Read the summary.** Lines under `warnings:` must be dealt with (see
   *Diagnostics*); `notes:` say what the layout chose (a figure turned or folded).
4. **Look at every PNG** (`build/<id>-NN.png`) before calling the deck done:
   crowded slides, small figure words, a slide saying two things. Fix the words
   or split the slide and build again. Rebuilds are fast: figures are cached.

## A complete deck

```python
from flexo_talk import Deck

def talk(theme: str = "paper") -> Deck:
    with Deck("results", theme=theme, look="classic", footer="Group meeting · 2026") as deck:
        deck.title("Folding with diffusion", subtitle="What the model learns", author="Ada", date="2026")
        deck.agenda()                                   # lists the section slides below
        deck.section("Why", subtitle="The gap")
        deck.statement("Prediction is cheap. [Trust]{accent} is not.")
        with deck.slide("The gap in numbers") as slide:
            slide.stats(("200M", "structures predicted"), ("0.1%", "solved"))
            slide.callout("A model that knows *how sure it is* tells us what to solve.", title="Idea")
        with deck.slide("The model", layout="two-columns") as slide:
            slide.left.bullets("A language model reads $s$", "A denoiser makes $x_0$",
                               ["trained on solved structures"])      # nested list = level below
            with slide.right.figure() as figure:                     # a flexo Figure
                s = figure.text("s", "Sequence $s$")
                lm = figure.block("lm", label="Language model", input=s, tone="encoder", badge="frozen")
                figure.block("den", label="Denoiser", input=lm, tone="head", badge="trained")
            slide.notes("Say: the encoder is frozen.")
        with deck.slide("Results") as slide:
            slide.table([["Method", "RMSD (Å)"], ["Ensemble", "3.4"], ["**Ours**", "**2.2**"]])
            slide.footnote("[1] Ho et al., [*DDPM*](https://arxiv.org/abs/2006.11239), 2020.")
        with deck.slide("Thanks", layout="columns", widths=(3, 2)) as slide:
            slide.columns[0].gallery([("ada.jpg", "**Ada**\nPI")], crop="circle", height=90)
            slide.columns[1].text("**Funded by** [Wellcome]{accent}", size=16)
    return deck

if __name__ == "__main__":
    print(talk().build("build").summary())
```

## Slides

| Call | Makes |
| --- | --- |
| `deck.title(title, subtitle=, author=, date=, background=, shade=)` | The opening slide |
| `deck.agenda(title="Outline")` | The deck's `section` slides, numbered (they may come later) |
| `deck.section(title, subtitle=)` | A divider between parts |
| `deck.statement(words, by=)` | One sentence, large, centred; `by` credits a quotation |
| `deck.slide(title, layout="content")` | A title over one region: `slide.body` |
| `deck.slide(title, layout="two-columns", split=0.4)` | `slide.left`, `slide.right`; `split` is the left's share |
| `deck.slide(title, layout="columns", columns=3)` | `slide.columns[i]`; `widths=(2, 1, 1)` for uneven ones |
| `deck.slide(title, layout="figure")` | One figure as large as the slide allows |
| `deck.slide(layout="blank")` | The whole slide as one region |

Every slide also takes `subtitle=`, `background=` (a `"#hex"` colour, or a
picture file that fills the slide, cropped not stretched), `shade=0.4` (darkens
a picture; words turn light), `dark=` (force light words), and `align=` (see
*Alignment*). Methods called on the slide itself go to its first region.

## Blocks (on a region, set one under the other)

| Call | Makes |
| --- | --- |
| `bullets(*items, numbered=, reveal=, size=)` | A native list; a nested list is the level below; `reveal=True` builds one click at a time |
| `text(words, size=, align="start"\|"middle"\|"end", muted=, colour=)` | A paragraph |
| `with region.figure(**Figure options) as figure:` | A new flexo figure in the deck's theme |
| `add(flexo_figure, turn=True)` | An existing flexo figure, redrawn in the deck's theme |
| `plot(matplotlib_figure)` | A plot laid out again at its place's size: vectors and live text |
| `image(path)` | An SVG as vectors when flexo can draw it exactly, else a picture; PNG/JPEG pictures |
| `table(rows, header=True, align="lrr")` | A booktabs-ruled native table; numbers flush right by default |
| `code(source)` | A monospace listing on a tinted panel |
| `gallery(items, columns=, height=, crop="circle"\|"square", align=)` | Logos, or people as `(file, "**Name**\nRole")` |
| `quote(words, by=)` | A quotation set large, an accent quotation mark hung in the margin |
| `stats((value, label), ..., colour=)` | Big numbers in the accent with labels under them |
| `callout(words, title=, colour="accent"\|"accent2"...)` | A key point on a tinted panel with a bar |

Slide-level extras: `slide.notes(text)` (speaker notes), `slide.footnote(text)`
(small and muted above the footer; several stack in order).

**Markup in any slide text** (titles, bullets, cells, captions): `$...$` maths
(flexo's LaTeX subset), `*italic*`, `**bold**`, `` `code` ``, `[words](https://url)`
a link, `[words]{accent}` a colour (`accent2`, `accent3`, ..., `muted`, `#rrggbb`).
Right-to-left text (Persian, Arabic, Hebrew) is set right to left by itself,
with English words, numbers, and maths inside it kept in order.

## Theme, look, and type

- **Theme** (`Deck(theme=...)`): colours, type, figure style. Any flexo theme --
  `paper`, `tikz`, `slides`, `dark`, `archive`, `print`, `economist`, `rams`,
  `swiss`, `bauhaus`, `midcentury`, `sketch`, `classic` -- or a theme file
  (`theme="lab.yaml"`); `palette=`, `conventions=`, `sketch=` as on a Figure.
- **Look** (`Deck(look=...)`): the page around the words.
  `classic` (a short rule under titles), `band` (titles on an accent band,
  sections filled with the accent), `editorial` (a hairline under titles,
  section numbers set large), `keynote` (centred titles and content, filled
  sections), `margin` (an accent bar down each slide, accent titles).
  Pairs that work: classic/paper, band/swiss, editorial/classic with
  `title_font="Latin Modern Roman"`, keynote/dark, margin/midcentury.
  `examples/showcase.py` builds one talk in all five.
- **Fine control**: `Deck(style=DeckStyle.look("band", body_size=22))`, or any
  `DeckStyle` field: sizes (`title_size`, `subtitle_size`, `body_size`,
  `small_size`, `figure_size`), `margin`, `column_gap`, `block_gap`,
  `header` (`rule`/`band`/`line`/`none`), `opening` (`centred`/`left`/`band`),
  `sections` (`rule`/`fill`/`number`), `edge`, `title_align` (`start`/`middle`),
  `title_role`, `title_weight`, `numbers`, `align`, and `width`/`height`
  (960x540 pt is 16:9; 720x540 is 4:3). `from flexo_talk import DeckStyle`.
- **Type by role**: `Deck(font=, title_font=, figure_font=)`; each falls back to
  `font`, then to the theme's family.

## Alignment (the layout does it; never position by hand)

flexo lays out each figure; flexo-talk lays out the slide, measuring every word
with flexo's own measurer so every output wraps identically.

- Words that don't fit are set smaller together (down to `small_size`) and
  reported. Figures in one region share one scale, so their words match.
- `align="auto"` (default): words at the top; a figure, plot, picture, gallery,
  or quote standing alone is centred in its room; a column of pictures is
  centred against the words beside it (and the words against taller
  pictures); columns of words share one top. `align="top"` or `"middle"` per
  slide (`deck.slide(..., align=)`) or for the deck (`DeckStyle.align`).
- A one-column gallery (logos) sits flush with the words above it; a grid is centred.
- A figure is laid out for its place's width *and* height: as written, turned
  (a tall stack read left to right), spaced closer, or folded onto two lines --
  whichever sets its words largest, never above the body size.
  `add(figure, turn=False)` keeps it as written.

## Plots

```python
import matplotlib.pyplot as plt
with deck.plotting():                 # the deck's font, sizes, inks, and tone colours
    fig, ax = plt.subplots()
    ax.plot(x, y, label="ours"); ax.set_xlabel("Epoch"); ax.legend()
slide.plot(fig)
```

Don't set `figsize`, call `savefig`, or `tight_layout`: the plot is laid out
again at the size of its place.

## Diagnostics (from `result.summary()`)

| Message | Do |
| --- | --- |
| `slideN: words set at 80% to fit` | Too many words: cut them or split the slide |
| `slideN: the words do not fit even at the small size` | Split the slide |
| `slideN fig: its words are 5.2pt, too small to read` | Give the figure its own slide (`layout="figure"`), a wider column, or fewer parts |
| `slideN fig: routing.connector.crossing` (and other flexo codes) | flexo's lint on the figure: simplify it; see flexo's docs |
| `slideN: the agenda lists section slides, and the deck has none` | Add `deck.section(...)` slides or drop the agenda |

## Habits that make decks good

- One idea per slide; three to five one-line bullets; detail goes in `notes`.
- Use the paper's theme (or theme file) so slides and figures match; keep tone
  names (`tone="encoder"`) the same in every figure so a colour means one thing.
- Add the paper's figures as they are (`slide.add(figure)`); never shrink or
  redraw them for slides.
- For emphasis, reach for `statement`, `stats`, `quote`, and `callout`, not bold
  paragraphs; give talks longer than ~10 slides `section`s and an `agenda`.
- People: `gallery(..., crop="circle")`; a title over a photograph:
  `background=photo, shade=0.4`.

## Output notes

- PPTX: every rectangle, line (exact arrowheads), and word is a native, editable
  shape; flexo components are named groups; lists, numbered lists, builds
  (`reveal`), tables, links, backgrounds, and notes are native. The program that
  opens it draws the text in its installed fonts: install the theme's fonts there
  (`flexo.fonts.bundled_font_directory()`). Variable fonts come out regular or
  bold only; emoji are refused.
- PDF: a page per slide (a page per reveal step unless `build(handout=True)`),
  fonts embedded, text selectable, links clickable.
- `build(formats=("pptx", "pdf"))` skips SVG and PNG.
- Laid-out figures are cached in `~/Library/Caches/flexo-talk` (or under
  `$XDG_CACHE_HOME`); `FLEXO_TALK_CACHE=0` turns it off, `FLEXO_TALK_CACHE=dir` moves it.

## Working on flexo-talk itself

- `deck.py`: the authoring API, `DeckStyle`, `LOOKS`. `compose.py`: slide layout,
  drawn as SVG. `pptx.py`: SVG to native PowerPoint. `export.py`: every format.
  `cli.py`: the command line.
- A slide is drawn once as SVG; the PDF, PNG, and PPTX are all made from it
  (lists and tables are also written natively into the PPTX from `ListLayout`
  and `TableLayout`), so anything `compose.py` draws appears in every output.
- `uv run pytest`; `uv run ruff check --fix src tests examples` (never
  `ruff format`); lines up to 120.
- `examples/stress/` holds decks that push at the edges (plots, typefaces,
  CJK/Arabic/Persian, maths, acknowledgements): rebuild them after a layout
  change and look at their PNGs.

## Reference

`README.md` (the full API), `examples/demo.py` (short), `examples/showcase.py`
(every slide and block, in every look), flexo's `SKILL.md` and
`docs/tutorial.md` (everything about figures).
