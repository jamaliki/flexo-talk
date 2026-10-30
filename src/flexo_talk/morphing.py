"""Morph: a slide that arrives by moving what it shares with the slide before into place.

A talk often builds a picture up over several slides, each a copy of the one before with a
little more: a molecule slid into its pocket, a pipeline given a stage, an inset grown out of
what it magnifies. Keynote's Magic Move and PowerPoint's Morph turn such a pair of slides into
motion, and so does a slide that says::

  - title: Weight the samples
    transition: morph                       # from the slide before, in 1 s
  - title: Resample
    transition: {kind: morph, duration: 2}  # in 2 s

What the two slides share moves from where it was to where it is, growing or shrinking as it
goes; what only the slide before has fades out in the first quarter of the time, and what only
this one has fades in over the last quarter. A slide morphs only from the one shown before it,
going forward: a slide gone back to, or jumped to, is simply shown.

**What is shared** is found in this order, each step among what the steps before left
unpaired, the nearest first where several could be:

1. **The same name.** Any object or shape may name its partner with ``morph:`` -- the same
   name on both slides: ``{text: Encoder, morph: encoder}``. For when what follows is not
   enough.
2. **The same frame.** Figures drawn in one frame (``frame:``, ``flexo_talk.framing``) are the
   same figure; within it each part goes to the part with its id.
3. **The same thing.** The same picture or GIF, the same figure (``'#pipeline'``, one file, or
   one written in the deck, a copy of a slide's included), the same shape (by its ``id``), the
   same words, list, table or equation -- and a slide's title, number, footer and logos.
4. **The same place.** An object of the same kind in the same place of the layout (a column)
   whose box is where the other's is, give or take ``NEAR`` points.

Nothing is paired for looking alike: what is unpaired fades. The slide's drawing says what
each object is (``mark``): ``data-flexo-morph`` its name, ``data-flexo-framed`` its frame and
``data-flexo-same`` what it is; the studio pairs what is drawn by these as it presents (its
``morph.js``), and a PowerPoint here (``Plan``).

**PowerPoint** has Morph of its own, which plays the same way when the deck is presented from
it: a morphing slide is written with it (``p159:morph``, a fade where a PowerPoint is too old
for Morph), and every object on a slide either side of it named ``!!`` and a name, the same on
both slides for a pair -- PowerPoint's own way to be told what goes with what -- so it pairs
them as Flexo does. A figure is one object there: it moves whole.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from flexo_talk.deck import SettingError

KINDS = ("morph",)
"""The transitions a slide may arrive with."""

DURATION = 1.0
"""How long a morph takes unless its slide says (seconds)."""

SHORTEST, LONGEST = 0.1, 10.0
"""The least and most a morph may take (seconds)."""

NEAR = 8.0
"""How far apart (points) two objects of one kind in one place may be and still be the same:
the drift a layout makes from a little more or less beside them."""

_SVG = "{http://www.w3.org/2000/svg}"

# -- what a slide says --


@dataclass(frozen=True, slots=True)
class Transition:
    """How a slide arrives from the one shown before it."""

    kind: str = "morph"
    duration: float = DURATION
    """Seconds."""


def transition_of(value: object) -> Transition | None:
    """A slide's ``transition`` as written -- ``morph``, ``{kind: morph, duration: 2}``, or none
    (``none``, ``false``) -- checked: what is wrong said under its key."""

    if value is None or value is False or value == "none":
        return None
    said = f"transition must be morph, or {{kind: morph, duration: 1.5}} (seconds), not {value!r}."
    if isinstance(value, str):
        if value.strip() not in KINDS:
            raise SettingError("transition", said)
        return Transition(value.strip())
    if not isinstance(value, dict) or any(key not in {"kind", "duration"} for key in value):
        raise SettingError("transition", said)
    kind = value.get("kind", "morph")
    if kind not in KINDS:
        raise SettingError("transition", said)
    duration = value.get("duration", DURATION)
    if isinstance(duration, bool) or not isinstance(duration, int | float) or not math.isfinite(duration):
        raise SettingError("transition", f"A transition's duration must be a number of seconds, not {duration!r}.")
    if not SHORTEST <= duration <= LONGEST:
        raise SettingError(
            "transition",
            f"A transition's duration must be between {SHORTEST:g} and {LONGEST:g} seconds, not {duration:g}.",
        )
    return Transition(str(kind), float(duration))


def transition_written(transition: Transition | None) -> object:
    """``transition`` as a deck document writes it: its kind alone where it takes the time it
    takes unless told."""

    if transition is None:
        return None
    if abs(transition.duration - DURATION) < 1e-9:
        return transition.kind
    duration = transition.duration
    return {"kind": transition.kind, "duration": int(duration) if float(duration).is_integer() else duration}


def slide_transition(slide: Any) -> Transition | None:
    """The transition ``slide`` (a ``deck.Slide``) arrives with, as its document says; none
    where it says nothing, or what cannot be read."""

    try:
        return transition_of(getattr(slide, "source", {}).get("transition"))
    except SettingError:
        return None


def morph_name(value: object, what: str = "morph") -> str | None:
    """An object's or a shape's ``morph`` as written: the name its partner on the slide before
    or after has too. Words, or a number."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str | int | float) or not str(value).strip():
        raise SettingError(
            what,
            f"morph must be a name -- the same on the object it goes with on the slide "
            f"before or after -- such as encoder, not {value!r}.",
        )
    return str(value).strip()


