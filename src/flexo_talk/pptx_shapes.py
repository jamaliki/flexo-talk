"""A slide's shapes (``Slide.shape``) as PowerPoint's own: each the shape PowerPoint has of
its kind -- a rectangle, a rounded one, an oval, a triangle, a diamond, a pentagon, a star,
a parallelogram, a trapezoid, a block arrow, a chevron, a plus, a cloud, a speech bubble, a
brace, a bracket -- its settings (a corner, a slant, a callout's tail) as PowerPoint's
adjustments, so it is edited there as what it is; any other kind a freeform of the same
outline, a path too (its pieces, holes and all, filled as it fills them). Its words are its
own text, in it, as PowerPoint sets words in that shape. A
straight line or an elbow is a connector, joined to the shapes its ends are glued to, its
arrowheads its line ends; any other line a freeform with the same ends. A shape that builds
in is named as the slide's drawing names it, so its click finds it (``export.write_pptx``).
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from lxml import etree

from flexo_talk.deck import ShapeLayout
from flexo_talk.pptx import (
    _HEADS,
    _NS,
    EMU_PER_POINT,
    Placement,
    _colour,
    _fitted,
    _Ids,
    _picture,
    _runs_xml,
)

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

_BOX_SITES = {"top": 0, "left": 1, "bottom": 2, "right": 3}
_OVAL_SITES = {"top": 0, "left": 2, "bottom": 4, "right": 6}
"""Where a connector meets a shape, by side, as PowerPoint numbers them: a rectangle's, a
rounded one's, a diamond's and a freeform's written here; an oval's."""

_DASHES = {"dashed": "dash", "dotted": "sysDot"}
_CAPS = {"butt": "flat", "round": "rnd", "square": "sq"}


def _hundred(value: float) -> int:
    return round(value * 100000)


def _custom_dash(dashes: object, width: float) -> str:
    """A dash pattern of its own lengths as PowerPoint's: each a share of the line's width."""

    if isinstance(dashes, str) or not isinstance(dashes, list | tuple) or len(dashes) < 2 or width <= 0:
        return ""
    pairs = list(zip(dashes[0::2], dashes[1::2], strict=False))
    return "<a:custDash>" + "".join(
        f'<a:ds d="{max(1, round(on / width * 100000))}" sp="{max(1, round(off / width * 100000))}"/>'
        for on, off in pairs
    ) + "</a:custDash>"


class ShapeWriter:
    """Writes a slide's shapes into its shape tree, numbering each as it goes, so a line
    written later is joined to a shape written earlier -- behind the slide's words, or over
    them -- by the number PowerPoint knows it by."""

    def __init__(self, tree: etree._Element, deck, palette) -> None:
        self.tree = tree
        self.deck = deck
        self.palette = palette
        existing = [int(item) for item in tree.xpath(".//@id") if str(item).isdigit()]
        self.next = max(existing, default=1)
        self.numbers: dict[str, int] = {}
        """The number each shape is written with, by the id it is drawn with."""
        self.sites: dict[str, dict[str, int]] = {}
        """Where a connector may be joined to each shape, by side: those PowerPoint draws
        sites on as these are drawn."""
        self.pictures = None
        """How a picture's bytes are added to the slide (``pptx.slide_pictures``): a picture
        shape (a drawing's part kept as drawn) is left out without it."""
        self.pending: list[tuple[etree._Element, str, str, str]] = []
        """Connectors' ends waiting for the shape they are glued to to be written (one later
        in the list, or over the slide's words where the line is behind them): the
        connector's properties, which end, the shape, and its side."""
        self.views: dict = {}
        """What each zoom inset shows, by its id: its view, as the slide's drawing reads it."""
        self.pictures = None
        """Adds a picture to the slide (``pptx.slide_pictures``): a zoom inset's view."""

    def number(self) -> int:
        self.next += 1
        return self.next

    def write(self, layouts: list[ShapeLayout]) -> list[str]:
        """Each shape, in order, appended to the tree; the names of what was written."""

        # (Numbered after whatever else is on the slide by now.)
        existing = [int(item) for item in self.tree.xpath(".//@id") if str(item).isdigit()]
        self.next = max(self.next, *existing) if existing else self.next
        names = []
        for layout in layouts:
            for element in self._shape(layout):
                self.tree.append(element)
                names.append(_name_of(element))
        self._join()
        return names

    def _join(self) -> None:
        """Each connector's end joined to the shape it is glued to, once that is written."""

        waiting = []
        for joined, tag, target, side in self.pending:
            site = self.sites.get(target, {}).get(side)
            if target in self.numbers and site is not None:
                etree.SubElement(joined, f"{{{_A}}}{tag}", id=str(self.numbers[target]), idx=str(site))
            elif target not in self.numbers:
                waiting.append((joined, tag, target, side))
        # (A start is joined before an end, as PowerPoint writes them.)
        for joined in {id(item[0]): item[0] for item in self.pending}.values():
            ends = sorted(joined, key=lambda end: 0 if etree.QName(end).localname == "stCxn" else 1)
            for end in ends:
                joined.remove(end)
                joined.append(end)
        self.pending = waiting

    # -- one shape --

    def _shape(self, layout: ShapeLayout) -> list[etree._Element]:
        from flexo import freeform

        spec = layout.spec
        kind = str(spec["kind"])
        placement = Placement(scale=layout.scale)
        if kind == "group":
            parts = [part for child in layout.children for part in self._shape(child)]
            return [self._group(parts, layout.id)] if parts else []
        if kind == "inset":
            from flexo_talk.pptx_insets import inset_parts

            parts = inset_parts(self, layout, placement)
            return [self._group(parts, layout.id)] if len(parts) > 1 else parts
        form = freeform.family(kind)
        if kind == "picture":
            made = self._picture(layout, placement)
            return [made] if made is not None else []
        if form in ("box", "text"):
            return [self._boxed(layout, placement)]
        if form == "path":
            return [self._path(layout, placement)]
        made = [self._line(layout, placement)]
        if layout.words is not None:
            made.append(self._label(layout, placement))
        return [part for part in made if part is not None]

    def _boxed(self, layout: ShapeLayout, placement: Placement) -> etree._Element:
        spec, made = layout.spec, layout.geometry
        x, y, w, h = made.box
        number = self.number()
        self.numbers[layout.id] = number
        geometry, sites = self._geometry(spec, made, placement)
        if sites is not None:
            flip = spec.get("flip") if spec.get("kind") != "bubble" else None
            sites = dict(sites)
            if flip in ("horizontal", "both"):
                sites["left"], sites["right"] = sites["right"], sites["left"]
            if flip in ("vertical", "both"):
                sites["top"], sites["bottom"] = sites["bottom"], sites["top"]
            self.sites[layout.id] = sites
        left, top = placement.point(x, y)
        turn = f' rot="{round(made.turn * 60000) % 21600000}"' if made.turn else ""
        flips = ""
        if spec.get("kind") != "bubble" and spec.get("kind") != "text":
            flip = spec.get("flip")
            flips = (' flipH="1"' if flip in ("horizontal", "both") else "") + (
                ' flipV="1"' if flip in ("vertical", "both") else "")
        text = ' txBox="1"' if spec["kind"] == "text" else ""
        return etree.fromstring(
            f'<p:sp {_NS}><p:nvSpPr><p:cNvPr id="{number}" name="{escape(layout.id)}"/><p:cNvSpPr{text}/><p:nvPr/>'
            f"</p:nvSpPr><p:spPr><a:xfrm{turn}{flips}><a:off x=\"{left}\" y=\"{top}\"/>"
            f'<a:ext cx="{max(1, placement.length(w))}" cy="{max(1, placement.length(h))}"/></a:xfrm>'
            f"{geometry}{self._fill(spec, closed=True)}{self._ln(spec, placement)}{self._shadow(spec, placement)}"
            f"</p:spPr>{self._body(layout, placement)}</p:sp>"
        )

    def _picture(self, layout: ShapeLayout, placement: Placement) -> etree._Element | None:
        """A picture shape (a drawing's part kept as drawn) as a picture: its file's bitmap,
        or an SVG with its picture beside it, as a slide's pictures are written."""

        import base64
        from pathlib import Path

        from flexo.drawing import Image

        spec, made = layout.spec, layout.geometry
        source = Path(str(spec.get("source") or ""))
        if self.pictures is None or not source.is_file():
            return None
        kind = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
            source.suffix.lower())
        if kind is None:
            return None
        data = source.read_bytes()
        if kind == "image/svg+xml":
            from flexo.artwork import load_artwork

            data = load_artwork("picture", str(source)).markup.encode("utf-8")
        x, y, w, h = made.box
        flip = spec.get("flip")
        image = Image(layout.id, x, y, w, h, f"data:{kind};base64,{base64.b64encode(data).decode()}", "none",
                      flip_x=flip in ("horizontal", "both"), flip_y=flip in ("vertical", "both"))
        ids = _Ids(self.next, self.pictures)
        drawn = _picture(image, placement, ids)
        self.next = ids.next
        if drawn is None:
            return None
        frame = drawn.find(f".//{{{_A}}}xfrm")
        if made.turn and frame is not None:
            frame.set("rot", str(round(made.turn * 60000) % 21600000))
        alpha = float(spec.get("opacity", 1.0))
        blip = drawn.find(f".//{{{_A}}}blip")
        if alpha < 0.999 and blip is not None:
            blip.insert(0, etree.fromstring(f'<a:alphaModFix xmlns:a="{_A}" amt="{_hundred(alpha)}"/>'))
        self.numbers[layout.id] = int(drawn.find(f".//{{{_P}}}cNvPr").get("id"))
        return drawn

    def _geometry(self, spec: dict, made, placement: Placement) -> tuple[str, dict[str, int] | None]:
        """PowerPoint's preset of the shape's kind, with its settings as adjustments -- or, where
        it has none, the outline as a freeform, its words' room and its sides' sites with it."""

        kind = spec["kind"]
        x, y, w, h = made.box
        ss = max(min(w, h), 1e-9)

        def preset(name: str, **adjust: float) -> str:
            guides = "".join(f'<a:gd name="{key}" fmla="val {round(value)}"/>' for key, value in adjust.items())
            return f'<a:prstGeom prst="{name}"><a:avLst>{guides}</a:avLst></a:prstGeom>'

        corner = float(spec.get("corner") or 0.0)
        if kind in ("rectangle", "rounded-rectangle", "highlight", "text"):
            if corner <= 0 or kind == "text":
                return preset("rect"), _BOX_SITES
            return preset("roundRect", adj=_hundred(min(corner, ss / 2.0) / ss)), _BOX_SITES
        if kind in ("ellipse", "ring"):
            return preset("ellipse"), _OVAL_SITES
        if kind == "triangle":
            return preset("triangle", adj=_hundred(float(spec["apex"]))), None
        if kind == "right-triangle":
            return preset("rtTriangle"), None
        if kind == "diamond" or (kind == "polygon" and int(spec["sides"]) == 4):
            return preset("diamond"), _BOX_SITES
        if kind == "polygon" and int(spec["sides"]) == 3:
            return preset("triangle", adj=50000), None
        if kind == "polygon" and int(spec["sides"]) == 5:
            return preset("pentagon"), None
        if kind == "star" and int(spec["tips"]) in (4, 5):
            return preset(f"star{int(spec['tips'])}", adj=_hundred(float(spec["ratio"]) / 2.0)), None
        if kind == "parallelogram":
            return preset("parallelogram", adj=_hundred(float(spec["slant"]))), None
        if kind == "trapezoid":
            return preset("trapezoid", adj=_hundred(float(spec["inset"]))), None
        arrows = {"arrow-right": "rightArrow", "arrow-left": "leftArrow", "arrow-up": "upArrow",
                  "arrow-down": "downArrow", "arrow-left-right": "leftRightArrow"}
        if kind in arrows:
            return preset(arrows[kind], adj1=_hundred(float(spec["shaft"])), adj2=_hundred(float(spec["head"]))), None
        if kind == "chevron":
            return preset("chevron", adj=_hundred(float(spec["point"]))), None
        if kind == "plus":
            return preset("plus", adj=_hundred(float(spec["arm"]))), None
        if kind == "cloud":
            return preset("cloud"), None
        if kind == "bubble":
            from flexo import freeform

            tail = spec.get("tail") or [x + w * 0.25, y + h * 1.45]
            tx, ty = freeform._unturned(tail, (x + w / 2.0, y + h / 2.0), made.turn)
            adjust = {"adj1": _hundred((tx - x - w / 2.0) / max(w, 1e-9)),
                      "adj2": _hundred((ty - y - h / 2.0) / max(h, 1e-9))}
            body = spec.get("body")
            if body == "oval":
                return preset("wedgeEllipseCallout", **adjust), None
            if body == "rectangle":
                return preset("wedgeRectCallout", **adjust), None
            return preset("wedgeRoundRectCallout", **adjust, adj3=_hundred(min(corner, ss / 2.0) / ss)), None
        return self._custom(made, placement), _BOX_SITES

    def _custom(self, made, placement: Placement, *, filled: bool = True, area: bool = True) -> str:
        """The outline as a freeform in its own box, unturned, its words' room said."""

        x, y, w, h = made.box
        width, height = max(1, placement.length(w)), max(1, placement.length(h))

        def point(px: float, py: float) -> str:
            return f'<a:pt x="{placement.length(px - x)}" y="{placement.length(py - y)}"/>'

        body = []
        for segment in made.segments:
            if segment[0] == "M":
                body.append(f"<a:moveTo>{point(segment[1], segment[2])}</a:moveTo>")
            elif segment[0] == "L":
                body.append(f"<a:lnTo>{point(segment[1], segment[2])}</a:lnTo>")
            elif segment[0] == "C":
                body.append(f"<a:cubicBezTo>{point(*segment[1:3])}{point(*segment[3:5])}{point(*segment[5:7])}</a:cubicBezTo>")
            else:
                body.append("<a:close/>")
        room = made.area if area and made.area else made.box
        rect = (f'<a:rect l="{placement.length(room[0] - x)}" t="{placement.length(room[1] - y)}" '
                f'r="{placement.length(room[0] + room[2] - x)}" b="{placement.length(room[1] + room[3] - y)}"/>')
        joins = "".join(f'<a:cxn ang="{angle}"><a:pos x="{px}" y="{py}"/></a:cxn>' for angle, px, py in (
            ("3cd4", "hc", "t"), ("cd2", "l", "vc"), ("cd4", "hc", "b"), ("0", "r", "vc")))
        return (f"<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst>{joins}</a:cxnLst>{rect}<a:pathLst>"
                f'<a:path w="{width}" h="{height}"{"" if filled else " fill=\"none\""}>{"".join(body)}</a:path>'
                f"</a:pathLst></a:custGeom>")

    def _path(self, layout: ShapeLayout, placement: Placement) -> etree._Element:
        """A path as a freeform of its outline in its box, turned as it is (mirrored already),
        its words in it, a connector's sites at its sides' middles; its pieces gathered into
        the paths PowerPoint fills each even-odd, so it is filled as its fill rule fills it.
        Open at an end, its arrowheads are its line's ends -- or, where PowerPoint has none
        of that kind, shapes of their own, with it in a group."""

        from flexo import freeform, pathdata

        spec, made = layout.spec, layout.geometry
        heads = [spec.get(end) or "none" for end in ("start", "end")]
        native = all(head == "none" or head in _HEADS for head in heads)
        bare = made if not made.heads else freeform.geometry({**spec, "start": "none", "end": "none"})
        number = self.number()
        self.numbers[layout.id] = number
        self.sites[layout.id] = _BOX_SITES
        x, y, w, h = made.box
        left, top = placement.point(x, y)
        width, height = max(1, placement.length(w)), max(1, placement.length(h))

        def point(px: float, py: float) -> str:
            return f'<a:pt x="{placement.length(px - x)}" y="{placement.length(py - y)}"/>'

        paths = []
        drawn = bare if native else made
        for group in pathdata.fill_groups(drawn.segments, str(spec.get("fill_rule") or "nonzero")):
            body = []
            for segment in group:
                if segment[0] == "M":
                    body.append(f"<a:moveTo>{point(segment[1], segment[2])}</a:moveTo>")
                elif segment[0] == "L":
                    body.append(f"<a:lnTo>{point(segment[1], segment[2])}</a:lnTo>")
                elif segment[0] == "C":
                    body.append(f"<a:cubicBezTo>{point(*segment[1:3])}{point(*segment[3:5])}"
                                f"{point(*segment[5:7])}</a:cubicBezTo>")
                else:
                    body.append("<a:close/>")
            paths.append(f'<a:path w="{width}" h="{height}">{"".join(body)}</a:path>')
        joins = "".join(f'<a:cxn ang="{angle}"><a:pos x="{px}" y="{py}"/></a:cxn>' for angle, px, py in (
            ("3cd4", "hc", "t"), ("cd2", "l", "vc"), ("cd4", "hc", "b"), ("0", "r", "vc")))
        geometry = (f'<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst>{joins}</a:cxnLst>'
                    f'<a:rect l="0" t="0" r="{width}" b="{height}"/><a:pathLst>{"".join(paths)}</a:pathLst>'
                    f"</a:custGeom>")
        turn = f' rot="{round(made.turn * 60000) % 21600000}"' if made.turn else ""
        name = layout.id if native else f"{layout.id}.outline"
        shape = etree.fromstring(
            f'<p:sp {_NS}><p:nvSpPr><p:cNvPr id="{number}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/>'
            f'</p:nvSpPr><p:spPr><a:xfrm{turn}><a:off x="{left}" y="{top}"/><a:ext cx="{width}" cy="{height}"/>'
            f"</a:xfrm>{geometry}{self._fill(spec, closed=True)}"
            f"{self._ln(spec, placement, heads if native else None)}{self._shadow(spec, placement)}</p:spPr>"
            f"{self._body(layout, placement)}</p:sp>"
        )
        if native:
            return shape
        # (Heads drawn as shapes, turned as the path is about its box's middle.)
        parts = [shape]
        for head in made.heads:
            turned = [(segment[0], *(value for index in range(1, len(segment), 2)
                                     for value in freeform._turned(segment[index:index + 2], made.centre, made.turn)))
                      for segment in head.segments]
            parts.append(self._head(layout.id, freeform.Head(head.end, head.kind, turned, head.filled, head.stroked,
                                                              head.tip, head.angle), spec, placement))
        return self._group(parts, layout.id)

    # -- lines --

    def _line(self, layout: ShapeLayout, placement: Placement) -> etree._Element | None:
        from flexo import freeform

        spec, made = layout.spec, layout.geometry
        kind = spec["kind"]
        if kind in ("brace", "bracket"):
            return self._brace(layout, placement)
        heads = [spec.get(end) or "none" for end in ("start", "end")]
        native = all(head == "none" or head in _HEADS for head in heads)
        bare = freeform.geometry({**spec, "start": "none", "end": "none"}, made.ends)
        if native and kind in ("line", "arrow", "double-arrow", "elbow", "dimension", "scale-bar") and made.ends:
            corners = [point for point in freeform.flattened(bare.segments, 1)]
            connector = self._connector(layout, corners, heads, placement)
            if connector is not None:
                return connector
        number = self.number()
        self.numbers[layout.id] = number
        if native:
            return self._freeform(layout.id, number, bare, spec, placement, heads)
        # Heads PowerPoint has no line end for (a bar, a ring): drawn as shapes, with the line.
        parts = [self._freeform(f"{layout.id}.line", number, made, spec, placement, ["none", "none"])]
        for head in made.heads:
            parts.append(self._head(layout.id, head, spec, placement))
        return self._group(parts, layout.id)

    def _connector(self, layout: ShapeLayout, corners: list, heads: list[str], placement: Placement
                   ) -> etree._Element | None:
        spec = layout.spec
        kept = [corners[0]]
        for point in corners[1:]:
            if math.dist(point, kept[-1]) > 1e-6:
                kept.append(point)
        if len(kept) < 2:
            return None
        fitted = _fitted(kept)
        if fitted is None:
            return None
        preset, (left, top, width, height), turn, flip_h, flip_v, adjust = fitted
        number = self.number()
        self.numbers[layout.id] = number
        x, y = placement.point(left, top)
        guides = "".join(f'<a:gd name="adj{index}" fmla="val {round(value * 100000)}"/>'
                         for index, value in enumerate(adjust, 1))
        turned = (f' rot="{turn * 60000}"' if turn else "") + (' flipH="1"' if flip_h else "") + (
            ' flipV="1"' if flip_v else "")
        made = etree.fromstring(
            f'<p:cxnSp {_NS}><p:nvCxnSpPr><p:cNvPr id="{number}" name="{escape(layout.id)}"/>'
            f"<p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>"
            f'<p:spPr><a:xfrm{turned}><a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{placement.length(width)}" cy="{placement.length(height)}"/></a:xfrm>'
            f'<a:prstGeom prst="{preset}"><a:avLst>{guides}</a:avLst></a:prstGeom>'
            f"{self._ln(spec, placement, heads)}{self._shadow(spec, placement)}</p:spPr></p:cxnSp>"
        )
        joined = made.find(f".//{{{_P}}}cNvCxnSpPr")
        for tag, glue in zip(("stCxn", "endCxn"), layout.glue, strict=True):
            if glue is not None:
                self.pending.append((joined, tag, *glue))
        return made

    def _freeform(self, name: str, number: int, made, spec: dict, placement: Placement, heads: list[str]
                  ) -> etree._Element:
        x, y, w, h = made.box
        left, top = placement.point(x, y)
        geometry = self._custom(made, placement, filled=made.closed, area=False)
        fill = self._fill(spec, closed=made.closed)
        return etree.fromstring(
            f'<p:sp {_NS}><p:nvSpPr><p:cNvPr id="{number}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{left}" y="{top}"/>'
            f'<a:ext cx="{max(1, placement.length(w))}" cy="{max(1, placement.length(h))}"/></a:xfrm>'
            f"{geometry}{fill}{self._ln(spec, placement, heads)}{self._shadow(spec, placement)}</p:spPr></p:sp>"
        )

    def _head(self, owner: str, head, spec: dict, placement: Placement) -> etree._Element:
        from flexo import freeform

        points = [point for segment in head.segments for point in zip(segment[1::2], segment[2::2], strict=True)]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        made = freeform.Geometry(head.segments, head.filled, (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
        painted = {**spec, "fill": spec.get("line") if head.filled else "none", "fill_opacity": 1.0,
                   "line": spec.get("line") if head.stroked else "none", "dash": "solid"}
        return self._freeform(f"{owner}.head-{head.end}", self.number(), made, painted, placement, ["none", "none"])

    def _brace(self, layout: ShapeLayout, placement: Placement) -> etree._Element:
        """A brace or a bracket as PowerPoint's own (leftBrace, leftBracket), turned so its tip
        points where it does: its curl and its tip's place as their adjustments."""

        spec, made = layout.spec, layout.geometry
        (ax, ay), (bx, by) = made.ends
        length = math.dist((ax, ay), (bx, by))
        depth = float(spec.get("depth") or 0.0)
        reach = abs(depth)
        ux, uy = ((bx - ax) / length, (by - ay) / length) if length > 1e-9 else (1.0, 0.0)
        sign = 1.0 if depth >= 0 else -1.0
        tx, ty = uy * sign, -ux * sign  # the way its tip points
        turn = math.degrees(math.atan2(-ty, -tx))
        # Its own top-to-bottom, turned: along the span one way or the other.
        down = (-math.sin(math.radians(turn)), math.cos(math.radians(turn)))
        along = down[0] * ux + down[1] * uy >= 0
        centre = ((ax + bx) / 2.0 + tx * reach / 2.0, (ay + by) / 2.0 + ty * reach / 2.0)
        w, h = max(reach, 0.01), max(length, 0.01)
        ss = min(w, h)
        if spec["kind"] == "brace":
            tip = float(spec.get("tip", 0.5))
            tip_at = tip * length
            curl = min(float(spec.get("curl") or 0.0) * reach, tip_at / 2.0, (length - tip_at) / 2.0)
            guides = (f'<a:gd name="adj1" fmla="val {_hundred(curl / ss)}"/>'
                      f'<a:gd name="adj2" fmla="val {_hundred(tip if along else 1.0 - tip)}"/>')
            name = "leftBrace"
        else:
            curl = min(float(spec.get("curl") or 0.0) * reach, length / 2.0)
            guides = f'<a:gd name="adj" fmla="val {_hundred(curl / ss)}"/>'
            name = "leftBracket"
        number = self.number()
        self.numbers[layout.id] = number
        left, top = placement.point(centre[0] - w / 2.0, centre[1] - h / 2.0)
        rotation = round(turn * 60000) % 21600000
        made_line = (f'<p:sp {_NS}><p:nvSpPr><p:cNvPr id="{number}" name="{escape(layout.id)}"/><p:cNvSpPr/><p:nvPr/>'
                     f'</p:nvSpPr><p:spPr><a:xfrm rot="{rotation}"><a:off x="{left}" y="{top}"/>'
                     f'<a:ext cx="{max(1, placement.length(w))}" cy="{max(1, placement.length(h))}"/></a:xfrm>'
                     f'<a:prstGeom prst="{name}"><a:avLst>{guides}</a:avLst></a:prstGeom><a:noFill/>'
                     f"{self._ln(spec, placement)}{self._shadow(spec, placement)}</p:spPr></p:sp>")
        return etree.fromstring(made_line)

    def _label(self, layout: ShapeLayout, placement: Placement) -> etree._Element:
        """A line's words, beside it, in a box of their own: named as its caption is, so it
        builds in with it."""

        words = layout.words
        x, y, w, h = words.box
        cx, cy = x + w / 2.0, y + h / 2.0
        if words.angle:
            turn = math.radians(words.angle)
            px, py = words.pivot
            cx, cy = (px + math.cos(turn) * (cx - px) - math.sin(turn) * (cy - py),
                      py + math.sin(turn) * (cx - px) + math.cos(turn) * (cy - py))
        left, top = placement.point(cx - w / 2.0, cy - h / 2.0)
        rotation = f' rot="{round(words.angle * 60000) % 21600000}"' if words.angle else ""
        return etree.fromstring(
            f'<p:sp {_NS}><p:nvSpPr><p:cNvPr id="{self.number()}" name="{escape(layout.id)}.caption"/>'
            f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm{rotation}><a:off x="{left}" y="{top}"/>'
            f'<a:ext cx="{max(1, placement.length(w))}" cy="{max(1, placement.length(h))}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f"{self._text(words, placement, wrap=False)}</p:sp>"
        )

    # -- painting --

    def _fill(self, spec: dict, *, closed: bool) -> str:
        from flexo import freeform

        colour = freeform.paint(spec.get("fill"), self.palette)[0] if closed else None
        if colour is None:
            return "<a:noFill/>"
        alpha = float(spec.get("fill_opacity", 1.0)) * float(spec.get("opacity", 1.0))
        if isinstance(spec.get("fill"), dict):
            return self._gradient(spec["fill"], alpha)
        extra = f'<a:alpha val="{_hundred(alpha)}"/>' if alpha < 0.999 else ""
        return f'<a:solidFill><a:srgbClr val="{_colour(colour)}">{extra}</a:srgbClr></a:solidFill>'

    def _gradient(self, fill: dict, alpha: float) -> str:
        """A gradient fill as PowerPoint's: its stops, its way (a linear one's angle, which
        PowerPoint measures as Flexo does, clockwise from left to right) or its middle (a
        radial one's, out to the box's corners, where Flexo's reaches its radius)."""

        from flexo import freeform, gradients

        stops = gradients.stops_of(fill, lambda colour: freeform.paint(colour, self.palette))
        reach = 1.0
        if fill.get("gradient") == "radial":
            centre = fill.get("centre") or [0.5, 0.5]
            rx, ry = gradients.radii(fill)
            far = max(math.hypot(max(centre[0], 1 - centre[0]), max(centre[1], 1 - centre[1])), 1e-6)
            reach = min(1.0, math.hypot(rx, ry) / math.sqrt(2.0) / far) if rx and ry else 1.0
        listed = "".join(
            f'<a:gs pos="{round(min(1.0, offset * reach) * 100000)}"><a:srgbClr val="{_colour(colour)}">'
            + (f'<a:alpha val="{_hundred(opacity * alpha)}"/>' if opacity * alpha < 0.999 else "")
            + "</a:srgbClr></a:gs>"
            for offset, colour, opacity, _ in stops
        )
        if fill.get("gradient") == "radial":
            u, v = fill.get("centre") or [0.5, 0.5]
            way = (f'<a:path path="circle"><a:fillToRect l="{_hundred(u)}" t="{_hundred(v)}" '
                   f'r="{_hundred(1 - u)}" b="{_hundred(1 - v)}"/></a:path>')
        else:
            way = f'<a:lin ang="{round(float(fill.get("angle", 0.0)) * 60000) % 21600000}" scaled="0"/>'
        return f'<a:gradFill rotWithShape="1"><a:gsLst>{listed}</a:gsLst>{way}</a:gradFill>'

    def _ln(self, spec: dict, placement: Placement, heads: list[str] | None = None) -> str:
        from flexo import freeform

        colour = freeform.paint(spec.get("line"), self.palette)[0]
        width = float(spec.get("line_width") or 0.0)
        if colour is None or width <= 0:
            return "<a:ln><a:noFill/></a:ln>"
        alpha = float(spec.get("opacity", 1.0)) * float(spec.get("line_opacity", 1.0))
        extra = f'<a:alpha val="{_hundred(alpha)}"/>' if alpha < 0.999 else ""
        written = spec.get("dash") or "solid"
        dash = _DASHES.get(str(written)) if isinstance(written, str) else None
        join = {"round": "<a:round/>", "bevel": "<a:bevel/>"}.get(str(spec.get("join")), '<a:miter lim="800000"/>')
        ends = ""
        length, breadth = freeform.head_size(spec)
        for tag, kind in zip(("headEnd", "tailEnd"), heads or ["none", "none"], strict=True):
            if kind in _HEADS:
                ends += f'<a:{tag} type="{_HEADS[kind]}" w="{_size(breadth, width)}" len="{_size(length, width)}"/>'
        return (f'<a:ln w="{placement.length(width)}" cap="{_CAPS.get(str(spec.get("cap")), "flat")}">'
                f'<a:solidFill><a:srgbClr val="{_colour(colour)}">{extra}</a:srgbClr></a:solidFill>'
                f'{f"<a:prstDash val=\"{dash}\"/>" if dash else _custom_dash(written, width)}{join}{ends}</a:ln>')

    def _shadow(self, spec: dict, placement: Placement) -> str:
        if not spec.get("shadow"):
            return ""
        look = self.deck.layout_style
        colour = _colour(self.palette.get("shadow"))
        offset = look.shadow_offset.points
        blur = 0 if look.shadow_style == "hard" else round(look.shadow_spread.points * 2.0 * EMU_PER_POINT)
        alpha = _hundred(min(1.0, look.shadow_opacity * (1.6 if look.shadow_style != "hard" else 1.0)))
        return (f'<a:effectLst><a:outerShdw blurRad="{blur}" dist="{round(offset * math.sqrt(2) * EMU_PER_POINT)}" '
                f'dir="2700000" algn="tl" rotWithShape="0"><a:srgbClr val="{colour}"><a:alpha val="{alpha}"/>'
                f"</a:srgbClr></a:outerShdw></a:effectLst>")

    # -- words --

    def _body(self, layout: ShapeLayout, placement: Placement) -> str:
        if layout.words is None:
            # (A shape PowerPoint may type in, with nothing in it yet.)
            if layout.spec.get("kind") == "text":
                return ""
            return ('<p:txBody><a:bodyPr rtlCol="0" anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/>'
                    '<a:endParaRPr lang="en-GB" dirty="0"/></a:p></p:txBody>')
        wrap = layout.spec.get("kind") != "text" or bool(layout.spec.get("width"))
        return self._text(layout.words, placement, wrap=wrap)

    def _text(self, words, placement: Placement, *, wrap: bool) -> str:
        from flexo.ir.semantic import TextRun
        from flexo.text import font_stack

        size = words.size * placement.scale
        typography = self.deck.typography(size)
        if words.family and words.family != typography.family:
            typography = typography.with_family(words.family)
        stack = font_stack(typography)
        lines: list[list[TextRun]] = [[]]
        for run in words.runs:
            parts = [run.text] if run.math else run.text.split("\n")
            for index, part in enumerate(parts):
                if part or run.math:
                    lines[-1].append(run if run.math else TextRun(**{**_fields(run), "text": part}))
                if index < len(parts) - 1:
                    lines.append([])
        align = {"start": "l", "middle": "ctr", "end": "r"}.get(words.align, "ctr")
        paragraphs = []
        for line in lines:
            pieces = _runs_xml(tuple(line), typography, stack, size, self.palette, words.colour, native=True)
            end = f'<a:endParaRPr lang="en-GB" sz="{round(size * 100)}" dirty="0"/>'
            paragraphs.append(f'<a:p><a:pPr algn="{align}"/>{pieces}{end}</a:p>')
        anchor = {"top": "t", "middle": "ctr", "bottom": "b"}.get(words.valign, "ctr")
        pad = placement.length(words.padding)
        return (f'<p:txBody><a:bodyPr wrap="{"square" if wrap else "none"}" lIns="{pad}" tIns="{pad}" rIns="{pad}" '
                f'bIns="{pad}" anchor="{anchor}" rtlCol="0"><a:noAutofit/></a:bodyPr><a:lstStyle/>'
                f'{"".join(paragraphs)}</p:txBody>')

    # -- groups --

    def _group(self, parts: list[etree._Element], name: str) -> etree._Element:
        from flexo_talk.pptx import _extent

        boxes = [_extent(part) for part in parts]
        left = min(box[0] for box in boxes)
        top = min(box[1] for box in boxes)
        right = max(box[0] + box[2] for box in boxes)
        bottom = max(box[1] + box[3] for box in boxes)
        group = etree.fromstring(
            f'<p:grpSp {_NS}><p:nvGrpSpPr><p:cNvPr id="{self.number()}" name="{escape(name)}"/><p:cNvGrpSpPr/>'
            f"<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>"
            f'<a:off x="{left}" y="{top}"/><a:ext cx="{right - left}" cy="{bottom - top}"/>'
            f'<a:chOff x="{left}" y="{top}"/><a:chExt cx="{right - left}" cy="{bottom - top}"/>'
            f"</a:xfrm></p:grpSpPr></p:grpSp>"
        )
        for part in parts:
            group.append(part)
        return group


def _size(value: float, width: float) -> str:
    """A line end's size as PowerPoint names it: small, medium or large, against the line's width."""

    share = max(value / max(width, 1e-6), 1e-6)
    return min(("sm", 2.0), ("med", 3.0), ("lg", 5.0), key=lambda pair: abs(math.log(share / pair[1])))[0]


def _fields(run) -> dict:
    from dataclasses import fields

    return {item.name: getattr(run, item.name) for item in fields(run)}


def _name_of(element: etree._Element) -> str:
    found = next(element.iter(f"{{{_P}}}cNvPr"), None)
    return found.get("name", "") if found is not None else ""


def shape_name(spec: dict) -> str:
    """What PowerPoint's Selection Pane calls a shape: its kind, as the studio names it."""

    from flexo.freeform import LABELS

    return LABELS.get(str(spec.get("kind")), "Shape")
