"""Laying out one slide and drawing it as SVG.

A slide is a page of fixed size. Its layout gives it a title band and one or
two regions below; each region holds its blocks one under the other -- text
set and wrapped with flexo's own measurer, bullets with their marks, figures
compiled by flexo -- and the figures share whatever height the words leave.

A figure is compiled at the width of its place divided by a scale that brings
its words to the deck's figure size, then drawn scaled by it: the figure's own
layout decides everything inside it, exactly as in a paper, and the slide only
decides where it goes and how large.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace

import flexo
from flexo.artwork import load_artwork
from flexo.compiler import compile_figure
from flexo.ir.measured import TextMetrics
from flexo.ir.semantic import TextRun
from flexo.lint import lint_compilation
from flexo.render_common import render_runs
from flexo.svg import SVG_NS, element, inkscape_attr, layer, local_name, number, xml_document
from flexo.svg_resources import embed_fonts
from flexo.text import TextMeasurer
from flexo.themes import figure_style
from flexo.units import MILLIMETRES_PER_INCH, POINTS_PER_INCH

from flexo_talk.deck import (
    Deck,
    ListLayout,
    Region,
    RenderedSlide,
    Slide,
    _Bullets,
    _Figure,
    _Image,
    _Plot,
    _Words,
)


@dataclass(frozen=True, slots=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height


class _Canvas:
    """The slide's SVG under construction, and what writers need beside it."""

    def __init__(self, deck: Deck, slide: Slide) -> None:
        style = deck.style
        self.deck = deck
        self.slide = slide
        self.palette = deck.palette
        width_mm = style.width / POINTS_PER_INCH * MILLIMETRES_PER_INCH
        height_mm = style.height / POINTS_PER_INCH * MILLIMETRES_PER_INCH
        self.root = ET.Element(
            f"{{{SVG_NS}}}svg",
            {
                "id": slide.id,
                "width": f"{number(width_mm)}mm",
                "height": f"{number(height_mm)}mm",
                "viewBox": f"0 0 {number(style.width)} {number(style.height)}",
                "version": "1.1",
                "data-flexo-talk-slide": str(slide.index),
            },
        )
        self.defs = element(self.root, "defs", id=f"{slide.id}.defs")
        background = layer(self.root, "layer.background", "Background")
        page = deck.background
        element(
            background,
            "rect",
            id="canvas.background",
            x=0.0,
            y=0.0,
            width=style.width,
            height=style.height,
            fill=self.palette.get("canvas") if page is True else (page or "none"),
        )
        self.layer = layer(self.root, f"{slide.id}.content", "Slide")
        self.lists: list[ListLayout] = []
        self.diagnostics: list[str] = []
        self._figures = 0

    # -- text --

    def measure(
        self,
        runs: tuple[TextRun, ...],
        size: float,
        width: float | None,
        weight: int | None = None,
        *,
        balance: bool = True,
    ) -> TextMetrics:
        """Words set at ``size`` in ``width``. A list wraps greedily (``balance=False``),
        as the slide program that edits it will; a title or caption is balanced."""

        typography = self.deck.typography(size)
        return TextMeasurer(typography).measure(runs, max_width=width, weight=weight, balance=balance)

    def words(
        self,
        identifier: str,
        runs: tuple[TextRun, ...],
        box: Box,
        *,
        size: float,
        align: str = "start",
        weight: int | None = None,
        role: str = "ink",
        parent: ET.Element | None = None,
    ) -> float:
        """Set ``runs`` in ``box`` from its top; return the height they took."""

        if not runs:
            return 0.0
        metrics = self.measure(runs, size, box.width, weight)
        x = {"start": box.x, "middle": box.x + box.width / 2.0, "end": box.x + box.width}[align]
        render_runs(
            parent if parent is not None else self.layer,
            identifier,
            metrics,
            x=x,
            y=box.y + metrics.baseline,
            typography=self.deck.typography(size),
            palette=self.palette,
            fill_role=role,
            anchor=None if align == "start" else align,
            weight=weight,
        )
        return metrics.height


