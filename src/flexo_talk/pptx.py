"""PowerPoint shapes from a Flexo drawing: every box, line, and word native and editable.

A drawing (``flexo.drawing``) is placed straight into a slide's shape tree:

- a rectangle is a rectangle or a rounded rectangle, an ellipse an ellipse, so
  they stay editable as what they are; any other path is a freeform shape with
  the same lines and curves;
- an arrowhead is drawn exactly, as a small filled shape grouped with its line
  (PowerPoint's own line ends come in three sizes and would not match);
- text is a text box per label, its lines and runs as written -- italic,
  weight, face, colour, raised scripts -- placed so each baseline lands where
  Flexo set it. A label whose runs step back over one another (stacked
  scripts, an accent's mark) is set as one box per run instead;
- groups keep Flexo's groups and ids, so a component moves as one.

Coordinates are points on the drawing; ``place`` maps them onto the slide (an
offset and a scale), so a figure can be put anywhere on a slide at any size.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache
from xml.sax.saxutils import escape

from flexo.drawing import Drawing, Group, Image, Paint, Segment, Shape, Text
from lxml import etree

EMU_PER_POINT = 12700
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS = f'xmlns:a="{_A}" xmlns:p="{_P}" xmlns:r="{_R}"'

ASCENT = 0.8
"""Where a text box's first baseline sits below its top, as a fraction of the
line spacing, when the spacing is set exactly. Calibrated against renderers."""

SCRIPT_SCALE = 0.65
"""How much smaller a slide program draws a raised or lowered run than its size
says (measured in ONLYOFFICE, which follows PowerPoint): a script is written at
its own size divided by this, so it is drawn at its own size."""

DASHES = {
    "sysDot": (1.0, 1.0),
    "sysDash": (3.0, 1.0),
    "dash": (4.0, 3.0),
    "lgDash": (8.0, 3.0),
    "dot": (1.0, 3.0),
}
"""PowerPoint's preset dashes, as (dash, gap) in line widths. Presets, not
custom dashes: every slide program draws them, and some draw custom ones solid."""


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a drawing goes on a slide: points on the drawing to points on the slide."""

    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0

    def point(self, x: float, y: float) -> tuple[int, int]:
        return (
            round((self.x + x * self.scale) * EMU_PER_POINT),
            round((self.y + y * self.scale) * EMU_PER_POINT),
        )

    def length(self, value: float) -> int:
        return round(value * self.scale * EMU_PER_POINT)


type Pictures = Callable[[bytes, str], str]
"""Adds a picture's bytes (and media type) to the slide; returns its relationship id."""


class _Ids:
    def __init__(self, start: int, pictures: Pictures | None = None) -> None:
        self.next = start
        self.pictures = pictures

    def __call__(self) -> int:
        self.next += 1
        return self.next


def add_drawing(
    tree: etree._Element,
    drawing: Drawing,
    placement: Placement | None = None,
    *,
    name: str | None = None,
    background: bool = True,
    groups: bool = True,
    pictures: Pictures | None = None,
) -> None:
    """Append ``drawing`` to a slide's shape tree (``slide.shapes._spTree``).

    ``groups=False`` lays every shape flat on the slide instead of in Flexo's
    groups -- for renderers that cannot draw a freeform inside a group (macOS
    Quick Look). ``pictures`` adds an image's bytes to the slide (see
    ``slide_pictures``); without it, pictures are left out.
    """

    placement = placement or Placement()
    existing = [int(item) for item in tree.xpath(".//@id") if str(item).isdigit()]
    ids = _Ids(max(existing, default=1), pictures)
    items = [
        item
        for item in drawing.root.items
        if background or not (isinstance(item, Group) and item.id == "layer.background")
    ]
    group = Group(name or drawing.root.id, items)
    element = _group(group, placement, ids)
    if element is None:
        return
    if groups:
        tree.append(element)
        return
    for leaf in element.iter(f"{{{_P}}}sp"):
        tree.append(leaf)


