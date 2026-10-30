"""A deck's comments: threads on its slides, the objects on them, and the parts of their figures.

A slide's are under its ``comments``; an object's under the object's own (``{figure: ...,
comments: [...]}``), a figure's part's there too, naming the part (``part: encoder``). Each is
a thread as ``flexo.studio.commenting`` writes it. They go where the slide or the object goes
-- moved, dragged to another slide, merged -- and with it when it is deleted. None is drawn,
presented or exported as part of a slide (a PowerPoint carries them as its own comments:
``flexo_talk.pptx_comments``), and a change to one draws nothing again.

Here the deck says where a thread is (``place``: "Slide 3 · Figure"), which mapping a new one
goes in (``holder``), what a change to them did, for the activity ("commented on slide 3":
``note``), and a slide as it is drawn, without them (``uncommented``).
"""

from __future__ import annotations

import re
from typing import Any

REGIONS = ("body", "left", "right", "columns")
OBJECT = re.compile(r"^\s*(body|left|right|columns\[(\d+)\]|columns\.(\d+))\[(\d+)\]\s*$")
_OBJECTS = {"bullets": "List", "text": "Text", "figure": "Figure", "image": "Picture", "table": "Table",
            "math": "Equation", "code": "Code", "quote": "Quote", "callout": "Callout", "stats": "Numbers",
            "gallery": "Gallery", "plot": "Plot", "mechanism": "Mechanism"}


def place(document: Any, path: list[Any]) -> dict[str, Any]:
    """Where the mapping at ``path`` (as ``commenting.threads`` gives one) is: ``label``, in
    words ("Slide 3 · Figure"), and ``where``, as the activity's places are (its slide's
    ``page`` and, an object's, ``object``: ``{region, index}``)."""

    if len(path) < 2 or path[0] != "slides" or not isinstance(path[1], int):
        return {"label": "The deck", "where": None}
    page = path[1] + 1
    where: dict[str, Any] = {"page": page, "label": f"Slide {page}"}
    rest = path[2:]
    region = None
    if len(rest) == 2 and rest[0] in ("body", "left", "right") and isinstance(rest[1], int):
        region, index = rest[0], rest[1]
    elif len(rest) == 3 and rest[0] == "columns" and isinstance(rest[1], int) and isinstance(rest[2], int):
        region, index = f"columns.{rest[1]}", rest[2]
    if region is None:
        return {"label": f"Slide {page}", "where": where}
    block = _at(document, path)
    where["object"] = {"region": region, "index": index}
    return {"label": f"Slide {page} · {_name(block)}", "where": where}


def holder(document: Any, where: dict[str, Any]) -> list[Any]:
    """The path of the mapping a new comment goes in: the slide ``where["slide"]`` (1 is the
    first), or the object ``where["object"]`` on it (``body[0]``, ``columns[1][0]``) -- a
    figure's, for a ``part``. A ``ValueError`` saying what is wrong, if it is not there."""

    slides = document.get("slides") if isinstance(document, dict) else None
    if not isinstance(slides, list) or not slides:
        raise ValueError("The deck has no slides to comment on.")
    slide = where.get("slide")
    if slide is None:
        raise ValueError("Say which slide: slide (1 is the first).")
    if not isinstance(slide, int) or not 1 <= slide <= len(slides):
        raise ValueError(f"There is no slide {slide}; the deck has {len(slides)}.")
    data = slides[slide - 1]
    if not isinstance(data, dict):
        raise ValueError(f"Slide {slide} is not written as a slide (a mapping).")
    named = where.get("object")
    if not named:
        if where.get("part"):
            raise ValueError("Say which object the part is in: object, as body[0].")
        return ["slides", slide - 1]
    found = OBJECT.match(str(named))
    if not found:
        raise ValueError(f"{named!r} names no object: write it as body[0], left[1] or columns[1][0].")
    index = int(found[4])
    if found[1] in ("body", "left", "right"):
        blocks, path = data.get(found[1]), ["slides", slide - 1, found[1], index]
    else:
        column = int(found[2] if found[2] is not None else found[3])
        columns = data.get("columns")
        blocks = columns[column] if isinstance(columns, list) and 0 <= column < len(columns) else None
        path = ["slides", slide - 1, "columns", column, index]
    if not isinstance(blocks, list) or not 0 <= index < len(blocks) or not isinstance(blocks[index], dict):
        raise ValueError(f"Slide {slide} has no object {named}.")
    part = where.get("part")
    if part:
        figure = blocks[index].get("figure")
        ids = {str(node.get("id")) for key in ("nodes", "groups", "edges")
               for node in (figure.get(key) or [] if isinstance(figure, dict) else []) if isinstance(node, dict)}
        if not isinstance(figure, dict):
            raise ValueError(f"{named} on slide {slide} is no figure written in the deck: it has no parts to name.")
        if str(part) not in ids:
            raise ValueError(f"The figure {named} on slide {slide} has no part {part!r}.")
    return path