def render_slide(deck: Deck, slide: Slide) -> RenderedSlide:
    canvas = _Canvas(deck, slide)
    style = deck.style
    width, height, margin = style.width, style.height, style.margin
    title_weight = deck.layout_style.typography.title_weight
    bottom = height - margin - (style.small_size if style.numbers or deck.footer else 0.0)
    if slide.layout == "title":
        _title_slide(canvas, slide)
    elif slide.layout == "section":
        _section_slide(canvas, slide)
    else:
        top = margin
        if slide.title_runs and slide.layout != "blank":
            used = canvas.words(
                f"{slide.id}.title",
                slide.title_runs,
                Box(margin, top, width - 2 * margin, 0.0),
                size=style.title_size,
                weight=title_weight,
            )
            top += used
            if slide.subtitle_runs:
                top += 4.0 + canvas.words(
                    f"{slide.id}.subtitle",
                    slide.subtitle_runs,
                    Box(margin, top + 4.0, width - 2 * margin, 0.0),
                    size=style.subtitle_size,
                    role="muted-ink",
                )
            if style.rule:
                element(
                    canvas.layer,
                    "rect",
                    id=f"{slide.id}.rule",
                    x=margin,
                    y=top + 8.0,
                    width=40.0,
                    height=3.0,
                    fill=canvas.palette.get("tone-1-stroke"),
                    data__flexo__fill="tone-1-stroke",
                )
                top += 11.0
            top += style.title_gap
        body = Box(margin, top, width - 2 * margin, bottom - top)
        names = list(slide.regions)
        if len(names) == 2:
            column = (body.width - style.column_gap) / 2.0
            boxes = [
                Box(body.x, body.y, column, body.height),
                Box(body.x + column + style.column_gap, body.y, column, body.height),
            ]
        else:
            boxes = [body]
        for name, box in zip(names, boxes, strict=True):
            _region(canvas, slide.regions[name], box)
    _furniture(canvas, slide)
    stylesheet = element(canvas.defs, "style", id=f"{slide.id}.fonts", type="text/css")
    embed_fonts(stylesheet, canvas.root, deck.layout_style)
    return RenderedSlide(slide, xml_document(canvas.root), canvas.lists, canvas.diagnostics)


def _title_slide(canvas: _Canvas, slide: Slide) -> None:
    deck, style = canvas.deck, canvas.deck.style
    width, height, margin = style.width, style.height, style.margin
    box = Box(margin * 2, 0.0, width - 4 * margin, 0.0)
    bold = deck.layout_style.typography.title_weight
    title = canvas.measure(slide.title_runs, style.title_size * 1.4, box.width, bold)
    subtitle = (
        canvas.measure(slide.subtitle_runs, style.subtitle_size * 1.15, box.width) if slide.subtitle_runs else None
    )
    total = title.height + (subtitle.height + 14.0 if subtitle else 0.0) + 60.0
    top = (height - total) / 2.0
    used = canvas.words(
        f"{slide.id}.title", slide.title_runs, replace(box, y=top), size=style.title_size * 1.4,
        align="middle", weight=deck.layout_style.typography.title_weight,
    )
    top += used + 14.0
    if subtitle is not None:
        top += canvas.words(
            f"{slide.id}.subtitle", slide.subtitle_runs, replace(box, y=top),
            size=style.subtitle_size * 1.15, align="middle", role="muted-ink",
        )
    element(
        canvas.layer, "rect", id=f"{slide.id}.rule", x=width / 2.0 - 30.0, y=top + 14.0,
        width=60.0, height=3.0, fill=canvas.palette.get("tone-1-stroke"),
        data__flexo__fill="tone-1-stroke",
    )
    _region(canvas, slide.body, Box(margin, top + 34.0, width - 2 * margin, height - top - 34.0 - margin))


