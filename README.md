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
figure it turned or folded; `slide.add(figure, turn=False)` keeps one from
turning (folded it may still be), and `width=` (points; `width:` in a deck file) draws one that wide,
smaller or larger, as far as its place allows -- the studio writes it when a
figure's or picture's corner is dragged. Figures on one slide -- in one region or side by side -- set their
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
  numbers standing alone stands a little above the middle of the room it has,
  where the eye takes the middle to be (a table narrower than its place is
  centred across it); a column of pictures is centred against a taller
  column of words beside it, and a taller one starts level with the words.
- `top`: everything at the top. `middle`: the content centred in the body.

Any object can be set where it is asked to stand instead: across its place
(`horizontal: start`, `middle`, `end`, or a share between, `0.25` halfway from the left to
the middle) and down it (`vertical: top`, `middle`, `bottom`, or a share) in a deck
document, or `region.place("middle", vertical=0.25)` after adding it in Python -- a table
centred under a list, say. Words, a list, a listing, a quotation, a callout or numbers
stand there as a box as wide as they are, their lines as they were set. Down, an object
takes that share of the room its place has to spare above it, and what comes after it
follows it.

Any object can be given a width of its own, in points (`width: 300` in a deck document,
`width=300` in Python): the most it takes across its place, standing where its place
stands it -- words, a list, a quotation, a callout or a listing at the side their words
are set against (centred words centred), an equation as it is aligned, a plot, gallery or
table where a picture stands -- or where `horizontal` asks. Words wrap in it (a listing
is set smaller, then wrapped, as in a place too narrow for it); numbers share it; an
equation is set smaller to fit it; a plot is drawn that wide, its height in proportion; a
gallery's cells and pictures shrink with it; a table's columns share it (wider than its
words, each in proportion to them; narrower, each its longest word at least). With no
width an object is drawn as it always was: words, lists, quotations, callouts, numbers,
plots and galleries fill their place; a table, a listing and an equation are as wide as
they are of themselves. The PowerPoint's native lists, tables and text boxes take the
same widths.

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

A deck's **logos** -- an institution's, its funders' -- are the deck's, not a slide's:
`Deck(logos=["logos/institute.png", "logos/funder.svg"])`, PNG, JPEG, SVG or PDF
pictures in the order they stand. On a title slide they stand in a row along its
foot, centred and evenly spaced, each `logo_height` points tall (40 unless set) in its
own proportions -- a very wide one narrowed until the row fits -- and the title, subtitle
and byline make room above them. With `logos_on="every"` the other slides carry them
too, small (half that height) in the footer, clear of its words and the slide's number.
A logo is drawn as it is, never recoloured, on light and dark slides alike, and is a
native picture in the PowerPoint. In a document:
`deck: {logos: [logos/institute.png, logos/funder.svg], logos_on: every, logo_height: 36}`.

A region takes blocks, set one under the other: `bullets(*items)` (a nested list
is the level below; `numbered=True` numbers every level in its tier (1., a., i.), natively in PowerPoint;
`plain=True` draws no bullets or numbers, each item at its level's indent (Keynote's None);
`reveal=True` shows the outer items one click at a time -- PowerPoint builds, and a
PDF page per step unless `deck.build(handout=True)`), `text(words, size=, align=, muted=)`, `figure(**options)`
(a new flexo `Figure`, used as a `with` block), `add(figure)` (an existing one),
`plot(matplotlib_figure)`, `table(rows)`, `gallery(pictures)` (logos or people in a
grid, captions under them, `crop="circle"` for photographs), `code(source)` (a monospace listing
on a tinted panel, comment lines muted), `image(path, description=, crop=, mask=)` (`description` says what it
shows, for screen readers and PowerPoint's alt text; `crop=[x, y, width, height]` keeps a part of
it, as fractions of the whole picture -- `[0.1, 0, 0.8, 1]` the middle 80% across -- which is then
the picture, its size and proportions, a native crop in PowerPoint; `mask="circle"` draws it
round), `quote(words, by=)` (set large,
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
`start`/`middle`/`end` to choose); `header=False` drops the header, and
`outline=False` the rules above and below (with neither, it is words in aligned
columns, no lines at all). In the PowerPoint it is a native table with the same
columns, rows, and rules.

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

