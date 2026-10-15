"""Convert to Figure Parts on a slide: shapes drawn as a diagram made a figure on the slide.

A diagram pasted from Inkscape onto a slide, or drawn there with its Shape tools, is the slide's
shapes: drawn where they are put, in none of the deck's figures' look. ``convert`` reads those
chosen as the diagram they draw (``flexo.recognise``) and puts a figure of it on the slide,
written in the deck as a slide's figure is (``figure: {figure, nodes, edges, groups}``): its
parts in the deck's theme, laid out as they were drawn, and edited on the slide as any figure
is. What of them was no part of the diagram (a highlight, a brace, a free curve) is drawn over
the figure -- its own shapes, attached to its parts. The shapes go from the slide, and a line
of the slide's glued to one of them is glued to the figure.

The figure goes into the region the page says (``region``, ``index``; ``replace``: in place of
the layout's empty placeholders there), else at the end of the slide's first; the lines of the
slide's glued to objects after it there follow them.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

WORDLESS = frozenset({"title", "section", "statement", "agenda"})
"""Layouts with no room for objects: their words are their own."""

SLIDE_ONLY = ("build", "hidden")
"""What a slide's shape says that a figure's shape cannot: it appears on a click, it is hidden."""

OBJECT = re.compile(r"^(body|left|right|columns\.(\d+)|columns\[(\d+)\])\[(\d+)\]$")


def regions_of(slide: Mapping[str, Any]) -> list[str]:
    """The regions a slide holds objects in, as the editor names them (``columns.1``)."""

    layout = str(slide.get("layout") or "content")
    if layout in WORDLESS:
        return []
    if layout == "two-columns":
        return ["left", "right"]
    if layout == "columns":
        return [f"columns.{index}" for index in range(len(slide.get("columns") or []))]
    return ["body"]


def _blocks(slide: dict[str, Any], region: str) -> list[Any]:
    if region.startswith("columns."):
        index = int(region.split(".", 1)[1])
        columns = slide.setdefault("columns", [])
        while len(columns) <= index:
            columns.append([])
        return columns[index]
    if not isinstance(slide.get(region), list):
        slide[region] = []
    return slide[region]


def _name(region: str, index: int) -> str:
    """An object's name, as a shape glued to it writes it: ``body[2]``, ``columns[1][0]``."""

    if region.startswith("columns."):
        return f"columns[{region.split('.', 1)[1]}][{index}]"
    return f"{region}[{index}]"


def _place(name: object) -> tuple[str, int] | None:
    found = OBJECT.fullmatch(str(name or "").strip())
    if not found:
        return None
    column = found.group(2) or found.group(3)
    return (f"columns.{column}" if column else found.group(1)), int(found.group(4))


def _placeholder(block: Any) -> bool:
    """A layout's placeholder: one said so, or an empty text or list."""

    if not isinstance(block, dict):
        return False
    if block.get("placeholder"):
        return True
    for key in ("text", "bullets"):
        if key in block:
            return not re.sub(r"[\[\]\",\s]", "", str(block[key] or ""))
    return False


def convert(document: dict[str, Any], action: Mapping[str, Any], base: Path) -> dict[str, Any]:
    """``{"do": "convert", "slide", "shapes"}`` (their places in the slide's list): those shapes
    made a figure on the slide. Answers with the deck as it is then, where the figure is
    (``select``), and what was made, in words (``said``)."""

    from flexo.recognise import document_of, recognise
    from flexo.studio.figure_edit import EditError

    from flexo_talk.document import make_deck

    changed = copy.deepcopy(document)
    try:
        number = int(action.get("slide", -1))
        slide = (changed.get("slides") or [])[number]
    except (IndexError, TypeError, ValueError):
        raise EditError("This slide no longer exists. Someone else may have changed the deck.") from None
    shapes = slide.get("shapes") if isinstance(slide.get("shapes"), list) else []
    picks = sorted({int(index) for index in action.get("shapes") or []})
    if not picks or any(not 0 <= index < len(shapes) for index in picks):
        raise EditError("Choose the shapes on the slide to make a figure of.")
    regions = regions_of(slide)
    if not regions:
        raise EditError("This layout has no room for objects. Choose a different layout first.")
    deck = make_deck(changed.get("deck") or {}, base)
    words = deck.style.body_size * 960.0 / max(deck.style.width, 1.0)
    # (A line chosen glued to what is not -- a shape left on the slide, an object -- ends where
    # that is: the figure has none of it to be glued to.)
    named = {name for at in picks for name in _names(shapes[at])}
    middles = {name: point for shape in shapes for name, point in _middles(shape).items()}
    drawn = [_unglued(copy.deepcopy(shapes[at]), named, middles) for at in picks]
    try:
        found = recognise(
            drawn,
            palette=deck.palette,
            taken={"root"},
            holder="root",
            word_size=words,
            style=str(deck.theme),
        )
    except ValueError as error:
        raise EditError(str(error)) from None
    over = {name for shape in found.shapes for name in _names(shape)}
    for shape in found.shapes:
        _for_figure(shape, over)
    figure = document_of(found, id=_figure_id(changed))

    # Where it goes: the region asked for, in place of its placeholders or among its objects.
    region = str(action.get("region") or "")
    region = region if region in regions else regions[0]
    blocks = _blocks(slide, region)
    replace = action.get("replace")
    replace = all(_placeholder(block) for block in blocks) and bool(blocks) if replace is None else bool(replace)
    index = len(blocks) if action.get("index") is None else int(action["index"])
    index = 0 if replace else max(0, min(index, len(blocks)))
    gone = len(blocks) if replace else 0
    here = _name(region, index)

    # The slide's shapes: the chosen gone; a line of the rest glued to one of them, glued to the
    # figure; one glued to an object after it in its region, to that object where it now is.
    chosen = {name for at in picks for name in _names(shapes[at])}
    points = {name: point for at in picks for name, point in _middles(shapes[at]).items()}
    kept = [shape for at, shape in enumerate(shapes) if at not in picks]
    for shape in kept:
        _reglue(shape, chosen, points, region, index, gone, here)
    if kept:
        slide["shapes"] = kept
    else:
        slide.pop("shapes", None)
    if replace:
        blocks[:] = [{"figure": figure}]
    else:
        blocks.insert(index, {"figure": figure})
    return {
        "document": changed,
        "select": {"slide": number, "region": region, "index": index},
        "said": found.said,
    }


