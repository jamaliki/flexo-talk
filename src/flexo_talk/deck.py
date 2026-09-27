"""A slide deck written the way a flexo figure is: a ``with`` block, one theme.

```python
from flexo_talk import Deck

with Deck("results", theme="paper") as deck:
    deck.title("Figures that draw themselves", subtitle="Group meeting")
    with deck.slide("Why") as slide:
        slide.bullets("Figures take hours", "They break when the model changes")
    with deck.slide("The model", layout="two-columns") as slide:
        slide.left.bullets("An encoder", "A head")
        with slide.right.figure() as figure:
            x = figure.root.text("x", "$x$")
            figure.root.block("encoder", label="Encoder", input=x)
deck.build("build")                      # talk.pptx, talk.pdf, and an SVG and PNG per slide
```

Every slide is set in the deck's theme -- any flexo theme or theme file, with
its palette, font, conventions, and hand -- so titles, bullets, and figures
share one typeface and one set of colours. A figure on a slide is compiled at
the width of its place, at a size where its words read at the deck's figure
size, and scaled to fit; it is the same flexo figure a paper would print.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import flexo
from flexo.ir.semantic import FigureSpec, TextRun
from flexo.markup import parse_label
from flexo.style import LayoutStyle, Palette, TypographyStyle
from flexo.themes import resolve_palette, resolve_style, with_tone_roles
from flexo.units import pt

type Layout = Literal[
    "content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"
]
LAYOUTS: tuple[str, ...] = (
    "content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"
)


@dataclass(frozen=True, slots=True)
class DeckStyle:
    """The proportions of a deck's slides; the look comes from the flexo theme.

    Sizes are in points on a 16:9 slide of 960 by 540 points (13.33 by 7.5 in).
    """

    width: float = 960.0
    height: float = 540.0
    margin: float = 48.0
    title_size: float = 30.0
    subtitle_size: float = 18.0
    body_size: float = 20.0
    small_size: float = 14.0
    figure_size: float = 13.0
    """The size a figure's words are set at on a slide: figures are scaled so."""
    line_height: float = 1.25
    paragraph_gap: float = 0.55
    """Space between two bullets, as a fraction of the body size."""
    indent: float = 26.0
    """How far each bullet level steps in."""
    column_gap: float = 36.0
    block_gap: float = 18.0
    """Space between two blocks placed one under the other in a region."""
    title_gap: float = 22.0
    """Space between a slide's title and its body."""
    header: Literal["rule", "band", "line", "none"] = "rule"
    """What marks a slide's title: a short accent rule under it, a band of the
    accent colour behind it, a hairline across the slide under it, or nothing."""
    opening: Literal["centred", "left", "band"] = "centred"
    """The title slide: centred, flush left beside an accent bar, or on an accent band."""
    sections: Literal["rule", "fill", "number"] = "rule"
    """Section slides: a rule over the title, the whole slide in the accent colour
    (with the section's number), or the section's number set large in the accent."""
    edge: bool = False
    """A thin accent bar down the left edge of every slide but the opening."""
    align: Literal["auto", "top", "middle"] = "auto"
    """Where a slide's content sits in its body, top to bottom: ``auto`` keeps
    words at the top, centres pictures standing alone in the room they have, and
    centres a column of pictures against a column of words beside it (and the
    words against the pictures when those are taller); ``top`` sets everything at
    the top; ``middle`` centres the whole content in the body."""
    numbers: bool = True
    """A slide number in the bottom-right corner."""
    title_weight: int | None = None
    """The weight of slide titles; the theme's title weight when unset."""
    title_align: Literal["start", "middle"] = "start"
    """Slide titles flush left, or centred (with their rule)."""
    title_role: str = "ink"
    """The palette role that paints slide titles: ``ink``, or ``tone-1-stroke`` for the accent."""

    @classmethod
    def look(cls, name: str, **changes: object) -> DeckStyle:
        """A named look (see ``LOOKS``), with any field changed: ``DeckStyle.look("band", body_size=22)``."""

        if name not in LOOKS:
            raise ValueError(f'unknown look "{name}"; looks are {", ".join(LOOKS)}')
        return cls(**{**LOOKS[name], **changes})  # type: ignore[arg-type]


