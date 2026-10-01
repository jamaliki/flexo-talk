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
still smaller than that is **folded** when that sets its words clearly larger,
its long rows set on two lines (the full transformer on one slide: encoder
above, decoder folded, 7pt words instead of 4pt). The build summary notes a
figure it turned or folded; `slide.add(figure, turn=False)` keeps one as
written. Figures on one slide -- in one region or side by side -- set their
words at one size: the largest at which every one fits its place, each laid out
as written where that reaches it. A figure whose words still end up under
7pt is reported with what to do. Laying a figure out can take a while for a large one (the
full transformer, about half a minute), so each is kept in a cache between builds
(`~/Library/Caches/flexo-talk` or `$XDG_CACHE_HOME/flexo-talk`), keyed by the figure,
its place, and flexo's own source: a rebuild after editing words is immediate.
`FLEXO_TALK_CACHE=0` turns the cache off; `FLEXO_TALK_CACHE=dir` moves it.

The slide's proportions -- sizes of title, body and figure text, margins,
indents, gaps, slide numbers -- are `DeckStyle` fields:
`Deck(style=DeckStyle(body_size=22, numbers=False))`.

A theme file can also say how slides set in it look: `slides:` beside `theme:`
takes the deck's `look`, `style` (any `DeckStyle` field), `background` (a colour,
or a picture such as a paper texture, drawn under every slide), and its families by
role (`font`, `title_font`, `figure_font`). A deck takes each unless it says
otherwise, and what came from the theme is not written into the deck's document.

```yaml
theme: {name: notebook, base: sketch, font: Kalam, palette: ["#c0392b", "#2b4c9b"]}
fonts: [fonts/]
slides:
  look: margin
  background: papers/notebook.jpg
  title_font: Caveat
  style: {header: none, title_size: 40}
```

A slide over a picture sets its words light or dark from how light the picture is.

## Looks

The theme decides type and colour; a **look** decides the page around them --
how titles are marked, how the talk opens, how sections are divided.
`Deck(look="band")` picks one; `DeckStyle.look("band", body_size=22)` picks one
and changes any field.

| Look | Titles | Opening slide | Sections |
| --- | --- | --- | --- |
| `classic` (default) | a short accent rule under each | centred | a rule over the title |
| `band` | on a band of the accent across the top | title on an accent band | the slide filled with the accent, numbered |
| `editorial` | a hairline across the slide under each | flush left beside an accent bar | the number set large in the accent |
| `keynote` | centred, no rule; content centred on the slide | centred | filled with the accent, centred |
| `margin` | in the accent; a bar down each slide's edge | flush left beside an accent bar | the number set large |

