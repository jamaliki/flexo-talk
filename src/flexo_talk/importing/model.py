"""What a PowerPoint or Keynote deck says, read into one shape before it is written as a deck.

Both readers (``flexo_talk.importing.powerpoint``, ``flexo_talk.importing.keynote``) make a
``Presentation`` of these; ``flexo_talk.importing.writing`` makes a Flexo deck of it. Every
place and size is in points on the source's own slide, y down; every colour is ``#rrggbb``
with its alpha apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# -- paint ----------------------------------------------------------------------------------


@dataclass
class Colour:
    """A colour, and how opaque it is (0 to 1). ``scheme`` names the theme's colour it was
    written as (``accent1``, ``tx1``...), when it was: a theme's colour stays the theme's."""

    hex: str
    alpha: float = 1.0
    scheme: str | None = None


@dataclass
class Gradient:
    """A gradient fill: ``stops`` as (where, 0 to 1, colour); ``angle`` in degrees clockwise
    from left to right for a linear one."""

    stops: list[tuple[float, Colour]]
    angle: float = 0.0
    radial: bool = False


@dataclass
class Media:
    """A file the deck holds: its bytes and its name (whose ending says what it is)."""

    name: str
    data: bytes


@dataclass
class Stroke:
    colour: Colour | None
    width: float = 1.0
    dash: str | list[float] = "solid"
    head: str = "none"
    """The arrowhead where the line starts: one of Flexo's (``triangle``, ``open``...)."""
    tail: str = "none"
    """The arrowhead where the line ends."""
    head_size: float = 1.0
    cap: str | None = None
    join: str | None = None


Fill = Colour | Gradient | Media | None
"""A shape's fill: a colour, a gradient, a picture, or none."""

# -- words ------------------------------------------------------------------------------------


@dataclass
class Run:
    """Words in one look. ``tex`` is a formula in the words (its ``text`` then unused);
    ``field`` a slide program's field (``slide-number``, ``date``)."""

    text: str
    bold: bool | None = None
    italic: bool | None = None
    underline: bool = False
    strike: bool = False
    baseline: float = 0.0
    """Raised (more than 0) or lowered (less), as a share of the size."""
    size: float | None = None
    colour: Colour | None = None
    font: str | None = None
    link: str | None = None
    tex: str | None = None
    field: str | None = None
    caps: bool = False


@dataclass
class Paragraph:
    runs: list[Run] = field(default_factory=list)
    level: int = 0
    bullet: Literal["bullet", "number"] | None = None
    align: Literal["start", "middle", "end", "justify"] | None = None
    display: str | None = None
    """A paragraph that is one displayed formula: its TeX."""
    space_before: float = 0.0
    space_after: float = 0.0
    line_spacing: float | None = None
    """Lines as a share of the size (1.0 single), where it says."""
    line_points: float | None = None
    """Lines this many points apart, where it says so exactly."""
    size: float | None = None
    """The size of an empty paragraph (its end), for the room it takes."""
    indent: float | None = None
    """How far in from its box's edge its words stand, in points, where it says."""

    @property
    def words(self) -> str:
        return "".join(run.text if run.tex is None else run.tex for run in self.runs)


@dataclass
class Frame:
    """Words in a box: its paragraphs, how far in from its edges they are set (left, top,
    right, bottom), where they stand down it, and whether they wrap."""

    paragraphs: list[Paragraph]
    insets: tuple[float, float, float, float] = (7.2, 3.6, 7.2, 3.6)
    anchor: Literal["top", "middle", "bottom"] = "top"
    wrap: bool = True
    scale: float = 1.0
    """What a slide program's shrink-to-fit made its words, as a share of their sizes."""
    vertical: bool = False

    @property
    def words(self) -> str:
        return "\n".join(paragraph.words for paragraph in self.paragraphs)

    @property
    def empty(self) -> bool:
        return not any(paragraph.words.strip() or paragraph.display for paragraph in self.paragraphs)


# -- what a slide holds ------------------------------------------------------------------------


@dataclass
class Box:
    """Where something is: its top left and size, turned ``rotate`` degrees clockwise about
    its middle, mirrored as ``flip_h`` and ``flip_v`` say."""

    x: float
    y: float
    w: float
    h: float
    rotate: float = 0.0
    flip_h: bool = False
    flip_v: bool = False

    @property
    def centre(self) -> tuple[float, float]:
        return self.x + self.w / 2.0, self.y + self.h / 2.0