## Mechanisms

```python
slide.mechanism([
    {"smiles": "[OH-:5].[CH3:1][C:2](=[O:3])[Cl:4]", "arrows": ["5 -> 2", "2=3 -> 3"],
     "reagents": "NaOH"},
    {"arrows": ["3 -> 2", "2-4 -> 4"], "label": "tetrahedral intermediate"},
])
```

A reaction mechanism, drawn as chemists draw it: each step a structure in SMILES and
its curly arrows, a reaction arrow (reagents over it, conditions under it) to the next.
Atoms are named by their atom maps (`[O-:5]` is 5). An arrow from a lone pair is
`"5 -> 2"`, from a bond `"2=3 -> 3"`, a bond moved `"1=2 -> 2-6"`, a fishhook `"~>"`.
A step with no SMILES is drawn from the arrows before it, its atoms where they were;
one written out is checked against them. A step that cannot be -- carbon with ten
electrons, a lone pair that is not there -- is drawn as far as it goes, its arrows on
it, and what is wrong said when the slide is drawn, in words. The curly arrows carry the lone pairs they take, in magenta unless `arrow_colour` gives
another (`accent`, `ink`, `muted`, which follow the theme, or `#rrggbb`). A step's
`place` puts its molecules where you want them (`{5: {move: [-1, 0.5], turn: 30, flip:
true}}`: the molecule with atom 5). In a document it is a `mechanism:` block (a SMILES,
or a list of steps with `smiles`, `arrows`, `label`, `reagents`, `conditions`,
`arrow`). In the PowerPoint the structures are shapes and their arrows curves, all
editable.