# -- what the slide's drawing says of each object (compose) --

_COPY = re.compile(r"-copy(?:-\w+)?$")
"""What the studio adds to a figure's id written in a slide it copies (``pipeline-copy-x3k1``):
the copy is the same figure, for a morph."""

_REGION = re.compile(r"^(body|left|right|column\d+)\.(\d+)$")
_SHAPE = re.compile(r"^shapes\.\d+$")
_OWN = re.compile(r"^(?:presented-)?slide\d+\.(.+)$")


def mark(root: ET.Element, slide: Any) -> None:
    """Each object and shape of ``slide`` drawn in ``root`` (its SVG) said for a morph to pair
    it: its own name (``data-flexo-morph``), its figure's frame (``data-flexo-framed``) and what
    it is (``data-flexo-same``: a picture, a figure, a shape, its words)."""

    wanted: dict[str, dict[str, str]] = {}
    for name, region in slide.regions.items():
        for index, block in enumerate(region.blocks):
            source = region.sources[index] if index < len(region.sources) else {}
            said = _block_marks(block, source if isinstance(source, dict) else {})
            if said:
                wanted[f"{slide.id}.{name}.{index}"] = said
    for index, shape in enumerate(slide.shapes):
        if not isinstance(shape, dict):
            continue
        said = {}
        if (named := _name(shape.get("morph"))) is not None:
            said["data-flexo-morph"] = named
        if shape.get("id") is not None and str(shape["id"]).strip():
            said["data-flexo-same"] = f"shape:{str(shape['id']).strip()}"
        elif shape.get("kind") == "picture" and shape.get("source"):
            said["data-flexo-same"] = _hashed("picture", str(shape["source"]))
        if said:
            wanted[f"{slide.id}.shapes.{index}"] = said
    if not wanted:
        return
    for element in root.iter():
        said = wanted.get(element.get("id") or "")
        if said:
            for key, value in said.items():
                element.set(key, value)


def _name(value: object) -> str | None:
    try:
        return morph_name(value)
    except SettingError:
        return None


