"""Zoom insets (``flexo.insets``) in a PowerPoint: a cropped picture and PowerPoint's own shapes.

A slide program cannot draw part of its slide again, magnified, so what an inset shows is a
picture: a photograph or a micrograph the picture it magnifies is, cropped natively to the
region (PowerPoint's Crop: the rest is there still, to be shown again); a figure, a plot or
a drawing a picture of its vectors (an SVG, with a PNG beside it for programs that draw no
SVG) exactly the box's size. The frame round the region, the lines joining it to the box,
and the box's outline and its label are PowerPoint's own rectangles, lines and words, the
whole grouped and named as the studio names it ("Zoom Inset").
"""

from __future__ import annotations

import base64
from dataclasses import replace

from flexo.drawing import Drawing, Group, Image, Shape, Text, ink_bounds
from lxml import etree

from flexo_talk.deck import ShapeLayout
from flexo_talk.pptx import Placement, _Ids, _picture


def inset_views(group: Group) -> dict[str, Group]:
    """What each zoom inset on a slide shows, by the id its inset is drawn with: its view."""

    found: dict[str, Group] = {}
    for item in group.items:
        if not isinstance(item, Group):
            continue
        if item.data.get("data-flexo-inset") == "view" and item.id:
            found[item.id.removesuffix(".view")] = item
        else:
            found |= inset_views(item)
    return found


def view_picture(view: Group, placement: Placement, ids: _Ids) -> etree._Element | None:
    """What an inset's view shows, as one picture: a photograph it magnifies cropped natively,
    anything else drawn as a picture of exactly its box."""

    box = view.clip
    if box is None:
        left, top, right, bottom = ink_bounds(Drawing(0.0, 0.0, Group(None, [view])))
        box = (left, top, right, bottom)
    if box[2] - box[0] < 0.01 or box[3] - box[1] < 0.01:
        return None
    pictures = [item for item in _walk(view) if isinstance(item, Image)]
    drawn = [item for item in _walk(view) if isinstance(item, Shape | Text)]
    if len(pictures) == 1 and not drawn and not pictures[0].oval and not pictures[0].outline:
        picture = pictures[0]
        if not picture.href.startswith("data:image/svg"):
            clip = box if picture.clip is None else _within(picture.clip, box)
            return _picture(replace(picture, clip=clip), placement, ids)
    from flexo.insets import view_svg

    data = base64.b64encode(view_svg(view, box).encode()).decode()
    left, top, right, bottom = box
    image = Image(view.id, left, top, right - left, bottom - top, f"data:image/svg+xml;base64,{data}", "none")
    return _picture(image, placement, ids)


def inset_parts(writer, layout: ShapeLayout, placement: Placement) -> list[etree._Element]:
    """A slide's zoom inset as PowerPoint's shapes (for ``pptx_shapes.ShapeWriter``): its region's
    frame and the lines joining it to its box, the box's fill, what it shows, and the box's
    outline with its words -- the shape a line glued to the inset is joined to."""

    from flexo import freeform, insets

    spec, made, shown = layout.spec, layout.geometry, layout.inset
    parts: list[etree._Element | None] = []
    if shown is not None:
        rx, ry, rw, rh = shown.region
        frame = freeform.normalised({"kind": "rectangle", "at": [rx, ry], "size": [rw, rh], "fill": "none",
                                     **insets.piece(spec, "frame")})
        parts.append(writer._boxed(ShapeLayout(f"{layout.id}.frame", frame, freeform.geometry(frame), layout.scale),
                                   placement))
        joining = insets.piece(spec, "connector")
        if joining["line"] not in (None, "none") and joining["line_width"] > 0:
            for number, (a, b) in enumerate(shown.connectors):
                line = freeform.normalised({"kind": "line", "from": list(a), "to": list(b), **joining})
                parts.append(writer._line(ShapeLayout(f"{layout.id}.connector{number}", line,
                                                      freeform.geometry(line), layout.scale), placement))
    box = {**spec, "kind": "rectangle", "corner": 0.0}
    if freeform.paint(spec.get("fill"), writer.palette)[0] is not None:
        parts.append(writer._boxed(ShapeLayout(f"{layout.id}.box", {**box, "line": "none"}, made, layout.scale),
                                   placement))
    view = writer.views.get(layout.id)
    if view is not None and writer.pictures is not None:
        # (Numbered as the writer numbers its shapes, so none is numbered twice.)
        ids = _Ids(writer.next, writer.pictures)
        scaled = Placement(scale=1.0)
        parts.append(view_picture(view, scaled, ids))
        writer.next = max(writer.next, ids.next)
    parts.append(writer._boxed(ShapeLayout(layout.id, {**box, "fill": "none", "shadow": False}, made, layout.scale,
                                           words=layout.words), placement))
    return [part for part in parts if part is not None]


def _walk(group: Group):
    for item in group.items:
        if isinstance(item, Group):
            yield from _walk(item)
        else:
            yield item


def _within(one: tuple[float, float, float, float], other: tuple[float, float, float, float]):
    return (max(one[0], other[0]), max(one[1], other[1]), min(one[2], other[2]), min(one[3], other[3]))