LOOKS: dict[str, dict[str, object]] = {
    "classic": {},
    "band": {"header": "band", "opening": "band", "sections": "fill"},
    "editorial": {"header": "line", "opening": "left", "sections": "number", "title_size": 32},
    "keynote": {
        "header": "none", "title_align": "middle", "sections": "fill", "title_size": 34, "body_size": 22,
        "align": "middle",
    },
    "margin": {"edge": True, "opening": "left", "sections": "number", "title_role": "tone-1-stroke"},
}
"""Named looks: the same theme and words, a different page. ``classic`` is a short
rule under each title; ``band`` sets titles on a band of the accent colour and fills
section slides with it; ``editorial`` rules a hairline under each title and numbers
sections large; ``keynote`` centres titles and content, without rules; ``margin``
runs an accent bar down each slide's edge and paints titles in the accent."""


@dataclass(slots=True)
class _Bullets:
    items: list[tuple[int, tuple[TextRun, ...]]]
    size: float | None = None
    numbered: bool = False
    reveal: bool = False


@dataclass(slots=True)
class _Words:
    runs: tuple[TextRun, ...]
    size: float | None = None
    align: Literal["start", "middle", "end"] = "start"
    muted: bool = False
    colour: str | None = None


@dataclass(slots=True)
class _Figure:
    figure: flexo.Figure | FigureSpec
    turn: bool = True
    """Whether flexo may lay the figure out turned when that fits its place better."""


@dataclass(slots=True)
class _Image:
    source: str
    width: float | None = None


@dataclass(slots=True)
class _Plot:
    figure: object
    """A matplotlib ``Figure``."""
    aspect: float | None = None
    """Width over height; ``None`` fills the height the place has."""


@dataclass(slots=True)
class _Table:
    rows: list[list[tuple[TextRun, ...]]]
    header: bool = True
    align: tuple[str, ...] = ()
    size: float | None = None


@dataclass(slots=True)
class _Gallery:
    items: list[tuple[str, tuple[TextRun, ...]]]
    """``(picture file, caption runs)`` for each cell."""
    columns: int | None = None
    height: float | None = None
    crop: str | None = None
    size: float | None = None
    align: str | None = None
    """``start`` or ``middle``; ``None`` sets one column flush with the words, a grid centred."""


@dataclass(slots=True)
class _Code:
    lines: list[str]
    size: float | None = None


@dataclass(slots=True)
class _Quote:
    runs: tuple[TextRun, ...]
    by: tuple[TextRun, ...] = ()
    size: float | None = None


@dataclass(slots=True)
class _Stats:
    items: list[tuple[tuple[TextRun, ...], tuple[TextRun, ...]]]
    """``(value, label)`` runs for each figure."""
    colour: str | None = None
    size: float | None = None


@dataclass(slots=True)
class _Callout:
    runs: tuple[TextRun, ...]
    title: tuple[TextRun, ...] = ()
    colour: str = "accent"
    size: float | None = None


type _Block = (
    _Bullets | _Words | _Figure | _Image | _Plot | _Table | _Code | _Gallery | _Quote | _Stats | _Callout
)


def accent_field(palette: Palette) -> str:
    """The accent as a field to set words on: itself, or deepened when it is light
    (a dark theme's accent), so light words read on it either way."""

    from flexo.colour import is_dark, with_lightness

    accent = palette.get("tone-1-stroke")
    return accent if is_dark(accent) else with_lightness(accent, 0.45)


def inline(words: str) -> tuple[TextRun, ...]:
    """Slide text as runs: ``*emphasis*`` is italic, ``**strong**`` bold, ``$...$``
    math, ``code`` between backticks is set in the monospace family,
    ``[words](url)`` links, and ``[words]{accent}`` (or ``{accent2}``, ``{muted}``,
    ``{#c0392b}``) colours.

    Emphasis is slide markup only -- a figure's labels keep their asterisks.
    """

    runs: list[TextRun] = []
    # Split on links, code, maths, ** and *; each piece takes the styles open around it.
    tokens = re.split(
        r"(\[[^\]\n]+\]\([^)\s]+\)|\[[^\]\n]+\]\{[^}\s]+\}|`[^`]*`|\$[^$]*\$|\*\*|\*)", words
    )
    bold = italic = False
    for token in tokens:
        if token == "**":
            bold = not bold
            continue
        if token == "*":
            italic = not italic
            continue
        if not token:
            continue
        link = re.fullmatch(r"\[([^\]\n]+)\]\(([^)\s]+)\)", token)
        coloured = re.fullmatch(r"\[([^\]\n]+)\]\{([^}\s]+)\}", token)
        # A link's or a colour's words may carry emphasis of their own.
        if link:
            pieces = tuple(replace(run, link=link.group(2)) for run in inline(link.group(1)))
        elif coloured:
            pieces = tuple(replace(run, color=coloured.group(2)) for run in inline(coloured.group(1)))
        else:
            pieces = parse_label(token)
        for run in pieces:
            runs.append(
                replace(
                    run,
                    weight=700 if bold else run.weight,
                    italic=run.italic or italic,
                )
            )
    return tuple(runs)