def _block_marks(block: Any, source: dict[str, Any]) -> dict[str, str]:
    from flexo_talk.deck import _Figure, _Image, _Missing
    from flexo_talk.document import BLOCKS

    said: dict[str, str] = {}
    if (named := _name(source.get("morph"))) is not None:
        said["data-flexo-morph"] = named
    if isinstance(block, _Figure) and block.frame:
        said["data-flexo-framed"] = block.frame
    kind = next((key for key in source if key in BLOCKS), None)
    if isinstance(block, _Missing):
        return said
    if isinstance(block, _Image):
        said["data-flexo-same"] = _hashed("picture", str(block.source))
    elif isinstance(block, _Figure) and kind in {None, "figure"}:
        written = source.get("figure")
        if isinstance(written, str) and written.strip():
            said["data-flexo-same"] = _hashed("figure", written.strip())
        elif ident := _figure_id(written if isinstance(written, dict) else None, block.figure):
            said["data-flexo-same"] = _hashed("figure", f"id:{_COPY.sub('', ident)}")
    elif kind is not None:
        # What it says (its words, its list, its rows, its equation, its mechanism), word for word.
        said["data-flexo-same"] = _hashed(kind, json.dumps(source[kind], sort_keys=True, default=str))
    return said


def _figure_id(written: dict[str, Any] | None, figure: Any) -> str | None:
    if written is not None:
        inner = written.get("figure")
        if isinstance(inner, dict) and inner.get("id"):
            return str(inner["id"])
    spec = getattr(figure, "spec", figure)
    ident = getattr(spec, "id", None)
    return str(ident) if ident else None


def _hashed(kind: str, value: str) -> str:
    """What something is, as its drawing says it: its kind and a short digest -- never a file's
    path, which an SVG sent on would carry."""

    return f"{kind}:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


# -- pairing --


@dataclass(slots=True)
class Unit:
    """One thing on a slide a morph moves as a whole: an object, a shape, the title, a logo."""

    key: str
    """Its id on its slide, the slide's own part taken off: ``title``, ``body.0``, ``shapes.2``."""
    ident: str
    """The id it is drawn with (``slide3.body.0``)."""
    kind: str
    """What it is drawn as: its ``data-flexo-talk`` (``figure``, ``bullets``), a shape's
    ``shape``, else its element (``text``, ``image``)."""
    box: tuple[float, float, float, float]
    """Where it is drawn on the slide: ``x, y, width, height`` (points)."""
    region: str = ""
    """The place in the layout of an object (``body``, ``left``, ``column2``), ``shapes`` for a
    shape; ``""`` for the rest."""
    morph: str = ""
    framed: str = ""
    same: str = ""
    owner: str = ""
    """The object it is part of, drawn apart (a figure's caption): it goes where that goes."""
    texty: bool = False
    """Whether it is words (set from a corner, its size its type's, not its box's)."""
    data: dict[str, Any] = field(default_factory=dict)


def _centre(unit: Unit) -> tuple[float, float]:
    x, y, w, h = unit.box
    return x + w / 2.0, y + h / 2.0


def _near(old: Unit, new: Unit) -> bool:
    (ox, oy, ow, oh), (nx, ny, nw, nh) = old.box, new.box
    if old.texty or new.texty:
        # Words: their first line where it was, from the side they are set from, whatever it says.
        across = min(abs(ox - nx), abs(ox + ow / 2 - nx - nw / 2), abs(ox + ow - nx - nw))
        return abs(oy - ny) <= NEAR and across <= NEAR
    return abs(ox - nx) <= NEAR and abs(oy - ny) <= NEAR and abs(ow - nw) <= NEAR and abs(oh - nh) <= NEAR


TIERS: tuple[tuple[str, Callable[[Unit], str]], ...] = (
    ("named", lambda unit: unit.morph),
    ("framed", lambda unit: unit.framed),
    ("same", lambda unit: unit.same),
    ("placed", lambda unit: f"{unit.kind}|{unit.region}" if unit.region else ""),
)