def _group(group: Group, placement: Placement, ids: _Ids) -> etree._Element | None:
    children = [child for item in group.items if (child := _item(item, placement, ids)) is not None]
    if not children:
        return None
    if len(children) == 1 and not group.id:
        return children[0]
    boxes = [_extent(child) for child in children]
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    element = etree.fromstring(
        f"<p:grpSp {_NS}><p:nvGrpSpPr><p:cNvPr id=\"{ids()}\" name=\"{escape(group.id or 'group', {'"': '&quot;'})}\"/>"
        f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>"
        f'<a:off x="{left}" y="{top}"/><a:ext cx="{right - left}" cy="{bottom - top}"/>'
        f'<a:chOff x="{left}" y="{top}"/><a:chExt cx="{right - left}" cy="{bottom - top}"/>'
        f"</a:xfrm></p:grpSpPr></p:grpSp>"
    )
    for child in children:
        element.append(child)
    return element


def _extent(element: etree._Element) -> tuple[int, int, int, int]:
    off = element.find(f".//{{{_A}}}off")
    ext = element.find(f".//{{{_A}}}ext")
    return int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy"))


def _item(item: Shape | Text | Image | Group, placement: Placement, ids: _Ids):
    if isinstance(item, Group):
        return _group(item, placement, ids)
    if isinstance(item, Shape):
        return _shape(item, placement, ids)
    if isinstance(item, Text):
        return _text(item, placement, ids)
    if isinstance(item, Image):
        return _picture(item, placement, ids)
    return None


def slide_pictures(slide) -> Pictures:
    """A ``Pictures`` for a python-pptx slide: PNG and JPEG as they are; an SVG
    as a PNG drawn at print resolution with the SVG beside it, which PowerPoint
    shows (and can turn into shapes) and other programs replace by the PNG."""

    from io import BytesIO

    from pptx.opc.constants import RELATIONSHIP_TYPE
    from pptx.opc.package import Part

    def add(data: bytes, mime: str) -> str:
        if mime == "image/svg+xml":
            raise ValueError("an SVG picture is added with its PNG: use add_svg")
        return slide.part.get_or_add_image_part(BytesIO(data))[1]

    def add_svg(data: bytes) -> str:
        partname = slide.part.package.next_image_partname("svg")
        part = Part(partname, "image/svg+xml", slide.part.package, data)
        return slide.part.relate_to(part, RELATIONSHIP_TYPE.IMAGE)

    add.svg = add_svg  # type: ignore[attr-defined]
    return add


def _picture(image: Image, placement: Placement, ids: _Ids) -> etree._Element | None:
    import base64
    import re
    import struct

    if ids.pictures is None:
        return None
    match = re.match(r"data:([^;,]+);base64,(.*)", image.href, re.DOTALL)
    if match is None:
        return None
    mime, data = match.group(1), base64.b64decode(match.group(2))
    extension = ""
    if mime == "image/svg+xml":
        import resvg_py

        svg = data.decode("utf-8")
        pixels = max(1, round(image.width * placement.scale / 72.0 * 300.0))
        data = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=pixels))
        embed = ids.pictures(data, "image/png")
        svg_id = ids.pictures.svg(svg.encode("utf-8"))  # type: ignore[attr-defined]
        extension = (
            '<a:extLst><a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">'
            '<asvg:svgBlip xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main" '
            f'r:embed="{svg_id}"/></a:ext></a:extLst>'
        )
        x, y, width, height = image.x, image.y, image.width, image.height
    elif mime in {"image/png", "image/jpeg"}:
        embed = ids.pictures(data, mime)
        size = struct.unpack(">II", data[16:24]) if mime == "image/png" else None
        x, y, width, height = image.placed(*size) if size else (image.x, image.y, image.width, image.height)
    else:
        return None
    left, top = placement.point(x, y)
    flips = (' flipH="1"' if image.flip_x else "") + (' flipV="1"' if image.flip_y else "")
    label = escape(image.id or "picture", {'"': "&quot;"})
    return etree.fromstring(
        f'<p:pic {_NS}><p:nvPicPr><p:cNvPr id="{ids()}" name="{label}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{embed}">{extension}</a:blip><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm{flips}><a:off x="{left}" y="{top}"/>'
        f'<a:ext cx="{placement.length(width)}" cy="{placement.length(height)}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
    )