def uncommented(value: Any) -> Any:
    """A slide (or anything in it) as it is drawn: its comments, and its objects', left out --
    the very value, where it has none."""

    if isinstance(value, dict):
        if "comments" not in value and not any(isinstance(item, dict | list) for item in value.values()):
            return value
        kept = {key: uncommented(item) for key, item in value.items() if key != "comments"}
        return value if len(kept) == len(value) and all(kept[key] is value[key] for key in kept) else kept
    if isinstance(value, list):
        if not any(isinstance(item, dict | list) for item in value):
            return value
        kept_items = [uncommented(item) for item in value]
        return value if all(a is b for a, b in zip(kept_items, value, strict=True)) else kept_items
    return value


def note(old: Any, new: Any, index: int) -> dict[str, Any] | None:
    """What a change to a slide did, as the activity says it, when all it changed was comments
    -- its own, or its objects': "commented on slide 3", "replied to a comment on slide 3",
    "resolved a comment on the figure on slide 3". None when it changed more, or no comment."""

    if not isinstance(old, dict) or not isinstance(new, dict) or old == new:
        return None
    if uncommented(old) != uncommented(new):
        return None
    where: dict[str, Any] = {"page": index + 1, "label": f"Slide {index + 1}"}
    verb, what = "changed a comment", ""
    for path, was, now in _held(old, new):
        if was == now:
            continue
        verb = _verb(was, now)
        if path:
            region, at = path
            blocks = new.get(region) if region != "columns" else None
            if region.startswith("columns."):
                columns = new.get("columns") or []
                column = int(region.split(".")[1])
                blocks = columns[column] if column < len(columns) else []
            block = blocks[at] if isinstance(blocks, list) and at < len(blocks) else None
            what = f" the {_name(block).lower()}"
            where["object"] = {"region": region, "index": at}
        break
    return {"text": f"{verb}{f' on{what}' if what else ''} on slide {index + 1}", "where": where}


def _held(old: dict[str, Any], new: dict[str, Any]):
    """Each holder of comments in two versions of a slide, as ``(path, before, after)``: the
    slide's own (path None), then each object's (``(region, index)``)."""

    yield None, old.get("comments") or [], new.get("comments") or []
    for region in ("body", "left", "right"):
        was, now = old.get(region) or [], new.get(region) or []
        for at in range(max(len(was), len(now))):
            yield (region, at), _comments_of(was, at), _comments_of(now, at)
    old_columns, new_columns = old.get("columns") or [], new.get("columns") or []
    for column in range(max(len(old_columns), len(new_columns))):
        was = old_columns[column] if column < len(old_columns) and isinstance(old_columns[column], list) else []
        now = new_columns[column] if column < len(new_columns) and isinstance(new_columns[column], list) else []
        for at in range(max(len(was), len(now))):
            yield (f"columns.{column}", at), _comments_of(was, at), _comments_of(now, at)


def _comments_of(blocks: Any, at: int) -> list:
    block = blocks[at] if isinstance(blocks, list) and at < len(blocks) else None
    held = block.get("comments") if isinstance(block, dict) else None
    return held if isinstance(held, list) else []


def _verb(was: list, now: list) -> str:
    """What became of a holder's comments: one added, replied to, resolved, opened again, or
    deleted."""

    def ids(items: list) -> dict[str, dict]:
        return {str(item.get("id")): item for item in items if isinstance(item, dict)}

    before, after = ids(was), ids(now)
    if len(after) > len(before):
        return "commented"
    if len(after) < len(before):
        return "deleted a comment"
    for key, item in after.items():
        old = before.get(key)
        if old is None:
            continue
        if bool(item.get("resolved")) != bool(old.get("resolved")):
            return "resolved a comment" if item.get("resolved") else "reopened a comment"
        if len(item.get("replies") or []) > len(old.get("replies") or []):
            return "replied to a comment"
    return "edited a comment"


def _at(document: Any, path: list[Any]) -> Any:
    value = document
    for key in path:
        try:
            value = value[key]
        except (KeyError, IndexError, TypeError):
            return None
    return value


def _name(block: Any) -> str:
    kind = next((key for key in block if key in _OBJECTS), "") if isinstance(block, dict) else ""
    return _OBJECTS.get(kind, "Object")
