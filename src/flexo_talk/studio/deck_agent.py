"""A deck as an agent reads it in brief, names what it sees on a slide, finds what is selected in
it, and hears what its edit did -- the deck kind's ``outline``, ``excerpt``, ``marks``,
``selected``, ``at_step`` and ``report``, for flexo's agent tools (``flexo.studio.agent``).

Paths are written as the YAML has them: ``slides[2].body[0]`` is the third slide's first
object, ``slides[3].columns[1][0]`` the first object of its second column, and a figure's part
is named by its id (``slides[2].right[0].figure.nodes[1]``, ``encoder``)."""

from __future__ import annotations

import json
import re
from typing import Any

from flexo.studio.agent_look import Mark
from flexo.studio.agent_read import excerpt as excerpt_of
from flexo.studio.agent_read import todos, warnings

SVG_REGIONS = {"body": "body", "left": "left", "right": "right"}
"""A slide's places for objects, by the name its drawing gives them (a column's: column1...)."""


def regions(slide: Any) -> list[tuple[str, str, list]]:
    """A slide's places for objects: each as its path in the YAML (``body``, ``columns[1]``),
    its name in the slide's drawing (``body``, ``column2``), and its objects."""

    if not isinstance(slide, dict):
        return []
    found = []
    for key, drawn in SVG_REGIONS.items():
        if isinstance(slide.get(key), list):
            found.append((key, drawn, slide[key]))
    if isinstance(slide.get("columns"), list):
        for index, column in enumerate(slide["columns"]):
            if isinstance(column, list):
                found.append((f"columns[{index}]", f"column{index + 1}", column))
    return found


def _object(block: Any) -> str:
    from flexo_talk.studio import _object_name

    return _object_name(block)


def _clip(text: Any, limit: int = 60) -> str:
    from flexo_talk.studio import _clipped

    return _clipped(" ".join(str(text or "").split()), limit)


def _figure_of(block: Any, figures: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str]:
    """A figure block's figure: how it is named, the figure itself where the deck holds it
    (written in the block, or among the deck's ``figures``), and its path in the YAML."""

    value = block.get("figure") if isinstance(block, dict) else None
    if isinstance(value, dict):
        figure = value.get("figure") if isinstance(value.get("figure"), dict) else {}
        return str(figure.get("id") or "figure"), value, ".figure"
    if isinstance(value, str) and value.startswith("#"):
        shared = figures.get(value[1:])
        return value, shared if isinstance(shared, dict) else None, ""
    return str(value or ""), None, ""


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _said_block(block: Any, figures: dict[str, Any]) -> str:
    name = _object(block)
    if isinstance(block, dict) and "figure" in block:
        called, figure, _ = _figure_of(block, figures)
        parts = len(figure.get("nodes") or []) if figure else 0
        name += f" ({called}{f', {_count(parts, 'part')}' if parts else ''})"
    if isinstance(block, dict):
        if block.get("at") is not None:
            name += " placed"
        if block.get("hide") is True:
            name += " hidden"
    return name


def outline(document: Any, drawing: Any) -> list[str]:
    """A deck in brief: a line a slide -- its number, title, layout, objects, shapes, build
    steps, notes, TODOs and warnings -- then its shared figures and what the drawing warns of."""

    from flexo_talk.studio import _label

    document = document if isinstance(document, dict) else {}
    deck = document.get("deck") if isinstance(document.get("deck"), dict) else {}
    slides = document.get("slides") if isinstance(document.get("slides"), list) else []
    figures = document.get("figures") if isinstance(document.get("figures"), dict) else {}
    settings = ", ".join(f"{key} {deck[key]}" for key in ("theme", "look", "palette") if key in deck)
    lines = [f"{_count(len(slides), 'slide')}{f'; {settings}' if settings else ''}."]
    pages = drawing.pages if len(drawing.pages) == len(slides) else [None] * len(slides)
    warned: dict[str, int] = {}
    for message in drawing.messages:
        if message.page and message.severity in ("error", "warning"):
            warned[message.page] = warned.get(message.page, 0) + 1
    for number, (slide, page) in enumerate(zip(slides, pages, strict=True), start=1):
        if not isinstance(slide, dict):
            lines.append(f"{number}. (not a slide: {_clip(json.dumps(slide, default=str), 40)})")
            continue
        layout = str(slide.get("layout") or "content")
        title = _clip(_label(slide)) or "(no title)"
        head = f"{number}. {f'[{layout}] ' if layout != 'content' else ''}{title}"
        said = []
        for key, _, blocks in regions(slide):
            if blocks:
                said.append(f"{key}: " + ", ".join(_said_block(block, figures) for block in blocks))
        extras = []
        shapes = slide.get("shapes") if isinstance(slide.get("shapes"), list) else []
        if shapes:
            extras.append(_count(len(shapes), "shape"))
        if page is not None and page.steps > 1:
            extras.append(f"{page.steps} build steps")
        if slide.get("skip"):
            extras.append("skipped")
        if slide.get("notes"):
            extras.append("notes")
        found = todos(slide)
        if found:
            extras.append(_count(found, "TODO"))
        count = warned.get(page.id, 0) if page is not None else 0
        if count:
            extras.append(f"! {_count(count, 'warning')}")
        body = " -- " + "; ".join(said) if said else ""
        lines.append(head + body + (" · " + " · ".join(extras) if extras else ""))
    if figures:
        shared = ", ".join(
            f"{name} ({_count(len(figure.get('nodes') or []), 'part')})" if isinstance(figure, dict) else name
            for name, figure in figures.items()
        )
        lines.append(f"Shared figures (figures:, named '#name' from a slide): {shared}.")
    found = todos({key: value for key, value in document.items() if key != "slides"})
    if found:
        lines.append(f"TODOs outside the slides: {found}.")
    numbers = {page.id: number for number, page in enumerate(drawing.pages, start=1)}
    lines += warnings(drawing.messages, numbers)
    return lines