The pieces are `DeckStyle` fields and mix freely: `header` (`rule`, `band`,
`line`, `none`), `opening` (`centred`, `left`, `band`), `sections` (`rule`,
`fill`, `number`), `edge`, `title_align`, `title_role`, `align`. A light accent
(a dark theme's) is deepened where words are set on it, so they read either way.
`examples/showcase.py` builds one talk in every look, each with a theme that
suits it (classic/paper, band/swiss, editorial/classic with Latin Modern
headings, keynote/dark, margin/midcentury).

## Alignment

flexo lays out each *figure* (its boxes, ports, routes); the *slide* is laid out
by flexo-talk, measuring every word with flexo's own measurer, so wrapping and
sizes agree in every output. Each region is set from its top and then aligned
as a whole (`DeckStyle.align`, or `deck.slide(..., align=)`):

- `auto` (the default): words start at the top of the body, on every slide; a
  figure, plot, picture, gallery, quotation, table, code listing, or row of
  numbers standing alone is centred in the room it has (a table narrower than
  its place across it too); a column of pictures is centred against a taller
  column of words beside it, and a taller one starts level with the words.
- `top`: everything at the top. `middle`: the content centred in the body.

A single-column gallery (a column of logos) stands flush with the words above
it; a grid is centred. Native lists and tables move with their region, so the
PowerPoint matches the PDF.

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
| `deck.agenda(title="Outline")` | The talk's section slides, numbered (wherever they are in the deck) |
| `deck.statement(words, by=)` | One sentence, large, in the middle of the slide |

Any slide (title and section slides too) can take `background=`: a colour
(`"#1b2a41"`) or a picture that fills the slide, cropped rather than stretched
(a native crop in PowerPoint), with `shade=0.4` to darken it. On a dark
background the slide's words and accents are set light (`dark=` overrides).

A region takes blocks, set one under the other: `bullets(*items)` (a nested list
is the level below; `numbered=True` numbers the outer level, natively in PowerPoint;
`reveal=True` shows the outer items one click at a time -- PowerPoint builds, and a
PDF page per step unless `deck.build(handout=True)`), `text(words, size=, align=, muted=)`, `figure(**options)`
(a new flexo `Figure`, used as a `with` block), `add(figure)` (an existing one),
`plot(matplotlib_figure)`, `table(rows)`, `gallery(pictures)` (logos or people in a
grid, captions under them, `crop="circle"` for photographs), `code(source)` (a monospace listing
on a tinted panel, comment lines muted), `image(path)`, `quote(words, by=)` (set large,
an accent quotation mark hung in the margin), `stats(("93%", "accuracy"), ("4x", "faster"))`
(numbers to remember, very large in the accent, labels under them), and
`callout(words, title=, colour="accent2")` (a key point on a panel tinted in a tone). Words take the
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
no grid -- with its header bold (its maths regular, as LaTeX sets maths in bold
words) and each column as wide as its widest cell.
Columns of numbers are set flush right (`align="lrr"` or a list of
`start`/`middle`/`end` to choose); `header=False` drops the header. In the
PowerPoint it is a native table with the same columns, rows, and rules.

## Maths

```python
slide.math(r"\mathcal{L}(\theta) = -\frac{1}{N}\sum_{i=1}^{N} \log p_\theta(y_i \mid x_i)")
slide.text(r"The rate $k = A e^{-E_a/RT}$ rises with temperature.")
```

Maths is LaTeX. `math(...)` -- a `math:` block in a document, or a paragraph that is
only `$$...$$` or `\[...\]` -- displays an equation on its own line, centred, at the
words' size or smaller if it is wider than its place: fractions, roots, sums and
integrals with their limits, brackets that grow (`\left( ... \right)`, `\big`),
accents, braces over and under, matrices (`pmatrix`, `bmatrix`, `vmatrix`...), `cases`,
lines aligned at `&` and broken at `\\` (in `aligned`, or without it), chemistry
(`\ce{2H2 + O2 -> 2H2O}`) and units (`\SI{9.81}{\metre\per\second\squared}`).

In words, `$...$` or `\(...\)` sets maths in the line, and a formula too long for its
line breaks after a relation or an operator, as TeX breaks it. Dollars are read as
pandoc reads them, so "it costs $5 and $10" stays two prices, and `\$` is a dollar.
Simple maths (`$x_t$`) is set as words; the rest is laid out by TeX's rules. Its
letters are the deck's own face, and its Greek, signs and brackets come from a maths
font that suits it -- Fira Math beside a sans face, Latin Modern Math beside a serif
one -- in formulas, in words and in plots alike, so a formula reads with the words
around it. Code is set in the bundled IBM Plex Mono unless a theme names another. Maths that cannot be read is drawn in red
and said in the build summary (and beside the equation in the studio), with the
command a typo probably meant.

In the PowerPoint, maths is PowerPoint's own: each equation, and each passage, list and
table cell with maths in it, opens in PowerPoint's equation editor (in Cambria Math,
PowerPoint's maths font). A program that does not read PowerPoint's equations is
shown Flexo's drawing of it instead, which is in the file beside it (as the file
format provides): formulas as shapes, over native lists and tables that leave room for
them. A formula with rules in an array (`{c|c}`, `\hline`), which PowerPoint's
equations cannot draw, keeps the drawing in PowerPoint too.
`deck.build(..., editable_maths=False)` writes only the drawing, so PowerPoint
shows the maths in the deck's own maths font as well.

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
real text. A label or title with maths in it is set by flexo, as a slide's maths is --
all of LaTeX that flexo reads, in the deck's maths font -- and drawn as shapes. `deck.plotting()` gives matplotlib the deck's look (`deck.plot_style()`
is the same settings as a dict). An SVG saved by any program --
`slide.image("plot.svg")` -- is placed as vectors the same way when it holds
only what flexo draws exactly (paths, text, clips, pictures); otherwise, and for
PNG and JPEG files, it is a picture. An Illustrator file or a PDF --
`slide.image("figure.ai")`, `slide.image("paper.pdf#2")` -- is read back as the
drawing it is: its shapes become freeforms, its words their glyphs' outlines,
its photographs pictures, and a gradient or a curved mask a picture of that part
alone (see "Illustrator and PDF files" in flexo's guide).

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

## Decks as documents, and the studio

A deck can also be a YAML (or JSON) document that says what the Python says:

```yaml
schema_version: 1
deck: {id: results, theme: paper, look: band, footer: Group meeting}
slides:
- layout: title
  title: Figures that draw themselves
  author: Kiarash Jamali
- title: Why another figure tool?
  body:
  - bullets:
    - Figures take hours to draw
    - - boxes drift out of line        # a nested list is the level below
  notes: Everyone here has redrawn a figure at 2 a.m.
- title: The model
  layout: two-columns
  left: [{text: Write what the model *is*}]
  right: [{figure: model.yaml}]        # a flexo figure file, or model.py:figure
- title: Training
  body: [{plot: plots.py:loss}]        # a function returning a matplotlib figure
```

Each slide takes `layout` (`content` when left out), the settings its `Deck` call
takes, and its regions (`body`, `left`/`right`, or `columns`, a list of block
lists); each block is named by its kind with that call's options beside it. A
figure is a flexo figure file, a figure document written inline, or
`file.py:function`; a plot is `file.py:function` (called inside
`deck.plotting()`). Files are found next to the document. A wrong document says
where: `slides[3].left[1] (table): a table is a list of rows`. A document that
names Python runs it when drawn, as a Python deck would: open only decks you trust.

`flexo-talk build talk.yaml` builds one; `flexo-talk convert talk.py` writes a
Python deck as a document (its figures inline, its plots saved as SVG pictures);
`flexo_talk.document` reads and writes them from Python.

`flexo-talk studio talk.yaml` opens the deck in **flexo studio**, the browser
editor flexo serves from this machine (see flexo's README for the studio as a
whole: live co-editing with Claude and other agents, themes, figures). For a deck:

- **The slide is where you work.** Click a part to choose it; double-click words
  (a title, a list, a paragraph) to edit them in place, on the slide. The bar
  above adds slides (N, with a picture of each layout) and parts -- text, a list,
  a figure, a picture, a table, and more -- after the one chosen. Pictures dropped
  on the slide are added to it.
- **Figures are edited on their slides.** Choose a figure and its parts can be
  chosen, typed on (double-click), connected, and gathered where they are drawn,
  as in flexo's figure editor: a bar above the figure adds parts (A) and draws
  lines (C), and the inspector shows the part chosen. A figure written in the deck
  changes in the deck, and undoes with it; a figure file changes in its file,
  comments and all. Esc steps out, a part at a time. A figure made in Python is
  changed in its Python.
- **The inspector shows what is chosen**: a part's own settings, or, with nothing
  chosen, the slide's title, its parts in order (drag to reorder), its layout,
  background, and footnotes. **Design** holds the look, theme, palette, type, and
  proportions; *Customise* starts a theme file from the deck's theme and opens it
  in the theme editor, and the deck redraws as the theme changes.
- **Slides** are listed on the left: drag to reorder, ⌘D to duplicate, ⌫ to
  delete, **+** between two to insert. Speaker notes sit under the slide. The slide
  being edited is drawn first; the others follow.
- **Others, live**: slides an agent or another person changes flash in their
  colour, and their avatars show which slide they are on.
- It presents full screen (reveals, notes, a clock) and exports PowerPoint, PDF,
  SVG, and PNG. Saving is automatic; ⌘Z undoes your own last change. Saving
  writes the document back as YAML (comments in a hand-written file are not kept).

## Command line

```bash
flexo-talk build talk.py              # the deck the function talk() returns
flexo-talk build talk.py:results -o out --formats pptx,pdf --theme dark
flexo-talk build talk.yaml            # a deck document
flexo-talk convert talk.py            # talk.py's deck as talk.yaml
flexo-talk studio talk.yaml           # edit it in the browser (made if missing)
```

## Development

```bash
uv sync --all-groups        # uses ../flexo, editable
uv run pytest
uv run python examples/demo.py
```

`examples/journal_club.py` is a real talk -- a journal club on the Vision
Transformer, with its figures, a table and plots from the paper, code, and a
picture -- built in any theme (`python examples/journal_club.py
../design-corner/talks/themes/night.yaml`).

`examples/stress/` holds decks that push at the edges: `results.py` (matplotlib
plots, a saved SVG and a PNG, a table, maths, an overfull slide), `variety.py`
(`sketchy`, hand-drawn with literature figures; `lab`, a YAML theme file),
`typefaces.py` (a family per role, code), and `edges.py` (4:3 slides, CJK and
Arabic, unbreakable words, deep lists, a JPEG, a gradient SVG). Each is checked
by rendering its PowerPoint file in ONLYOFFICE (its `x2t` converter, to PDF) and
comparing every page with flexo-talk's own PDF of the same deck; they agree to
within antialiasing.

## License

flexo-talk is licensed under the [Apache License 2.0](LICENSE).