class Region:
    """A place on a slide that holds blocks, one under the other."""

    def __init__(self, slide: Slide, name: str) -> None:
        self._slide = slide
        self.name = name
        self.blocks: list[_Block] = []

    def bullets(
        self,
        *items: str | Sequence[str],
        size: float | None = None,
        numbered: bool = False,
        reveal: bool = False,
    ) -> Region:
        """A bulleted list. A nested list of strings is the level below the item before it.
        ``numbered=True`` numbers the outer level (1., 2., ...); levels below keep bullets.
        ``reveal=True`` shows the outer items one at a time: a click each in the
        PowerPoint, a page each in the PDF (the SVG and PNG show them all)."""

        flattened: list[tuple[int, tuple[TextRun, ...]]] = []

        def add(entries: Iterable[str | Sequence[str]], level: int) -> None:
            for entry in entries:
                if isinstance(entry, str):
                    flattened.append((level, inline(entry)))
                else:
                    add(entry, level + 1)

        add(items, 0)
        self.blocks.append(_Bullets(flattened, size, numbered, reveal))
        return self

    def text(
        self,
        words: str,
        *,
        size: float | None = None,
        align: Literal["start", "middle", "end"] = "start",
        muted: bool = False,
        colour: str | None = None,
    ) -> Region:
        """A paragraph, wrapped to the region; ``$...$`` is math, as in flexo labels.
        ``colour`` paints it: ``accent`` (``accent2``...), ``muted``, a palette role,
        or ``#rrggbb``; ``[words]{colour}`` paints only some words."""

        self.blocks.append(_Words(inline(words), size, align, muted, colour))
        return self

    def gallery(
        self,
        items: Sequence[str | Path | tuple[str | Path, str]],
        *,
        columns: int | None = None,
        height: float | None = None,
        crop: Literal["circle", "square"] | None = None,
        size: float | None = None,
        align: Literal["start", "middle"] | None = None,
    ) -> Region:
        """Pictures in a grid -- logos, or people with their names -- each with an
        optional caption under it (``(file, "**Name**\\nInstitute")``).

        ``columns`` defaults to all in one row up to five; ``height`` is each
        picture's height (the cell's width at most); ``crop="circle"`` cuts
        photographs to circles (and ``"square"`` to squares), which needs Pillow.
        ``align`` sets a single column flush with the words (``start``, its default)
        or centred; a grid of several columns is centred.
        """

        cells = []
        for item in items:
            source, caption = (item, "") if isinstance(item, str | Path) else item
            cells.append((str(source), inline(caption) if caption else ()))
        self.blocks.append(_Gallery(cells, columns, height, crop, size, align))
        return self

    def quote(self, words: str, *, by: str = "", size: float | None = None) -> Region:
        """A quotation set large in the title face, an accent quotation mark hung in
        the margin beside it, and who said it (``by``) under it, muted."""

        self.blocks.append(_Quote(inline(words), inline(f"\u2014 {by}") if by else (), size))
        return self

    def stats(
        self,
        *items: tuple[object, str],
        colour: str | None = None,
        size: float | None = None,
    ) -> Region:
        """Numbers to remember, side by side: ``stats(("93%", "top-1 accuracy"), ("4x", "faster"))``.
        Each value is set very large in the accent colour (``colour`` to choose
        another: ``accent2``, ``#hex``) with its label under it, muted; ``size``
        is the values' size."""

        if not items:
            raise ValueError("stats needs at least one (value, label) pair")
        self.blocks.append(
            _Stats([(inline(str(value)), inline(label)) for value, label in items], colour, size)
        )
        return self

    def callout(
        self, words: str, *, title: str = "", colour: str = "accent", size: float | None = None
    ) -> Region:
        """A key point on a panel tinted in a tone, a bar of the tone along its edge:
        ``colour`` is ``accent`` (``accent2``, ...); ``title`` is set bold above the words."""

        if not (colour.startswith("accent") and colour[6:] in {"", *map(str, range(1, 13))}):
            raise ValueError(f'a callout\'s colour is "accent", "accent2", ... not "{colour}"')
        self.blocks.append(_Callout(inline(words), inline(f"**{title}**") if title else (), colour, size))
        return self

    def figure(self, id: str | None = None, *, turn: bool = True, **options: object) -> flexo.Figure:
        """A flexo figure in the deck's theme, laid out for this place: use it as a
        ``with`` block. ``turn=False`` keeps it as written (see ``add``)."""

        deck = self._slide.deck
        options = {**deck.figure_options(), **options}
        figure = flexo.Figure(id or f"{self._slide.id}-{self.name}-{len(self.blocks)}", **options)
        self.blocks.append(_Figure(figure, turn))
        return figure

    def add(self, figure: flexo.Figure | FigureSpec, *, turn: bool = True) -> Region:
        """An existing flexo figure, laid out again in the deck's theme for this place.

        Flexo lays it out for the place's width *and* height: as written, or turned
        (a tall stack read left to right) or spaced closer when that lets its words
        be larger -- ``turn=False`` keeps it as written.
        """

        self.blocks.append(_Figure(figure, turn))
        return self

    def image(self, source: str | Path, *, width: float | None = None) -> Region:
        """A picture file, scaled to fit: an SVG (a saved plot, a drawing) is drawn
        as vectors -- native shapes and text in the PowerPoint -- and a PNG as a picture."""

        self.blocks.append(_Image(str(source), width))
        return self

    def table(
        self,
        rows: Sequence[Sequence[object]],
        *,
        header: bool = True,
        align: str | Sequence[str] = "",
        size: float | None = None,
    ) -> Region:
        """A table, ruled as in a paper: a rule above, one under the header, one below.

        ``rows`` are lists of cells (words, with ``$...$`` maths, or numbers);
        the first row is the header unless ``header=False``. ``align`` gives each
        column ``start``, ``middle``, or ``end`` (``"lrr"`` also works); by
        default a column of numbers is set flush right and any other flush left.
        """

        cells = [[inline(str(cell)) for cell in row] for row in rows]
        columns = max((len(row) for row in cells), default=0)
        cells = [row + [()] * (columns - len(row)) for row in cells]
        names = {"l": "start", "c": "middle", "r": "end"}
        if isinstance(align, str) and align and all(ch in names for ch in align):
            aligned = tuple(names[ch] for ch in align)
        elif isinstance(align, str):
            aligned = ()
        else:
            aligned = tuple(align)
        if len(aligned) != columns:
            body = [list(row) for row in rows[1 if header else 0 :]]
            aligned = tuple(
                "end"
                if body and all(_numeric(row[index]) for row in body if index < len(row))
                else "start"
                for index in range(columns)
            )
        self.blocks.append(_Table(cells, header, aligned, size))
        return self

    def code(self, source: str, *, size: float | None = None) -> Region:
        """A code listing in the monospace family, on a tinted panel; lines are kept as
        written (tabs become four spaces) and whole-line comments are set muted."""

        import textwrap

        text = textwrap.dedent(source.expandtabs(4)).strip("\n")
        self.blocks.append(_Code(text.splitlines() or [""], size))
        return self

    def plot(self, figure: object, *, aspect: float | None = None) -> Region:
        """A matplotlib figure, drawn at the size of this place in the deck's type.

        The figure is laid out again at the place's size (matplotlib's
        constrained layout), so its words are the deck's figure size rather than
        scaled; its text is set in the deck's font and stays text. Make it inside
        ``with deck.plotting():`` for the deck's colours as well.
        """

        self.blocks.append(_Plot(figure, aspect))
        return self


