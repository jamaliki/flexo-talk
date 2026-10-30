"""Anything on a slide shown, highlighted, dimmed or hidden, where it stands.

A talk shows one slide several ways: all of it, then one point with the rest faint, then
that point alone. Every object on a slide -- and each part of a list, a table, a gallery,
numbers, code or a figure -- and every shape a slide draws is shown one of four ways, the
same way everywhere:

- shown: as it is (what nothing says);
- highlighted: as it is, and what stands with it drawn faint -- an object's the slide's other
  objects and shapes (its title, its footer and number shown still), a list's item its list's
  other items (the items under it go with it), a table's row its table's other rows (its
  header shown still), a figure's part the rest of its figure (``flexo.showing``);
- dimmed: drawn faint where it stands, every colour most of the way to the page's (as a
  figure's parts are: ``flexo.showing.faint``), a picture or a GIF see-through;
- hidden: not drawn when presenting or exporting, its place kept -- nothing else moves -- and
  a ghost while it is edited, to be chosen and shown again.

A block says so with the keys a figure's parts are named by: ``hide``, ``dim`` and
``highlight``, each ``true`` (the whole object) or a list of its parts::

  - {bullets: [Encoder, [Attention, Feed-forward], Decoder], highlight: [2]}
  - {table: [[Model, Loss], [A, 0.31], [B, 0.27]], dim: [2]}   # row 2: A's
  - {image: pictures/cell.png, dim: true}
  - {figure: '#pipeline', hide: [store]}                       # a figure's parts by id

A list's items are named by their numbers from 1, an item under another by both, in quotes
(``'1.2'``: the second item under the first); a table's rows by their numbers, the header
row 1 (and a cell by its row's and its column's: ``'3.2'``); a gallery's pictures, numbers'
figures and code's lines by theirs. A name of a part the object has none of is passed over
(an item since deleted). Hidden is stronger than dimmed, dimmed than highlighted.

A shape says it with ``hide: true``, ``dim: true`` or ``highlight: true``; its ``hidden:
true``, as decks said it before, is ``hide: true``. Words are dimmed with markup:
``[words]{dim}``, the words' own colour drawn faint.

A hidden object builds in on no click (nor does a hidden item of a list revealed item by
item): there is nothing to show. How anything is shown may change on a click, held until a
later one changes it again (``click 2: {highlight: [2]}``): ``flexo_talk.onclick``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

HIDDEN, DIMMED, HIGHLIGHTED = "hidden", "dimmed", "highlighted"
KEYS = {"hide": HIDDEN, "dim": DIMMED, "highlight": HIGHLIGHTED}
"""Each key a block or a shape says how it is shown with, and the way it says."""
_STRENGTH = {HIGHLIGHTED: 1, DIMMED: 2, HIDDEN: 3}

PARTS: dict[str, tuple[str, str, str]] = {
    "bullets": ("items", r"[1-9]\d*(?:\.[1-9]\d*)*", "2, or '2.1' for the first item under item 2"),
    "table": ("rows", r"[1-9]\d*(?:\.[1-9]\d*)?", "2 (the header is row 1), or '2.3' for its third cell"),
    "gallery": ("pictures", r"[1-9]\d*", "2"),
    "stats": ("numbers", r"[1-9]\d*", "2"),
    "code": ("lines", r"[1-9]\d*", "2"),
}
"""The kinds of objects whose parts are shown apart, their parts as named, by number: what
they are, the names written, and an example."""

_NOUNS = {"bullets": "list", "image": "picture", "stats": "set of numbers", "math": "equation"}


@dataclass(slots=True)
class Shown:
    """How a block is shown: ``whole`` (hidden, dimmed or highlighted; ``None`` shown) and
    its parts, by name as written (``"2"``, ``"2.1"``) -- a figure's are its own
    (``FigureSpec.hidden``...)."""

    whole: str | None = None
    parts: dict[str, str] = field(default_factory=dict)
    named: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """A figure's parts, by how they are shown (``hidden``, ``dimmed``, ``highlighted``): as a
    click says them (``flexo_talk.onclick``) -- a figure's own are its spec's."""

    def __bool__(self) -> bool:
        return self.whole is not None or bool(self.parts) or bool(self.named)


def stronger(one: str | None, other: str | None) -> str | None:
    """The stronger of two ways of being shown: hidden over dimmed over highlighted."""

    return max((one, other), key=lambda how: _STRENGTH.get(how or "", 0))


def written(kind: str, said: dict[str, object]) -> Shown:
    """How a block of ``kind`` is shown, from what it says (``hide``, ``dim``, ``highlight``:
    ``true``, or a list of its parts): checked, what is wrong said under its key. A figure's
    lists are its parts' (``FigureSpec``): only its ``true`` is kept here."""

    from flexo_talk.deck import SettingError

    shown = Shown()
    noun = _NOUNS.get(kind, kind)
    for key, how in KEYS.items():
        value = said.get(key)
        if value is None or value is False:
            continue
        if value is True:
            shown.whole = stronger(shown.whole, how)
            continue
        if kind == "figure":
            if not isinstance(value, list | tuple) or not all(isinstance(item, str) for item in value):
                raise SettingError(key, f"{key} must be true (the whole figure) or a list of the names of the "
                                        "figure\u2019s parts.")
            shown.named[how] = tuple(value)
            continue
        if kind not in PARTS:
            raise SettingError(key, f"A {noun} is {how} as a whole: {key}: true, not {value!r}.")
        parts, pattern, example = PARTS[kind]
        if not isinstance(value, list | tuple):
            raise SettingError(key, f"{key} must be true (the whole {noun}) or a list of its {parts} by number "
                                    f"({example}), not {value!r}.")
        for item in value:
            name = _name(item)
            if name is None or not re.fullmatch(pattern, name):
                raise SettingError(key, f"{key} names a {noun}\u2019s {parts} by number, from 1 ({example}), "
                                        f"not {item!r}.")
            shown.parts[name] = stronger(shown.parts.get(name), how) or how
    return shown


