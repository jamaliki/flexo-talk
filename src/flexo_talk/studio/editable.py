"""Make Editable on a slide: a drawing placed as a picture made the slide's own shapes.

A picture whose file is a drawing (an SVG; a PDF's or an Illustrator file's page) -- one
placed before the studio read drawings as shapes, or with Paste as Picture -- is one object:
its boxes can't be dragged. ``editable`` makes it the shapes it draws (``flexo.studio.editable``)
in one group in the slide's ``shapes``, exactly where the slide drew it and at the size it was
drawn (read from the slide drawn as the studio draws it), as the picture showed it: its words
in the deck's figure font, its texts and colours as it changed them, its colours the theme's
where they are the theme's, its words in the slide's markup. What else it had goes with it
where a shape can carry it:

- built in on a click (``build``): the group builds in, the first of the slide's shapes that
  do -- the click straight after the slide's objects' that build (said, if an object after it
  built later and so now builds before it);
- cropped: the shapes wholly outside the part kept are left out (said), those part outside
  kept whole; a mask is left off (said);
- its caption: a box of words under the group, where the caption was;
- a line glued to the picture: glued to the group; one glued to an object after it in its
  region, to that object where it is now; a zoom inset of it, taken away (an inset shows an
  object, not shapes; said).

The picture goes from its region, which closes up after it as when an object is deleted --
in a slide of columns, the other column stays as it was. The drawing's file stays in the
folder. ``{"do": "editable", "at": {"slide", "region", "index"}}`` makes one picture
editable; ``{"do": "editable", "all": true}`` every drawing placed as a picture in the deck.
One step either way, answered with the deck as it is then, the group chosen (``select``) and
what was done in words (``said``).
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flexo_talk.studio.convert import OBJECT, regions_of

SHAPE_FRAME = 960.0
"""A slide's shapes' units across (``flexo_talk.document``): its points scaled to 960."""


def _region_name(region: str) -> str:
    """The deck's name for a region the document names (``columns.1`` is ``column2``)."""

    return f"column{int(region.split('.', 1)[1]) + 1}" if region.startswith("columns.") else region


def _glue_name(region: str, index: int) -> str:
    if region.startswith("columns."):
        return f"columns[{region.split('.', 1)[1]}][{index}]"
    return f"{region}[{index}]"


def _place(name: object) -> tuple[str, int] | None:
    found = OBJECT.fullmatch(str(name or "").strip())
    if not found:
        return None
    column = found.group(2) or found.group(3)
    return (f"columns.{column}" if column else found.group(1)), int(found.group(4))


def _blocks(slide: Mapping[str, Any], region: str) -> list[Any]:
    if region.startswith("columns."):
        columns = slide.get("columns") or []
        index = int(region.split(".", 1)[1])
        return columns[index] if index < len(columns) and isinstance(columns[index], list) else []
    value = slide.get(region)
    return value if isinstance(value, list) else []


def drawings_in(document: Mapping[str, Any]) -> list[tuple[int, str, int]]:
    """Every picture of the deck whose file is a drawing: ``(slide, region, index)``."""

    from flexo.studio.editable import is_drawing

    found = []
    for number, slide in enumerate(document.get("slides") or []):
        if not isinstance(slide, dict):
            continue
        for region in regions_of(slide):
            for index, block in enumerate(_blocks(slide, region)):
                if isinstance(block, dict) and is_drawing(block.get("image")):
                    found.append((number, region, index))
    return found


def editable(document: dict[str, Any], action: Mapping[str, Any], base: Path) -> dict[str, Any]:
    """The pictures ``action`` names made the slide's shapes (see the module's words)."""

    from flexo.studio.figure_edit import EditError

    if action.get("all"):
        targets = drawings_in(document)
        if not targets:
            raise EditError("No slide has a drawing placed as a picture.")
    else:
        at = action.get("at") or {}
        try:
            targets = [(int(at["slide"]), str(at["region"]), int(at["index"]))]
        except (KeyError, TypeError, ValueError):
            raise EditError("Choose a picture of a drawing to make editable.") from None
        if targets[0] not in drawings_in(document):
            raise EditError(
                "This picture is not a drawing (an SVG, a PDF or an Illustrator file), or it is no longer there."
            )
    changed = copy.deepcopy(document)
    by_slide: dict[int, list[tuple[str, int]]] = {}
    for number, region, index in targets:
        by_slide.setdefault(number, []).append((region, index))
    made: list[dict[str, Any]] = []
    failed: list[str] = []
    notes: list[str] = []
    for number, places in by_slide.items():
        done = _slide(changed, document, number, places, base, failed, notes)
        made += [{"slide": number, **item} for item in done]
    if not made:
        raise EditError(
            failed[0] if len(failed) == 1 else "None of the drawings could be made shapes: " + "; ".join(failed)
        )
    shapes = sum(item["count"] for item in made)
    if action.get("all"):
        slides = len({item["slide"] for item in made})
        said = (
            f"{len(made)} {'drawing' if len(made) == 1 else 'drawings'} on {slides} "
            f"{'slide' if slides == 1 else 'slides'} made editable: {shapes:,} shapes"
        )
    else:
        said = f"Made editable: {made[0]['count']:,} shapes, where the picture was"
    words = [said, *dict.fromkeys(notes)]
    if failed:
        words.append(f"{len(failed)} could not be: " + "; ".join(failed))
    # (Each drawing is one group, chosen: its pieces are a step away.)
    words.append("Ungroup (\u21e7\u2318G) to move its pieces one by one")
    first = made[0]
    return {
        "document": changed,
        "select": {"slide": first["slide"], "shape": first["at"]},
        "said": ". ".join(word.rstrip(".") for word in words) + ".",
        "made": len(made),
        "shapes": shapes,
        "failed": failed,
    }