def _numeric(cell: object) -> bool:
    if isinstance(cell, int | float):
        return True
    text = str(cell).strip().replace("$", "").replace("*", "").replace(",", "")
    text = text.replace("\\pm", "±").rstrip("%").strip()
    return bool(re.fullmatch(r"[-+\u2212]?\d+(\.\d+)?(\s*±\s*\d+(\.\d+)?)?\s*[kKMGTBx\u00d7]?", text))


class Slide:
    """One slide: a title, regions by layout, and speaker notes."""

    def __init__(
        self,
        deck: Deck,
        index: int,
        title: str,
        layout: Layout,
        subtitle: str,
        split: float = 0.5,
        columns: int = 3,
        widths: Sequence[float] | None = None,
        background: str | Path | None = None,
        shade: float = 0.0,
        dark: bool | None = None,
        align: str | None = None,
    ) -> None:
        if layout not in LAYOUTS:
            raise ValueError(f'unknown layout "{layout}"; layouts are {", ".join(LAYOUTS)}')
        self.deck = deck
        self.index = index
        self.id = f"slide{index}"
        self.title_runs = inline(title) if title else ()
        self.subtitle_runs = inline(subtitle) if subtitle else ()
        self.layout = layout
        self.split = split
        """The share of the width the left column takes, on a two-column slide."""
        self.notes_text = ""
        self.footnotes: list[tuple[TextRun, ...]] = []
        self.background = str(background) if background is not None else None
        """This slide's own background: a colour (``#1b2a41``) or a picture file."""
        self.shade = shade
        """How much a background picture is darkened (0 to 1), for words over it."""
        self.dark = dark
        """Whether the slide's words are light; decided from the background when unset."""
        if align not in {None, "auto", "top", "middle"}:
            raise ValueError(f'align is "auto", "top", or "middle", not "{align}"')
        self.align = align
        """Where the content sits in the body; the deck style's ``align`` when unset."""
        self.byline_runs: tuple[TextRun, ...] = ()
        """Who and when, on a title slide."""
        if layout == "columns":
            count = len(widths) if widths else columns
            if count < 1:
                raise ValueError("a columns slide needs at least one column")
            names = tuple(f"column{index + 1}" for index in range(count))
            total = sum(widths) if widths else float(count)
            self.shares = [share / total for share in widths] if widths else [1.0 / count] * count
        else:
            names = {"two-columns": ("left", "right")}.get(layout, ("body",))
            self.shares = [split, 1.0 - split] if layout == "two-columns" else [1.0]
        """Each column's share of the width, left to right."""
        self.regions = {name: Region(self, name) for name in names}

    @property
    def backdrop(self) -> str | None:
        """What the slide is drawn on when not the deck's page: its own background,
        or the accent colour that fills a section slide in a look that fills them."""

        if self.background:
            return self.background
        if self.layout == "section" and self.deck.style.sections == "fill":
            return accent_field(self.deck.palette)
        return None

    @property
    def columns(self) -> list[Region]:
        """The regions left to right: ``slide.columns[0]`` is the first column."""

        return list(self.regions.values())

    def __enter__(self) -> Slide:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def body(self) -> Region:
        return self._region("body")

    @property
    def left(self) -> Region:
        return self._region("left")

    @property
    def right(self) -> Region:
        return self._region("right")

    def _region(self, name: str) -> Region:
        if name not in self.regions:
            raise AttributeError(
                f'a "{self.layout}" slide has regions {", ".join(self.regions)}, not "{name}"'
            )
        return self.regions[name]

    # The first region stands for the slide, so a one-region slide reads simply.
    def bullets(
        self,
        *items: str | Sequence[str],
        size: float | None = None,
        numbered: bool = False,
        reveal: bool = False,
    ) -> Slide:
        next(iter(self.regions.values())).bullets(*items, size=size, numbered=numbered, reveal=reveal)
        return self

    def text(self, words: str, **options: object) -> Slide:
        next(iter(self.regions.values())).text(words, **options)  # type: ignore[arg-type]
        return self

    def figure(self, id: str | None = None, *, turn: bool = True, **options: object) -> flexo.Figure:
        return next(iter(self.regions.values())).figure(id, turn=turn, **options)

    def add(self, figure: flexo.Figure | FigureSpec, *, turn: bool = True) -> Slide:
        next(iter(self.regions.values())).add(figure, turn=turn)
        return self

    def image(self, source: str | Path, *, width: float | None = None) -> Slide:
        next(iter(self.regions.values())).image(source, width=width)
        return self

    def gallery(self, items, **options: object) -> Slide:
        next(iter(self.regions.values())).gallery(items, **options)  # type: ignore[arg-type]
        return self

    def code(self, source: str, *, size: float | None = None) -> Slide:
        next(iter(self.regions.values())).code(source, size=size)
        return self

    def table(self, rows: Sequence[Sequence[object]], **options: object) -> Slide:
        next(iter(self.regions.values())).table(rows, **options)  # type: ignore[arg-type]
        return self

    def plot(self, figure: object, *, aspect: float | None = None) -> Slide:
        next(iter(self.regions.values())).plot(figure, aspect=aspect)
        return self

    def quote(self, words: str, **options: object) -> Slide:
        next(iter(self.regions.values())).quote(words, **options)  # type: ignore[arg-type]
        return self

    def stats(self, *items: tuple[object, str], **options: object) -> Slide:
        next(iter(self.regions.values())).stats(*items, **options)  # type: ignore[arg-type]
        return self

    def callout(self, words: str, **options: object) -> Slide:
        next(iter(self.regions.values())).callout(words, **options)  # type: ignore[arg-type]
        return self

    def notes(self, text: str) -> Slide:
        """What to say: kept as the slide's speaker notes."""

        self.notes_text = text
        return self

    def footnote(self, text: str) -> Slide:
        """A reference or aside, set small and muted at the foot of the slide
        (above the footer); several stack in the order given."""

        self.footnotes.append(inline(text))
        return self