# -- shapes ----------------------------------------------------------------------------


def _colour(value: str) -> str:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return value.upper()


def _fill(colour: str | None, alpha: float) -> str:
    if colour is None:
        return "<a:noFill/>"
    extra = f'<a:alpha val="{round(alpha * 100000)}"/>' if alpha < 0.999 else ""
    return f'<a:solidFill><a:srgbClr val="{_colour(colour)}">{extra}</a:srgbClr></a:solidFill>'


def _line(paint: Paint, placement: Placement) -> str:
    if paint.stroke is None:
        return "<a:ln><a:noFill/></a:ln>"
    width = placement.length(paint.stroke_width)
    cap = {"round": "rnd", "square": "sq"}.get(paint.linecap, "flat")
    join = {"round": "<a:round/>", "bevel": "<a:bevel/>"}.get(paint.linejoin, '<a:miter lim="800000"/>')
    dash = f'<a:prstDash val="{dash_preset(paint)}"/>' if paint.dash else ""
    return (
        f'<a:ln w="{width}" cap="{cap}">'
        f"{_fill(paint.stroke, paint.stroke_opacity * paint.opacity)}{dash}{join}</a:ln>"
    )


def dash_preset(paint: Paint) -> str:
    """The preset dash nearest a line's dash pattern, as the eye sees it.

    A preset's dash includes its caps; a round or square cap adds a line width
    to what an SVG dash draws (a zero-length dash with round caps is a dot).
    """

    import math

    width = max(paint.stroke_width, 1e-6)
    pattern = list(paint.dash) if len(paint.dash) % 2 == 0 else list(paint.dash) * 2
    capped = 1.0 if paint.linecap in {"round", "square"} else 0.0
    on = max(pattern[0] / width + capped, 0.25)
    off = max(pattern[1] / width - capped, 0.25)
    return min(
        DASHES,
        key=lambda name: abs(math.log(on / DASHES[name][0])) + abs(math.log(off / DASHES[name][1])),
    )


def _shape(shape: Shape, placement: Placement, ids: _Ids) -> etree._Element | None:
    parts = [_geometry_shape(shape, placement, ids)]
    for head in shape.arrowheads:
        xs = [x for segment in head.outline for x, _ in segment.points]
        ys = [y for segment in head.outline for _, y in segment.points]
        outline = Shape(
            None, "path", head.paint, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys),
            segments=head.outline,
        )
        parts.append(_geometry_shape(outline, placement, ids, name="arrowhead"))
    parts = [part for part in parts if part is not None]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else _wrap(parts, shape.id, ids)


def _wrap(parts: list[etree._Element], name: str | None, ids: _Ids) -> etree._Element:
    boxes = [_extent(part) for part in parts]
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    element = etree.fromstring(
        f"<p:grpSp {_NS}><p:nvGrpSpPr><p:cNvPr id=\"{ids()}\" name=\"{escape(name or 'line')}\"/>"
        f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>"
        f'<a:off x="{left}" y="{top}"/><a:ext cx="{right - left}" cy="{bottom - top}"/>'
        f'<a:chOff x="{left}" y="{top}"/><a:chExt cx="{right - left}" cy="{bottom - top}"/>'
        f"</a:xfrm></p:grpSpPr></p:grpSp>"
    )
    for part in parts:
        element.append(part)
    return element