def _slide(
    changed: dict[str, Any],
    document: Mapping[str, Any],
    number: int,
    places: list[tuple[str, int]],
    base: Path,
    failed: list[str],
    notes: list[str],
) -> list[dict[str, Any]]:
    """The pictures ``places`` of slide ``number`` made its shapes, in ``changed``: each where
    the slide (as ``document`` has it) drew it."""

    from flexo.studio.editable import NotEditable, ids_of, keeper, shapes_of_picture

    drawn = _drawn(document, number, base)
    deck, slide_id, root = drawn["deck"], drawn["id"], drawn["root"]
    k = deck.style.width / SHAPE_FRAME
    slide = changed["slides"][number]
    shapes = slide.get("shapes") if isinstance(slide.get("shapes"), list) else []
    taken = ids_of(shapes)
    roles = dict(deck.palette.paints)
    out: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    gone: list[tuple[str, int, str]] = []
    for region, index in places:
        data = _blocks(slide, region)[index]
        name = Path(str(data.get("image"))).name
        block = _deck_block(deck, number, region, index)
        if block is None:
            failed.append(f"{name} on slide {number + 1} isn\u2019t there")
            continue
        found = _picture(root, f"{slide_id}.{_region_name(region)}.{index}")
        if found is None:
            failed.append(f"{name} on slide {number + 1} isn\u2019t drawn")
            continue
        _, whole, kept = found
        box = [value / k for value in whole]
        kept_box = [value / k for value in kept] if data.get("crop") is not None else None
        try:
            made = shapes_of_picture(
                Path(block.source),
                box,
                restyle=block.restyle,
                family=deck.figure_family,
                roles=roles,
                markup="slide",
                keep=keeper(base, Path(str(data.get("image"))).stem),
                taken=taken,
                kept_box=kept_box,
            )
        except NotEditable as error:
            failed.append(f"{name} on slide {number + 1}: {str(error).rstrip('.')}")
            continue
        group = made.group
        taken += ids_of([group])
        if data.get("caption"):
            group["shapes"].append(_caption(data["caption"], kept, root, slide_id, region, deck, k))
        if data.get("build"):
            group["build"] = True
            if _later_builds(slide, region, index):
                notes.append("It builds in after the slide\u2019s objects that build now")
        if made.cropped:
            notes.append(
                f"{made.cropped:,} {'shape' if made.cropped == 1 else 'shapes'} its crop hid "
                f"{'is' if made.cropped == 1 else 'are'} left out"
            )
        if data.get("mask") is not None:
            notes.append("Its mask is left off")
        if data.get("description"):
            notes.append("Its description is left off")
        if made.kept:
            notes.append(
                f"{len(made.kept)} {'part' if len(made.kept) == 1 else 'parts'} no shape draws "
                f"{'is' if len(made.kept) == 1 else 'are'} kept as {'a picture' if len(made.kept) == 1 else 'pictures'}"
            )
        groups.append(group)
        gone.append((region, index, str(group["id"])))
        out.append({"count": made.count - 1, "region": region, "index": index})
    if not groups:
        return []
    # The pictures go from their regions -- the last first, so each is where it was -- and what
    # was glued to them, or to an object after them, follows.
    for region, index, ident in sorted(gone, key=lambda item: -item[1]):
        _blocks(slide, region).pop(index)
        insets = _reglue(shapes, region, index, ident)
        if insets:
            notes.append("A zoom inset of it is taken away")
    # Under the shapes drawn over it, as the picture was; the first of those that build.
    shapes[0:0] = groups
    slide["shapes"] = shapes
    for place, item in enumerate(out):
        item["at"] = place
    return out