class Deck:
    """A slide deck in one flexo theme; see the module docs."""

    def __init__(
        self,
        id: str = "talk",
        *,
        theme: str = "paper",
        palette: str | Sequence[str] = "default",
        font: str | None = None,
        title_font: str | None = None,
        figure_font: str | None = None,
        conventions: dict[str, object] | None = None,
        sketch: object = None,
        background: bool | str = True,
        footer: str = "",
        style: DeckStyle | None = None,
        look: str | None = None,
    ) -> None:
        # A theme file is read now, by the Figure machinery that knows how.
        probe = flexo.Figure("probe", theme=theme, palette=palette)
        self.id = id
        self.theme = probe.style
        self.palette_name = probe.palette
        self.font = font
        """The family of the slides' words and figures; the theme's when unset."""
        self.title_font = title_font
        """The family of slide titles and section headings; ``font`` when unset."""
        self.figure_font = figure_font
        """The family of the figures' words; ``font`` when unset."""
        from flexo.fonts import require_family

        for family in (font, title_font, figure_font):
            if family:
                require_family(family)
        self.conventions = conventions
        self.sketch = sketch
        self.background = background
        self.footer = footer
        if look is not None:
            if look not in LOOKS:
                raise ValueError(f'unknown look "{look}"; looks are {", ".join(LOOKS)}')
            # A look sets the page; a style given beside it keeps its own sizes.
            style = replace(style, **LOOKS[look]) if style else DeckStyle.look(look)  # type: ignore[arg-type]
        self.style = style or DeckStyle()
        self.slides: list[Slide] = []

    def __enter__(self) -> Deck:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    # -- authoring --

    def slide(
        self,
        title: str = "",
        *,
        layout: Layout = "content",
        subtitle: str = "",
        split: float = 0.5,
        columns: int = 3,
        widths: Sequence[float] | None = None,
        background: str | Path | None = None,
        shade: float = 0.0,
        dark: bool | None = None,
        align: Literal["auto", "top", "middle"] | None = None,
    ) -> Slide:
        """A slide: ``content`` (a title over one body), ``two-columns`` (``split`` is
        the left column's share of the width), ``columns`` (``columns`` of them, or
        as many as ``widths``, relative: ``(2, 1, 1)``; ``slide.columns[i]``),
        ``figure`` (a title over a figure as large as the slide allows), or ``blank``.

        ``background`` gives this slide its own background: a colour, or a picture
        that fills the slide (cropped, never stretched), darkened by ``shade``; on a
        dark background the slide's words are set light (``dark`` overrides).
        ``align`` places the content in the body (see ``DeckStyle.align``)."""

        if not 0.15 <= split <= 0.85:
            raise ValueError("split is the left column's share of the width, between 0.15 and 0.85")
        made = Slide(
            self, len(self.slides) + 1, title, layout, subtitle, split, columns, widths,
            background, shade, dark, align,
        )
        self.slides.append(made)
        return made

    def title(
        self,
        title: str,
        *,
        subtitle: str = "",
        author: str = "",
        date: str = "",
        background: str | Path | None = None,
        shade: float = 0.0,
    ) -> Slide:
        """The opening slide: the talk's title, a subtitle, who and when (and, if
        given, a background colour or picture: see ``slide``)."""

        made = self.slide(title, layout="title", subtitle=subtitle, background=background, shade=shade)
        byline = " · ".join(part for part in (author, date) if part)
        made.byline_runs = inline(byline) if byline else ()
        return made

    def section(
        self, title: str, *, subtitle: str = "", background: str | Path | None = None, shade: float = 0.0
    ) -> Slide:
        """A divider between parts of the talk."""

        return self.slide(title, layout="section", subtitle=subtitle, background=background, shade=shade)

    def statement(
        self, words: str, *, by: str = "", background: str | Path | None = None, shade: float = 0.0
    ) -> Slide:
        """A slide that says one thing, large, in the middle: a claim, a question, a
        quotation (``by`` says whose). ``[words]{accent}`` paints the words that matter."""

        made = self.slide(words, layout="statement", background=background, shade=shade)
        made.byline_runs = inline(f"\u2014 {by}") if by else ()
        return made

    def agenda(self, title: str = "Outline") -> Slide:
        """A slide listing the talk's sections, numbered -- the ``section`` slides
        anywhere in the deck, so it can come before them."""

        return self.slide(title, layout="agenda")

    def figure_options(self) -> dict[str, object]:
        options: dict[str, object] = {"theme": self.theme, "palette": self.palette_name}
        if self.figure_font or self.font:
            options["font"] = self.figure_font or self.font
        if self.conventions:
            options["conventions"] = self.conventions
        if self.sketch is not None:
            options["sketch"] = self.sketch
        return options

    # -- the look --

    @property
    def layout_style(self) -> LayoutStyle:
        return resolve_style(self.theme, self.font, None, flexo.sketch.parse_sketch(self.sketch))

    @property
    def palette(self) -> Palette:
        return with_tone_roles(resolve_palette(self.theme, self.palette_name))

    def plot_style(self) -> dict[str, object]:
        """matplotlib settings for plots in the deck's look: its font and figure
        size, its inks, and the palette's tones as the colour cycle."""

        from cycler import cycler
        from flexo.colour import is_dark, with_lightness

        palette = self.palette
        dark = is_dark(palette.get("canvas"))
        tones = [palette.get(f"tone-{index}-stroke") for index in range(1, 7)]
        colours = [with_lightness(tone, 0.74 if dark else 0.58, 0.16) for tone in tones]
        ink, muted = palette.get("ink"), palette.get("muted-ink")
        family = self.layout_style.typography.family
        # Plot words sit a little above figure labels: tick labels are read from afar.
        size = self.style.figure_size * 1.15
        return {
            "font.family": [family],
            "font.size": size,
            "axes.titlesize": size * 1.1,
            "axes.labelsize": size,
            "xtick.labelsize": size * 0.9,
            "ytick.labelsize": size * 0.9,
            "legend.fontsize": size * 0.9,
            "text.color": ink,
            "axes.labelcolor": ink,
            "axes.titlecolor": ink,
            "axes.edgecolor": muted,
            "xtick.color": muted,
            "ytick.color": muted,
            "xtick.labelcolor": ink,
            "ytick.labelcolor": ink,
            "grid.color": muted,
            "grid.alpha": 0.25,
            "axes.prop_cycle": cycler(color=colours),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.facecolor": "none",
            "figure.facecolor": "none",
            "legend.frameon": False,
            "lines.linewidth": 2.0,
            "patch.edgecolor": "none",
            "mathtext.fontset": "custom",
            "mathtext.rm": family,
            "mathtext.it": f"{family}:italic",
            "mathtext.bf": f"{family}:bold",
            # Symbols the deck's face lacks come from Unicode fonts, so they stay
            # the right characters when set as text (TeX fonts would not).
            "mathtext.fallback": "stix",
            "svg.fonttype": "none",
            "figure.constrained_layout.use": True,
        }

    def plotting(self):
        """``with deck.plotting():`` -- matplotlib figures made inside take the deck's look."""

        import matplotlib

        from flexo_talk.compose import register_fonts_with_matplotlib

        register_fonts_with_matplotlib()
        return matplotlib.rc_context(self.plot_style())

    def typography(self, size: float, *, title: bool = False) -> TypographyStyle:
        """The type at ``size``: in the title font for a heading, else the words' font."""

        typography = self.layout_style.typography
        if title and self.title_font:
            typography = typography.with_family(self.title_font)
        return replace(typography, size=pt(size), minimum_size=pt(min(size, 6.0)))

    @property
    def title_weight(self) -> int:
        return self.style.title_weight or self.layout_style.typography.title_weight

    # -- output --

    def render(self) -> list[RenderedSlide]:
        """Every slide laid out and drawn as SVG."""

        from flexo_talk.compose import render_slide

        return [render_slide(self, slide) for slide in self.slides]

    def build(
        self,
        directory: str | Path = "build",
        *,
        formats: Sequence[str] = ("pptx", "pdf", "svg", "png"),
        handout: bool = False,
    ) -> DeckBuild:
        """Write the deck: ``pptx`` and ``pdf`` (one file each), ``svg`` and ``png`` per slide."""

        from flexo_talk.export import build_deck

        return build_deck(self, Path(directory), tuple(formats), handout=handout)