def _for_figure(shape: dict[str, Any], over: set[str]) -> None:
    """A slide's shape made one drawn over a figure: what only a slide's says left out, and an
    end glued to what the figure has none of (a slide's object, a shape not drawn over it with
    this one) where it was."""

    for key in SLIDE_ONLY:
        shape.pop(key, None)
    for key in ("from", "to"):
        end = shape.get(key)
        if not isinstance(end, dict) or end.get("part") is not None:
            continue
        if end.get("shape") is not None and str(end["shape"]) in over:
            continue
        if end.get("at") is not None:
            shape[key] = list(end["at"])
    for child in shape.get("shapes") or [] if shape.get("kind") == "group" else []:
        _for_figure(child, over)


def _unglued(shape: Any, named: set[str], middles: Mapping[str, list[float]]) -> Any:
    """``shape``, its ends glued to what is not among ``named`` (the shapes chosen) where that
    is: where they were kept (``at``), or the middle of the shape they were glued to."""

    if not isinstance(shape, dict):
        return shape
    for key in ("from", "to"):
        end = shape.get(key)
        if not isinstance(end, dict) or (end.get("shape") is not None and str(end["shape"]) in named):
            continue
        point = end.get("at") or middles.get(str(end.get("shape")))
        if point is not None:
            shape[key] = list(point)
    for child in shape.get("shapes") or [] if shape.get("kind") == "group" else []:
        _unglued(child, named, middles)
    return shape


def _figure_id(document: Mapping[str, Any]) -> str:
    """An id for the new figure no other figure of the deck has: ``diagram``, ``diagram-2``."""

    taken = set()
    for slide in document.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        lists = [slide.get(key) for key in ("body", "left", "right")] + list(slide.get("columns") or [])
        for blocks in lists:
            for block in blocks if isinstance(blocks, list) else []:
                figure = block.get("figure") if isinstance(block, dict) else None
                if isinstance(figure, dict) and isinstance(figure.get("figure"), dict):
                    taken.add(str(figure["figure"].get("id")))
    made, number = "diagram", 2
    while made in taken:
        made, number = f"diagram-{number}", number + 1
    return made


def _names(shape: Any) -> list[str]:
    if not isinstance(shape, dict):
        return []
    own = [str(shape["id"])] if shape.get("id") is not None else []
    if shape.get("kind") == "group":
        own += [name for child in shape.get("shapes") or [] for name in _names(child)]
    return own


def _middles(shape: Any) -> dict[str, list[float]]:
    """Where each named shape of ``shape`` is: its middle, for an end glued to it to stay at."""

    from flexo import freeform

    found: dict[str, list[float]] = {}
    if not isinstance(shape, dict):
        return found
    if shape.get("id") is not None:
        try:
            left, top, right, bottom = freeform.bounds(shape)
            found[str(shape["id"])] = [round((left + right) / 2, 1), round((top + bottom) / 2, 1)]
        except (KeyError, TypeError, ValueError):
            pass
    for child in shape.get("shapes") or [] if shape.get("kind") == "group" else []:
        found |= _middles(child)
    return found


def _reglue(
    shape: Any,
    chosen: set[str],
    points: Mapping[str, list[float]],
    region: str,
    index: int,
    gone: int,
    here: str,
) -> None:
    """A slide's shape kept: an end glued to a shape made the figure, glued to the figure; one
    glued to an object of ``region`` after ``index``, to it a place on (or, its placeholders
    replaced, where it was)."""

    if not isinstance(shape, dict):
        return
    for key in ("from", "to"):
        end = shape.get(key)
        if not isinstance(end, dict):
            continue
        if end.get("shape") is not None and str(end["shape"]) in chosen:
            glue = {"object": here, **({"side": end["side"]} if end.get("side") else {})}
            at = end.get("at") or points.get(str(end["shape"]))
            if at is not None:
                glue["at"] = list(at)
            shape[key] = glue
            continue
        place = _place(end.get("object")) if end.get("object") is not None else None
        if place is None or place[0] != region:
            continue
        if gone:
            # (Glued to a placeholder the figure took the place of: where it was.)
            if end.get("at") is not None:
                shape[key] = list(end["at"])
            continue
        if place[1] >= index:
            shape[key] = {**end, "object": _name(region, place[1] + 1)}
    for child in shape.get("shapes") or [] if shape.get("kind") == "group" else []:
        _reglue(child, chosen, points, region, index, gone, here)