def excerpt(text: str, numbers: list[int]) -> str:
    """Some of a deck's slides, as its whole text has them."""

    return excerpt_of(text, "slides", numbers)


FIELDS = {"title": "title", "subtitle": "subtitle", "byline": "author"}
"""A slide's words drawn by name (its ``{slide}.title``...), by the key they are written in."""


def marks(document: Any, number: int, page: Any) -> list[Mark]:
    """What to outline on a slide: its title and other words, each object, each figure's parts
    and shapes, and the slide's own shapes."""

    slides = document.get("slides") if isinstance(document, dict) else None
    if not isinstance(slides, list) or not 1 <= number <= len(slides) or not isinstance(slides[number - 1], dict):
        return []
    figures = document.get("figures") if isinstance(document.get("figures"), dict) else {}
    slide, sid, at = slides[number - 1], page.id, f"slides[{number - 1}]"
    found: list[Mark] = []
    statement = slide.get("layout") == "statement"
    for drawn, key in FIELDS.items():
        if statement and drawn == "title":
            key = "words"
        elif statement and drawn == "byline":
            key = "by"
        elif drawn == "byline" and "author" not in slide and "date" in slide:
            key = "date"
        found.append(Mark(f"{sid}.{drawn}", f"{at}.{key}", key, "", "field"))
    for key, drawn, blocks in regions(slide):
        for index, block in enumerate(blocks):
            label, prefix = f"{key}[{index}]", f"{sid}.{drawn}.{index}"
            found.append(Mark(prefix, f"{at}.{label}", label, _object(block), "object"))
            found += _parts(block, figures, prefix, f"{at}.{label}")
    for index, shape in enumerate(slide.get("shapes") or []):
        if not isinstance(shape, dict):
            continue
        label = f"shapes[{index}]" + (f" {shape['id']}" if shape.get("id") else "")
        found.append(Mark(f"{sid}.shapes.{index}", f"{at}.shapes[{index}]", label, str(shape.get("kind", "")), "shape"))
    return found


def _parts(block: Any, figures: dict[str, Any], prefix: str, path: str) -> list[Mark]:
    """A figure object's parts, groups and shapes, as drawn in it (``{prefix}.{id}``)."""

    called, figure, inner = _figure_of(block, figures)
    if figure is None:
        return []
    where = f"figures.{called[1:]}" if called.startswith("#") else f"{path}{inner}"
    root = str((figure.get("figure") or {}).get("root") or "root") if isinstance(figure.get("figure"), dict) else "root"
    found = []
    for key, sort in (("groups", "object"), ("nodes", "part")):
        for index, item in enumerate(figure.get(key) or []):
            identifier = str(item.get("id", "")) if isinstance(item, dict) else ""
            if identifier and identifier != root:
                what = "group" if key == "groups" else str(item.get("kind") or "block")
                found.append(Mark(f"{prefix}.{identifier}", f"{where}.{key}[{index}]", identifier, what, sort))
    for index, shape in enumerate(figure.get("shapes") or []):
        if isinstance(shape, dict):
            drawn = f"{prefix}.{shape['id']}" if shape.get("id") else f"{prefix}.shapes.{index}"
            label = f"shapes[{index}]" + (f" {shape['id']}" if shape.get("id") else "")
            found.append(Mark(drawn, f"{where}.shapes[{index}]", label, str(shape.get("kind", "")), "shape"))
    return found


def selected(document: Any, where: dict[str, Any]) -> str | None:
    """Where a person is in a deck (their page's ``where``: its ``page``, the ``block`` chosen,
    ``body[1]`` or ``columns.0[1]``, the ``field`` typed in, the ``part`` of the object chosen)
    as a path in its YAML, with what it is: "slides[2].right[0] (Figure), part encoder"."""

    page = where.get("page")
    slides = document.get("slides") if isinstance(document, dict) else None
    if not isinstance(page, int) or not isinstance(slides, list) or not 1 <= page <= len(slides):
        return None
    at = f"slides[{page - 1}]"
    block = re.fullmatch(r"(body|left|right|columns\.(\d+))\[(\d+)\]", str(where.get("block") or ""))
    if block is None:
        field = where.get("field")
        return f"{at}.{field}" if field else f"{at} (the slide)"
    region = f"columns[{block[2]}]" if block[2] is not None else block[1]
    index = int(block[3])
    slide = slides[page - 1] if isinstance(slides[page - 1], dict) else {}
    blocks = next((items for key, _, items in regions(slide) if key == region), [])
    what = f" ({_object(blocks[index])})" if 0 <= index < len(blocks) else ""
    part = f", part {where['part']}" if where.get("part") else ""
    return f"{at}.{region}[{index}]{what}{part}"