def _drawn(document: Mapping[str, Any], number: int, base: Path) -> dict[str, Any]:
    """Slide ``number`` drawn as the studio draws it while it is edited: where its pictures
    are, as the page shows them."""

    from flexo.studio.figure_edit import EditError

    from flexo_talk.compose import EDITING, PLACEHOLDERS, STANDING_ASIDE, render_slide
    from flexo_talk.document import deck_from_document

    errors: list[Any] = []
    deck = deck_from_document(copy.deepcopy(dict(document)), base, errors=errors)
    slide = deck.slides[number]
    tokens = (EDITING.set(True), PLACEHOLDERS.set(True), STANDING_ASIDE.set(True))
    try:
        svg = render_slide(deck, slide).svg
    except Exception as error:
        raise EditError(f"Slide {number + 1} can\u2019t be drawn: {error}") from None
    finally:
        for variable, token in zip((EDITING, PLACEHOLDERS, STANDING_ASIDE), tokens, strict=True):
            variable.reset(token)
    return {"deck": deck, "id": slide.id, "root": ET.fromstring(svg)}


def _deck_block(deck: Any, number: int, region: str, index: int) -> Any:
    from flexo_talk.deck import _Image

    try:
        block = deck.slides[number].regions[_region_name(region)].blocks[index]
    except (IndexError, KeyError):
        return None
    return block if isinstance(block, _Image) else None


def _numbers(value: str | None) -> list[float] | None:
    try:
        found = [float(item) for item in (value or "").split()]
    except ValueError:
        return None
    return found if len(found) == 4 else None


def _picture(root: ET.Element, identifier: str) -> tuple[ET.Element, list[float], list[float]] | None:
    """The picture drawn as ``identifier`` (its caption apart): its whole box and the part
    of it shown, in the slide's points."""

    found = {item.get("id"): item for item in root.iter() if item.get("id") in (identifier, f"{identifier}.picture")}
    element = found.get(f"{identifier}.picture", found.get(identifier))
    if element is None:
        return None
    whole = _numbers(element.get("data-flexo-whole"))
    kept = _numbers(element.get("data-flexo-box")) or whole
    if whole is None or kept is None:
        return None
    return element, whole, kept


def _caption(
    words: str, kept: list[float], root: ET.Element, slide_id: str, region: str, deck: Any, k: float
) -> dict[str, Any]:
    """The picture's caption as a box of words where it was: under it, centred under it, a size
    smaller, as wide as it could be within its region (``compose._caption``)."""

    from flexo_talk.compose import CAPTION_GAP

    size = deck.style.small_size
    room = None
    for item in root.iter():
        if item.get("id") == f"{slide_id}.{_region_name(region)}":
            room = _numbers(item.get("data-flexo-box"))
            break
    x, y, width, height = kept
    middle = x + width / 2.0
    reach = max(min(middle - room[0], room[0] + room[2] - middle), width / 2.0, 1.0) if room else width / 2.0
    top = y + height + size * CAPTION_GAP
    return {
        "kind": "text",
        "at": [round((middle - reach) / k, 2), round(top / k, 2)],
        "width": round(2.0 * reach / k, 2),
        "text": str(words),
        "font_size": round(size / k, 2),
        "align": "middle",
    }


def _later_builds(slide: Mapping[str, Any], region: str, index: int) -> bool:
    """Whether an object after the picture builds in (whole, or a list an item at a time): it
    did so before the picture's click, and the group, a shape, builds after it now."""

    regions = regions_of(slide)
    here = (regions.index(region), index)
    return any(
        (regions.index(each), at) > here
        for each in regions
        for at, block in enumerate(_blocks(slide, each))
        if isinstance(block, dict) and (block.get("build") or block.get("reveal"))
    )


def _reglue(shapes: list[Any], region: str, index: int, ident: str) -> int:
    """The slide's shapes once the picture at ``index`` of ``region`` is gone: an end glued to
    it glued to its group (``ident``), one glued to an object after it to that object where it
    is now; an inset of it taken away, one of an object after it following that object. How many
    insets were taken away."""

    removed = 0
    for at in range(len(shapes) - 1, -1, -1):
        shape = shapes[at]
        if not isinstance(shape, dict):
            continue
        if shape.get("kind") == "inset":
            place = _place(shape.get("of"))
            if place is not None and place[0] == region:
                if place[1] == index:
                    shapes.pop(at)
                    removed += 1
                elif place[1] > index:
                    shape["of"] = _glue_name(region, place[1] - 1)
            continue
        for key in ("from", "to"):
            end = shape.get(key)
            if not isinstance(end, dict) or end.get("object") is None:
                continue
            place = _place(end.get("object"))
            if place is None or place[0] != region:
                continue
            if place[1] == index:
                glue = {"shape": ident, **{name: end[name] for name in ("side", "at") if name in end}}
                shape[key] = glue
            elif place[1] > index:
                shape[key] = {**end, "object": _glue_name(region, place[1] - 1)}
        if shape.get("kind") == "group":
            removed += _reglue(shape.setdefault("shapes", []), region, index, ident)
    return removed


__all__ = ["drawings_in", "editable"]
