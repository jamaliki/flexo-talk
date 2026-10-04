---
name: flexo-talk
description: Make slide decks with flexo-talk -- titles, bullets, tables, plots, quotes, big numbers, people, and real flexo figures in one theme and one look -- written in Python or as a YAML deck document, edited in flexo studio, and exported to editable PowerPoint (PPTX), PDF, and SVG/PNG per slide. Use when asked for a talk, presentation, slides, a lab-meeting, journal-club or conference deck, or an acknowledgements slide, especially one that should match a paper's figures.
---

# Making slide decks with flexo-talk

flexo-talk writes a deck the way [flexo](https://github.com/jamaliki/flexo)
writes a figure: a `with` block in one theme, no coordinates. You say what is on
each slide; flexo-talk decides where it goes and how large, and every figure is a
real flexo figure laid out for its place. Every output is written in Python (no
Inkscape, no LibreOffice): a PowerPoint of native, editable shapes and text, a
PDF with embedded fonts, and an SVG and PNG per slide.

## Setup

flexo-talk lives next to flexo (`../flexo`, installed editable by uv); keep
both checkouts on the same branch. Python 3.12 to 3.14.

```bash
uv sync --all-groups                 # in the flexo-talk checkout
uv run python talk.py                # a script that builds its deck
uv run flexo-talk build talk.py      # or: build the deck that talk() returns
uv run flexo-talk build talk.py:results -o out --formats pptx,pdf --theme dark
uv run flexo-talk build talk.yaml    # a deck document (below)
uv run flexo-talk convert talk.py    # talk.py's deck as talk.yaml
uv run flexo-talk studio talk.yaml   # edit it in the browser (made if missing)
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

## A deck as a document (YAML)

The same deck can be a YAML (or JSON) document: what a person or an agent in
flexo studio edits. Prefer it when the deck will be edited in the studio.

```yaml
schema_version: 1
deck: {id: results, theme: paper, look: band, footer: Group meeting}
slides:
- layout: title
  title: Folding with diffusion
  author: Ada
- title: The gap
  body:
  - bullets: [Prediction is cheap, [only 0.1% solved]]   # nested list = level below
  notes: Say the number slowly.
- title: The model
  layout: two-columns
  left: [{text: Write what the model *is*}]
  right: [{figure: model.yaml}]        # a flexo figure file, an inline figure, or model.py:figure
- title: Training
  body: [{plot: plots.py:loss}]        # a function returning a matplotlib figure
```

A slide takes `layout` (`content` when left out), the options its `Deck` call
takes, and its regions (`body`, `left`/`right`, or `columns`, a list of block
lists); each block is named by its kind with that call's options beside it.
Files are found next to the document. A wrong document says where
(`slides[3].left[1] (table): a table is a list of rows`). Python a document
names (plots, `file.py:function` figures) runs only in a folder its person has
trusted in the studio, in a process of its own. `flexo_talk.document` reads and
writes documents from Python.

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
| `bullets(*items, numbered=, reveal=, plain=, size=)` | A native list; a nested list is the level below; `reveal=True` builds one click at a time; `plain=True` has no bullets, its levels kept |
| `text(words, size=, align="start"\|"middle"\|"end", muted=, colour=)` | A paragraph |
| `with region.figure(**Figure options) as figure:` | A new flexo figure in the deck's theme |
| `add(flexo_figure, turn=True, caption=)` | An existing flexo figure, redrawn in the deck's theme |
| `plot(matplotlib_figure)` | A plot laid out again at its place's size: vectors and live text |
| `image(path, description=, caption=)` | An SVG as vectors when flexo can draw it exactly, else a picture; PNG/JPEG pictures. `description`: what it shows, read out by screen readers and PowerPoint's alt text |
| `table(rows, header=True, align="lrr", caption=)` | A booktabs-ruled native table; numbers flush right by default |
| `code(source)` | A monospace listing on a tinted panel |
| `gallery(items, columns=, height=, crop="circle"\|"square", align=)` | Logos, or people as `(file, "**Name**\nRole")` |
| `quote(words, by=)` | A quotation set large, an accent quotation mark hung in the margin |
| `stats((value, label), ..., colour=)` | Big numbers in the accent with labels under them |
| `callout(words, title=, colour="accent"\|"accent2"...)` | A key point on a tinted panel with a bar |

Slide-level extras: `slide.notes(text)` (speaker notes), `slide.footnote(text)`
(small and muted above the footer; several stack in order).

A figure's, picture's or table's `caption=` is set under it, centred and a size
smaller, as part of it (a Caption in the PDF's tags, grouped with a picture or
figure in the PowerPoint). `region.build_in()` (`build: true` in a document) makes
the block added last appear on a click of its own, in the slide's order: a click in
PowerPoint, a page in the PDF, a step when presenting.

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
- **A theme file can carry the slides' look**: beside `theme:`, a `slides:`
  section gives the deck's `look`, `style` (any `DeckStyle` field), `background`
  (a colour, or a picture such as a paper texture under every slide), and fonts
  by role. A deck takes each unless it says otherwise:

  ```yaml
  theme: {name: notebook, base: sketch, font: Kalam}
  fonts: [fonts/]
  slides: {look: margin, background: papers/notebook.jpg, title_font: Caveat}
  ```

## Alignment (the layout does it; never position by hand)

flexo lays out each figure; flexo-talk lays out the slide, measuring every word
with flexo's own measurer so every output wraps identically.

- Words that don't fit are set smaller together (down to `small_size`) and
  reported. Figures on one slide -- in one region or side by side -- set their
  words at one size: the largest at which every one fits its place.
- `align="auto"` (default): words start at the top of the body on every slide,
  the same distance under the title; a figure, plot, picture, gallery, quote,
  table, code listing or row of numbers standing alone is centred in its room;
  a picture beside words is centred against them only when it is shorter, and a
  taller one starts level with them; columns of words share one top. `align="top"` or `"middle"` per
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
| `slideN: Text size reduced to 80% to fit the slide.` | Too many words: cut them or split the slide |
| `slideN: Text does not fit, even at the smallest size. …` | Split the slide |
| `slideN fig: Text in this figure is 5.2 pt, too small to read. …` | Give the figure its own slide (`layout="figure"`), a wider column, or fewer shapes |
| `slideN fig: Lines cross in this figure.` (and other figure checks) | flexo's checks on the figure: simplify it; see flexo's docs |
| `slideN: The agenda is empty because the deck has no section slides.` | Add `deck.section(...)` slides or drop the agenda |

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

## The studio, and working in it as an agent

`flexo-talk studio talk.yaml` (or `flexo studio` in the folder) opens the deck in
flexo studio: the slide is where you work (click to choose, double-click words to
type on the slide), figures are edited on their slides part by part, the
inspector holds a part's settings or, with nothing chosen, the slide's, and
**Design** holds look, theme, palette and type. It presents full screen and
exports PPTX, PDF, SVG and PNG. People and agents edit the same document live.

As an agent: `claude mcp add flexo-studio -- flexo studio mcp` (once, in the
folder) gives `list_documents`, `open_document`, `read_document`,
`edit_document`, `write_document`, `look`, and `status`. Work the loop on the
YAML: `read_document`, `edit_document` a few lines, `look` at the slides you
changed (pictures plus the same warnings as `summary()`), fix, and say what you
are doing with `status`. A figure written inline in the deck is edited in the
deck; a figure file in its own file.

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

`README.md` (the full API, documents, the studio), `examples/demo.py` (short),
`examples/showcase.py` (every slide and block, in every look),
`examples/journal_club.py` (a journal-club talk on a paper: figures, a picture
cut into patches, code, plots), flexo's `SKILL.md` and `docs/tutorial.md`
(everything about figures).