def at_step(page: Any, step: int) -> str:
    """A slide's drawing as it stands at build ``step``, as the PDF of its steps draws it."""

    from flexo_talk.deck import RenderedSlide

    return RenderedSlide(None, page.svg, [], steps=page.steps).at_step(step)  # type: ignore[arg-type]


def report(kind: Any, before: Any, after: Any) -> dict[str, Any]:
    """What an edit did to a deck: each change as the activity list says it (the ``kind``'s
    ``describe``), every slide, object and shape it deleted, and the slides to look at
    (numbered as after it)."""

    from flexo_talk.studio import _slide_pairs, _stable

    notes = kind.describe(before, after)
    pages = sorted(
        {
            note["where"]["page"]
            for note in notes
            if isinstance(note.get("where"), dict)
            and isinstance(note["where"].get("page"), int)
        }
    )
    old = (before if isinstance(before, dict) else {}).get("slides") or []
    new = (after if isinstance(after, dict) else {}).get("slides") or []
    deleted: list[str] = []
    everywhere = {_stable(block) for slide in new for _, _, blocks in regions(slide) for block in blocks}
    for step, a, b in _slide_pairs(old, new):
        if step == "deleted":
            for index in a:
                deleted.append(_slide_said(old[index], index))
        elif step in ("changed", "moved") and old[a] != new[b]:
            deleted += _gone_from(old[a], new[b], a, everywhere)
    old_figures = (before if isinstance(before, dict) else {}).get("figures") or {}
    new_figures = (after if isinstance(after, dict) else {}).get("figures") or {}
    if isinstance(old_figures, dict) and isinstance(new_figures, dict):
        deleted += [f"the shared figure {name}" for name in old_figures if name not in new_figures]
    return {"changes": [note["text"] for note in notes], "deleted": deleted, "pages": pages, "noun": "slide"}


def _slide_said(slide: Any, index: int) -> str:
    from flexo_talk.studio import _label

    title = _clip(_label(slide), 40)
    count = sum(len(blocks) for _, _, blocks in regions(slide))
    held = f", with {count} object{'s' if count != 1 else ''}" if count else ""
    return f"slide {index + 1}{f' “{title}”' if title else ''}{held}"


def _gone_from(old: Any, new: Any, index: int, everywhere: set[str]) -> list[str]:
    """What an edit took off a slide (numbered ``index`` before it): objects gone from the deck
    (not moved, nor changed in place), its shapes, and its figures' parts."""

    from flexo_talk.studio import _stable

    gone = []
    places = {key: blocks for key, _, blocks in regions(new)}
    for key, _, blocks in regions(old):
        now = places.get(key, [])
        kept = {_stable(block) for block in now}
        lost = [block for block in blocks if _stable(block) not in kept and _stable(block) not in everywhere]
        # (As many fewer as there are: the others are the ones changed in place.)
        fewer = len(blocks) - len(now)
        for block in lost[: max(fewer, 0)]:
            gone.append(f"the {_object(block).lower()} on slide {index + 1} ({key})")
    # A figure written in the slide, by its id wherever it is on the slide now: its parts.
    figures = {_figure_id(block): block for _, _, blocks in regions(new) for block in blocks}
    for _, _, blocks in regions(old):
        for block in blocks:
            if (name := _figure_id(block)) is not None and name in figures:
                gone += _parts_gone(block, figures[name], index)
    shapes = [old.get("shapes"), new.get("shapes")] if isinstance(old, dict) and isinstance(new, dict) else [[], []]
    was, now = (value if isinstance(value, list) else [] for value in shapes)
    if len(now) < len(was):
        fewer = len(was) - len(now)
        gone.append(f"{fewer} shape{'s' if fewer > 1 else ''} of slide {index + 1}")
    return gone


def _figure_id(block: Any) -> str | None:
    """The id of a figure written in an object, if it holds one."""

    figure = block.get("figure") if isinstance(block, dict) else None
    named = figure.get("figure") if isinstance(figure, dict) else None
    return str(named.get("id")) if isinstance(named, dict) and named.get("id") is not None else None


def _parts_gone(old: Any, new: Any, index: int) -> list[str]:
    """A figure written in a slide's object, its parts deleted by an edit."""

    if not (isinstance(old, dict) and isinstance(new, dict)):
        return []
    was, now = old.get("figure"), new.get("figure")
    if not (isinstance(was, dict) and isinstance(now, dict)):
        return []
    kept = {str(node.get("id")) for node in now.get("nodes") or [] if isinstance(node, dict)}
    return [
        f"the part {node.get('id')} of the figure on slide {index + 1}"
        for node in was.get("nodes") or []
        if isinstance(node, dict) and str(node.get("id")) not in kept
    ]