def _section_slide(canvas: _Canvas, slide: Slide) -> None:
    deck, style = canvas.deck, canvas.deck.style
    width, height, margin = style.width, style.height, style.margin
    box = Box(margin * 1.5, 0.0, width - 3 * margin, 0.0)
    bold = deck.layout_style.typography.title_weight
    title = canvas.measure(slide.title_runs, style.title_size * 1.25, box.width, bold)
    top = height / 2.0 - title.height
    element(
        canvas.layer, "rect", id=f"{slide.id}.rule", x=box.x, y=top - 18.0, width=60.0,
        height=4.0, fill=canvas.palette.get("tone-1-stroke"), data__flexo__fill="tone-1-stroke",
    )
    used = canvas.words(
        f"{slide.id}.title", slide.title_runs, replace(box, y=top), size=style.title_size * 1.25,
        weight=deck.layout_style.typography.title_weight,
    )
    if slide.subtitle_runs:
        canvas.words(
            f"{slide.id}.subtitle", slide.subtitle_runs, replace(box, y=top + used + 10.0),
            size=style.subtitle_size, role="muted-ink",
        )


def _furniture(canvas: _Canvas, slide: Slide) -> None:
    """The slide number and the footer, small and quiet."""

    deck, style = canvas.deck, canvas.deck.style
    if slide.layout in {"title", "section"}:
        return
    size = style.small_size * 0.8
    y = style.height - style.margin + size * 0.2
    if style.numbers:
        canvas.words(
            f"{slide.id}.number", (TextRun(str(slide.index)),),
            Box(style.width - style.margin - 60.0, y, 60.0, 0.0), size=size, align="end",
            role="muted-ink",
        )
    if deck.footer:
        canvas.words(
            f"{slide.id}.footer", flexo.markup.parse_label(deck.footer),
            Box(style.margin, y, style.width / 2.0, 0.0), size=size, role="muted-ink",
        )


# -- regions ---------------------------------------------------------------------------


def _region(canvas: _Canvas, region: Region, box: Box) -> None:
    style = canvas.deck.style
    blocks = _fitted(canvas, region, box)
    words = [block for block in blocks if not isinstance(block, _Figure | _Image | _Plot)]
    pictures = [block for block in blocks if isinstance(block, _Figure | _Image | _Plot)]
    # Words take what they need; pictures share the height that is left.
    needed = sum(_height(canvas, block, box.width) for block in words)
    gaps = style.block_gap * max(0, len(blocks) - 1)
    room = box.height - needed - gaps
    share = room / len(pictures) if pictures else 0.0
    # Figures in one place share one scale, so their words are one size: the
    # largest at which all of them fit the room figures have together.
    prepared = {
        index: _prepare(canvas, block, box.width)
        for index, block in enumerate(blocks)
        if isinstance(block, _Figure)
    }
    scale = 0.0
    if prepared:
        figure_room = max(room * len(prepared) / len(pictures), 40.0 * len(prepared))
        scale = min(
            min(item.most for item in prepared.values()),
            min(box.width / item.width for item in prepared.values()),
            figure_room / sum(item.height for item in prepared.values()),
        )
        _check_legible(canvas, prepared.values(), scale)
    top = box.y
    for index, block in enumerate(blocks):
        identifier = f"{canvas.slide.id}.{region.name}.{index}"
        if isinstance(block, _Bullets):
            top += _bullets(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Words):
            size = block.size or style.body_size
            top += canvas.words(
                identifier, block.runs, Box(box.x, top, box.width, 0.0), size=size,
                align=block.align, role="muted-ink" if block.muted else "ink",
            )
        elif isinstance(block, _Figure):
            alone = len(blocks) == 1
            height = room if alone else prepared[index].height * scale
            top += _place_figure(canvas, identifier, prepared[index], Box(box.x, top, box.width, height), scale)
        elif isinstance(block, _Image):
            top += _image(canvas, identifier, block, Box(box.x, top, box.width, max(share, 40.0)))
        elif isinstance(block, _Plot):
            top += _plot(canvas, identifier, block, Box(box.x, top, box.width, max(share, 60.0)))
        top += style.block_gap


PICTURE_LEAST = 120.0
"""The least height a figure, plot, or picture keeps when words crowd its place."""