def _name(item: object) -> str | None:
    if isinstance(item, bool):
        return None
    if isinstance(item, int):
        return str(item)
    if isinstance(item, float):
        # (YAML reads 2.1 unquoted as a number: the item it names, as written.)
        return repr(item)
    if isinstance(item, str):
        return item.strip()
    return None


def part_written(item: object) -> object:
    """A part's name as a document writes it: a number as a number, an item under another
    (``"2.1"``) or a figure's part as words."""

    name = _name(item)
    return int(name) if name is not None and name.isdigit() else item


_CLASSES = {
    "_Bullets": "bullets", "_Words": "text", "_Figure": "figure", "_Image": "image", "_Plot": "plot",
    "_Table": "table", "_Gallery": "gallery", "_Code": "code", "_Quote": "quote", "_Stats": "stats",
    "_Callout": "callout", "_Math": "math",
}


def kind_of(block: object, source: dict | None = None) -> str:
    """The kind of object a block is, as a document names it (``bullets``, ``mechanism``):
    as it is written (``source``), else by what it is."""

    from flexo_talk.document import BLOCKS

    written_as = next((key for key in source or {} if key in BLOCKS), None)
    return written_as or _CLASSES.get(type(block).__name__, "object")


def item_paths(levels: Iterable[int]) -> list[str]:
    """Each item of a list by its levels, named as a document names it: ``"2"``, the second
    at the top; ``"2.1"``, the first under it."""

    counts: list[int] = []
    paths = []
    for level in levels:
        counts = (counts + [0] * (level + 1))[: level + 1]
        counts[level] += 1
        paths.append(".".join(str(count) for count in counts))
    return paths


