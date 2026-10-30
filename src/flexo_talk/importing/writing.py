"""A ``Presentation`` (what a PowerPoint or Keynote deck says) written as a Flexo deck.

Each slide's objects stand where they stood: words, lists, pictures, tables and equations are
the slide's objects placed with ``at`` and ``width`` (in the units a slide's shapes are placed
in, 960 across), and drawn shapes, lines and connectors its shapes. The title a placeholder
holds is the slide's title, drawn where the deck's look draws titles -- a look set from the
source's (its titles' size, weight and side, how far in they stand) -- unless a slide's title
stands elsewhere, when it is placed words as any other. A text box whose words stand in the
middle or at the foot of its box, or whose paragraphs differ (a heading over a list), is set
where its slide program set it once its words' heights are known (``settle``). What cannot be
brought across is kept as its place: a picture of it where the source has one, else a dashed
box hidden from the show, marked TODO, and said in the report.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flexo_talk.deck import SHAPE_FRAME
from flexo_talk.importing import markup as marks
from flexo_talk.importing.model import (
    Box,
    Colour,
    Connector,
    Element,
    Equation,
    Frame,
    Gradient,
    Group,
    Media,
    Paragraph,
    Picture,
    Presentation,
    Run,
    Shape,
    Slide,
    Stroke,
    Table,
    TextBox,
    Unknown,
)
from flexo_talk.importing.report import Progress, Report, quiet

PICTURES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}
"""Picture files a deck shows as they are."""

STAND_INS = {
    "calibri": "Carlito",
    "calibri light": "Carlito",
    "cambria": "Caladea",
    "aptos": "Figtree",
    "aptos display": "Figtree",
    "segoe ui": "Figtree",
    "segoe ui light": "Figtree",
    "century gothic": "Figtree",
    "open sans": "Figtree",
    "roboto": "Figtree",
    "lato": "Figtree",
    "source sans pro": "IBM Plex Sans",
    "gill sans": "Figtree",
    "gill sans mt": "Figtree",
    "trebuchet ms": "Figtree",
    "verdana": "Liberation Sans",
    "tahoma": "Liberation Sans",
    "franklin gothic book": "Liberation Sans",
    "consolas": "IBM Plex Mono",
    "courier new": "IBM Plex Mono",
    "menlo": "IBM Plex Mono",
    "monaco": "IBM Plex Mono",
    "times new roman": "Latin Modern Roman",
    "times": "Latin Modern Roman",
    "georgia": "Latin Modern Roman",
    "garamond": "Latin Modern Roman",
    "palatino": "Latin Modern Roman",
    "book antiqua": "Latin Modern Roman",
}
"""A family to set words in where the source's is not on this Mac: the one standing closest
of those that are, the first that resolves (``flexo.fonts``)."""

SANS, SERIF, MONO = "Figtree", "Latin Modern Roman", "IBM Plex Mono"
SERIFS = re.compile(r"times|georgia|garamond|palatino|cambria|book|serif|minion|baskerville|caslon|bodoni|didot", re.I)

TITLE_REACH = 16.0
"""How far (in points) a slide's title may stand from where the deck's look draws titles and
still be drawn there; one further is placed where it stood."""

HEAVY = 600
"""More shapes than this in one group and it is brought across as a picture of them (an SVG,
made shapes again by a double-click on it in the studio): a slide stays quick to edit."""

GLUE_REACH = 6.0
"""How near (in shape units) a line's end must be to a side's middle to be glued there."""


def _hex6(colour: str) -> str:
    return colour.lower()[:7]


def _round(value: float, places: int = 1) -> float | int:
    rounded = round(float(value), places)
    return int(rounded) if float(rounded).is_integer() else rounded


@dataclass
class _Item:
    """One of a slide's objects in its stacking order: a block or a shape, with where it is
    (in the source's points) and the source's id for it (what a line is glued to)."""

    block: dict | None = None
    shape: dict | None = None
    box: Box | None = None
    ident: str = ""


@dataclass
class _Stack:
    """The blocks one text box became, to be set in its box as its slide program set them
    (``settle``): its words' room (top and height, in the deck's points), where they stand
    down it, and the room before each block after the first."""

    slide: int
    blocks: list[dict]
    top: float
    room: float
    anchor: str
    gaps: list[float]


@dataclass
class Writer:
    presentation: Presentation
    folder: Path
    report: Report
    progress: Progress = quiet
    heavy: int = HEAVY
    media: dict[str, str | None] = field(default_factory=dict)
    stacks: list[_Stack] = field(default_factory=list)
    _names: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        source = self.presentation
        self.across = SHAPE_FRAME / source.width
        """Shape units (960 across the slide) a point of the source is."""
        self.k = 1.0 if source.width <= 1100 else SHAPE_FRAME / source.width
        """Deck points a point of the source is: its own, or -- for a slide far larger than a
        slide program's (Keynote's 1920 by 1080) -- as if it were 960 across."""
        self.width = _round(source.width * self.k, 2)
        self.height = _round(source.height * self.k, 2)
        theme = source.theme
        self.ink, self.paper = _page_colours(source)
        self.accents = _accents(source)
        self.font = self.family(theme.minor) or SANS
        self.title_font = self.family(theme.major) or self.font
        self.title_size = 30.0
        self.title_align = "start"
        self.margin = 48.0
        self._slide = Slide(0)
        self._index = 0
        self._ids: Counter = Counter()
        self._shapes_only = False
        self.settings: dict[str, Any] = {"id": "deck", "theme": "paper"}

    # -- families ------------------------------------------------------------------------

    def family(self, name: str | None) -> str | None:
        """``name`` if this Mac has it, else the family set in its place (said in the report)."""

        if not name:
            return None
        from flexo.fonts import family_faces

        name = name.strip()
        with contextlib.suppress(Exception):
            if family_faces(name):
                return name
        for stand_in in (STAND_INS.get(name.casefold()), MONO if marks.MONOSPACE.search(name) else None,
                         SERIF if SERIFS.search(name) else None, SANS):
            if not stand_in:
                continue
            with contextlib.suppress(Exception):
                if family_faces(stand_in):
                    self.report.fonts.setdefault(name, stand_in)
                    return stand_in
        return None

    # -- colours -------------------------------------------------------------------------

    def colour(self, colour: Colour | None, *, words: bool = False) -> str | None:
        """A colour as a deck writes it, ``#rrggbb`` as it was (a theme's colours are
        Flexo's own, made from the deck's: no slide program's colour is one by name).
        ``words``: ``None`` for the words' own colour, the deck's ink."""

        if colour is None:
            return None
        hex_colour = _hex6(colour.hex)
        if words and hex_colour == self.ink:
            return None
        return hex_colour

    def _named(self, colour: Colour) -> str | None:
        return self.colour(colour, words=True)

    def _readable(self, colour: Colour) -> str | None:
        """A colour for words, unless it would not read on the deck's page."""

        from flexo.colour import contrast

        named = self.colour(colour, words=True)
        try:
            return named if named is None or contrast(named, self.paper) >= 1.8 else None
        except Exception:
            return named

    def paint(self, fill: object) -> object:
        """A shape's fill as a deck writes it."""

        if isinstance(fill, Colour):
            return self.colour(fill) or _hex6(fill.hex)
        if isinstance(fill, Gradient) and fill.stops:
            stops = [[_round(min(max(at, 0.0), 1.0), 3), self.colour(stop) or _hex6(stop.hex)]
                     for at, stop in fill.stops]
            if fill.radial:
                return {"gradient": "radial", "stops": stops}
            return {"gradient": "linear", "angle": _round(fill.angle % 360, 1), "stops": stops}
        return "none"

    # -- files ---------------------------------------------------------------------------

    def picture_file(self, media: Media | None) -> str | None:
        """Where a picture the deck holds is written, beside it (``assets/``): one file however
        often it is shown. A kind no slide shows (a TIFF, a BMP, a HEIC) is made a PNG; one
        that cannot be (a Windows metafile) is ``None``."""

        if media is None or not media.data:
            return None
        digest = hashlib.sha1(media.data).hexdigest()
        if digest in self.media:
            return self.media[digest]
        name = _safe_name(Path(media.name).name or "picture")
        ending = Path(name).suffix.lower()
        data: bytes | None = media.data
        if ending not in PICTURES:
            data = _as_png(media.data, ending)
            name = f"{Path(name).stem or 'picture'}.png"
        if data is None:
            self.media[digest] = None
            return None
        written = self._unique(name)
        target = self.folder / "assets" / written
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.media[digest] = f"assets/{written}"
        return self.media[digest]

    def _unique(self, name: str) -> str:
        stem, ending = Path(name).stem, Path(name).suffix
        candidate, count = name, 1
        while candidate.lower() in self._names:
            count += 1
            candidate = f"{stem}-{count}{ending}"
        self._names.add(candidate.lower())
        return candidate

    def cropped_file(self, picture: Picture) -> str | None:
        """A bitmap with its crop cut into it, for a picture drawn as a shape (turned, in a
        group), which keeps no crop of its own."""

        source = self.picture_file(picture.media)
        if source is None or _crop(picture.crop) is None or Path(source).suffix.lower() not in (".png", ".jpg",
                                                                                                    ".jpeg"):
            return source
        try:
            from PIL import Image

            with Image.open(self.folder / source) as image:
                image.load()
                w, h = image.size
                left, top, right, bottom = (min(max(value, 0.0), 1.0) for value in picture.crop)
                box = (round(w * left), round(h * top), round(w * (1 - right)), round(h * (1 - bottom)))
                if box[2] - box[0] < 1 or box[3] - box[1] < 1:
                    return source
                out = io.BytesIO()
                image.crop(box).save(out, "PNG")
        except Exception:
            return source
        return self.picture_file(Media(f"{Path(source).stem}-cropped.png", out.getvalue()))

    # -- the deck ------------------------------------------------------------------------

    def theme_file(self, stem: str) -> str:
        """The source's look as a Flexo theme of its own, a file beside the deck
        (``flexo.theme_files``): its faces, its colours (as a palette, in their order), and
        its words' ink and page -- based on Flexo's light theme, or its dark one."""

        settings: dict[str, Any] = {"name": f"{_safe_id(stem)}-imported",
                                    "base": "dark" if self.presentation.theme.dark else "paper",
                                    "font": self.font}
        if self.title_font != self.font:
            settings["type"] = {"title_family": self.title_font}
        if self.accents:
            settings["palette"] = self.accents
        settings["page"] = {"ink": self.ink, "canvas": self.paper}
        import yaml

        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "theme.yaml").write_text(
            yaml.safe_dump({"theme": settings}, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return "theme.yaml"

    def document(self, stem: str) -> dict[str, Any]:
        source = self.presentation
        style: dict[str, Any] = {"width": self.width, "height": self.height, "header": "none"}
        deck: dict[str, Any] = {"id": _safe_id(stem), "theme": self.theme_file(stem)}
        self._title_look(style)
        self._spacing(style)
        numbered = sum(1 for slide in source.slides if any(
            isinstance(element, TextBox) and element.role == "number" for element in slide.elements))
        style["numbers"] = bool(source.slides) and numbered * 2 >= len(source.slides)
        footers = Counter(
            marks.plain(element.frame.paragraphs[0])
            for slide in source.slides for element in slide.elements
            if isinstance(element, TextBox) and element.role == "footer" and element.frame.paragraphs
        )
        footer = next((words for words, count in footers.most_common() if words), None)
        if footer:
            deck["footer"] = footer
        deck["style"] = style
        self.settings = deck
        slides = []
        for index, slide in enumerate(source.slides):
            self.progress(0.6 + 0.25 * index / max(len(source.slides), 1),
                          f"Writing slide {index + 1} of {len(source.slides)}")
            self._index = index
            try:
                slides.append(self.slide(slide))
            except Exception as error:  # a slide that cannot be written is kept, empty, and said
                self.report.placeholder(slide.number, "Slide", f"could not be brought across ({error})")
                self.stacks = [stack for stack in self.stacks if stack.slide != index]
                slides.append({"layout": "blank", **({"notes": slide.notes} if slide.notes else {})})
        self.report.slides = len(slides)
        return {"schema_version": 1, "deck": deck, "slides": slides}

    def _title_look(self, style: dict[str, Any]) -> None:
        """The deck's titles set as the source sets them: their size, weight and side, and
        how far in from the slide's corner they stand."""

        look = self.presentation.title_style
        size = look.get("size")
        if isinstance(size, int | float) and size > 0:
            style["title_size"] = _round(min(max(float(size) * self.k, 8.0), 200.0))
        if look.get("bold") is not None:
            style["title_weight"] = 700 if look.get("bold") else 400
        if look.get("align") == "middle":
            style["title_align"] = "middle"
        box = look.get("box")
        if isinstance(box, Box):
            margin = box.x * self.k
            if 8.0 <= margin <= min(self.width, self.height) / 4:
                style["margin"] = _round(margin)
        self.title_size = float(style.get("title_size") or 30.0)
        self.title_align = str(style.get("title_align") or "start")
        self.margin = float(style.get("margin") or 48.0)

    def _spacing(self, style: dict[str, Any]) -> None:
        """The deck's lines and a list's items spaced as the source's are, mostly."""

        lines, gaps = [], []
        for slide in self.presentation.slides:
            for element in slide.elements:
                if not isinstance(element, TextBox) or element.role not in ("body", None):
                    continue
                for paragraph in element.frame.paragraphs:
                    size = _size_of(paragraph)
                    if not size or not paragraph.words.strip():
                        continue
                    if paragraph.line_points:
                        lines.append(paragraph.line_points / size)
                    elif paragraph.line_spacing:
                        lines.append(1.2 * paragraph.line_spacing)
                    if paragraph.bullet and paragraph.space_before:
                        gaps.append(paragraph.space_before / size)
        if len(lines) >= 3:
            line = sorted(lines)[len(lines) // 2]
            if 1.0 <= line <= 2.0 and abs(line - 1.25) > 0.04:
                style["line_height"] = _round(line, 2)
        if len(gaps) >= 3:
            gap = sorted(gaps)[len(gaps) // 2]
            if 0.0 <= gap <= 1.5:
                style["paragraph_gap"] = _round(gap, 2)

    # -- a slide -------------------------------------------------------------------------

    def slide(self, slide: Slide) -> dict[str, Any]:
        self._slide = slide
        self._ids = Counter()
        written: dict[str, Any] = {}
        elements = [element for element in slide.elements if not element.hidden]
        found = self._title(slide, elements)
        layout = "blank"
        if found is not None:
            words, subtitle, title = found
            layout = "title" if slide.layout == "title" else "content"
            written["title"] = words
            elements = [element for element in elements if element is not title]
            if subtitle is not None:
                written["subtitle"] = marks.paragraph_markup(_joined(subtitle.frame), colour_name=self._named)
                elements = [element for element in elements if element is not subtitle]
        if layout != "content":
            written = {"layout": layout, **written}
        self._shapes_only = layout == "title"
        items: list[_Item] = []
        for decoration in slide.decorations:
            items.extend(self.items(decoration, behind=True))
        for element in elements:
            items.extend(self.items(element))
        self._behind(items)
        body = [item.block for item in items if item.block is not None]
        shapes = [item.shape for item in items if item.shape is not None]
        self._glue(items, body)
        background = self.background(slide.background)
        if isinstance(background, dict):
            shapes.insert(0, background)
        elif background:
            written["background"] = background
        if body:
            written["body"] = body
        if shapes:
            written["shapes"] = shapes
        if slide.notes.strip():
            written["notes"] = slide.notes.strip()
        if slide.skip:
            written["skip"] = True
        return written

    def _title(self, slide: Slide, elements: list[Element]) -> tuple[str, TextBox | None, TextBox] | None:
        """The slide's title, where it is drawn as the deck's titles are: its words, its
        subtitle and the text box it was. ``None``: it has none, or one standing elsewhere
        (placed as any words are)."""

        titles = [element for element in elements if isinstance(element, TextBox) and element.role == "title"
                  and not element.frame.empty]
        if not titles:
            return None
        title = titles[0]
        frame = title.frame
        if any(paragraph.display or paragraph.bullet for paragraph in frame.paragraphs) or title.box.rotate % 360:
            return None
        if title.fill is not None or title.stroke is not None:
            return None
        words = self._title_words(frame)
        if slide.layout == "title":
            # (A title slide is set as it was: Flexo's own opening slide draws its own marks.)
            return None
        # Where the deck's look draws a title: its corner at the margin. Is this one there?
        left = (title.box.x + frame.insets[0]) * self.k
        top = self._words_top(title) * self.k
        size = (_size_of(frame.paragraphs[0]) or self.title_size / self.k) * frame.scale * self.k
        if abs(top - self.margin) > TITLE_REACH:
            return None
        if self.title_align == "middle":
            # Centred: across the slide, as the deck's look centres titles.
            width = self.presentation.width
            if abs(title.box.centre[0] - width / 2) > width * 0.05 or _align(frame) != "middle":
                return None
        elif abs(left - self.margin) > TITLE_REACH or _align(frame) not in ("start", None):
            return None
        if abs(size - self.title_size) > max(4.0, self.title_size * 0.2):
            return None
        return words, None, title

    def _title_words(self, frame: Frame) -> str:
        """A title's words as markup: its colour on them where it is not the theme's ink, and
        no bold of its own where the deck's titles are bold."""

        runs = [run for paragraph in frame.paragraphs for run in paragraph.runs if run.text.strip()]
        bold = self.presentation.title_style.get("bold")
        if bold:
            runs_all = [Run(**{**run.__dict__, "bold": None if run.bold else run.bold}) for run in
                        (r for paragraph in frame.paragraphs for r in paragraph.runs)]
            joined = _joined(Frame([Paragraph(runs=runs_all)]))
        else:
            joined = _joined(frame)
        colours = Counter(self.colour(run.colour, words=True) for run in runs if run.colour is not None)
        colour = colours.most_common(1)[0][0] if colours else None
        words = marks.paragraph_markup(joined, base_colour=colour, colour_name=self._named)
        if colour and "\n" not in words:
            words = f"[{words}]{{{colour}}}"
        return words

    def _words_top(self, box: TextBox) -> float:
        """Where a text box's words start, in the source's points: its top inset in, and down
        it as far as it sets them (by an estimate of their height)."""

        frame = box.frame
        top = box.box.y + frame.insets[1]
        room = box.box.h - frame.insets[1] - frame.insets[3]
        if frame.anchor == "top" or room <= 0:
            return top
        tall = _estimate(frame, max(box.box.w - frame.insets[0] - frame.insets[2], 10.0))
        spare = max(room - tall, 0.0)
        return top + (spare / 2 if frame.anchor == "middle" else spare)

    def _behind(self, items: list[_Item]) -> None:
        """Shapes under an object drawn over them in the source are drawn behind the slide's
        objects (a panel under words, a band under a picture): Flexo draws its objects under
        its shapes, and those behind under its objects."""

        for index, item in enumerate(items):
            if item.shape is None or item.box is None or item.shape.get("behind"):
                continue
            if any(later.block is not None and later.box is not None and _overlap(item.box, later.box)
                   for later in items[index + 1 :]):
                item.shape["behind"] = True

    def _glue(self, items: list[_Item], body: list[dict]) -> None:
        """Each line glued to the shape or object its source line was glued to, where its end
        is at one of that one's sides (else left where it is)."""

        targets: dict[str, tuple[dict[str, Any], Box]] = {}
        for item in items:
            if not item.ident or item.box is None:
                continue
            if item.block is not None:
                index = next(at for at, block in enumerate(body) if block is item.block)
                targets[item.ident] = ({"object": f"body[{index}]"}, item.box)
            elif item.shape is not None and item.shape.get("id"):
                targets[item.ident] = ({"shape": item.shape["id"]}, item.box)

        def walk(specs: list) -> list:
            found = []
            for spec in specs:
                found.append(spec)
                if spec.get("kind") == "group":
                    found.extend(walk(spec.get("shapes") or []))
            return found

        every = walk([item.shape for item in items if item.shape is not None])
        for spec in every:
            for ident, box in spec.pop("_members", []):
                if spec.get("id") and ident not in targets:
                    targets[ident] = ({"shape": spec["id"]}, box)
        for spec in every:
            glue = spec.pop("_glue", None)
            if not glue or spec.get("kind") not in ("line", "arrow", "double-arrow", "elbow"):
                continue
            for key, ident in zip(("from", "to"), glue, strict=True):
                if ident is None or ident not in targets:
                    continue
                target, box = targets[ident]
                side = self._side(spec[key], box)
                if side is not None:
                    spec[key] = {**target, "side": side, "at": spec[key]}

    def _side(self, end: list[float], box: Box) -> str | None:
        x, y, w, h = (value * self.across for value in (box.x, box.y, box.w, box.h))
        if box.rotate % 360:
            return None
        middles = {"top": (x + w / 2, y), "right": (x + w, y + h / 2), "bottom": (x + w / 2, y + h),
                   "left": (x, y + h / 2)}
        side, point = min(middles.items(), key=lambda pair: math.dist(pair[1], end))
        return side if math.dist(point, end) <= GLUE_REACH else None

    # -- a slide's objects ---------------------------------------------------------------

    def items(self, element: Element, *, behind: bool = False) -> list[_Item]:
        """An element as the slide's objects and shapes, in the order they are drawn."""

        try:
            made = self._items(element)
        except Exception as error:  # never fails: kept as its place, and said
            made = [self.placeholder(element, type(element).__name__, f"could not be brought across ({error})")]
        if behind:
            for item in made:
                if item.shape is not None:
                    item.shape["behind"] = True
                    item.shape["locked"] = True
        if self._shapes_only:
            made = [_Item(shape=self._as_shape(item.block, item.box), box=item.box, ident=item.ident)
                    if item.block is not None else item for item in made]
        return made

    def _items(self, element: Element) -> list[_Item]:
        if isinstance(element, TextBox):
            if element.role in ("number", "date", "footer"):
                return []
            if element.frame.empty and element.fill is None and element.stroke is None:
                return []
            if element.box.rotate % 360 or element.frame.vertical:
                return [self.shape_item(element, self.text_shape(element))]
            if element.fill is not None or element.stroke is not None:
                # Words on a panel: the panel a shape, under them; the words the slide's own.
                panel = self.text_shape(TextBox(element.box, frame=Frame([]), fill=element.fill,
                                                stroke=element.stroke, name=element.name))
                words = self.text_items(element)
                return [_Item(shape=panel, box=element.box), *words] if words else [
                    self.shape_item(element, panel)]
            return self.text_items(element)
        if isinstance(element, Picture):
            return self.picture_items(element)
        if isinstance(element, Shape):
            spec = self.shape(element)
            if isinstance(spec, _Item):
                return [spec]
            return [self.shape_item(element, spec)] if spec is not None else []
        if isinstance(element, Connector):
            spec = self.connector(element)
            return [self.shape_item(element, spec)] if spec is not None else []
        if isinstance(element, Table):
            return [self.table_item(element)]
        if isinstance(element, Equation):
            return [self.equation_item(element)]
        if isinstance(element, Group):
            return self.group_items(element)
        if isinstance(element, Unknown):
            return [self.unknown_item(element)]
        return [self.placeholder(element, type(element).__name__, "not understood")]

    def shape_item(self, element: Element, spec: dict[str, Any]) -> _Item:
        self.report.made["shapes"] += 1
        if element.ident and spec.get("kind") != "group":
            self._shape_id(spec, element)
        return _Item(shape=spec, box=element.box, ident=element.ident)

    def _shape_id(self, spec: dict[str, Any], element: Element) -> str:
        """A name of its own on its slide for a shape a line may be glued to."""

        if "id" not in spec:
            base = _safe_id(element.name or str(spec.get("kind", "shape")))[:24] or "shape"
            candidate, count = base, 1
            while candidate in self._ids:
                count += 1
                candidate = f"{base}-{count}"
            self._ids[candidate] += 1
            spec["id"] = candidate
        return str(spec["id"])

    def at(self, x: float, y: float) -> list[float]:
        return [_round(x * self.across, 1), _round(y * self.across, 1)]

    # -- words -----------------------------------------------------------------------------

    def text_items(self, box: TextBox) -> list[_Item]:
        """A text box as the slide's objects: its words, a list, an equation -- one, or several
        set one under another where its paragraphs differ (a heading over a list)."""

        frame = box.frame
        paragraphs = _trimmed(frame.paragraphs)
        if not paragraphs:
            return []
        left, top, right, bottom = frame.insets
        across = max(box.box.w - left - right, 4.0)
        x, y = box.box.x + left, box.box.y + top
        room = max(box.box.h - top - bottom, 0.0)
        width = across
        if not frame.wrap:
            # Words a slide program set on one line, however long: as much room as the slide
            # has beside them, for them to stay on one line where they stand.
            align, slide = _align(frame), self.presentation.width
            if align == "middle":
                half = max(min(x + across / 2, slide - x - across / 2), across / 2)
                x, width = x + across / 2 - half, 2 * half
            elif align == "end":
                width = max(x + across, across)
                x = x + across - width
            else:
                width = max(slide - x, across)
        blocks, gaps = [], []
        segments = _segments(paragraphs)
        previous: list[Paragraph] | None = None
        for segment in segments:
            block = self.words_block(segment, frame)
            if block is None:
                continue
            if previous is not None:
                gaps.append((segment[0].space_before + previous[-1].space_after) * frame.scale * self.k)
            previous = segment
            block["at"] = self.at(x, y)
            block["width"] = _round(width * self.across, 1)
            blocks.append(block)
        if not blocks:
            return []
        self.report.made["lists" if any("bullets" in block for block in blocks) else "words"] += 1
        if len(blocks) > 1 or frame.anchor != "top":
            spare = max(room - _estimate(Frame(paragraphs, scale=frame.scale), across), 0.0)
            shift = spare / 2 if frame.anchor == "middle" else spare if frame.anchor == "bottom" else 0.0
            blocks[0]["at"] = self.at(x, y + shift)
            self.stacks.append(_Stack(self._index, blocks, y * self.k, room * self.k, frame.anchor, gaps))
        items = [_Item(block=block, box=box.box) for block in blocks]
        items[0].ident = box.ident
        return items

    def words_block(self, paragraphs: list[Paragraph], frame: Frame) -> dict[str, Any] | None:
        """Paragraphs of one kind as one object: a list, words, or an equation."""

        colour = self._dominant_colour(paragraphs)
        if len(paragraphs) == 1 and paragraphs[0].display:
            paragraph = paragraphs[0]
            block: dict[str, Any] = {"math": " ".join(paragraph.display.split())}
            size = _size_of(paragraph)
            if size:
                block["size"] = self._size(size * frame.scale)
            if paragraph.align in ("start", "end"):
                block["align"] = paragraph.align
            if colour:
                block["colour"] = colour
            self.report.made["equations"] += 1
            return block
        size = _dominant_size(paragraphs)
        options = {"base_colour": colour, "colour_name": self._named, "number": self._slide.number}
        listed = any(paragraph.bullet or paragraph.level for paragraph in paragraphs)
        if listed:
            items = _nested([(paragraph.level, marks.paragraph_markup(paragraph, **options))
                             for paragraph in paragraphs if paragraph.words.strip() or paragraph.display])
            block = {"bullets": items}
            if any(paragraph.bullet == "number" for paragraph in paragraphs) and all(
                paragraph.bullet == "number" for paragraph in paragraphs if paragraph.level == 0 and paragraph.bullet
            ):
                block["numbered"] = True
            if not any(paragraph.bullet for paragraph in paragraphs):
                block["plain"] = True
        else:
            words = "\n".join(marks.paragraph_markup(paragraph, **options) for paragraph in paragraphs)
            if not words.strip():
                return None
            block = {"text": words}
            align = _align(Frame(paragraphs))
            if align in ("middle", "end"):
                block["align"] = align
        if size:
            block["size"] = self._size(size * frame.scale)
        if colour:
            block["colour"] = colour
        return block

    def _size(self, size: float) -> float | int:
        return _round(min(max(size * self.k, 4.0), 400.0), 1)

    def _dominant_colour(self, paragraphs: list[Paragraph]) -> str | None:
        counted: Counter = Counter()
        for paragraph in paragraphs:
            for run in paragraph.runs:
                if run.text.strip() or run.tex:
                    named = self.colour(run.colour, words=True) if run.colour is not None else None
                    counted[named] += len(run.text or "x")
        if not counted:
            return None
        return counted.most_common(1)[0][0]

    def text_shape(self, box: TextBox) -> dict[str, Any]:
        """A text box as a shape: a box (filled, outlined or neither) with its words in it,
        turned as it was -- words in a group, turned, or on a coloured panel."""

        spec: dict[str, Any] = {"kind": "rectangle", "at": self.at(box.box.x, box.box.y),
                                "size": [_round(max(box.box.w, 1.0) * self.across),
                                         _round(max(box.box.h, 1.0) * self.across)]}
        self._turned(spec, box.box)
        self._filled(spec, box.fill if not isinstance(box.fill, Media) else None)
        self._stroked(spec, box.stroke, closed=True)
        self._words_in(spec, box.frame)
        return spec

    def _words_in(self, spec: dict[str, Any], frame: Frame | None) -> None:
        """A frame's words set in a shape, in its look."""

        if frame is None or frame.empty:
            return
        paragraphs = _trimmed(frame.paragraphs)
        runs = [run for paragraph in paragraphs for run in paragraph.runs if run.text.strip()]
        bold = bool(runs) and all(run.bold for run in runs)
        italic = bool(runs) and all(run.italic for run in runs)
        colour = self._dominant_colour(paragraphs)
        options = {"base_bold": bold, "base_italic": italic, "base_colour": colour, "colour_name": self._named,
                   "number": self._slide.number}
        lines = []
        for paragraph in paragraphs:
            words = marks.paragraph_markup(paragraph, **options)
            if paragraph.bullet:
                words = "\u2003" * paragraph.level + ("\u2022 " if paragraph.bullet == "bullet" else "") + words
            lines.append(words)
        spec["text"] = "\n".join(lines)
        size = _dominant_size(paragraphs)
        if size:
            spec["font_size"] = _round(min(max(size * frame.scale * self.across, 4.0), 400.0), 1)
        if bold:
            spec["bold"] = True
        if italic:
            spec["italic"] = True
        if colour:
            spec["colour"] = colour
        fonts = Counter(run.font for run in runs if run.font)
        if fonts:
            family = self.family(fonts.most_common(1)[0][0])
            if family and family != self.font:
                spec["font"] = family
        spec["align"] = _align(frame) or "start"
        spec["valign"] = frame.anchor
        padding = (frame.insets[0] + frame.insets[2]) / 2
        spec["padding"] = _round(min(max(padding * self.across, 0.0), 50.0), 1)

    # -- pictures -------------------------------------------------------------------------

    def picture_items(self, picture: Picture) -> list[_Item]:
        source = self.picture_file(picture.media)
        if source is None:
            return [self.placeholder(picture, _kind_of(picture.media), "a kind of picture Flexo cannot show")]
        box = picture.box
        if box.w <= 0.5 or box.h <= 0.5:
            return []
        if box.rotate % 360 or box.flip_h or box.flip_v or self._stretched(picture, source):
            self.report.made["pictures"] += 1
            spec = self.picture_shape(picture)
            if picture.ident:
                self._shape_id(spec, picture)
            return [_Item(shape=spec, box=box, ident=picture.ident)]
        block: dict[str, Any] = {"image": source}
        if source.lower().endswith(".svg"):
            block["font"] = "drawn"  # (its words in its own faces, as it was drawn)
        crop = _crop(picture.crop)
        if crop is not None:
            block["crop"] = crop
        if picture.mask == "circle":
            block["mask"] = "circle"
        if picture.description.strip():
            block["description"] = " ".join(picture.description.split())[:300]
        block["at"] = self.at(box.x, box.y)
        block["width"] = _round(box.w * self.across, 1)
        if picture.opacity < 0.75:
            block["dim"] = True
        self.report.made["pictures"] += 1
        return [_Item(block=block, box=box, ident=picture.ident)]

    def _stretched(self, picture: Picture, source: str) -> bool:
        """Whether a photograph is drawn out of its own proportions (a slide program stretches
        what it crops to its box; an object of Flexo's keeps its picture's proportions)."""

        if Path(source).suffix.lower() not in (".png", ".jpg", ".jpeg"):
            return False
        try:
            from PIL import Image

            with Image.open(self.folder / source) as image:
                w, h = image.size
        except Exception:
            return False
        left, top, right, bottom = (min(max(value, 0.0), 1.0) for value in picture.crop)
        kept_w, kept_h = w * max(1 - left - right, 0.01), h * max(1 - top - bottom, 0.01)
        box = picture.box
        if box.h <= 0 or kept_h <= 0:
            return False
        return abs((kept_w / kept_h) / (box.w / box.h) - 1.0) > 0.03

    def picture_shape(self, picture: Picture) -> dict[str, Any]:
        source = self.cropped_file(picture)
        box = picture.box
        spec: dict[str, Any] = {"kind": "picture", "at": self.at(box.x, box.y),
                                "size": [_round(box.w * self.across), _round(box.h * self.across)], "source": source}
        self._turned(spec, box)
        if picture.opacity < 1.0:
            spec["opacity"] = _round(picture.opacity, 2)
        return spec

    # -- shapes -----------------------------------------------------------------------------

    def _turned(self, spec: dict[str, Any], box: Box) -> None:
        turn = box.rotate % 360
        if turn:
            spec["rotate"] = _round(turn, 2)
        if box.flip_h or box.flip_v:
            spec["flip"] = "both" if box.flip_h and box.flip_v else "horizontal" if box.flip_h else "vertical"

    def _stroked(self, spec: dict[str, Any], stroke: Stroke | None, *, closed: bool) -> None:
        if stroke is None or stroke.colour is None or stroke.width <= 0 or stroke.colour.alpha <= 0.001:
            spec["line"] = "none"
            if not closed:
                spec["end"] = "none"
            return
        spec["line"] = self.colour(stroke.colour) or _hex6(stroke.colour.hex)
        spec["line_width"] = _round(min(max(stroke.width * self.across, 0.1), 50.0), 2)
        if stroke.colour.alpha < 0.999:
            spec["line_opacity"] = _round(max(stroke.colour.alpha, 0.0), 2)
        if stroke.dash != "solid":
            spec["dash"] = stroke.dash if isinstance(stroke.dash, str) else [
                _round(max(value * self.across, 0.1), 2) for value in stroke.dash]
        if not closed or stroke.head != "none" or stroke.tail != "none":
            spec["start"] = stroke.head
            spec["end"] = stroke.tail
            if abs(stroke.head_size - 1.0) > 0.05:
                spec["head_size"] = _round(min(max(stroke.head_size, 0.25), 4.0), 2)
        if stroke.cap:
            spec["cap"] = stroke.cap
        if stroke.join:
            spec["join"] = stroke.join

    def _filled(self, spec: dict[str, Any], fill: object) -> None:
        if fill is None or isinstance(fill, Media):
            spec["fill"] = "none"
            return
        spec["fill"] = self.paint(fill)
        if isinstance(fill, Colour) and fill.alpha < 0.999:
            spec["fill_opacity"] = _round(max(fill.alpha, 0.0), 2)

    def shape(self, shape: Shape) -> dict[str, Any] | _Item | None:
        box = shape.box
        if isinstance(shape.fill, Media) and shape.kind in ("rectangle", "ellipse") and (
                shape.frame is None or shape.frame.empty):
            # A shape filled with a picture: the picture, in that shape.
            picture = Picture(box, shape.name, shape.ident, media=shape.fill,
                              mask="circle" if shape.kind == "ellipse" else None)
            items = self.picture_items(picture)
            return items[0] if items else None
        if shape.kind == "path":
            if not shape.path:
                return None
            spec: dict[str, Any] = {"kind": "path", "d": _placed_path(shape.path, box, self.across)}
            if not shape.closed:
                spec["fill"] = "none"
            else:
                self._filled(spec, shape.fill)
        else:
            spec = {"kind": shape.kind, "at": self.at(box.x, box.y),
                    "size": [_round(max(box.w, 0.5) * self.across), _round(max(box.h, 0.5) * self.across)]}
            for key, value in shape.parameters.items():
                spec[key] = _scaled_parameter(key, value, self.across)
            self._turned(spec, box)
            self._filled(spec, shape.fill)
        if isinstance(shape.fill, Media):
            self.report.note("A shape filled with a picture other than a rectangle or an oval is drawn empty.")
        self._stroked(spec, shape.stroke, closed=shape.closed)
        if spec.get("fill") == "none" and spec.get("line") == "none" and (shape.frame is None or shape.frame.empty):
            return None
        if shape.opacity < 0.999:
            spec["opacity"] = _round(shape.opacity, 2)
        if shape.shadow:
            spec["shadow"] = True
        self._words_in(spec, shape.frame)
        return spec

    def connector(self, line: Connector) -> dict[str, Any] | None:
        stroke = line.stroke
        if stroke is None or stroke.colour is None:
            return None
        a, b = line.start, line.end
        if line.route == "path" and line.path:
            spec: dict[str, Any] = {"kind": "path", "d": _scaled_path(line.path, self.across), "fill": "none"}
        elif line.route == "elbow" and line.points:
            spec = self._elbow(line)
        elif line.route == "curved" and line.points:
            spec = {"kind": "path", "d": _curve([a, *line.points, b], self.across), "fill": "none"}
        else:
            if math.dist(a, b) < 0.25:
                return None
            spec = {"kind": "line", "from": self.at(*a), "to": self.at(*b)}
        self._stroked(spec, stroke, closed=False)
        if spec["kind"] == "line":
            heads = (spec.get("start", "none") != "none", spec.get("end", "none") != "none")
            spec["kind"] = {(True, True): "double-arrow", (False, True): "arrow"}.get(heads, "line")
        self._words_in(spec, line.frame)
        if line.start_glue or line.end_glue:
            spec["_glue"] = (line.start_glue, line.end_glue)
        return spec

    def _elbow(self, line: Connector) -> dict[str, Any]:
        """An elbow connector as Flexo's elbow where it turns as one does (across, down, across;
        or down, across, down), else a line through its corners."""

        a, b = line.start, line.end
        points = [a, *line.points, b]
        if len(points) == 4:
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
            across = abs(y1 - y0) < 0.5 and abs(x2 - x1) < 0.5 and abs(y3 - y2) < 0.5
            down = abs(x1 - x0) < 0.5 and abs(y2 - y1) < 0.5 and abs(x3 - x2) < 0.5
            if across and abs(x3 - x0) > 0.5 and 0.0 <= (x1 - x0) / (x3 - x0) <= 1.0:
                return {"kind": "elbow", "from": self.at(*a), "to": self.at(*b),
                        "elbow": _round((x1 - x0) / (x3 - x0), 3), "route": "across"}
            if down and abs(y3 - y0) > 0.5 and 0.0 <= (y1 - y0) / (y3 - y0) <= 1.0:
                return {"kind": "elbow", "from": self.at(*a), "to": self.at(*b),
                        "elbow": _round((y1 - y0) / (y3 - y0), 3), "route": "down"}
        return {"kind": "polyline", "points": [self.at(*point) for point in points]}

    # -- tables, equations, groups ----------------------------------------------------------

    def table_item(self, table: Table) -> _Item:
        rows = []
        sizes: list[float] = []
        aligns: list[Counter] = []
        for number, row in enumerate(table.rows):
            # (A header is set bold by the table: its own bold is its look already.)
            heading = number == 0 and table.header
            cells = []
            for column, cell in enumerate(row):
                if cell.merged:
                    cells.append("")
                    continue
                frame = cell.frame
                paragraphs = [paragraph for paragraph in frame.paragraphs
                              if paragraph.words.strip() or paragraph.display]
                # (A table is drawn on the page, its cells' own colours left out: words light on
                # a dark cell are the words' own colour there.)
                naming = self._named if cell.fill is None else self._readable
                words = " ".join(marks.paragraph_markup(paragraph, colour_name=naming, number=self._slide.number,
                                                        base_bold=heading)
                                 for paragraph in paragraphs)
                cells.append(words.replace("\n", " "))
                size = _dominant_size(paragraphs)
                if size:
                    sizes.append(size * frame.scale)
                while len(aligns) <= column:
                    aligns.append(Counter())
                aligns[column][_align(frame) or "start"] += 1
            rows.append(cells)
        if not rows or not any(any(cell.strip() for cell in row) for row in rows):
            return self.placeholder(table, "Table", "empty")
        count = max(len(row) for row in rows)
        rows = [row + [""] * (count - len(row)) for row in rows]
        block: dict[str, Any] = {"table": rows}
        if not table.header:
            block["header"] = False
        if not table.ruled:
            block["outline"] = False
        columns = [counter.most_common(1)[0][0] if counter else "start" for counter in aligns][:count]
        if any(align != "start" for align in columns):
            block["align"] = [{"middle": "middle", "end": "end"}.get(align, "start") for align in columns]
        if sizes:
            block["size"] = self._size(sorted(sizes)[len(sizes) // 2])
        block["at"] = self.at(table.box.x, table.box.y)
        block["width"] = _round(table.box.w * self.across, 1)
        self.report.made["tables"] += 1
        if any(cell.fill is not None for row in table.rows for cell in row):
            self.report.note("Tables are ruled as Flexo rules them: their cells' own colours are not kept.")
        return _Item(block=block, box=table.box, ident=table.ident)

    def equation_item(self, equation: Equation) -> _Item:
        if not equation.tex.strip():
            return self.placeholder(equation, "Equation", "empty")
        block: dict[str, Any] = {"math": " ".join(equation.tex.split())}
        if equation.size:
            block["size"] = self._size(equation.size)
        colour = self.colour(equation.colour, words=True)
        if colour:
            block["colour"] = colour
        block["align"] = "start"
        block["at"] = self.at(equation.box.x, equation.box.y)
        block["width"] = _round(max(equation.box.w, 10.0) * self.across, 1)
        self.report.made["equations"] += 1
        return _Item(block=block, box=equation.box, ident=equation.ident)

    def group_items(self, group: Group) -> list[_Item]:
        """A group as one of Flexo's groups of shapes, its words and pictures shapes in it --
        or, holding what only a slide's object can be (a table, an equation), its members
        each placed as the slide's own. One of very many shapes is a picture of them."""

        members = _flattened(group)
        if not members:
            return []
        if any(isinstance(member, Table | Equation) for member in members) or any(
            isinstance(member, TextBox) and any(paragraph.display for paragraph in member.frame.paragraphs)
            for member in members
        ):
            items: list[_Item] = []
            for child in group.children:
                items.extend(self.items(child))
            return items
        if len(members) > self.heavy:
            item = self.drawing_item(group)
            if item is not None:
                return [item]
        known: list[tuple[str, Box]] = []
        shapes = [spec for spec in (self.member(child, known) for child in group.children) if spec is not None]
        if not shapes:
            return []
        if len(shapes) == 1:
            spec = shapes[0]
        else:
            spec = {"kind": "group", "shapes": shapes}
            self.report.made["groups"] += 1
        if known:
            spec["_members"] = known
        return [_Item(shape=spec, box=group.box)]

    def member(self, element: Element, known: list[tuple[str, Box]]) -> dict[str, Any] | None:
        """One of a group's members as a shape (a group in it as a group of them); ``known``
        is told the source's id of each with an id of its own (what a line is glued to)."""

        if element.hidden:
            return None
        spec: dict[str, Any] | None
        try:
            if isinstance(element, Group):
                shapes = [one for one in (self.member(child, known) for child in element.children) if one is not None]
                if not shapes:
                    return None
                return shapes[0] if len(shapes) == 1 else {"kind": "group", "shapes": shapes}
            if isinstance(element, TextBox):
                if element.role in ("number", "date", "footer"):
                    return None
                if element.frame.empty and element.fill is None and element.stroke is None:
                    return None
                spec = self.text_shape(element)
                self.report.made["words"] += 1
            elif isinstance(element, Picture):
                if self.picture_file(element.media) is None:
                    self.report.placeholder(self._slide.number, _kind_of(element.media),
                                            "a kind of picture Flexo cannot show")
                    return None
                spec = self.picture_shape(element)
                self.report.made["pictures"] += 1
            elif isinstance(element, Shape):
                made = self.shape(element)
                if isinstance(made, _Item):
                    made = made.shape if made.shape is not None else self._as_shape(made.block, made.box)
                spec = made
                if spec is not None:
                    self.report.made["shapes"] += 1
            elif isinstance(element, Connector):
                spec = self.connector(element)
                if spec is not None:
                    self.report.made["shapes"] += 1
            elif isinstance(element, Unknown):
                item = self.unknown_item(element)
                spec = item.shape if item.shape is not None else self._as_shape(item.block, item.box)
            else:
                return None
        except Exception as error:
            self.report.placeholder(self._slide.number, type(element).__name__,
                                    f"could not be brought across ({error})")
            return None
        if spec is not None and element.ident and spec.get("kind") not in ("group", "picture"):
            self._shape_id(spec, element)
            known.append((element.ident, element.box))
        return spec

    def drawing_item(self, group: Group) -> _Item | None:
        """A group of very many shapes as one picture of them (an SVG drawn here), placed
        where it was: as a drawing pasted as a picture is, made shapes by a double-click."""

        box = group.box
        try:
            from flexo_talk.importing.drawing import drawn

            svg = drawn(group, self)
        except Exception as error:
            self.report.note(f"A group of {len(_flattened(group))} shapes could not be drawn as a picture ({error}).")
            return None
        if svg is None:
            return None
        name = _safe_name(group.name or "drawing")[:40] or "drawing"
        source = self.picture_file(Media(f"{Path(name).stem}.svg", svg.encode("utf-8")))
        if source is None:
            return None
        block = {"image": source, "font": "drawn", "at": self.at(box.x, box.y), "width": _round(box.w * self.across, 1)}
        self.report.made["drawings kept as pictures"] += 1
        return _Item(block=block, box=box)

    # -- what cannot be brought across -------------------------------------------------------

    def unknown_item(self, unknown: Unknown) -> _Item:
        picture = unknown.picture
        if picture is not None and self.picture_file(picture.media) is not None:
            items = self.picture_items(picture)
            if items:
                self.report.made["pictures"] -= 1
                self.report.placeholder(self._slide.number, unknown.kind, unknown.why, picture=True)
                return items[0]
        return self.placeholder(unknown, unknown.kind, unknown.why)

    def placeholder(self, element: Element, kind: str, why: str = "") -> _Item:
        """What could not be brought across, kept as its place: a dashed box saying what it
        was, marked TODO, hidden from the show and every export."""

        self.report.placeholder(self._slide.number, kind, why)
        box = element.box
        words = f"TODO {kind} from the original" + (f": {why}" if why else "")
        spec = {
            "kind": "rectangle", "at": self.at(box.x, box.y),
            "size": [_round(max(box.w, 20.0) * self.across), _round(max(box.h, 12.0) * self.across)],
            "fill": "none", "line": "muted", "line_width": 1, "dash": "dashed",
            "text": marks.escaped(words), "font_size": 12, "colour": "muted", "hide": True,
        }
        self._turned(spec, box)
        return _Item(shape=spec, box=box)

    # -- backgrounds ---------------------------------------------------------------------------

    def background(self, fill: object) -> str | dict | None:
        if isinstance(fill, Colour):
            colour = _hex6(fill.hex)
            return None if colour == self.paper else colour
        if isinstance(fill, Media):
            return self.picture_file(fill)
        if isinstance(fill, Gradient):
            return {"kind": "rectangle", "id": "background", "at": [0, 0],
                    "size": [SHAPE_FRAME, _round(self.presentation.height * self.across)],
                    "fill": self.paint(fill), "line": "none", "behind": True, "locked": True}
        return None

    def _as_shape(self, block: dict[str, Any] | None, box: Box | None) -> dict[str, Any] | None:
        """An object as a shape, for a slide that takes none (a title slide's)."""

        if block is None:
            return None
        at = block.get("at") or [0, 0]
        width = float(block.get("width") or 200)
        tall = (box.h * self.across) if box is not None else width * 0.75
        if "image" in block:
            return {"kind": "picture", "at": at, "size": [width, _round(tall)], "source": block["image"]}
        words = block.get("text") or ""
        if "bullets" in block:
            words = "\n".join("\u2022 " + str(item) for item in _flat(block["bullets"]))
        if "math" in block:
            words = f"$${block['math']}$$"
        if "table" in block:
            words = "\n".join("\u2003".join(row) for row in block["table"])
        spec: dict[str, Any] = {"kind": "text", "at": at, "width": width, "text": words}
        if block.get("size"):
            spec["font_size"] = _round(float(block["size"]) / self.k * self.across, 1)
        if block.get("colour"):
            spec["colour"] = block["colour"]
        if block.get("align"):
            spec["align"] = block["align"]
        return spec


# -- settling words where their slide program set them -------------------------------------------


def settle(document: dict[str, Any], writer: Writer, folder: Path, progress: Progress = quiet) -> None:
    """Each text box's blocks set in its box as its slide program set them -- its words in the
    middle or at the foot of their room, a list under the heading before it -- now that the
    height of each is known: the slides that have any are drawn, and their blocks measured."""

    if not writer.stacks:
        return
    from flexo_talk.compose import PLACEHOLDERS, render_slide
    from flexo_talk.document import deck_from_document

    try:
        deck = deck_from_document(document, base=folder, errors=[])
    except Exception:
        return
    by_slide: dict[int, list[_Stack]] = {}
    for stack in writer.stacks:
        by_slide.setdefault(stack.slide, []).append(stack)
    scale = writer.width / SHAPE_FRAME
    token = PLACEHOLDERS.set(True)
    try:
        for done, (index, stacks) in enumerate(sorted(by_slide.items())):
            progress(0.85 + 0.1 * done / len(by_slide), f"Setting the words of slide {index + 1}")
            slide_document = document["slides"][index]
            body = slide_document.get("body") or []
            try:
                rendered = render_slide(deck, deck.slides[index])
            except Exception:
                continue
            frames = _frames(rendered.svg, deck.slides[index].id)
            for stack in stacks:
                heights = []
                for block in stack.blocks:
                    at = next((position for position, one in enumerate(body) if one is block), None)
                    frame = frames.get(at) if at is not None else None
                    heights.append(frame[3] if frame else None)
                if any(height is None for height in heights):
                    continue
                total = sum(heights) + sum(stack.gaps)
                spare = max(stack.room - total, 0.0)
                top = stack.top + {"middle": spare / 2, "bottom": spare}.get(stack.anchor, 0.0)
                for position, block in enumerate(stack.blocks):
                    block["at"] = [block["at"][0], _round(top / scale, 1)]
                    top += heights[position] + (stack.gaps[position] if position < len(stack.gaps) else 0.0)
    finally:
        PLACEHOLDERS.reset(token)


def _frames(svg: str, slide_id: str) -> dict[int, tuple[float, float, float, float]]:
    """Where each of a slide's placed objects is drawn, by its place in the body: its frame."""

    import xml.etree.ElementTree as ET

    found = {}
    pattern = re.compile(rf"{re.escape(slide_id)}\.body\.(\d+)")
    for node in ET.fromstring(svg).iter():
        ident, frame = node.get("id") or "", node.get("data-flexo-frame")
        matched = pattern.fullmatch(ident)
        if matched and frame:
            values = [float(value) for value in frame.split()]
            if len(values) == 4:
                found[int(matched.group(1))] = (values[0], values[1], values[2], values[3])
    return found


# -- helpers -----------------------------------------------------------------------------------


def _page_colours(source: Presentation) -> tuple[str, str]:
    """The deck's ink and page: the colour most of its words are set in and most of its
    slides are on (else its theme's)."""

    theme = source.theme
    ink = (theme.colours.get("lt1" if theme.dark else "dk1") or ("#ffffff" if theme.dark else "#000000")).lower()
    paper = (theme.colours.get("dk1" if theme.dark else "lt1") or ("#000000" if theme.dark else "#ffffff")).lower()
    words: Counter = Counter()

    def count(elements: list[Element]) -> None:
        for element in elements:
            if isinstance(element, Group):
                count(element.children)
                continue
            frame = getattr(element, "frame", None)
            for paragraph in frame.paragraphs if frame is not None else []:
                for run in paragraph.runs:
                    if run.colour is not None and run.text.strip():
                        words[_hex6(run.colour.hex)] += len(run.text)

    pages: Counter = Counter()
    for slide in source.slides:
        count(slide.elements)
        # (A slide with no background of its own is on the theme's page.)
        pages[_hex6(slide.background.hex) if isinstance(slide.background, Colour) else paper] += 1
    if words:
        ink = words.most_common(1)[0][0]
    if pages:
        paper = pages.most_common(1)[0][0]
    return ink, paper


def _accents(source: Presentation) -> list[str]:
    """The deck's colours, in order: its lists' bullets' (where it colours them), then its
    theme's accents."""

    named = source.theme.colours
    colours = [named[f"accent{n}"].lower() for n in range(1, 7) if named.get(f"accent{n}")]
    if source.accent:
        colours.insert(0, source.accent.lower())
    return list(dict.fromkeys(colours))


def _safe_name(name: str) -> str:
    keep = "".join(character if character.isalnum() or character in "._-" else "-" for character in name)
    keep = re.sub(r"-{2,}", "-", keep).strip("-.")
    return keep or "picture"


def _safe_id(name: str) -> str:
    keep = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower()
    return keep or "deck"


def _as_png(data: bytes, ending: str) -> bytes | None:
    """A picture of a kind no slide shows, as a PNG; ``None`` where it cannot be read."""

    if ending in (".emf", ".wmf", ".emz", ".wmz"):
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.mode not in ("RGB", "RGBA", "L", "LA"):
                image = image.convert("RGBA")
            out = io.BytesIO()
            image.save(out, "PNG")
            return out.getvalue()
    except Exception:
        pass
    if ending in (".heic", ".heif", ".tif", ".tiff"):
        return _by_sips(data, ending)
    return None


def _by_sips(data: bytes, ending: str) -> bytes | None:
    """A photograph Pillow cannot read (an iPhone's HEIC) made a PNG by the Mac's own ``sips``."""

    import shutil
    import subprocess
    import sys
    import tempfile

    sips = shutil.which("sips") if sys.platform == "darwin" else None
    if sips is None:
        return None
    with tempfile.TemporaryDirectory(prefix="flexo-import-") as aside:
        source, target = Path(aside) / f"photo{ending}", Path(aside) / "photo.png"
        source.write_bytes(data)
        try:
            subprocess.run([sips, "-s", "format", "png", str(source), "--out", str(target)],
                           check=True, capture_output=True, timeout=60)
            return target.read_bytes()
        except (OSError, subprocess.SubprocessError):
            return None


def _kind_of(media: Media | None) -> str:
    ending = Path(media.name).suffix.lower().lstrip(".") if media is not None else ""
    if ending in ("emf", "wmf", "emz", "wmz"):
        return "Windows metafile picture"
    return f"{ending.upper()} picture" if ending else "Picture"


def _crop(crop: tuple[float, float, float, float]) -> list[float] | None:
    left, top, right, bottom = (min(max(value, 0.0), 1.0) for value in crop)
    width, height = 1.0 - left - right, 1.0 - top - bottom
    if width < 0.01 or height < 0.01 or max(left, top, right, bottom) < 0.001:
        return None
    return [_round(left, 4), _round(top, 4), _round(width, 4), _round(height, 4)]


def _overlap(one: Box, other: Box) -> bool:
    return (one.x < other.x + other.w and other.x < one.x + one.w
            and one.y < other.y + other.h and other.y < one.y + one.h)


def _size_of(paragraph: Paragraph) -> float | None:
    sizes: Counter = Counter()
    for run in paragraph.runs:
        if run.size and (run.text.strip() or run.tex) and not run.baseline:
            sizes[run.size] += len(run.text or "x")
    if sizes:
        return sizes.most_common(1)[0][0]
    return paragraph.size


def _dominant_size(paragraphs: list[Paragraph]) -> float | None:
    sizes: Counter = Counter()
    for paragraph in paragraphs:
        for run in paragraph.runs:
            if run.size and (run.text.strip() or run.tex) and not run.baseline:
                sizes[run.size] += len(run.text or "x")
    if not sizes:
        return next((paragraph.size for paragraph in paragraphs if paragraph.size), None)
    return sizes.most_common(1)[0][0]


def _align(frame: Frame) -> str | None:
    for paragraph in frame.paragraphs:
        if paragraph.words.strip() or paragraph.display:
            return {"justify": "start"}.get(paragraph.align or "start", paragraph.align)
    return None


def _trimmed(paragraphs: list[Paragraph]) -> list[Paragraph]:
    """Paragraphs without the empty ones before and after the words."""

    kept = list(paragraphs)
    while kept and not kept[-1].words.strip() and not kept[-1].display:
        kept.pop()
    while kept and not kept[0].words.strip() and not kept[0].display:
        kept.pop(0)
    return kept


def _joined(frame: Frame) -> Paragraph:
    """A frame's paragraphs as one, its paragraphs its lines (a title of two lines)."""

    runs: list[Run] = []
    for paragraph in frame.paragraphs:
        if not paragraph.words.strip():
            continue
        if runs:
            runs.append(Run("\n"))
        runs.extend(paragraph.runs)
    return Paragraph(runs=runs)


def _segments(paragraphs: list[Paragraph]) -> list[list[Paragraph]]:
    """Paragraphs in runs of one kind -- words, a list, an equation -- at much one size."""

    segments: list[list[Paragraph]] = []

    def kind(paragraph: Paragraph) -> str:
        if paragraph.display:
            return "math"
        return "list" if paragraph.bullet or paragraph.level else "words"

    for paragraph in paragraphs:
        if not paragraph.words.strip() and not paragraph.display:
            if segments:
                segments[-1].append(paragraph)
            continue
        if segments:
            last = segments[-1]
            last_size = _dominant_size(last) or 0.0
            size = _size_of(paragraph) or last_size
            same_size = not last_size or abs(size - last_size) <= max(1.5, 0.15 * last_size)
            if kind(paragraph) == kind(last[0]) != "math" and same_size:
                last.append(paragraph)
                continue
        segments.append([paragraph])
    return [_trimmed(segment) for segment in segments]


def _nested(items: list[tuple[int, str]]) -> list:
    """Items with their levels as Flexo's nested lists: a list under the item before it (an
    empty item standing for one a deeper item has none of)."""

    if not items:
        return []
    lowest = min(level for level, _ in items)
    root: list = []
    opened: list[tuple[int, list]] = [(lowest, root)]
    for level, words in items:
        level = max(level, lowest)
        while level < opened[-1][0]:
            opened.pop()
        while level > opened[-1][0]:
            holder = opened[-1][1]
            if not holder or isinstance(holder[-1], list):
                holder.append("")
            child: list = []
            holder.append(child)
            opened.append((opened[-1][0] + 1, child))
        opened[-1][1].append(words)
    return root


def _flat(items: list) -> list[str]:
    out = []
    for item in items:
        if isinstance(item, list):
            out.extend(_flat(item))
        else:
            out.append(str(item))
    return out


def _flattened(group: Group) -> list[Element]:
    out: list[Element] = []
    for child in group.children:
        if isinstance(child, Group):
            out.extend(_flattened(child))
        else:
            out.append(child)
    return out


def _estimate(frame: Frame, width: float) -> float:
    """About how tall a frame's words are, in the source's points, as a slide program sets
    them: each paragraph's lines (its characters half their size wide) at its spacing."""

    total = 0.0
    for paragraph in frame.paragraphs:
        size = (_size_of(paragraph) or 18.0) * frame.scale
        if paragraph.display:
            total += size * 2.0
            continue
        indent = 27.0 * (paragraph.level + (1 if paragraph.bullet else 0))
        across = max(width - indent, size)
        text = "".join(run.text for run in paragraph.runs) or " "
        lines = sum(max(1, math.ceil(len(part) * size * 0.5 / across)) for part in text.split("\n"))
        spacing = paragraph.line_points / size if paragraph.line_points else 1.2 * (paragraph.line_spacing or 1.0)
        total += lines * size * spacing + (paragraph.space_before + paragraph.space_after) * frame.scale
    return total


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _scaled_path(data: str, factor: float) -> str:
    """Path data with every number scaled (from slide points to shape units)."""

    return _NUMBER.sub(lambda found: _n(float(found.group()) * factor), data)


def _placed_path(data: str, box: Box, factor: float) -> str:
    """A shape's outline (in its box's units) where it stands on the slide, mirrored and
    turned as its box is, in shape units."""

    from flexo import pathdata

    read = pathdata.parsed(data)
    cx, cy = box.w / 2.0, box.h / 2.0
    turn = math.radians(box.rotate % 360)
    cos, sin = math.cos(turn), math.sin(turn)

    def moved(x: float, y: float) -> tuple[float, float]:
        if box.flip_h:
            x = box.w - x
        if box.flip_v:
            y = box.h - y
        dx, dy = x - cx, y - cy
        x, y = cx + dx * cos - dy * sin, cy + dx * sin + dy * cos
        return (box.x + x) * factor, (box.y + y) * factor

    out = []
    for segment in read.segments:
        letter, values = segment[0], segment[1:]
        points = [moved(values[i], values[i + 1]) for i in range(0, len(values), 2)]
        out.append(f"{letter} " + " ".join(f"{_n(x)} {_n(y)}" for x, y in points) if points else letter)
    return " ".join(out)


def _curve(points: list[tuple[float, float]], factor: float) -> str:
    """A curved connector's route: a cubic through its controls, as a slide program draws it."""

    scaled = [(x * factor, y * factor) for x, y in points]
    if len(scaled) == 4:
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = scaled
        return f"M {_n(x0)} {_n(y0)} C {_n(x1)} {_n(y1)} {_n(x2)} {_n(y2)} {_n(x3)} {_n(y3)}"
    if len(scaled) == 3:
        (x0, y0), (x1, y1), (x2, y2) = scaled
        return f"M {_n(x0)} {_n(y0)} Q {_n(x1)} {_n(y1)} {_n(x2)} {_n(y2)}"
    return "M " + " L ".join(f"{_n(x)} {_n(y)}" for x, y in scaled)


_SCALED = {"corner", "depth"}
"""A shape's settings measured in points (scaled with it), not as shares of it."""


_SHARES = {"shaft", "head", "point", "slant", "inset", "apex", "arm", "ratio"}
"""A shape's settings that are shares of it, from 0 to 1."""


def _scaled_parameter(key: str, value: object, factor: float) -> object:
    if key in _SHARES and isinstance(value, int | float):
        return _round(min(max(float(value), 0.0), 1.0), 3)
    if key in _SCALED and isinstance(value, int | float):
        return _round(value * factor, 2)
    if key == "tail" and isinstance(value, list | tuple):
        return [_round(value[0] * factor, 1), _round(value[1] * factor, 1)]
    return _round(value, 3) if isinstance(value, float) else value


def write(presentation: Presentation, folder: Path, stem: str, report: Report,
          progress: Progress = quiet, *, heavy: int = HEAVY) -> dict[str, Any]:
    """``presentation`` as a deck document, its pictures written into ``folder/assets``, its
    words set where their slide program set them."""

    from flexo_talk.importing.repairing import repaired

    writer = Writer(presentation, folder, report, progress, heavy)
    document = repaired(writer.document(stem), folder, report)
    settle(document, writer, folder, progress)
    return document
