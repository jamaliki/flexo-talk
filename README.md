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

One figure can be shown on several slides with parts of it hidden, faint or highlighted,
and nothing moved from slide to slide: `{figure: pipeline.yaml, hide: [store],
highlight: [api]}` (or `dim: [...]`) on a slide's figure, each a list of the figure's
shapes, groups and lines by id; a figure written in the slide says the same in its own
`figure: {hide: [...]}`. In the studio, choose shapes in a slide's figure and set
**Show** to Highlight, Dimmed or Hidden (for a figure kept in a file, it is that
slide's alone: written on its block, the file left as it is).

So can anything on a slide, the same four ways and with the same keys: every object (words,
a list, a table, numbers, a quote, a callout, code, an equation, a picture, a gallery, a plot,
a mechanism, a figure, in line or placed freely), a part of one, and the slide's shapes:

```yaml
body:
- bullets: [Encoder, [Attention, Feed-forward], Decoder]
  highlight: [2]            # item 2; the list's other items faint ('1.2': the second under 1)
- table: [[Model, Loss], [A, 0.31], [B, 0.27]]
  hide: [3]                 # row 3 (the header is row 1; '3.2' a cell)
- {image: pictures/cell.png, dim: true}        # the whole picture, faint
- {text: The rest, highlight: true}            # the slide's other objects and shapes faint
shapes:
- {kind: arrow, from: [600, 420], to: [520, 330], hide: true}
```

**Hidden** is not presented or exported, its place kept -- nothing else moves -- and a ghost
while editing; **Dimmed** is drawn as a figure's faint parts are, every colour most of the way to
the page's (a picture or a GIF see-through); **Highlighted** is drawn as it is and what stands
with it faint: a list's other items, a table's other rows (its header kept), the slide's other
objects and shapes (its title kept), the rest of a figure. Each key is `true` (the whole object)
or a list of its parts by number -- a list's items, a table's rows, a gallery's pictures,
numbers' figures, code's lines -- or a figure's parts by id. A shape's `hidden: true`, as decks
said it before, is `hide: true`. Words are dimmed in place with `[words]{dim}` (the Dim button
of the words' format bar): their own colour, faint. Hidden takes no click when presenting (an
object that builds in, a list's item revealed). The PDF and the PowerPoint keep all of it: in
the PowerPoint a list's hidden item and a table's hidden row are see-through words that keep
their room, and a faint picture is PowerPoint's own picture transparency. In the studio, the
inspector's **Show** sets it for what is chosen -- objects, shapes, several at once -- and,
for a list, a table, a gallery, numbers or code, for each of its parts; a right-click has
**Show ▸** for the object and for the item or row under the pointer; the palette has Show,
Highlight, Dim and Hide (Format › Show As in the Mac app) and Show All on Slide.

A visualisation that changes a little from slide to slide -- a part added, a label changed,
each slide its own figure -- is drawn as one when its blocks name one **frame**:

```yaml
slides:
- title: Sample the prior
  right:
  - {figure: figures/smc-1.yaml, frame: smc}
- title: Weight the samples
  right:
  - {figure: figures/smc-2.yaml, frame: smc}
```

The figures naming a frame are laid out with each other's parts (each kept room for where it
lacks them, unseen), the same way (turned or not, as the frame's first), at one scale -- the
one that fits the largest, so none is made smaller to fit -- and from one top left; a shape whose
words change is as large on each slide as its largest words need, and each version is moved so
its parts are where the first's of the same name are. Parts with the same id stay exactly where
they are from one slide to the next; only what changed looks different. `hide`, `dim`,
`highlight` and `stages` stay each slide's own: a deck's own figure shown with different parts
hidden on each slide (`{figure: '#smc', hide: [move], frame: smc}`) keeps its whole room on
every slide, its hidden parts' too, where alone it is drawn larger the more is hidden. A frame's
figures line up where their slides set them in the same place: the same place of the same
layout, or placed at the same `at` with the same `width` (Match on Other Slides sets both). In
Python: `region.add(figure, frame="smc")`. In the studio, a figure's panel has **Frame**: None,
one of the deck's frames (with the slides it is on), or New Frame. Every output -- the studio,
presenting, the PDF, the PowerPoint, an image, a bundle -- draws it so.

A figure can also be built up on one slide, a click at a time: `{figure: ..., stages:
[[api], [queue, worker], [store]]}` names the shapes and groups that appear on each
click. The rest is there from the start, a line comes with the later of its ends, and
nothing moves. It is a state each in the slideshow, a page each in the PDF and a click
each in the PowerPoint. In the studio: choose shapes in the figure, **Build ›
Appears › On Click 1**.

Type can be set by role: `Deck(font="IBM Plex Sans", title_font="Latin Modern
Roman", figure_font="Figtree")` sets the words, the titles and section headings,
and the figures each in their own family (each falls back to `font`, then the
theme's: a theme file's `type: {title_family: ..., figure_family: ...}` sets
titles and figures apart for every deck in it). `DeckStyle(title_align="middle", title_role="tone-1-stroke",
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
its place, the files its parts draw (each picture, PDF page, structure and map, by its size and
when it last changed) and flexo's own source: a rebuild after editing words is immediate, and
one after editing a picture draws the picture as it is now.
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
equation is set smaller to fit it; a plot is drawn that wide, its height in proportion (its
`aspect`, else its place's, but no wider than 3:2: its words keep their size); a
gallery's cells and pictures shrink with it; a table's columns share it (wider than its
words, each in proportion to them; narrower, each its longest word at least). With no
width an object is drawn as it always was: words, lists, quotations, callouts, numbers,
plots and galleries fill their place; a table, a listing and an equation are as wide as
they are of themselves. The PowerPoint's native lists, tables and text boxes take the
same widths.

Any object can also be **placed anywhere on its slide**, out of its place's flow, as a shape is:
`at: [x, y]` is its top left and `width` its width there, in the units the slide's shapes are
placed in (points on a slide 960 by 540; one of another size scaled to that) -- in a deck
document

```yaml
body:
- text: Measured at 4 K
  at: [80, 440]
  width: 300
- {image: pictures/cell.png, at: [600, 120], width: 280}
```

or `slide.text("Measured at 4 K", width=300).place(at=[80, 440])` in Python. It is drawn there,
over what the slide lays out and under its shapes, and the rest of its place is laid out as if it
were not there. Its words keep their size, wrapped in its width; a picture, a figure, a gallery or
a table keeps its proportions, that wide; a plot is drawn in its `aspect` (else 3:2). Without a
width it is as large as its place would set it alone. A figure is laid out (turned or not) as it
would be in its place. Its `horizontal` and `vertical` wait meanwhile: without `at` it is back in
its place's flow, where it is in its list. It builds in on a click in the slide's order, and the
PDF, PNG, SVG, the show and the PowerPoint have it where it says (a native text box, list, table
or picture there, over what is in line and under the shapes). `locked: true` keeps it where it is
in the studio.

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

A slide of columns (`two-columns` or `columns`) can be set in **rows**, each with a label:
`deck.slide(title, layout="two-columns", rows=["", "Mechanism", "Geometry"])`. Block *i* of
every column is then in row *i*: every block of a row starts on one line, a row is as tall
as its tallest block, and the rows follow one another as a column's blocks do. Each label
stands beside its row, centred down it, in a gutter at the slide's left (its right, for
labels read right to left) -- in the deck's face, a step smaller than the body's words,
semibold and muted, light on a dark slide -- as wide as the widest label needs, one longer
than a fifth of the body wrapping; the columns share the width left by `split` or `widths`.
`""` leaves a row without a label (a row of headings), labels past the last row are kept
and not drawn, and `rows=[]` only lines the rows up. Words take the height they need and
the rows with pictures share the rest by need: a row that comes out shorter than an equal
share (a mechanism, a picture as wide as its column or as it was asked to be) takes what it
uses, and the rows that can use more share what it leaves. A picture or table shorter than
the words beside it in its row is centred against them (pictures side by side share one
top), and an object asked to stand down its place (`vertical`) stands so in its row.
Builds, placeholders, footnotes and `align` work as on any slide of columns; without `rows`,
each column stacks its blocks on its own, as before. In the PowerPoint a label is a text box
where it is drawn.

Any slide (title and section slides too) can take `background=`: a colour
(`"#1b2a41"`) or a picture that fills the slide, cropped rather than stretched
(a native crop in PowerPoint), with `shade=0.4` to darken it. On a dark
background the slide's words and accents are set light (`dark=` overrides).

A slide's **people** -- who the work on it was done with -- stand at the right end of its
title: `slide.person("people/sam.jpeg", "Sam Pellock")`, once for each, in the order they
stand. Each is a round portrait (the square in the middle of the picture, drawn round, as
`mask="circle"` draws a picture), nearly two lines of the title across, beside the
others with a small gap, their name (if given) set small and muted under it -- on a band,
in the band's words. `slide.size_people(96)` (`people_size: 96` in a document) makes every
portrait on the slide 96 points across instead, from 24 to 160; their names grow and
shrink a little with them. The row ends on the slide's right margin and its portraits' middle is
on the title's (and subtitle's); the title and subtitle wrap short of it (a centred title
as far in from each side), and the body starts below the names. Many people are made
smaller together, down to under half, to keep to about two fifths of the width (a size set
too). `slide.place_people((760, 400))` (`people_at: [760, 400]`) places them freely
instead, as a block's `at` places it: the row's top left (its first portrait's slot, the
portraits' top) at that point, in the units the slide's shapes are placed in (960 across),
drawn over the slide's objects. Placed so, the header is no taller for them and the title
takes the whole width -- unless they still stand beside its words, in the right half of the
slide across from them, where it wraps short of them as before. PNG, JPEG,
SVG or PDF pictures; content, two-columns, columns and figure slides take them (a title,
section, statement, agenda or blank slide refuses them). In the PowerPoint each is a
native picture cropped to its middle square, in an oval (Crop to Shape), its name its alt
text; a bundle carries the pictures. In a document:

```yaml
- title: Mechazyme builds a reaction-cycle motif
  people:
  - {image: assets/sam.jpeg, name: Sam Pellock}
  - assets/other.jpeg          # a bare picture: no name under it
  people_size: 96              # each portrait 96 points across (none: the title sets it)
  people_at: [760, 400]        # the row's top left, placed freely (none: beside the title)
  body: [...]
```

A deck's **logos** -- an institution's, its funders' -- are the deck's, not a slide's:
`Deck(logos=["logos/institute.png", "logos/funder.svg"])`, PNG, JPEG, GIF, SVG or PDF
pictures in the order they stand (a GIF holds still, at its first frame: a logo is on
every slide, and one moving there would draw the eye from what each slide shows). On a title slide they stand in a row along its
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
round; an SVG's words are set in the deck's figure font, the same on the slide and in every
export, `font="drawn"` keeping its file's faces, and `texts=[{"id": "text1", "words": ...,
"size": 20, "bold": True, "colour": ...}]` and `colours={"#4a90d9": "#2e7d32"}` restyle it,
its file never changed), `quote(words, by=)` (set large,
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

## Shapes

A slide's words and objects flow in its regions; **shapes** are drawn where they are put,
over them -- the arrow at part of a figure, the ring round a structure's pocket, the brace
and its words beside a list, a highlight behind a phrase, "3.1 Å" between two atoms, a
speech bubble, a box of words anywhere -- so a slide is marked up without leaving for
Inkscape. In Python:

```python
with deck.slide("The pocket", layout="figure") as slide:
    slide.add(figure)
    slide.shape("ring", at=[540, 230], size=[150, 90])
    slide.shape("arrow", from_=[760, 420], to={"shape": "note", "side": "left"})
    slide.shape("rounded-rectangle", id="note", at=[700, 150], size=[200, 70],
                fill="accent2-fill", line="accent2", text="**Binding** pocket")
    slide.shape("dimension", from_=[300, 470], to=[420, 470], text="3.1 Å")
```

and in a deck document, a slide's `shapes` list:

```yaml
shapes:
- {kind: arrow, from: [520, 300], to: {object: "body[0]", side: right}}
- {kind: brace, from: [470, 140], to: [470, 400], text: 3 steps}
- {kind: text, at: [80, 470], width: 300, text: Measured at 4 K, font_size: 14}
```

Places are points from the slide's top left on its 960 by 540 points; a slide of another
size has its shapes scaled with it, 960 across, so each keeps its place and proportions.
The kinds: lines from one point to another (`line`, `arrow`, `double-arrow`,
`curved-arrow` with its `bend`, `elbow`, `arc`, and the measures `brace`, `bracket`,
`dimension`, `scale-bar`), `polyline` and `pen` through `points`, closed shapes in a box
(`at`, `size`) -- `rectangle`, `rounded-rectangle`, `ellipse`, `triangle`,
`right-triangle`, `diamond`, `polygon`, `star`, `parallelogram`, `trapezoid`, five block
arrows, `chevron`, `plus`, `cross`, `check`, `cloud`, a speech `bubble` whose `tail`
points anywhere, `highlight` and `ring` -- `text`, any outline as a `path` (SVG path data,
`d: "M 10 10 C 20 0 40 0 50 10 L 50 40 Z"`, its pieces -- holes too -- filled by its
`fill_rule`, `nonzero` or `evenodd`; its box is what it draws), a `picture` (a box holding
an SVG or a bitmap, `source: assets/drawing-part-1.svg`: what a drawing pasted as shapes keeps
of what no shape draws), and a `group` of them. Each is painted
by the theme unless it says otherwise (`fill`, `line`: `accent`, `accent2-fill`, `muted`,
`ink`, `paper`, `grey`, `#rrggbb`, `none`; a fill may be a gradient, `{gradient: linear,
angle: 90, stops: [[0, accent], [1, "#ffffff"]]}` or `{gradient: radial, centre: [0.5, 0.5],
radius: 0.5, stops: ...}`), with its line's width, opacity and dash (`dashed`, `dotted`, or
its own lengths, `[6, 3]`), an arrowhead
at either end (`triangle`, `open`, `stealth`, `dot`, `circle`, `bar`, `diamond`), its
opacities, the theme's shadow, a turn and a flip; its `text` (slide markup) is set in it
in the deck's font. A drawing copied in Inkscape (or Illustrator, Affinity, a browser)
pastes onto a slide as these shapes, one group, centred where it is pasted and made smaller
to fit (`flexo import-svg drawing.svg` writes them); Edit › Paste as Picture (⌥⇧⌘V) places
it as one picture instead. An end of a line glued to a shape (`{shape: note, side: left}`) or to
one of the slide's objects (`{object: "body[0]"}`) follows it when it moves. `behind`
draws a shape under the slide's words, `build` makes it appear on a click (after the
objects that do), `hide` keeps it out of the show (`dim` draws it faint, `highlight` the
rest of the slide faint: as any object, above), `locked` keeps it in place in the studio.

Shapes are drawn into the slide's SVG at their place and stacking, so the PDF, the PNG,
the SVG, the show (their builds too) and the studio's thumbnails have them. In the
PowerPoint each is PowerPoint's own shape: a preset where it has one -- rectangles,
rounded ones, ovals, triangles, diamonds, pentagons, four- and five-pointed stars,
parallelograms, trapezoids, the block arrows, chevrons, plus signs, clouds, speech
bubbles, braces and brackets -- its settings as the preset's adjustments, any other (a
path too) a freeform of the same outline; its words in it; a straight or elbowed line a connector
joined to the shapes it is glued to; a build a click.

In the studio, **Shape** in the toolbar (or Insert › Shapes, or the palette's Add Arrow…)
draws one: drag on the slide, or click for its usual size; a polyline is clicked point by
point, the pencil drawn by hand, and the **Pen** draws a path point by point (a click for a
corner, a drag for a curve, a click on its first point to close it, Return to leave it open).
Chosen, a shape is moved by a drag (⇧ along one way, ⌥ a
copy), sized by its handles (⇧ its proportions kept, ⌥ about its middle), turned by the
handle over it (⇧ by 15°); a line by its ends, let go on a shape or an object to glue
them, and a curve by its middle; a corner, a tail or a star's points by their own
handles. Everything catches at the slide's edges and middles and at the other shapes' and
objects', a guide drawn (⌘: none). **#** (Grid in the toolbar, beside Arrange, or
**View › Show Grid**) draws a grid over the slide, in the studio alone: graph paper in
non-photo blue, squares of 12 points of the 960 across (80 by 45 on a wide slide), every fifth
line darker and the middles darker still, with the slide's layout over it in red -- the theme's
margins across the whole slide, and the places of the slide's layout outlined. Snap (the magnet,
beside Grid) -- or %, or the Mac app's View › Snap to Guides and Objects and Snap to Grid -- goes from guides to
the grid to off: snapping to the grid, what is dragged catches at the grid's lines instead, its
edges at every square's, its middle too at the layout's lines and the slide's middles; off,
nothing catches, and a line's end let go on a shape stays a point of its own (one glued before
stays glued), ⌘ held catching and gluing for that drag. The studio remembers both, for every
deck and figure. The arrows nudge
(⇧: ten points), a double-click types its words in it, ⇧-click or a band chooses several --
to align, distribute, group (⌘G), stack (⇧⌘F, ⇧⌘B), lock (⌘L), copy and paste -- and the
inspector restyles them. The slide's objects and its shapes are one choice, as in Keynote:
⇧-click (or ⌘-click) a shape with a text chosen, or a text with a shape chosen, and both are
chosen ("1 Object, 1 Shape"); a band across both chooses what it touches of each. Together
they are deleted (⌫), cut, copied and pasted (⌘X, ⌘C, ⌘V, and the Mac app's Edit menu: the
objects pasted where pasted objects go, the shapes where pasted shapes go), and duplicated
(⌘D) -- each one step, named for both, both chosen again by its undo; the inspector offers
that, and Align and Distribute moves both (below). A path's
points are edited where it is (a double-click on it, or Format › Edit Points): its points and
handles dragged (⌥: one handle alone), a point double-clicked made smooth or a corner, a
click on its outline adding one, ⌫ deleting those chosen. Format › Make Editable makes any
shape a path of the same outline, and Arrange › Combine Shapes makes two or more one path:
their union, the one at the back less the others, their intersection, or what one or other
covers but not both.

The slide's objects are arranged as its shapes are. The Arrange tab (⇧⌘A) names what is chosen
("Text", "2 Objects", "1 Object, 3 Shapes") and gives the objects their X and Y, one its Width and
Height (a picture's, a figure's or a table's height sets its width in proportion, a plot's its
aspect; words are as tall as they are), Put Back in Line, Locked, and Align and Distribute --
every Relative to, Beside, Move as a Group, Distribute, a set gap, Arrange in a Grid… -- as the
palette and the Mac app's Arrange menu have them by name. Whatever of these moves an object takes
it out of line: every object in line among those chosen is placed just where it stands, nothing
about it changed but what the command moves (an object already where Align puts it stays in line);
**Place Freely** (under its Position, in its right-click menu, the palette and the Mac app's
Arrange menu) takes one out of line where it stands, to be dragged anywhere -- a headshot beside a
title, a logo in a corner -- the rest of its place laid out without it; Put Back in Line puts it
back in its place's flow. A placed object is dragged anywhere (⇧ along one
way, ⌥ a copy) and sized by its handles -- words wrapped again in their new width as they are, the
rest in proportion -- catching at the slide's edges and middles, at the shapes and other objects
and where it is as far from its neighbours as they are apart, as a shape does (the magnet; ⌘ held
the other way); the arrows nudge it (⇧: ten points), ⌘L locks it and ⌥⌘L unlocks it, and a
duplicate stands a little below and right of it. An object in line is dragged between places as
ever and its arrows go from one object to the next; ⌘ held as it starts to be dragged takes it out
of line, to be placed where it is let go. Chosen with shapes, objects move with them: Align and
its kin move both (one in line among them taken out of line as it moves); a drag of a placed
object or of a chosen shape carries the shapes and the placed objects together, and the arrows
nudge them together -- an object in line staying laid out. Placed objects are drawn in the slide's
order over what it lays out, under every shape but those Behind Slide Content: there is no
stacking them among the shapes, which Bring Forward and Send Backward still order among
themselves.

Slides that show one thing changing are lined up across them by overlaying them. Choose the slides
in the list (⌘-click or ⇧-click them) and press **O** -- or right-click them and choose **Overlay
Slides**, the first item of the list's menu; or View › Overlay Slides, the palette, or the toggle
in the zoom bar -- and each is drawn over the one shown as a faint ghost, in the studio alone:
never presented or exported. With one slide chosen, the presented slides either side of the one
shown are overlaid (a skipped slide is passed over), following it as another is shown. Four ghosts
or fewer are tinted as an animator's onion skin: those before the slide shown in blue, those after
it in red, each fainter the further it is; more than four, each in a hue of its own. On a dark
slide they are drawn as light ink, in lighter tints, its pictures as on a light page. The zoom bar
keys them -- each slide's number in its tint, the one shown in ink, a click going to it -- and the
list marks each ghost's thumbnail with a stripe in its tint. **Page Up** and **Page Down** go from
one overlaid slide to the next, the overlay kept; going to a slide that is not among those chosen
(another thumbnail, ↑↓ in the list) stops it, as do O again, **Stop Overlaying** wherever Overlay
Slides was, and Esc when it has nothing else to do (nothing chosen, no drag or crop). Pointed at
where nothing of the slide shown is, an object of a ghost is outlined, dashed, in its tint, its
slide named; clicked, that slide is shown with the object chosen on it, the overlay kept (the slide
that was shown now a ghost). The studio remembers whether the slides either side are overlaid, as a
deck opens (Show Neighbouring Slides and Include Next Slide, which overlaying replaces, are carried
over so); a set chosen is for now. O, as % and # are, is the page's own while nothing is typed:
words chosen are typed over by any other key, not by it. While slides are overlaid, a shape or a
placed object dragged, sized or nudged catches at the edges and middles of what is on each as at
the slide's own -- with the magnet, ⌘ the other way; snapping to the grid, the grid's lines alone
-- its guide drawn in that slide's tint with the box it caught at, so it reads as "where it is on
slide 29"; a nudge that would step over such a guide stops on it. **Arrange › Match on Overlaid
Slides** (the first item of the right-click menu of what is chosen, while slides are overlaid; also
the palette and the Arrange tab's Other Slides) puts what is chosen where it is on each overlaid
slide. **Arrange › Match on Other Slides…** (also the right-click menu, the palette, and the
Arrange tab's Other Slides) puts what is chosen -- a shape, a group, a placed object, a picture, a
figure, several -- where it is, as large, on the next slide, the previous one, every slide of its
run (the slides either side that each have its match), or the slides chosen in the list (⌘-click or
⇧-click them, then choose the object on the one shown); the palette has Match on Next Slide, on
Previous Slide and on This Run too. Its match on each slide is a picture of the same file; the same
figure (the deck's own by name, the same file, or the same figure id); a shape with the same id,
or, without one, of the same kind at the same place in the slide's list; else the object in its
place of the same kind. A slide with none is passed over, and said why. An object stands where the
one chosen stands, as wide (`at`, `width`); a figure is put in the chosen one's frame too (a frame
made and named for it if it has none, and the chosen one, in line, placed where it stands), so both
are drawn at one scale; a shape takes its place and size. It is one step to undo.

A group is entered as Inkscape enters one: double-click it (or choose it and press Return,
or Enter Group). Its shapes are then the slide's to click, drag, size, turn, restyle in the
inspector, retype (a double-click on their words), copy, duplicate, nudge, lock and delete
one by one, each change written back into the group as one step. A group in it is entered by
another double-click, and ⌥-click chooses the shape under the pointer however deep in groups
it is. A dotted frame shows the group, and a chip over the slide names where one is (Slide 3 ›
Group › Group): each level a way back to it, ✕ out a level. Esc steps out a level once nothing
in it is chosen, the group then chosen; a click on the slide's empty space (or a double-click)
leaves it, and a click on a shape outside it chooses that shape instead. Undo and redo keep
one inside while the group is there. **Ungroup All** (the right-click menu, the palette,
Arrange › Ungroup All) takes the groups chosen apart at every level in one step; a shape in a
group may be written `locked: true`.

A drawing placed as a picture -- an Inkscape SVG, a PDF's or an Illustrator file's page,
placed before the studio read drawings as shapes, or with Paste as Picture -- is made the
slide's own shapes by a double-click on it: one group, exactly where the picture was, entered
where it was double-clicked, so that the next click chooses one box, arrow or word of it (one
step to undo). Format › Make Editable, its right-click menu and its inspector's button do the
same, the group chosen; Make All Drawings Editable does every one in the deck. Such a picture
is still cropped by Crop… in its right-click menu, its inspector or the palette, or by Return.

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

A mechanism may be schematic: a bracket atom whose symbol is no element is a
placeholder, drawn as it is written -- `[X]`, `[Nu-]`, `[E]`, `[LG]`, `[EWG]`, `[R1]`
(R¹), or `[*Ar]` for a symbol that is also an element's. Its valence is unknown, so it
has a pair to give wherever an arrow starts from it and nothing is refused on its
account, but its charge is kept (X attacking ends X⁺) and the real atoms beside it
are checked as ever. Check its letters: an element mistyped into no element (`[Xx]`)
is drawn as written, though `[CL]` and `[cl]` are still refused, with what was meant.

```yaml
- mechanism:
  - {smiles: "[X:1].[Y:2][Z:3]", arrows: ["1 -> 2", "2-3 -> 3"]}
- mechanism:
  - {smiles: "[Nu-:1].[E:2]=[Z:3]", arrows: ["1 -> 2", "2=3 -> 3"]}
```

In the studio each step has **Draw Arrows…**: the structure it acts on, drawn large, to point
at. Click where the electrons come from -- an atom for its lone pair (pointing at an
atom shows its pairs; a placeholder always has one to give), or a bond -- then where
they go, and the arrow is written into the step (an atom with no map is given one in
its SMILES). A bond's electrons sent to
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
PNG and JPEG files, it is a picture. A GIF is a picture that plays: sized by its pixels,
cropped and masked as any picture is, and playing wherever a screen shows it -- the
studio, presenting, the slide's SVG in a browser, and PowerPoint and Keynote, which are
given the GIF itself. A PDF or a PNG shows one frame of it: the first, or the one `still`
names, counted from 1 (`slide.image("cells.gif", still=12)`; `still: 12` in a document).
In the studio its panel says how it plays (its frames and their seconds), takes its
**Still Frame**, and has **Pause** and **Play**, which hold it at that frame on the slide
while it is edited and play it again; presenting always plays it. A GIF pasted (copied
in a browser, Safari, Preview or the Finder) or dropped arrives as the GIF it is.
An Illustrator file or a PDF --
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
- title: Two ways a nucleophile attacks
  layout: two-columns
  rows: ["", Mechanism, Geometry]      # the columns' blocks in rows, a label beside each
  left: [{text: "**Backside attack**"}, {figure: sn2.yaml}, {image: sigma_star.png}]
  right: [{text: "**π\\* attack**"}, {figure: addition.yaml}, {image: pi_star.png}]
- title: Training
  body: [{plot: plots.py:loss}]        # a function returning a matplotlib figure
```

Each slide takes `layout` (`content` when left out), the settings its `Deck` call
takes, and its regions (`body`, `left`/`right`, or `columns`, a list of block
lists); each block is named by its kind with that call's options beside it. A
`two-columns` or `columns` slide may take `rows`, a list of its rows' labels (`""`
for a row without one; `[]` to line the rows up and label none): see *Slides*. A
figure is a flexo figure file, a figure document written inline, or
`file.py:function`; a plot is `file.py:function` (called inside
`deck.plotting()`). Files are found next to the document. A wrong document says
where: `slides[3].left[1] (table): a table is a list of rows`. A document that
names Python runs it when drawn, as a Python deck would: open only decks you trust.
A figure's own plots (a shape of `kind: plot`, in flexo's README) are that Python
too: in the studio they wait for the folder to be trusted, run in the folder's
workers as the deck's plots do, and are drawn again when their Python or the data
it read is saved. A folder has up to three workers, so a plot that never returns
holds up no other: it is stopped when its own 30 seconds are up, the rest drawn
meanwhile.

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
  proportion (a table's columns sharing its width; a plot no flatter than 3:2, its words
  keeping their size). The edge dragged follows the pointer
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
  (**Original**). **Mask with Shape** (Format) shows a picture only inside the closed
  shape drawn over it, as Keynote's does -- the shape is the picture's then (`mask:
  {kind: star}`), moved, sized and cropped again with it -- and **Unmask** shows it whole.
  **Add Zoom Inset** (Insert), a picture, a figure or a plot chosen, puts a box beside it
  showing its middle magnified, a frame round that region and two lines joining them
  (`{kind: inset, of: "body[0]", region: [x, y, w, h]}`): drag the region's corners or its
  middle on the object, and the box as any shape; its panel draws the frame and the lines
  in their own colours, widths and dashes. **Copy Style** and **Paste Style** (⌥⌘C, ⌥⌘V)
  put one shape's fill, line, dash, arrowheads, shadow, opacity and words' look on the
  shapes chosen -- and a figure's part's tone, own colours, outline and words' look on
  other parts, or either on the other where it maps (an accent is a tone). Every colour is
  also set by its code: the field beside a colour's name (and beside each own colour's well)
  takes `#1f77b4`, `1f77b4`, `#17b`, `rgb(31, 119, 180)`, `hsl(…)`, `(0.12, 0.47, 0.71)`,
  `steelblue` or `tab:blue`, typed (Return) or pasted (at once), each one step, an alpha
  after it (`#1f77b4cc`) the fill's or line's opacity; the colours applied last sit beside
  it. A colour's well opens the studio's picker, with the colours **On This Slide** and an
  eyedropper for any colour on the screen -- another object's own colour, exactly and by the
  theme's name where it has one, when it is one of the slide's (see flexo's README); **Pick
  Colour…** (⌃⌘C, Format) is the eyedropper at once, for what is chosen. **Set Colour…**
  (⇧⌘C, Format) opens a small popover by what is chosen -- shapes, a
  group, a text, both, a figure's shapes, or with nothing chosen the slide's background --
  naming what it will colour ("Fill of 3 Shapes", a switch for its Outline and Text): paste
  a code and it is applied, or type one and Return; a colour copied already is shown, ready
  for Return; Esc closes it. ⌘C, ⌘X and ⌘V copy, cut and paste what is chosen -- a figure's
  parts (into another figure, or a figure of their own), a part of the slide, or the
  slide -- and paste pictures, structure files and words copied elsewhere: a drawing
  copied in Inkscape is pasted as the SVG it is (in the Mac app), its lines and words
  drawn as lines and words (in the PowerPoint as shapes, where they can be), not as a
  picture of it. What is copied goes to other apps as the drawing it is: Keynote, Word and
  Pages paste a PDF in the deck's fonts, PowerPoint its own editable shapes, Inkscape and
  Illustrator an SVG, the rest a picture four times its size (in a browser, the picture
  and the SVG, where the browser takes them). The bar
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
  background, and footnotes. A slide of columns has **Row Labels** under its layout:
  switched on, its rows line up and an empty label stands beside each (`rows`), shown
  faintly as "Label" until it is written -- on the slide, as any words are (click to
  choose, type to replace, double-click to type in place, Tab to the next), or in the
  fields under the switch; a row added gets a label of its own, and the last row
  deleted takes its empty one with it. Switched off, the labels go and each column
  stacks its objects on its own again.
- **Design** (⇧⌘D, View › Show Design in the Mac app) shows the Design bar under the
  toolbar: one low row of pop-up buttons, each naming what is in use. **Theme** opens a grid
  of the deck's title slide (else its first) drawn in each theme, the folder's theme files
  first; **Colours** the palettes as swatch strips (and the title colour); **Fonts** the
  theme's, pairs of faces and single faces, each set in itself, and the body, title and figure
  fonts one by one; **Sizes** the type sizes and spacing; **Background** the theme's page,
  none, a light colour, any colour, or a picture behind every slide; **Slide Size**
  Widescreen 16:9, Standard 4:3, 16:10, Square, or a width and height in points; and **More**
  the look (title slide, sections, the slides' furniture, alignment, arrowheads), the logos,
  the footer and **Customise…** (a theme file started from the deck's theme, opened in the
  theme editor, the deck redrawn as it changes). While the Theme or Colours menu is open, the
  theme or palette the pointer is over shows on the slide as it would be, the deck unchanged
  until it is chosen; chosen, it is one step to undo. The bar stays open as the slide is
  edited; Format or Arrange pressed puts it away. The name the exported files take is the
  Export menu's **Export File Name…**.
- **Logos**: on a title slide **Picture** (or a picture dropped on it) adds a logo,
  in the row along its foot. A logo on a slide is chosen by a click, as any object
  is: ⌫ deletes it, ⌥← ⌥→ or a drag along the row move it, and a corner sizes every
  logo at once (they share one height; it catches at the default, and a double-click
  on a corner goes back to it). **Design › More › Logos** lists them (drag to reorder),
  adds them, and says where they show and how tall; added to a deck with no title
  slide, they show on every slide.
- **People**: a slide with a title over its objects lists its people in its panel, under
  its title: each portrait, a **Name** field, and Remove (drag a row, or ⌥↑ ⌥↓ in it, to
  move them along the row). **Add Person…** chooses or uploads a picture, as Add Logo…
  does; so does the palette's **Add Person to Title…**, and pictures dropped on the
  slide's title are added as people, where they are let go among them. **Size** sets how
  wide every portrait on the slide is, in points; so does dragging a corner of a portrait
  chosen on the slide (all of them grow together; Esc puts them back, and a double-click
  on a corner, or **Reset People Size**, goes back to the default). Dragging a portrait
  itself moves all of the slide's people anywhere on it, together, caught where an object
  would be (⇧ along one way, ⌘ free; Esc puts them back): **Move People**, written as
  `people_at`. Once moved, the arrows nudge them (⇧ ten points; ⌥← ⌥→ still move the one
  chosen along the row), and their menu and the palette have **Put People Back in Line**,
  beside the title again. Each change is one step to undo.
- **Slides** are listed on the left: drag to reorder, ⌘D to duplicate, ⌫ to
  delete, **+** between two to insert. Speaker notes sit under the slide. The slide
  being edited is drawn first; the others follow.
- **Find and replace** (⌘F, Edit › Find in the Mac app): a bar over the slide finds a
  word in the whole deck as it is typed -- titles, subtitles and bylines, texts, lists,
  quotes, callouts and tables, numbers and captions, shapes' words, figures' labels
  (inline or in a figure file), equations, and the speaker notes -- markup aside
  (`en**zy**me` is found as "enzyme"), and says "3 of 17". Return and ⇧Return in its field
  go from match to match, slide to slide -- and n and ⇧N, as vim's, while it is open and no
  words are typed (a shape or text chosen is not typed over): every match on the slide shown is marked
  faintly, the one gone to strongly; one in the notes opens them and is marked there.
  **Match Case** and **Whole Words** narrow it. ⌥⌘F (or the bar's chevron) shows
  **Replace** and **Replace All**: each is one step in the history, the words put in
  taking the look of the first letter they replace (bold stays bold), a figure file's
  labels changed in the file with the deck's in the same step. Esc closes it, the last
  match's words chosen where they are typed. The top bar's **Search** (⌘K) lists the same
  matches, by slide, above the commands; choosing one goes there as the bar does.
- **Check Spelling…** (the palette, Edit › Spelling and Grammar in the Mac app): the deck's
  words -- the same as Find's, its notes and figures' labels too -- gone through for those the
  Mac's dictionary does not know, in its person's language, one after another in a bar where
  Find's is: the word marked on its slide, the dictionary's guesses beside it, a click each to
  put it in its place (one step in the history). **Ignore** passes over the word while the
  bar is open; **Add to Deck** keeps it in the deck (`deck: {spelling: [Mechazyme]}`), never
  said misspelt in it again. Code and equations, words between backticks or dollars, links
  and words with digits (5KKA, H2O) are left alone. In the Mac app words are also underlined
  as they are typed; in a browser that is the browser's, and Check Spelling… is not offered.
- **TODOs**: the word `TODO` in capitals, as a word of its own (`TODO`, `TODO:`,
  `TODO —`), anywhere in a slide's words -- the same words find finds, its notes too --
  is work left, shown in the studio only. The slide's thumbnail glows amber in the
  slide list, with how many under its number when it has several, and the list's foot
  says how many in all ("3 TODOs"; pressed, it goes to the next). On the slide each is
  marked amber behind its words (an equation's framed); zoomed in, markers at the
  stage's edges point to those out of sight. One in the notes puts a **TODO** chip on
  the notes' bar, which opens them at it. **Next TODO** (⌘') and **Previous TODO**
  (⇧⌘') go from one to the next, slide after slide (the palette; View in the Mac app).
  As a show starts or the deck is exported, a quiet word says "2 slides have TODOs".
  Nothing of it is presented or exported, and "todo" or "Todo" is just a word
  (`static/todos.js`, flexo's `todos.js`).
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
flexo-talk studio talk.flexo          # edit it in the browser: a bundle, made if missing
flexo-talk studio talk.yaml           # a deck in a folder instead, its files beside it
flexo bundle talk.yaml -o talk.flexo  # the deck and every file it names, as one file to send
flexo-talk build talk.flexo --trust   # built straight from a bundle, its plots' Python run
```

A bundle (`.flexo`, see flexo's README) holds the deck and every file it names: its theme
and palette files, pictures, logos and backgrounds, figure files (and theirs), plots' Python
(and the modules and data it reads), structures, maps, scenes and the pictures kept from
drawings pasted in. A new deck is a bundle: in Flexo Studio, File › New Deck (⌘N) makes one
where you say (File › New Deck in Folder… makes a folder instead), File › Save as Bundle…
makes one of a deck in a folder -- its figure files written into the deck as it is packed
(`flexo bundle --figure-files` keeps them as files) -- and a bundle double-clicked in the
Finder opens as a folder does.

A deck's figures live in the deck: each written in its slide's block, or -- one figure shown
on several slides -- once in the deck's `figures`, named from each block as `'#name'`
(see `flexo_talk.document`). In the studio, Embed Figure in Deck (and Embed All Figures in
Deck) writes a figure file's figure into the deck, one step to undo; in a bundle the file then
goes from it, in a folder it is left alone. Export Figure as File… writes a figure out as a
figure file of its own, the deck keeping its copy unless you ask it to show the file instead,
and Open in Figure Editor edits a figure of the deck's in a tab of its own, its source and
layout tree too, each edit made to the deck as it is made. A figure whose shapes have all
been taken out still holds room on its slide: in the studio it says "Empty figure" there,
faintly, to be chosen and deleted, and exported it is nothing.

A figure file from anywhere comes onto the slide shown with Insert › Figure from File… (Add
Figure from File… in the palette), or dropped on the slide: its figure is written into the
deck, and the files it names (structures, pictures, data) are copied into the deck's folder,
under `assets/<its name>/`, so the deck -- and its bundle -- holds them. In a browser, which is
given a dropped file but not where it was, drop the figure file together with the files it
names (see `flexo_talk.embedding`).

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