def _fitted(canvas: _Canvas, region: Region, box: Box) -> list:
    """The region's blocks, their words set smaller if that is what it takes to fit.

    Words shrink together, down to the deck's small size; a slide that still
    does not fit is reported, since it has more on it than a slide can hold.
    """

    style = canvas.deck.style
    blocks = list(region.blocks)
    pictures = sum(isinstance(block, _Figure | _Image | _Plot) for block in blocks)
    room = box.height - style.block_gap * max(0, len(blocks) - 1) - PICTURE_LEAST * pictures

    def needed(scale: float) -> float:
        return sum(_height(canvas, _sized(block, scale, style), box.width) for block in blocks)

    if needed(1.0) <= room:
        return blocks
    low, high = style.small_size / style.body_size, 1.0
    if needed(low) > room:
        canvas.diagnostics.append(
            f"{canvas.slide.id}: the words do not fit even at the small size -- split the slide"
        )
        return [_sized(block, low, style) for block in blocks]
    for _ in range(10):
        middle = (low + high) / 2.0
        low, high = (middle, high) if needed(middle) <= room else (low, middle)
    canvas.diagnostics.append(f"{canvas.slide.id}: words set at {round(low * 100)}% to fit")
    return [_sized(block, low, style) for block in blocks]


def _sized(block, scale: float, style):
    if scale == 1.0 or not isinstance(block, _Bullets | _Words):
        return block
    return replace(block, size=(block.size or style.body_size) * scale)


def _height(canvas: _Canvas, block, width: float) -> float:
    style = canvas.deck.style
    if isinstance(block, _Words):
        return canvas.measure(block.runs, block.size or style.body_size, width).height
    if isinstance(block, _Bullets):
        size = block.size or style.body_size
        total = 0.0
        for level, runs in block.items:
            offset = style.indent * level + size * 0.95
            metrics = canvas.measure(runs, size, width - offset, balance=False)
            total += metrics.height + style.paragraph_gap * size
        return total
    return 0.0


def _bullets(canvas: _Canvas, identifier: str, block: _Bullets, box: Box) -> float:
    style = canvas.deck.style
    size = block.size or style.body_size
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="bullets")
    layout = ListLayout(
        box.x, box.y, box.width, size, size * style.line_height, style.paragraph_gap * size,
        style.indent, id=identifier,
    )
    top = box.y
    for index, (level, runs) in enumerate(block.items):
        offset = style.indent * level + size * 0.95
        metrics = canvas.measure(runs, size, box.width - offset, balance=False)
        layout.line_height = metrics.line_height
        baseline = top + metrics.baseline
        radius = size * (0.15 if level == 0 else 0.12)
        cx = box.x + style.indent * level + size * 0.3
        cy = baseline - (metrics.cap_height or size * 0.7) / 2.0
        role = "tone-1-stroke" if level == 0 else "muted-ink"
        element(
            group, "circle", id=f"{identifier}.{index}.mark", cx=cx, cy=cy, r=radius,
            fill=canvas.palette.get(role), data__flexo__fill=role,
        )
        render_runs(
            group, f"{identifier}.{index}", metrics, x=box.x + offset, y=baseline,
            typography=canvas.deck.typography(size), palette=canvas.palette, fill_role="ink",
        )
        layout.items.append((level, runs, baseline))
        top += metrics.height + style.paragraph_gap * size
    canvas.lists.append(layout)
    return top - box.y - style.paragraph_gap * size


# -- figures ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Prepared:
    """A figure compiled for its place, and the extent of its ink."""

    svg: str
    left: float
    top: float
    width: float
    height: float
    most: float
    """The largest scale: words no larger than the body text."""
    size: float
    """The size of its words, unscaled."""
    id: str


LEGIBLE = 9.0
"""Words on a slide smaller than this (points) are reported: they will not read."""