@dataclass(slots=True)
class ListLayout:
    """Where a bulleted list was set, for writers that set lists natively."""

    x: float
    y: float
    width: float
    size: float
    line_height: float
    gap: float
    indent: float
    items: list[tuple[int, tuple[TextRun, ...], float]] = field(default_factory=list)
    """``(level, runs, baseline of its first line)`` for each item."""
    id: str = ""
    numbered: bool = False
    reveal: bool = False
    """Whether the outer items appear one click (one PDF page) at a time."""
    number_room: float = 0.0
    """How far an outer item's words start from its number's left edge, when numbered."""
    palette: Palette | None = None
    """The slide's paints (light words on a dark slide); the deck's when unset."""

    def offset(self, level: int) -> float:
        """Where an item's words start, from the list's left edge."""

        if self.numbered and level == 0:
            return self.number_room
        return self.indent * level + self.size * 0.95

    def mark_at(self, level: int) -> float:
        """Where an item's bullet or number starts, from the list's left edge."""

        return 0.0 if self.numbered and level == 0 else self.indent * level + self.size * 0.12


@dataclass(slots=True)
class TableLayout:
    """Where a table was set, for writers that set tables natively."""

    x: float
    y: float
    widths: list[float]
    heights: list[float]
    cells: list[list[tuple[TextRun, ...]]]
    align: tuple[str, ...]
    size: float
    line_height: float
    baseline: float
    """Where each row's first baseline sits below the row's top."""
    pad: float
    header: bool
    rules: tuple[float, float, float]
    """The widths of the top rule, the rule under the header, and the bottom rule."""
    id: str = ""
    rtl: bool = False
    """Whether the table reads from the right (its header is in a right-to-left script)."""
    palette: Palette | None = None
    """The slide's paints (light words on a dark slide); the deck's when unset."""