def _geometry_shape(
    shape: Shape, placement: Placement, ids: _Ids, *, name: str | None = None
) -> etree._Element | None:
    paint = shape.paint
    if paint.fill is None and paint.stroke is None:
        return None
    x, y = placement.point(shape.x, shape.y)
    width = max(1, placement.length(shape.width))
    height = max(1, placement.length(shape.height))
    if shape.kind == "rect" and shape.radius <= 0:
        geometry = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
    elif shape.kind == "rect":
        # A rounded rectangle's corner is a fraction of its shorter side (at most a half).
        adjust = round(min(0.5, shape.radius / max(1e-6, min(shape.width, shape.height))) * 100000)
        corner = f'<a:gd name="adj" fmla="val {adjust}"/>'
        geometry = f'<a:prstGeom prst="roundRect"><a:avLst>{corner}</a:avLst></a:prstGeom>'
    elif shape.kind == "ellipse":
        geometry = '<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
    else:
        geometry = _custom(shape.segments, shape.x, shape.y, width, height, placement, filled=paint.fill is not None)
    label = escape(name or shape.id or shape.kind, {'"': "&quot;"})
    return etree.fromstring(
        f"<p:sp {_NS}><p:nvSpPr><p:cNvPr id=\"{ids()}\" name=\"{label}\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{width}" cy="{height}"/></a:xfrm>'
        f"{geometry}{_fill(paint.fill, paint.fill_opacity * paint.opacity)}{_line(paint, placement)}</p:spPr>"
        f"</p:sp>"
    )


def _custom(
    segments: tuple[Segment, ...],
    left: float,
    top: float,
    width: int,
    height: int,
    placement: Placement,
    *,
    filled: bool,
) -> str:
    def point(p: tuple[float, float]) -> str:
        return (
            f'<a:pt x="{placement.length(p[0] - left)}" y="{placement.length(p[1] - top)}"/>'
        )

    body = []
    for segment in segments:
        if segment.kind == "M":
            body.append(f"<a:moveTo>{point(segment.points[0])}</a:moveTo>")
        elif segment.kind == "L":
            body.append(f"<a:lnTo>{point(segment.points[0])}</a:lnTo>")
        elif segment.kind == "C":
            body.append(f"<a:cubicBezTo>{''.join(point(p) for p in segment.points)}</a:cubicBezTo>")
        else:
            body.append("<a:close/>")
    fill = "" if filled else ' fill="none"'
    return (
        "<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>"
        '<a:rect l="0" t="0" r="r" b="b"/><a:pathLst>'
        f'<a:path w="{width}" h="{height}"{fill}>{"".join(body)}</a:path>'
        "</a:pathLst></a:custGeom>"
    )


# -- text ------------------------------------------------------------------------------


def _run_xml(run, *, size: float | None = None, baseline: int | None = None) -> str:
    """One run: its face, size, style, colour, and any raise."""

    size = size if size is not None else run.size
    face = escape(_family_name(run), {'"': "&quot;"})
    bold = ' b="1"' if run.weight >= 600 and not _named_weight(run) else ""
    italic = ' i="1"' if run.italic else ""
    raise_ = f' baseline="{baseline}"' if baseline else ""
    return (
        f'<a:r><a:rPr lang="en-GB" sz="{round(size * 100)}"{bold}{italic}{raise_} dirty="0">'
        f"{_fill(run.fill, 1.0)}"
        f'<a:latin typeface="{face}"/><a:ea typeface="{face}"/><a:cs typeface="{face}"/>'
        f"</a:rPr><a:t>{escape(run.text)}</a:t></a:r>"
    )


def _family_name(run) -> str:
    """The family name a slide program finds this run's face by.

    Office picks a face by family name plus bold and italic; a weight between
    (Figtree Medium, a semibold) is its own family there, under the font's
    legacy family name (name ID 1).
    """

    return _legacy_family(run.face.source, run.face.index) or run.face.family


@cache
def _legacy_family(source: str, index: int) -> str | None:
    from fontTools.ttLib import TTCollection, TTFont

    font = (
        TTCollection(source, lazy=True).fonts[index]
        if source.lower().endswith((".ttc", ".otc"))
        else TTFont(source, lazy=True)
    )
    name = font["name"]
    legacy = name.getDebugName(1)
    return str(legacy) if legacy else None


def _named_weight(run) -> bool:
    return _family_name(run) != run.face.family


def _text(text: Text, placement: Placement, ids: _Ids) -> etree._Element | None:
    element = _flat_text(replace(text, angle=0.0) if text.angle else text, placement, ids)
    if element is None or not text.angle:
        return element
    return _turned(element, text, placement)