def shape_state(shape: object, click: int = 0) -> str | None:
    """How a slide's shape is shown: hidden (``hide``, or ``hidden`` as decks said it before),
    dimmed or highlighted -- else ``None``. At ``click``, as its last ``click`` up to it says
    (``flexo_talk.onclick``), if it has one."""

    from flexo_talk.onclick import shape_said

    if not isinstance(shape, dict):
        return None
    said = shape_said(shape, click) if click else shape
    how = None
    for key, state in (*KEYS.items(), *((("hidden", HIDDEN),) if said is shape else ())):
        if said.get(key) is True:
            how = stronger(how, state)
    return how


def shown_at(region: Any, index: int, click: int = 0) -> Shown | None:
    """How a region's block (by index) is shown at ``click``: as its last ``click`` up to it says
    (``flexo_talk.onclick``), else as it says itself."""

    later = region.later.get(index) if click else None
    if later:
        named = [number for number in later if number <= click]
        if named:
            return later[max(named)]
    return region.shown.get(index)


def _units(block: Any, identifier: str, lines: list[int] | None) -> list[tuple[str, tuple[str, ...], bool]]:
    """A block's parts as drawn: each one's id, the names that name it (an item's and those
    of the items it is under), and whether it stands apart from a highlight (a header)."""

    from flexo_talk.deck import _Bullets, _Code, _Gallery, _Stats, _Table

    if isinstance(block, _Bullets):
        paths = item_paths(level for level, _ in block.items)
        return [(f"{identifier}.{index}", tuple(".".join(path.split(".")[: depth + 1])
                                                 for depth in range(path.count(".") + 1)), False)
                for index, path in enumerate(paths)]
    if isinstance(block, _Table):
        return [(f"{identifier}.{row}.{column}", (str(row + 1), f"{row + 1}.{column + 1}"), block.header and row == 0)
                for row, cells in enumerate(block.rows) for column in range(len(cells))]
    if isinstance(block, _Gallery | _Stats):
        return [(f"{identifier}.{index}", (str(index + 1),), False) for index in range(len(block.items))]
    if isinstance(block, _Code):
        drawn = lines if lines is not None else list(range(len(block.lines)))
        return [(f"{identifier}.{index}", (str(source + 1),), False) for index, source in enumerate(drawn)]
    return []


def part_states(block: Any, identifier: str, shown: Shown, lines: list[int] | None = None) -> dict[str, str]:
    """How each part of a block is drawn, where not plainly: hidden or dimmed, by its id."""

    if not shown.parts:
        return {}
    units = _units(block, identifier, lines)
    lit = {ident for ident, names, _ in units if any(shown.parts.get(name) == HIGHLIGHTED for name in names)}
    found: dict[str, str] = {}
    for ident, names, apart in units:
        how = None
        for name in names:
            how = stronger(how, shown.parts.get(name))
        if how == HIGHLIGHTED:
            continue
        if how is None and lit and ident not in lit and not apart:
            how = DIMMED
        if how is not None:
            found[ident] = how
    return found


def hidden_items(block: Any, shown: Shown | None) -> set[int]:
    """The items of a list that are hidden (all of them, the list hidden)."""

    if not shown:
        return set()
    if shown.whole == HIDDEN:
        return set(range(len(block.items)))
    return {int(ident.rsplit(".", 1)[1]) for ident, how in part_states(block, "", shown).items() if how == HIDDEN}