In the studio each step has **Draw Arrows…**: the structure it acts on, drawn large, to point
at. Click where the electrons come from -- an atom for its lone pair (pointing at an
atom shows its pairs), or a bond -- then where they go, and the arrow is written into
the step (an atom with no map is given one in its SMILES). A bond's electrons sent to
an atom outside it ask which end the new bond forms from; **Single electron (fishhook)** writes
fishhooks. The step holds still while it is drawn on; **Clean Up** lays it out again for
its arrows. **Arrange** moves a molecule where you drag it, turns it 30 degrees at a
time, flips it, or puts it back where it is laid out. The arrows' colour is chosen in
the mechanism's panel, from the deck's colours or any other. A step is usually wrong between one arrow and the next, so it is drawn
anyway, with what is wrong under it. Only the atoms the arrows name are numbered. See "Reaction
mechanisms" in flexo's README for how structures are laid out.

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
  (a title, a list, a paragraph) to type them in place, on the slide, in their own
  face and size; double-click a table's cell to type in it (Tab to the next, a new
  row after the last; Enter to the one below), or an equation to type its LaTeX
  under it as it redraws. Right-click anything for what can be done with it. Every
  object chosen has handles, as in Keynote: words (a text, a list, a quote, a callout,
  a listing, numbers, an equation) a handle at each side, which sets their width, the
  words wrapping again as it is dragged, where the slide will wrap them; a figure,
  picture, mechanism, plot, gallery or table a handle at each corner, which sizes it in
  proportion (a table's columns sharing its width). The edge dragged follows the pointer
  and the other stays (an object standing centred stays centred); it catches at the
  width of its place, the width it takes of itself and the width it was -- ⌘ drags it
  free of them -- and is never narrower than its longest word, a column's, or a
  picture's least. Esc puts it back; double-click a handle to give it no width of its
  own again. The inspector's Width is the same setting, empty for none. Double-click a
  picture (or choose it and press Return, or **Crop…**) to crop it, as Keynote masks
  one: the whole of it shows faintly round the part kept; drag the frame's handles to
  crop a side (⇧ keeps its proportions), the frame to move it over the picture, the
  picture to move it under the frame, or the bar's slider to zoom it in the frame;
  Return, **Done** or a click elsewhere keeps the crop (`crop: [x, y, width, height]`,
  fractions of the whole picture), Esc leaves it as it was. Its panel crops it to a
  square, 4:3, 16:9 or a circle at once (`mask: circle`), or back to the whole
  (**Original**). ⌘C, ⌘X and ⌘V copy, cut and paste what is chosen -- a figure's
  parts (into another figure, or a figure of their own), a part of the slide, or the
  slide -- and paste pictures, structure files and words copied elsewhere. The bar
  above adds slides (N, with a picture of each layout) and parts -- text, a list,
  a figure, a flow chart, a structure, a picture, a table, and more -- after the
  one chosen. Pictures dropped on the slide are added to it, and so are structures
  (PDB or mmCIF files), drawn by mol-sketch: several dropped at once make one
  figure, an arrow from each to the next, and one dropped on a figure joins it,
  after the part it lands on. **Structure** takes a file beside the deck, one
  uploaded, or a PDB ID.
- **Figures are edited on their slides**, as any other part of the slide is: one
  click on a box, a structure or a line chooses it, a double-click types on it,
  and a click where none of a figure's parts is chooses the figure. A part chosen
  can be connected, gathered, and dragged to another place in its row or into
  another group where it is drawn (a figure's only part -- a structure added with
  **Structure** -- moves the figure on the slide instead, and has **Position** in
  its panel), as in flexo's figure editor: a bar above the
  figure adds parts and draws lines, typing on a part chosen types over its words, a
  **+** beside the part chosen adds
  the next step, joined to it, its words typed at once, and the inspector shows
  the part chosen. A part added after one whose single line runs on to the next
  goes into that line, as a step into a flow chart. A chosen molecule turns as
  it is dragged, its trace turning over it; its corners, like a picture's, size
  it. A shape's **Type** may be made a structure or a picture -- a step becomes the
  backbones it stands for, keeping its words and lines. A figure written in the
  deck changes in the deck; a figure file changes in its file, comments and all,
  and either undoes with the deck (**Source › In Deck** writes its figure into the deck instead,
  the file left as it was). Esc steps out, a part at a time. A figure made in
  Python is changed in its Python. There is no separate figure editor to go to:
  to use a figure elsewhere, **Export** on the bar above it (or in its panel)
  writes it out by itself, in the deck's look -- an editable SVG, a PDF, a PNG,
  or its document as a flexo figure file (YAML).
- **Format shows what is selected**: an object's own settings, or, with nothing
  selected, the slide's title, its parts in order (drag to reorder), its layout,
  background, and footnotes. **Design** holds the look, theme, palette, type, logos
  and proportions; **Customise…** starts a theme file from the deck's theme and opens it
  in the theme editor, and the deck redraws as the theme changes.
- **Logos**: on a title slide **Picture** (or a picture dropped on it) adds a logo,
  in the row along its foot. A logo on a slide is chosen by a click, as any object
  is: ⌫ deletes it, ⌥← ⌥→ or a drag along the row move it, and a corner sizes every
  logo at once (they share one height; it catches at the default, and a double-click
  on a corner goes back to it). **Design › Logos** lists them (drag to reorder),
  adds them, and says where they show and how tall.
- **Slides** are listed on the left: drag to reorder, ⌘D to duplicate, ⌫ to
  delete, **+** between two to insert. Speaker notes sit under the slide. The slide
  being edited is drawn first; the others follow.
- **Others, live**: slides an agent or another person changes flash in their
  colour, and their avatars show which slide they are on.
- **Present** (⌘↩, or ⌥⌘↩ from the first slide) plays the deck full screen, as
  Keynote does: the audience sees the slides alone; the presenter view (the slide, the
  next one, the notes, the time) opens on a second screen, and on one screen X shows it
  in place of the slides. A click or → goes on; a slide's number then Return goes to
  it; B and W blank the screen black or white; Esc ends. **Export** makes a PDF (a
  page per slide, or per stage of its builds), a PowerPoint, or a PNG or SVG of each
  slide (a PNG 1280, 1920 or 3840 pixels wide, as last chosen), saved where you say
  (downloaded, in a browser). Saving is automatic; ⌘Z undoes your own last change, and the
  history beside it (⌥⌘Z) lists every change by name -- "Rename “Model” to
  “Encoder” · Slide 2" -- to go back, or forward, to any of them, the deck going
  to the slide each was made on. Saving writes the document back as YAML
  (comments in a hand-written file are not kept).

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