def _prepare(canvas: _Canvas, block: _Figure, width: float) -> _Prepared:
    deck = canvas.deck
    spec = block.figure.spec if isinstance(block.figure, flexo.Figure) else block.figure
    if not isinstance(block.figure, flexo.Figure) or spec.style != deck.theme:
        # A figure made elsewhere is redrawn in the deck's look.
        spec = replace(
            spec, style=deck.theme, palette=deck.palette_name,
            font=deck.font or spec.font,
        )
    base = figure_style(spec).typography.size.points
    # Laid out at the width that sets its words at the deck's figure size; then
    # cropped to its ink and scaled to fill its place, but never so far that its
    # words outgrow the body text.
    least = deck.style.figure_size / base
    spec = replace(spec, width=f"{width / least:.3f}pt", background=False)
    compiled = compile_figure(spec)
    for diagnostic in lint_compilation(compiled).diagnostics:
        canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}: {diagnostic.code}")
    left, top, right, bottom = _ink(compiled.document.text)
    pad = 2.0
    return _Prepared(
        compiled.document.text, left - pad, top - pad, right - left + 2 * pad, bottom - top + 2 * pad,
        deck.style.body_size / base, base, spec.id,
    )


def _check_legible(canvas: _Canvas, prepared, scale: float) -> None:
    for item in prepared:
        drawn = item.size * scale
        if drawn < LEGIBLE:
            canvas.diagnostics.append(
                f"{canvas.slide.id} {item.id}: its words are {drawn:.1f}pt, too small to read -- "
                "give the figure a slide of its own, a wider layout, or fewer parts"
            )


def _place_figure(canvas: _Canvas, identifier: str, item: _Prepared, box: Box, scale: float) -> float:
    """Put a prepared figure in ``box`` at ``scale``: centred across, and down if it has room."""

    x = box.x + (box.width - item.width * scale) / 2.0 - item.left * scale
    y = box.y + (box.height - item.height * scale) / 2.0 - item.top * scale
    _place_svg(canvas, identifier, item.svg, x, y, scale)
    return box.height


def _drawable(markup: str) -> bool:
    from flexo.drawing import _drawable as drawable

    return drawable(ET.fromstring(markup))


_REGISTERED = False


def register_fonts_with_matplotlib() -> None:
    """Let matplotlib measure text in flexo's bundled faces (once per process)."""

    global _REGISTERED
    if _REGISTERED:
        return
    from flexo.fonts import bundled_font_directory
    from matplotlib import font_manager

    for path in sorted(bundled_font_directory().iterdir()):
        if path.suffix.lower() in {".ttf", ".otf"}:
            try:
                font_manager.fontManager.addfont(str(path))
            except Exception:
                continue
    _REGISTERED = True


def _plot(canvas: _Canvas, identifier: str, block: _Plot, box: Box) -> float:
    """A matplotlib figure, laid out again at the size of its place, placed as vectors."""

    import io

    import matplotlib
    import matplotlib.text

    register_fonts_with_matplotlib()
    figure = block.figure
    width = box.width
    height = min(box.height, width / block.aspect) if block.aspect else box.height
    figure.set_size_inches(width / 72.0, height / 72.0)
    if figure.get_layout_engine() is None:
        figure.set_layout_engine("constrained")
    family = canvas.deck.layout_style.typography.family
    for text in figure.findobj(matplotlib.text.Text):
        text.set_fontfamily([family])
    settings = {
        "svg.fonttype": "none",
        "svg.hashsalt": identifier,
        "mathtext.fontset": "custom",
        "mathtext.rm": family,
        "mathtext.it": f"{family}:italic",
        "mathtext.bf": f"{family}:bold",
        "mathtext.fallback": "stix",
    }
    buffer = io.StringIO()
    with matplotlib.rc_context(settings):
        try:
            figure.savefig(buffer, format="svg", transparent=True, metadata={"Date": None})
        except (ZeroDivisionError, ValueError):
            # Constrained layout cannot take over a figure built without it
            # (a colour bar made first): lay it out tightly instead.
            figure.set_layout_engine("tight")
            buffer = io.StringIO()
            figure.savefig(buffer, format="svg", transparent=True, metadata={"Date": None})
    _place_svg(canvas, identifier, buffer.getvalue(), box.x, box.y, 1.0)
    return height