@dataclass
class Element:
    box: Box
    name: str = ""
    ident: str = ""
    """The source's own id for it: what a connector names to be glued to it."""
    hidden: bool = False
    description: str = ""


Role = Literal["title", "subtitle", "body", "footer", "number", "date", "notes", "other"]


@dataclass
class TextBox(Element):
    frame: Frame = field(default_factory=lambda: Frame([]))
    role: Role | None = None
    """What a placeholder it fills says it is: the slide's title, its subtitle..."""
    fill: Fill = None
    stroke: Stroke | None = None


@dataclass
class Picture(Element):
    media: Media | None = None
    crop: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    """How much is cut off each side (left, top, right, bottom), as shares of the whole."""
    mask: str | None = None
    """``circle`` for a picture drawn round; ``rounded`` for one in a rounded rectangle."""
    opacity: float = 1.0
    stroke: Stroke | None = None
    still: Media | None = None
    """What stands for what cannot be shown (a movie's first frame)."""


@dataclass
class Shape(Element):
    """A drawn shape. ``kind`` is Flexo's where it has one (``rectangle``, ``ellipse``...),
    with its ``parameters``; else ``path``, its outline ``path`` in SVG path data in its box's
    own units (0 to ``box.w`` across, 0 to ``box.h`` down)."""

    kind: str = "rectangle"
    parameters: dict[str, object] = field(default_factory=dict)
    path: str = ""
    closed: bool = True
    fill: Fill = None
    stroke: Stroke | None = None
    frame: Frame | None = None
    opacity: float = 1.0
    shadow: bool = False


@dataclass
class Connector(Element):
    """A line from ``start`` to ``end``, through ``points`` between (an elbow's corners, a
    curve's controls), glued at either end to the element whose ``ident`` it names."""

    start: tuple[float, float] = (0.0, 0.0)
    end: tuple[float, float] = (0.0, 0.0)
    route: Literal["straight", "elbow", "curved", "path"] = "straight"
    points: list[tuple[float, float]] = field(default_factory=list)
    path: str = ""
    """A route drawn freely: its outline in slide points (``route: path``)."""
    stroke: Stroke | None = None
    start_glue: str | None = None
    end_glue: str | None = None
    frame: Frame | None = None


@dataclass
class Cell:
    frame: Frame
    span: tuple[int, int] = (1, 1)
    """How many columns and rows it spans."""
    merged: bool = False
    """Covered by another cell's span."""
    fill: Colour | None = None


@dataclass
class Table(Element):
    rows: list[list[Cell]] = field(default_factory=list)
    columns: list[float] = field(default_factory=list)
    header: bool = True
    ruled: bool = True
    """Whether any of its cells has a line round it."""


@dataclass
class Equation(Element):
    tex: str = ""
    size: float | None = None
    colour: Colour | None = None


@dataclass
class Group(Element):
    children: list[Element] = field(default_factory=list)


@dataclass
class Unknown(Element):
    """What cannot be brought across: its ``kind`` in words (``Chart``, ``SmartArt``,
    ``Video``) and why, kept where it was. ``picture`` is what stands for it, where the
    source has one (a chart's or a movie's picture of itself)."""

    kind: str = "Object"
    why: str = ""
    picture: Picture | None = None


# -- slides and the deck ----------------------------------------------------------------------


@dataclass
class Slide:
    number: int
    elements: list[Element] = field(default_factory=list)
    layout: Literal["title", "section", "content", "blank"] = "content"
    background: Colour | Gradient | Media | None = None
    notes: str = ""
    skip: bool = False
    name: str = ""
    decorations: list[Element] = field(default_factory=list)
    """What its layout and master draw on it: a logo, a band, a rule."""


@dataclass
class Theme:
    colours: dict[str, str] = field(default_factory=dict)
    """The theme's colours by name: ``dk1``, ``lt1``, ``accent1``... as ``#rrggbb``."""
    major: str | None = None
    """Its headings' family."""
    minor: str | None = None
    """Its words' family."""
    dark: bool = False
    """Whether its slides are dark, its words light."""


@dataclass
class Presentation:
    width: float
    height: float
    slides: list[Slide] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    name: str = ""
    title_style: dict[str, object] = field(default_factory=dict)
    """How the source sets its titles, where it says: their ``size``, ``bold``, ``colour``,
    ``align`` and ``box`` (where a title stands on a slide)."""
    body_size: float | None = None
    accent: str | None = None
    """The colour its lists' bullets are set in, where it sets them in one."""