def paired(old: Sequence[Unit], new: Sequence[Unit]) -> list[tuple[int, int]]:
    """Which of ``old`` (the slide before's) goes with which of ``new``: ``(old, new)`` index
    pairs, in ``new``'s order. Each step (``TIERS``) pairs what the steps before left, each of
    ``new`` in turn with the nearest of ``old`` it may go with; then each part drawn apart (a
    caption) with the same part of what its object went with. (``morph.js`` pairs alike.)"""

    pairs: dict[int, int] = {}
    taken: set[int] = set()
    for tier, key_of in TIERS:
        for j, unit in enumerate(new):
            if j in pairs or unit.owner:
                continue
            key = key_of(unit)
            if not key:
                continue
            best: tuple[float, int] | None = None
            cx, cy = _centre(unit)
            for i, other in enumerate(old):
                if i in taken or other.owner or key_of(other) != key:
                    continue
                if tier == "placed" and not _near(other, unit):
                    continue
                ox, oy = _centre(other)
                distance = math.hypot(ox - cx, oy - cy)
                if best is None or distance < best[0] - 1e-9:
                    best = (distance, i)
            if best is not None:
                pairs[j] = best[1]
                taken.add(best[1])
    went = {old[i].key: new[j].key for j, i in pairs.items()}
    olds = {unit.key: i for i, unit in enumerate(old)}
    for j, unit in enumerate(new):
        if not unit.owner or j in pairs:
            continue
        mine = unit.owner
        theirs = next((key for key, now in went.items() if now == mine), None)
        if theirs is None:
            continue
        i = olds.get(theirs + unit.key[len(mine) :])
        if i is not None and i not in taken:
            pairs[j] = i
            taken.add(i)
    return sorted(((i, j) for j, i in pairs.items()), key=lambda pair: pair[1])


def units_of(svg: str, *, entering: bool = False) -> list[Unit]:
    """What a morph moves on the slide ``svg`` draws, in the order it is drawn: what is not
    shown left out -- and, ``entering`` (the slide morphed to), what builds in on a click."""

    from flexo.drawing import Drawing, Group, ink_bounds
    from flexo.drawings_kept import drawing_of

    root = ET.fromstring(svg)
    drawing = drawing_of(svg)
    items: dict[str, Any] = {}
    stack: list[Any] = [drawing.root]
    while stack:
        item = stack.pop()
        if getattr(item, "id", None):
            items.setdefault(item.id, item)
        if isinstance(item, Group):
            stack.extend(item.items)

    def box(ident: str) -> tuple[float, float, float, float] | None:
        item = items.get(ident)
        if item is None:
            return None
        left, top, right, bottom = ink_bounds(Drawing(drawing.width, drawing.height, Group(None, [item])))
        if not (right > left or bottom > top) or not all(map(math.isfinite, (left, top, right, bottom))):
            return None
        return left, top, right - left, bottom - top

    found: list[Unit] = []
    for element, key in _walk(root, entering):
        where = box(element.get("id") or "")
        if where is None:
            continue
        found.append(_unit(element, key, where))
    _owned(found)
    return found


_CONTAINERS = {"region", "placed", "shapes"}
_TEXTY = {"text", "bullets", "quote", "callout", "code", "table", "stats", "math"}


def _walk(root: ET.Element, entering: bool):
    """Each element of a slide's drawing a morph moves whole, with its key."""

    layers = [child for child in root if child.tag == f"{_SVG}g"]
    content = [layer for layer in layers if (layer.get("id") or "").endswith(".content")]
    presented = [layer for layer in root.iter(f"{_SVG}g") if layer.get("data-flexo-presented") is not None]
    if presented:
        content = presented
    background = [layer for layer in layers if layer.get("id") == "layer.background"]

    def shown(element: ET.Element) -> bool:
        if element.get("display") == "none" or element.get("visibility") == "hidden":
            return False
        if element.get("data-flexo-placeholder") is not None or element.get("data-flexo-editing") is not None:
            return False
        return not (entering and int(element.get("data-flexo-step", "0") or 0) > 1)

    def walk(parent: ET.Element):
        for child in parent:
            if not isinstance(child.tag, str) or not shown(child):
                continue
            tag = child.tag.removeprefix(_SVG)
            if tag in {"defs", "style", "title", "desc", "metadata"}:
                continue
            ident = child.get("id") or ""
            found = _OWN.match(ident)
            key = found.group(1) if found else ident
            if child.get("data-flexo-talk") in _CONTAINERS and not _SHAPE.match(key):
                yield from walk(child)
            elif key:
                yield child, key
            elif tag == "g":
                yield from walk(child)

    for layer in background + content:
        yield from walk(layer)