def _turned(element: etree._Element, text: Text, placement: Placement) -> etree._Element:
    """Turn a placed text about its pivot: a slide program turns a box about its centre,
    so the box moves to where its centre goes and turns there."""

    import math

    turn = math.radians(text.angle)
    cos, sin = math.cos(turn), math.sin(turn)
    px, py = placement.point(*text.pivot)
    boxes = [box for box in element.iter(f"{{{_A}}}xfrm") if box.getparent().tag != f"{{{_P}}}grpSpPr"]
    for box in boxes:
        off, ext = box.find(f"{{{_A}}}off"), box.find(f"{{{_A}}}ext")
        cx = int(off.get("x")) + int(ext.get("cx")) / 2.0
        cy = int(off.get("y")) + int(ext.get("cy")) / 2.0
        tx = px + cos * (cx - px) - sin * (cy - py)
        ty = py + sin * (cx - px) + cos * (cy - py)
        off.set("x", str(round(int(off.get("x")) + tx - cx)))
        off.set("y", str(round(int(off.get("y")) + ty - cy)))
        box.set("rot", str(round(text.angle * 60000) % 21600000))
    if element.tag == f"{{{_P}}}grpSp":
        # The group's own extent follows its turned children.
        own = {f"{{{_P}}}nvGrpSpPr", f"{{{_P}}}grpSpPr"}
        extents = [_extent(child) for child in element if child.tag not in own]
        left, top = min(e[0] for e in extents), min(e[1] for e in extents)
        right, bottom = max(e[0] + e[2] for e in extents), max(e[1] + e[3] for e in extents)
        group = element.find(f"{{{_P}}}grpSpPr/{{{_A}}}xfrm")
        for tag, values in (("off", (left, top)), ("chOff", (left, top))):
            node = group.find(f"{{{_A}}}{tag}")
            node.set("x", str(values[0]))
            node.set("y", str(values[1]))
        for tag in ("ext", "chExt"):
            node = group.find(f"{{{_A}}}{tag}")
            node.set("cx", str(right - left))
            node.set("cy", str(bottom - top))
    return element


def _flat_text(text: Text, placement: Placement, ids: _Ids) -> etree._Element | None:
    if not text.simple:
        # Runs stepped back over each other: each run in a box of its own.
        parts = []
        for line in text.lines:
            for run in line.runs:
                # Each box sits at its run's own baseline, so no run is raised.
                flat = replace(run, shift=0.0)
                single = Text(
                    None, "start", run.x, (type(line)(run.baseline, (flat,)),), run.size,
                    run.family, run.weight, run.fill, run.fill_role, text.line_height, True,
                )
                part = _text_box(single, placement, ids, name="run")
                if part is not None:
                    parts.append(part)
        return _wrap(parts, text.id, ids) if parts else None
    return _text_box(text, placement, ids, name=text.id)


def _text_box(text: Text, placement: Placement, ids: _Ids, *, name: str | None) -> etree._Element | None:
    lines = text.lines
    spacing = text.line_height or text.size * 1.2
    left = min(line.left for line in lines)
    right = max(line.right for line in lines)
    slack = 2.0
    first = lines[0].baseline
    top = first - ASCENT * spacing
    height = spacing * len(lines)
    align = {"start": "l", "middle": "ctr", "end": "r"}[text.anchor]
    paragraphs = []
    for line in lines:
        runs = []
        for run in line.runs:
            if run.shift:
                # A raised or lowered run is drawn smaller than its size: write
                # it larger so it is drawn at its own, raised as a percentage.
                written = run.size / SCRIPT_SCALE
                runs.append(
                    _run_xml(run, size=written, baseline=round(run.shift / written * 100000))
                )
            else:
                runs.append(_run_xml(run))
        paragraphs.append(
            f'<a:p><a:pPr algn="{align}"><a:lnSpc><a:spcPts val="{round(spacing * placement.scale * 100)}"/></a:lnSpc>'
            f'<a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="0"/></a:spcAft></a:pPr>'
            f"{''.join(runs)}</a:p>"
        )
    x, y = placement.point(left - slack, top)
    width = placement.length(right - left + 2 * slack)
    box = placement.length(height)
    label = escape(name or "text", {'"': "&quot;"})
    body = "".join(paragraphs)
    if placement.scale != 1.0:
        body = _scaled(body, placement.scale)
    return etree.fromstring(
        f"<p:sp {_NS}><p:nvSpPr><p:cNvPr id=\"{ids()}\" name=\"{label}\"/><p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{width}" cy="{box}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" rtlCol="0">'
        f"<a:noAutofit/></a:bodyPr><a:lstStyle/>{body}</p:txBody></p:sp>"
    )