def _ink(svg: str) -> tuple[float, float, float, float]:
    """The extent of everything a figure draws, in its own points."""

    from flexo.drawing import Image, Shape, Text, read_drawing

    xs: list[float] = []
    ys: list[float] = []
    for item in read_drawing(svg).walk():
        if isinstance(item, Shape):
            if item.paint.fill is None and item.paint.stroke is None:
                continue
            reach = item.paint.stroke_width / 2.0 if item.paint.stroke else 0.0
            xs += [item.x - reach, item.x + item.width + reach]
            ys += [item.y - reach, item.y + item.height + reach]
            for head in item.arrowheads:
                xs += [x for segment in head.outline for x, _ in segment.points]
                ys += [y for segment in head.outline for _, y in segment.points]
        elif isinstance(item, Text):
            for line in item.lines:
                xs += [line.left, line.right]
                ys += [line.baseline - item.size * 0.8, line.baseline + item.size * 0.25]
        elif isinstance(item, Image):
            xs += [item.x, item.x + item.width]
            ys += [item.y, item.y + item.height]
    return min(xs), min(ys), max(xs), max(ys)


def _place_svg(canvas: _Canvas, identifier: str, svg: str, x: float, y: float, scale: float) -> None:
    """Put an SVG on the slide at ``(x, y)``, scaled; its ids take a prefix.

    A ``*`` rule in its stylesheet (matplotlib writes one) becomes attributes on
    the group, so it applies to this drawing only, not to the whole slide.
    """

    source = ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", svg, count=1))
    prefix = f"{identifier}."
    universal: dict[str, str] = {}
    for item in source.iter():
        if local_name(item.tag) == "style" and item.text:
            for rule in re.finditer(r"(?:^|[}\s])\*\s*\{([^}]*)\}", item.text):
                for declaration in rule.group(1).split(";"):
                    name, _, value = declaration.partition(":")
                    if name.strip() and value.strip():
                        universal[name.strip()] = value.strip()
    for item in source.iter():
        if item.get("id"):
            item.set("id", prefix + item.get("id"))  # type: ignore[operator]
        for name, value in list(item.attrib.items()):
            if "url(#" in value:
                item.set(name, re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{prefix}{m.group(1)})", value))
            if name.endswith("href") and value.startswith("#"):
                item.set(name, "#" + prefix + value[1:])
    group = element(
        canvas.layer, "g", id=identifier,
        transform=f"translate({number(x)},{number(y)}) scale({number(scale)})",
        data__flexo__talk="figure",
    )
    for name, value in universal.items():
        group.set(name, value)
    view = [float(v) for v in re.split(r"[ ,]+", source.get("viewBox", "").strip()) if v]
    if len(view) == 4 and (view[0] or view[1]):
        group = element(group, "g", transform=f"translate({number(-view[0])},{number(-view[1])})")
    for child in source:
        tag = local_name(child.tag)
        if tag == "defs":
            for definition in child:
                if local_name(definition.tag) != "style":
                    canvas.defs.append(definition)
        elif tag in {"title", "desc", "metadata", "style"} or child.get(inkscape_attr("label")) == "Background":
            continue
        else:
            child.attrib.pop(inkscape_attr("groupmode"), None)
            group.append(child)


def _image(canvas: _Canvas, identifier: str, block: _Image, box: Box) -> float:
    art = load_artwork(identifier, block.source)
    natural_w = art.width or box.width
    natural_h = art.height or box.height
    scale = min((block.width or box.width) / natural_w, box.height / natural_h)
    width, height = natural_w * scale, natural_h * scale
    if art.format == "svg" and _drawable(art.markup):
        # Vectors the drawing reader draws exactly: placed as shapes and text.
        view = [float(v) for v in re.split(r"[ ,]+", ET.fromstring(art.markup).get("viewBox", "").strip()) if v]
        units = (natural_w / view[2]) if len(view) == 4 and view[2] else 1.0
        _place_svg(canvas, identifier, art.markup, box.x + (box.width - width) / 2.0, box.y, scale * units)
        return height
    if art.format == "svg":
        import base64

        href = "data:image/svg+xml;base64," + base64.b64encode(art.markup.encode()).decode()
    else:
        href = art.data_uri
    element(
        canvas.layer, "image", id=identifier, x=box.x + (box.width - width) / 2.0, y=box.y,
        width=width, height=height, href=href,
    )
    return height