def _unit(element: ET.Element, key: str, box: tuple[float, float, float, float]) -> Unit:
    tag = element.tag.removeprefix(_SVG)
    talk = element.get("data-flexo-talk") or ""
    region = ""
    if found := _REGION.match(key):
        region = found.group(1)
    elif _SHAPE.match(key):
        region = "shapes"
    kind = f"shape:{element.get('data-flexo-shape') or ''}" if region == "shapes" else talk or tag
    unit = Unit(
        key,
        element.get("id") or "",
        kind,
        box,
        region,
        morph=element.get("data-flexo-morph") or "",
        framed=element.get("data-flexo-framed") or "",
        same=element.get("data-flexo-same") or "",
        texty=kind in _TEXTY,
    )
    if not region and not unit.same:
        # A title, a number, a footer, a logo, the page: the same on every slide it is on.
        unit.same = f"furniture:{key}"
    return unit


def _owned(units: list[Unit]) -> None:
    """Each part drawn apart from its object (``right.0.caption``) said to be that object's."""

    blocks = {unit.key for unit in units if unit.region and unit.region != "shapes"}
    for unit in units:
        if unit.region:
            continue
        head = ".".join(unit.key.split(".")[:2])
        if head != unit.key and head in blocks:
            unit.owner = head
            unit.same = ""


# -- PDF --


def page_fades(rendered: Sequence[Any], *, handout: bool = False) -> list[float | None]:
    """How each page of a deck's PDF is arrived at by a reader presenting it full screen: the
    seconds the first page of a slide that morphs is faded to over (a PDF can do no more), else
    ``None``. A page for each step of a slide's builds, unless it is a ``handout``."""

    fades: list[float | None] = []
    for index, item in enumerate(rendered):
        transition = slide_transition(item.slide) if index else None
        fades += [transition.duration if transition else None] + [None] * ((1 if handout else item.steps) - 1)
    return fades


# -- PowerPoint --

P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def transition_xml(transition: Transition) -> str:
    """A slide's ``<p:transition>`` as PowerPoint writes Morph: its own (``p159:morph``, by
    object) for a PowerPoint that has it, else a fade of the same speed."""

    ms = round(transition.duration * 1000)
    speed = "fast" if ms <= 500 else "med" if ms <= 750 else "slow"
    return (
        f'<mc:AlternateContent xmlns:mc="{MC}" xmlns:p="{_P}">'
        f'<mc:Choice xmlns:p159="{P159}" Requires="p159">'
        f'<p:transition xmlns:p14="{P14}" spd="{speed}" p14:dur="{ms}"><p159:morph option="byObject"/></p:transition>'
        f"</mc:Choice>"
        f'<mc:Fallback><p:transition spd="{speed}"><p:fade/></p:transition></mc:Fallback>'
        f"</mc:AlternateContent>"
    )


def add_transition(slide_element: Any, transition: Transition) -> None:
    """``transition`` written into a slide's XML (lxml), where a slide has it: after its
    ``p:clrMapOvr``, before its ``p:timing`` -- in place of one it had."""

    from lxml import etree

    for old in list(slide_element):
        if etree.QName(old).localname == "transition" or (
            etree.QName(old).localname == "AlternateContent" and old.find(f".//{{{_P}}}transition") is not None
        ):
            slide_element.remove(old)
    made = etree.fromstring(transition_xml(transition))
    names = [etree.QName(child).localname for child in slide_element]
    if "clrMapOvr" in names:
        at = names.index("clrMapOvr") + 1
    elif "cSld" in names:
        at = names.index("cSld") + 1
    else:
        at = 0
    slide_element.insert(at, made)