@dataclass(slots=True)
class RenderedSlide:
    slide: Slide
    svg: str
    lists: list[ListLayout]
    diagnostics: list[str] = field(default_factory=list)
    tables: list[TableLayout] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    steps: int = 1
    """How many states the slide shows in turn (revealed lists); 1 for most."""

    def at_step(self, step: int) -> str:
        """The slide's SVG as it stands at ``step`` (1-based): later items hidden."""

        if self.steps <= 1:
            return self.svg
        import xml.etree.ElementTree as ET

        root = ET.fromstring(self.svg)
        for parent in root.iter():
            for child in list(parent):
                if int(child.get("data-flexo-step", "0")) > step:
                    parent.remove(child)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


@dataclass(frozen=True, slots=True)
class DeckBuild:
    pptx: Path | None
    pdf: Path | None
    svgs: tuple[Path, ...]
    pngs: tuple[Path, ...]
    diagnostics: tuple[str, ...]
    notes: tuple[str, ...] = ()
    """What the build chose that is worth knowing: a figure laid out turned to fit."""

    def summary(self) -> str:
        written = [str(path) for path in (self.pptx, self.pdf, *self.svgs, *self.pngs) if path]
        head = "ok" if not self.diagnostics else "warnings:\n  " + "\n  ".join(self.diagnostics)
        notes = ["notes:", *(f"  {note}" for note in self.notes)] if self.notes else []
        return "\n".join([head, *notes, *written])