def slide_states(
    slide: Any, lines: dict[str, list[int]] | None = None, click: int = 0,
    parts: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """How everything on ``slide`` is drawn, where not plainly: ``"hidden"`` or ``"dimmed"``,
    by the id it is drawn with -- an object's (``slide2.body.0``), a part's (an item,
    ``slide2.body.0.3``; a cell, ``slide2.body.1.2.0``), a shape's (``slide2.shapes.1``).
    Whatever is drawn with an id under one of these (``slide2.body.0.caption``) is drawn
    as it is. ``lines``: each listing's lines as drawn, by the line each is of. At ``click``,
    as what is on it says it is shown from a click on (``flexo_talk.onclick``); ``parts``: the
    parts of the figures drawn with none of their own shown apart, by the figure's id, as at
    that click (``onclick.figure_parts``)."""

    found: dict[str, str] = {}
    objects: list[tuple[str, str | None]] = []
    for name, region in slide.regions.items():
        for index, block in enumerate(region.blocks):
            identifier = f"{slide.id}.{name}.{index}"
            shown = shown_at(region, index, click)
            objects.append((identifier, shown.whole if shown else None))
            if parts and identifier in parts:
                found |= parts[identifier]
            if not shown:
                continue
            if shown.whole in (HIDDEN, DIMMED):
                found[identifier] = shown.whole
            found |= part_states(block, identifier, shown, (lines or {}).get(identifier))
    for index, shape in enumerate(slide.shapes):
        objects.append((f"{slide.id}.shapes.{index}", shape_state(shape, click)))
    for identifier, how in objects:
        if how in (HIDDEN, DIMMED):
            found[identifier] = how
    # One highlighted: the rest of what is on the slide faint (its own furniture aside).
    if any(how == HIGHLIGHTED for _, how in objects):
        for identifier, how in objects:
            if how is None:
                found[identifier] = DIMMED
    return found


def lookup(states: dict[str, str], identifier: str) -> str | None:
    """How what is drawn as ``identifier`` is shown: as it is said itself, else as what it is
    part of (``slide1.body.0.caption`` as ``slide1.body.0``)."""

    name = identifier
    while name:
        if name in states:
            return states[name]
        if "." not in name:
            return None
        name = name.rsplit(".", 1)[0]
    return None


def _key(states: dict[str, str], identifier: str) -> str | None:
    name = identifier
    while name:
        if name in states:
            return name
        if "." not in name:
            return None
        name = name.rsplit(".", 1)[0]
    return None


def mark_slide(root: ET.Element, states: dict[str, str], page: str) -> None:
    """``root`` (a slide's drawing) drawn as ``states`` says: what is hidden marked so where it
    stands, what is dimmed brought nearer the ``page``'s colour (``flexo.showing.mark``) --
    each once, at the outermost of what is drawn of it."""

    from flexo.showing import mark

    if not states:
        return
    chosen: dict[str, str] = {}
    stack: list[tuple[ET.Element, frozenset[str], str | None]] = [(root, frozenset(), None)]
    while stack:
        element, covered, within = stack.pop()
        identifier = element.get("id")
        if identifier and within != HIDDEN:
            key = _key(states, identifier)
            if key is not None and key not in covered:
                how = states[key]
                # (In something faint already, only what is hidden is marked again.)
                if within is None or how == HIDDEN:
                    chosen[identifier] = how
                    within = how if within is None or how == HIDDEN else within
                covered = covered | {key}
        stack.extend((child, covered, within) for child in reversed(list(element)))
    mark(root, chosen, canvas=page)


def dim_words(root: ET.Element, page: str) -> None:
    """Words dimmed by their markup (``[words]{dim}``): their own colour -- the colour of the
    words they are in -- drawn faint, as a dimmed object's are."""

    from flexo.showing import _HEX, MARK, faint

    parents = None
    for element in root.iter():
        if element.get("data-flexo-fill") != "dim":
            continue
        if parents is None:
            parents = {child: parent for parent in root.iter() for child in parent}
        colour, at = None, parents.get(element)
        while at is not None and colour is None:
            own = at.get("fill") or ""
            colour = own if _HEX.fullmatch(own.strip()) else None
            at = parents.get(at)
        element.attrib.pop("data-flexo-fill", None)
        if colour is not None:
            element.set("fill", faint(colour, page))
            element.set(MARK, DIMMED)


# -- in a PowerPoint ---------------------------------------------------------------------

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def natively(tree: Any, states: dict[str, str], page: str, *, lists: Iterable[str] = (), tables: Iterable[str] = (),
             shapes: Iterable[str] = ()) -> None:
    """What a slide's PowerPoint writes natively -- its ``lists`` and ``tables`` (by id), its
    ``shapes`` and the equations and words with maths it writes as its own -- drawn as
    ``states`` says: a hidden item or row's words see-through (its room kept), what is
    dimmed in colours nearer the ``page``'s, a picture in a shape see-through. (What comes
    from the slide's drawing is drawn so there already.)"""

    if not states:
        return
    lists, tables, shapes = set(lists), set(tables), set(shapes)

    def named(element: Any) -> str:
        found = next(element.iter(f"{{{_P}}}cNvPr"), None)
        return found.get("name", "") if found is not None else ""

    for element in list(tree.iter(f"{{{_P}}}sp", f"{{{_P}}}graphicFrame", f"{{{_P}}}grpSp", f"{{{_P}}}cxnSp",
                                  f"{{{_P}}}pic")):
        name = named(element)
        if name in lists and element.tag == f"{{{_P}}}sp":
            whole = lookup(states, name)
            if whole == DIMMED:
                _faded(element, page)
            for index, paragraph in enumerate(element.iter(f"{{{_A}}}p")):
                how = states.get(f"{name}.{index}") or (whole if whole == HIDDEN else None)
                if how == HIDDEN:
                    _unseen(paragraph, page)
                elif how == DIMMED and whole != DIMMED:
                    _faded(paragraph, page)
        elif name in tables and element.tag == f"{{{_P}}}graphicFrame":
            whole = lookup(states, name)
            if whole == DIMMED:
                _faded(element, page)
            for row, line in enumerate(element.iter(f"{{{_A}}}tr")):
                for column, cell in enumerate(line.iter(f"{{{_A}}}tc")):
                    how = states.get(f"{name}.{row}.{column}")
                    words = cell.find(f"{{{_A}}}txBody")
                    if words is None:
                        continue
                    if how == HIDDEN:
                        _unseen(words, page)
                    elif how == DIMMED and whole != DIMMED:
                        _faded(words, page)
        elif name in shapes and lookup(states, name) == DIMMED:
            _faded(element, page)
    # Equations and words with maths written as PowerPoint's own (their drawing, the fallback,
    # is drawn so already).
    for choice in tree.iter(f"{{{_MC}}}Choice"):
        name = named(choice)
        if name and name not in lists and lookup(states, name) == DIMMED:
            _faded(choice, page)


def _faded(element: Any, page: str) -> None:
    from flexo.showing import DIM, faint

    for colour in element.iter(f"{{{_A}}}srgbClr"):
        value = colour.get("val", "")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            colour.set("val", faint(f"#{value}", page).lstrip("#").upper())
    for blip in element.iter(f"{{{_A}}}blip"):
        _alpha(blip, DIM)


def _unseen(element: Any, page: str) -> None:
    """``element``'s words see-through, their room kept -- and in the page's colour, for a
    program that draws words whole whatever their alpha (macOS's Quick Look)."""

    for colour in element.iter(f"{{{_A}}}srgbClr"):
        for old in colour.findall(f"{{{_A}}}alpha"):
            colour.remove(old)
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", page or ""):
            colour.set("val", page.lstrip("#").upper())
        _sub(colour, f"{{{_A}}}alpha", val="0")


def _alpha(blip: Any, share: float) -> None:
    kept = blip.find(f"{{{_A}}}alphaModFix")
    was = int(kept.get("amt", "100000")) / 100000 if kept is not None else 1.0
    if kept is None:
        kept = _sub(blip, f"{{{_A}}}alphaModFix")
        # (Before any extension: a blip's effects come first.)
        blip.remove(kept)
        blip.insert(0, kept)
    kept.set("amt", str(round(was * share * 100000)))


def _sub(parent: Any, tag: str, **attributes: str) -> Any:
    from lxml import etree

    return etree.SubElement(parent, tag, attributes)