@dataclass(slots=True)
class Plan:
    """A deck's morphs as a PowerPoint writes them: which slides arrive by Morph, and the
    ``!!`` name of each object on a slide either side of one, by the id it is drawn with."""

    transitions: dict[int, Transition] = field(default_factory=dict)
    names: dict[int, dict[str, str]] = field(default_factory=dict)

    def key(self, index: int) -> tuple:
        """What slide ``index`` is written with here, for a slide kept as written to be
        known by (``export._WRITTEN``)."""

        transition = self.transitions.get(index)
        return (transition, tuple(sorted(self.names.get(index, {}).items())))

    def write(self, slide_element: Any, tree: Any, index: int) -> list[tuple[Any, str]]:
        """Slide ``index``'s transition written into it; and each of its objects that has a
        name found (``tree``: its shapes, before they are named as a person would name them),
        with the name it will have -- given it by ``rename`` once they are."""

        if index in self.transitions:
            add_transition(slide_element, self.transitions[index])
        names = self.names.get(index)
        if not names:
            return []
        found: list[tuple[Any, str]] = []
        for child in tree:
            properties = list(child.iter(f"{{{_P}}}cNvPr"))
            if not properties:
                continue
            name = names.get(properties[0].get("name") or "")
            if name is None:
                continue
            # (An equation is its PowerPoint's own and flexo's drawing for others, one each.)
            found += [(each, name) for each in properties if each.get("name") == properties[0].get("name")]
        return found


def rename(found: list[tuple[Any, str]]) -> None:
    """What ``Plan.write`` found named as it said, now that nothing finds it by its id."""

    for properties, name in found:
        properties.set("name", name)


_NOUNS = {
    "bullets": "List",
    "text": "Text",
    "figure": "Figure",
    "image": "Picture",
    "picture": "Picture",
    "math": "Equation",
    "table": "Table",
    "code": "Code",
    "quote": "Quote",
    "callout": "Callout",
    "stats": "Numbers",
    "gallery": "Gallery",
    "plot": "Plot",
    "shape": "Shape",
    "rect": "Shape",
    "path": "Shape",
    "g": "Group",
}
"""What a PowerPoint names an object a morph pairs by no name of its own: what it is."""


def plan(rendered: Sequence[Any]) -> Plan:
    """The morphs of the slides ``rendered`` (``deck.RenderedSlide``, in the order they are
    presented: none skipped): each slide that morphs from the one before, and the names that
    pair their objects as ``paired`` does."""

    made = Plan()
    for index, item in enumerate(rendered):
        transition = slide_transition(item.slide)
        if transition is not None and index > 0:
            made.transitions[index] = transition
    if not made.transitions:
        return made
    involved = sorted({at for index in made.transitions for at in (index - 1, index)})
    units: dict[int, list[Unit]] = {}

    def of(index: int) -> list[Unit]:
        if index not in units:
            try:
                units[index] = units_of(rendered[index].svg, entering=index in made.transitions)
            except (ET.ParseError, ValueError):
                units[index] = []
        return units[index]

    taken: set[str] = set()

    def fresh(unit: Unit) -> str:
        label = (
            unit.morph
            or unit.framed
            or (
                unit.same.removeprefix("shape:")
                if unit.same.startswith("shape:")
                else unit.key
                if unit.same.startswith("furniture:")
                else ""
            )
        )
        label = re.sub(r"\s+", " ", label).strip() or _NOUNS.get(unit.kind.split(":")[0], "Object")
        name, count = f"!!{label}", 1
        while name in taken:
            count += 1
            name = f"!!{label} {count}"
        taken.add(name)
        return name

    for index in involved:
        mine = of(index)
        names: dict[str, str] = {}
        partners: dict[int, int] = {}
        if index in made.transitions:
            partners = {j: i for i, j in paired(of(index - 1), mine)}
        before = made.names.get(index - 1, {})
        olds = of(index - 1) if index in made.transitions else []
        for j, unit in enumerate(mine):
            was = before.get(olds[partners[j]].ident) if j in partners else None
            names[unit.ident] = was or fresh(unit)
        made.names[index] = names
    return made