def _scaled(body: str, scale: float) -> str:
    import re

    return re.sub(r'sz="(\d+)"', lambda m: f'sz="{round(int(m.group(1)) * scale)}"', body)


# -- lists -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ListRun:
    text: str
    size: float
    weight: int
    italic: bool
    face: object
    fill: str
    shift: float = 0.0


def add_list(tree: etree._Element, deck, layout) -> None:
    """A bulleted list as one text box of bulleted paragraphs, wrapped by the slide program.

    The box is as wide as the list was set, so the words break where Flexo broke
    them when the fonts are the same, and reflow like any list when edited.
    """

    from flexo.text import FontStack, drawn_weight

    existing = [int(item) for item in tree.xpath(".//@id") if str(item).isdigit()]
    ids = _Ids(max(existing, default=1))
    typography = deck.typography(layout.size)
    stack = FontStack(typography)
    palette = deck.palette
    ink = palette.get("ink")
    accent = _colour(palette.get("tone-1-stroke"))
    muted = _colour(palette.get("muted-ink"))
    paragraphs = []
    for position, (level, runs, _baseline) in enumerate(layout.items):
        offset = layout.indent * level + layout.size * 0.95
        mark_at = layout.indent * level + layout.size * 0.12
        pieces = []
        for run in runs:
            weight = drawn_weight(run, None)
            for face, text in stack.segments(run.text, weight, run.italic):
                script = run.baseline_shift != "normal"
                size = layout.size * 0.72 / SCRIPT_SCALE if script else layout.size
                shift = {"super": 33000, "sub": -20000}.get(run.baseline_shift)
                pieces.append(
                    _run_xml(_ListRun(text, size, weight, run.italic, face, ink), baseline=shift)
                )
        before = 0 if position == 0 else round(layout.gap * 100)
        colour = accent if level == 0 else muted
        paragraphs.append(
            f'<a:p><a:pPr marL="{round(offset * EMU_PER_POINT)}" '
            f'indent="{round((mark_at - offset) * EMU_PER_POINT)}" lvl="{min(level, 8)}">'
            f'<a:lnSpc><a:spcPts val="{round(layout.line_height * 100)}"/></a:lnSpc>'
            f'<a:spcBef><a:spcPts val="{before}"/></a:spcBef><a:spcAft><a:spcPts val="0"/></a:spcAft>'
            f'<a:buClr><a:srgbClr val="{colour}"/></a:buClr><a:buSzPct val="{100000 if level == 0 else 85000}"/>'
            f'<a:buFont typeface="Arial"/><a:buChar char="\u2022"/></a:pPr>{"".join(pieces)}</a:p>'
        )
    first = layout.items[0][2] if layout.items else layout.y
    last = layout.items[-1][2] if layout.items else layout.y
    top = first - ASCENT * layout.line_height
    height = last - top + layout.line_height
    element = etree.fromstring(
        f"<p:sp {_NS}><p:nvSpPr><p:cNvPr id=\"{ids()}\" name=\"{escape(layout.id)}\"/>"
        f"<p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr><a:xfrm><a:off x="{round(layout.x * EMU_PER_POINT)}" y="{round(top * EMU_PER_POINT)}"/>'
        f'<a:ext cx="{round((layout.width + 0.25) * EMU_PER_POINT)}" cy="{round(height * EMU_PER_POINT)}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" rtlCol="0">'
        f"<a:noAutofit/></a:bodyPr><a:lstStyle/>{''.join(paragraphs)}</p:txBody></p:sp>"
    )
    tree.append(element)
