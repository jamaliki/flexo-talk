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

import functools
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import flexo
from flexo.artwork import load_artwork, picture_href, picture_link
from flexo.ir.measured import TextMetrics
from flexo.ir.semantic import TextRun
from flexo.lint import lint_compilation
from flexo.render_common import render_runs
from flexo.svg import SVG_NS, element, inkscape_attr, layer, local_name, number, xml_document
from flexo.svg_resources import embed_fonts
from flexo.text import TextMeasurer
from flexo.themes import figure_palette, figure_style
from flexo.units import MILLIMETRES_PER_INCH, POINTS_PER_INCH

from flexo_talk.deck import (
    Deck,
    ListLayout,
    Reference,
    Region,
    RenderedSlide,
    Slide,
    TableLayout,
    _Bullets,
    _Callout,
    _Code,
    _Figure,
    _Gallery,
    _Image,
    _Math,
    _Plot,
    _Quote,
    _Stats,
    _Table,
    _Words,
    accent_field,
    inline,
    made,
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
        self.palette = _slide_palette(deck, slide)
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
            fill=self.palette.get("canvas") if page is True or _is_picture(page) else (page or "none"),
        )
        self.layer = layer(self.root, f"{slide.id}.content", "Slide")
        if _is_picture(page) and not slide.backdrop:
            # The deck's paper, first in the slide (so a PowerPoint slide has it too),
            # under everything the slide draws; a slide with a backdrop of its own
            # (a colour, a picture, a filled section) is drawn on that instead.
            element(
                self.layer, "image", id=f"{slide.id}.paper", x=0.0, y=0.0, width=style.width,
                height=style.height, preserveAspectRatio="xMidYMid slice", href=_picture_href(str(page)),
            )
        if slide.backdrop:
            _slide_background(self, slide)
        self.lists: list[ListLayout] = []
        self.diagnostics: list[str] = []
        self.tables: list[TableLayout] = []
        self.notes: list[str] = []
        self.held: list[str] = []
        self.steps = 1
        self.alone = False
        """Whether the block being set has its region to itself."""
        """What the build did that the author may want to know (a figure turned to fit)."""
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
        title: bool = False,
    ) -> TextMetrics:
        """Words set at ``size`` in ``width``. A list wraps greedily (``balance=False``),
        as the slide program that edits it will; a title or caption is balanced.
        ``title`` sets them in the deck's title font."""

        typography = self.deck.typography(size, title=title)
        for run in runs:
            if run.math:
                from flexo.texmath import problems_in

                self.say_maths(run.math, problems_in(run.math))
        # A word wider than the slide (a URL) breaks rather than running off it.
        return TextMeasurer(typography).measure(
            runs, max_width=width, weight=weight, balance=balance, break_words=True
        )

    def say_maths(self, source: str, problems: tuple[str, ...] | list[str]) -> None:
        """What could not be read in a formula, said once for the slide."""

        shown = source.removeprefix("\\displaystyle ").strip()
        shown = shown if len(shown) <= 40 else shown[:39] + "…"
        for problem in problems:
            said = f"{self.slide.id}: {problem}, in the maths \u201c{shown}\u201d"
            if said not in self.diagnostics:
                self.diagnostics.append(said)

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
        title: bool = False,
        wrap: bool = True,
        fill: str | None = None,
        balance: bool = True,
    ) -> float:
        """Set ``runs`` in ``box`` from its top; return the height they took.
        ``wrap=False`` keeps each line whole (code keeps its indentation);
        ``balance=False`` fills each line before the next (words on a panel)."""

        if not runs:
            return 0.0
        if align == "start" and _rtl(runs):
            # Right-to-left words start at the right.
            align = "end"
        metrics = self.measure(runs, size, box.width if wrap else None, weight, title=title, balance=balance)
        x = {"start": box.x, "middle": box.x + box.width / 2.0, "end": box.x + box.width}[align]
        render_runs(
            parent if parent is not None else self.layer,
            identifier,
            metrics,
            x=x,
            y=box.y + metrics.baseline,
            typography=self.deck.typography(size, title=title),
            palette=self.palette,
            fill_role=role,
            fill=fill,
            anchor=None if align == "start" else align,
            weight=weight,
        )
        return metrics.height


def render_slide(deck: Deck, slide: Slide) -> RenderedSlide:
    canvas = _Canvas(deck, slide)
    _held_back(canvas, slide)
    style = deck.style
    width, height, margin = style.width, style.height, style.margin
    if style.edge and slide.layout != "title":
        _paint_rect(canvas, f"{slide.id}.edge", Box(0.0, 0.0, 6.0, height), "tone-1-stroke")
    bottom = height - margin - (style.small_size if style.numbers or deck.footer else 0.0)
    if slide.footnotes:
        # Footnotes sit at the foot of the body, above the footer; the body ends above them.
        size = style.small_size
        heights = [canvas.measure(runs, size, width - 2 * margin).height for runs in slide.footnotes]
        top = bottom - sum(heights) - size * 0.3 * (len(heights) - 1)
        for index, (runs, used) in enumerate(zip(slide.footnotes, heights, strict=True)):
            canvas.words(
                f"{slide.id}.footnote{index}", runs, Box(margin, top, width - 2 * margin, 0.0),
                size=size, role="muted-ink",
            )
            top += used + size * 0.3
        bottom -= sum(heights) + size * 0.3 * len(heights) + size * 0.6
    if slide.layout == "title":
        _title_slide(canvas, slide)
    elif slide.layout == "section":
        _section_slide(canvas, slide)
    elif slide.layout == "statement":
        _statement_slide(canvas, slide)
    else:
        top = _heading(canvas, slide) if slide.title_runs and slide.layout != "blank" else margin
        body = Box(margin, top, width - 2 * margin, bottom - top)
        if slide.layout == "agenda":
            _agenda(canvas, slide, body)
        else:
            _regions(canvas, slide, body)
    _furniture(canvas, slide)
    stylesheet = element(canvas.defs, "style", id=f"{slide.id}.fonts", type="text/css")
    embed_fonts(stylesheet, canvas.root, deck.layout_style)
    if deck.title_font:
        headings = element(canvas.defs, "style", id=f"{slide.id}.title-fonts", type="text/css")
        embed_fonts(headings, canvas.root, replace(deck.layout_style, typography=deck.typography(12, title=True)))
    return RenderedSlide(
        slide, xml_document(canvas.root), canvas.lists, canvas.diagnostics, canvas.tables, canvas.notes,
        canvas.steps, canvas.held,
    )


def _held_back(canvas: _Canvas, slide: Slide) -> None:
    """Python a slide names, in a folder not yet trusted, stands aside for a quiet line in
    its place: the rest of the slide is drawn as usual, and the page is told what waits."""

    from flexo_talk.document import UntrustedCode

    for region in slide.regions.values():
        for index, block in enumerate(region.blocks):
            reference = getattr(block, "figure", None)
            if not isinstance(reference, Reference):
                continue
            try:
                reference.resolve()
            except UntrustedCode as error:
                canvas.held.append(error.message)
                region.blocks[index] = _Words(
                    inline(f"*{reference.target}* is drawn once you trust this folder"),
                    align="middle", muted=True,
                )


def _paint_rect(canvas: _Canvas, identifier: str, box: Box, role: str | None, *, opacity: float = 1.0) -> None:
    """A filled rectangle painted by a palette role (so a retheme repaints it), or
    ``None`` for the accent field bands are painted in."""

    attributes: dict[str, object] = {"data__flexo__fill": role} if role else {}
    if opacity < 1.0:
        attributes["fill_opacity"] = opacity
    element(
        canvas.layer, "rect", id=identifier, x=box.x, y=box.y, width=box.width, height=box.height,
        fill=canvas.palette.get(role) if role else accent_field(canvas.deck.palette), **attributes,
    )


def _words_on(canvas: _Canvas) -> str:
    """The role whose words read best on the accent field: the page's own colour
    or the ink, whichever stands out more."""

    from flexo.colour import contrast

    field = accent_field(canvas.deck.palette)
    page, ink = canvas.palette.get("canvas"), canvas.palette.get("ink")
    return "canvas" if contrast(page, field) > contrast(ink, field) else "ink"


def _section_number(slide: Slide) -> int:
    return sum(other.layout == "section" for other in slide.deck.slides[: slide.index])


def _heading(canvas: _Canvas, slide: Slide) -> float:
    """A content slide's title (and subtitle) with the look's mark; returns where the body starts."""

    deck, style = canvas.deck, canvas.deck.style
    width, margin = style.width, style.margin
    weight = deck.title_weight
    span = width - 2 * margin
    heading = canvas.measure(slide.title_runs, style.title_size, span, weight, title=True)
    under = (
        canvas.measure(slide.subtitle_runs, style.subtitle_size, span).height + 4.0 if slide.subtitle_runs else 0.0
    )
    top = margin
    role, subtitle_role = style.title_role, "muted-ink"
    band = 0.0
    if style.header == "band":
        # The title on a band of the accent across the top of the slide.
        top = margin * 0.7
        band = top + heading.height + under + margin * 0.5
        _paint_rect(canvas, f"{slide.id}.band", Box(0.0, 0.0, width, band), None)
        role = subtitle_role = _words_on(canvas)
    # Where the title's ink ends: its last baseline and a descender below it.
    ink_bottom = top + heading.baseline + heading.line_height * (len(heading.lines) - 1)
    ink_bottom += style.title_size * 0.22
    top += canvas.words(
        f"{slide.id}.title", slide.title_runs, Box(margin, top, span, 0.0), size=style.title_size,
        weight=weight, role=role, title=True, align=style.title_align,
    )
    if slide.subtitle_runs:
        top += 4.0 + canvas.words(
            f"{slide.id}.subtitle", slide.subtitle_runs, Box(margin, top + 4.0, span, 0.0),
            size=style.subtitle_size, role=subtitle_role, align=style.title_align,
        )
    start = style.title_align == "start"
    if style.header == "rule":
        # Below the ink, not the line box: faces sit differently in theirs, and a
        # centred rule close under a word reads as its underline.
        x = (width - margin - 40.0 if _rtl(slide.title_runs) else margin) if start else width / 2.0 - 20.0
        y = max(top, ink_bottom) + (8.0 if start else 12.0)
        _paint_rect(canvas, f"{slide.id}.rule", Box(x, y, 40.0, 3.0), "tone-1-stroke")
        top = y + 3.0
    elif style.header == "line":
        y = max(top, ink_bottom) + 10.0
        _paint_rect(canvas, f"{slide.id}.rule", Box(margin, y, span, 0.75), "muted-ink", opacity=0.6)
        top = y + 0.75
    elif style.header == "band":
        top = band - style.title_gap * 0.35
    else:
        # No mark: the body starts where it would under a rule, so the words keep
        # one distance from the title whatever marks it.
        top = max(top, ink_bottom) + 11.0
    return top + style.title_gap


def _title_slide(canvas: _Canvas, slide: Slide) -> None:
    deck, style = canvas.deck, canvas.deck.style
    width, height, margin = style.width, style.height, style.margin
    bold = deck.title_weight
    opening = style.opening
    size, subtitle_size = style.title_size * 1.4, style.subtitle_size * 1.15
    left = margin * 1.5 + (18.0 if opening == "left" else 0.0)
    box = Box(margin * 2, 0.0, width - 4 * margin, 0.0) if opening == "centred" else Box(left, 0.0, width * 0.72, 0.0)
    align = "middle" if opening == "centred" else "start"
    title = canvas.measure(slide.title_runs, size, box.width, bold, title=True)
    subtitle = canvas.measure(slide.subtitle_runs, subtitle_size, box.width) if slide.subtitle_runs else None
    byline = canvas.measure(slide.byline_runs, style.subtitle_size, box.width) if slide.byline_runs else None
    block = title.height + (subtitle.height + 14.0 if subtitle else 0.0)
    role, subtitle_role = style.title_role, "muted-ink"
    if opening == "band":
        # Title and subtitle on a band of the accent, the byline under it.
        pad = margin * 0.8
        band_top = height * 0.3
        _paint_rect(canvas, f"{slide.id}.band", Box(0.0, band_top, width, block + 2 * pad), None)
        role = subtitle_role = _words_on(canvas)
        top = band_top + pad
        after = band_top + block + 2 * pad + 22.0
    else:
        total = block + (byline.height + 34.0 if byline else 0.0)
        top = (height - total) / 2.0 - (height * 0.04 if opening == "left" else 0.0)
        after = top + block + 34.0
        if opening == "left":
            _paint_rect(canvas, f"{slide.id}.bar", Box(margin * 1.5, top + 4.0, 5.0, block - 4.0), "tone-1-stroke")
    first = top
    top += canvas.words(
        f"{slide.id}.title", slide.title_runs, replace(box, y=top), size=size, align=align, weight=bold,
        role=role, title=True,
    ) + 14.0
    if subtitle is not None:
        canvas.words(
            f"{slide.id}.subtitle", slide.subtitle_runs, replace(box, y=top), size=subtitle_size,
            align=align, role=subtitle_role,
        )
    if opening == "centred":
        rule = Box(width / 2.0 - 30.0, first + block + 14.0, 60.0, 3.0)
        _paint_rect(canvas, f"{slide.id}.rule", rule, "tone-1-stroke")
    if byline is not None:
        canvas.words(
            f"{slide.id}.byline", slide.byline_runs, replace(box, y=after), size=style.subtitle_size,
            align=align, role="muted-ink",
        )
        after += byline.height + 20.0
    _region(canvas, slide.body, Box(margin, after, width - 2 * margin, max(height - after - margin, 0.0)))


def _section_slide(canvas: _Canvas, slide: Slide) -> None:
    deck, style = canvas.deck, canvas.deck.style
    width, height, margin = style.width, style.height, style.margin
    box = Box(margin * 1.5, 0.0, width - 3 * margin, 0.0)
    # Sections sit flush left, or centred with the titles of a deck that centres them.
    align = "middle" if style.title_align == "middle" else "start"
    left = width / 2.0 - 30.0 if align == "middle" else box.x
    bold = deck.title_weight
    size = style.title_size * 1.25
    title = canvas.measure(slide.title_runs, size, box.width, bold, title=True)
    subtitle = canvas.measure(slide.subtitle_runs, style.subtitle_size, box.width) if slide.subtitle_runs else None
    number = (TextRun(f"{_section_number(slide):02d}"),)
    sections = style.sections
    if sections == "number":
        # The section's number set large in the accent, the title under it.
        big = style.title_size * 2.6
        figure = canvas.measure(number, big, None, title=True)
        total = figure.height + 6.0 + title.height + (subtitle.height + 10.0 if subtitle else 0.0)
        top = (height - total) / 2.0
        canvas.words(
            f"{slide.id}.number", number, replace(box, y=top), size=big, role="tone-1-stroke", title=True,
            align=align,
        )
        top += figure.height + 6.0
    elif sections == "fill":
        small = style.subtitle_size
        figure = canvas.measure(number, small, None, 700)
        total = figure.height + 16.0 + title.height + (subtitle.height + 10.0 if subtitle else 0.0)
        top = (height - total) / 2.0
        canvas.words(
            f"{slide.id}.number", number, replace(box, y=top), size=small, weight=700, role="muted-ink",
            align=align,
        )
        _paint_rect(canvas, f"{slide.id}.rule", Box(left, top + figure.height + 6.0, 60.0, 3.0), "ink")
        top += figure.height + 16.0
    else:
        top = height / 2.0 - title.height
        _paint_rect(canvas, f"{slide.id}.rule", Box(left, top - 18.0, 60.0, 4.0), "tone-1-stroke")
    used = canvas.words(
        f"{slide.id}.title", slide.title_runs, replace(box, y=top), size=size, weight=bold,
        role="ink" if sections == "fill" else style.title_role, title=True, align=align,
    )
    if slide.subtitle_runs:
        canvas.words(
            f"{slide.id}.subtitle", slide.subtitle_runs, replace(box, y=top + used + 10.0),
            size=style.subtitle_size, role="muted-ink", align=align,
        )


def _statement_slide(canvas: _Canvas, slide: Slide) -> None:
    """One sentence, large, in the middle of the slide; who said it under it."""

    deck, style = canvas.deck, canvas.deck.style
    width, height = style.width, style.height
    box = Box(width * 0.14, 0.0, width * 0.72, 0.0)
    size = style.title_size * 1.3
    words = canvas.measure(slide.title_runs, size, box.width, deck.title_weight, title=True)
    byline = canvas.measure(slide.byline_runs, style.subtitle_size, box.width) if slide.byline_runs else None
    top = (height - words.height - (byline.height + 24.0 if byline else 0.0)) / 2.0
    top += canvas.words(
        f"{slide.id}.title", slide.title_runs, replace(box, y=top), size=size, align="middle",
        weight=deck.title_weight, title=True,
    )
    if slide.byline_runs:
        canvas.words(
            f"{slide.id}.byline", slide.byline_runs, replace(box, y=top + 24.0), size=style.subtitle_size,
            align="middle", role="muted-ink",
        )


def _agenda(canvas: _Canvas, slide: Slide, body: Box) -> None:
    """The deck's sections, numbered, one to a row with hairlines between them."""

    style = canvas.deck.style
    sections = [other for other in slide.deck.slides if other.layout == "section"]
    if not sections:
        canvas.diagnostics.append(f"{slide.id}: the agenda lists section slides, and the deck has none")
        return
    size = style.body_size * 1.1
    for scale in (1.0, 0.9, 0.8, 0.7):
        rows, total = _agenda_rows(canvas, sections, size * scale, body.width)
        if total <= body.height:
            break
    size *= scale
    top = body.y
    if (slide.align or style.align) == "middle":
        top += max(body.height - total, 0.0) / 2.0
    numbers = rows[0][0]
    for index, (_, height, other) in enumerate(rows):
        identifier = f"{slide.id}.agenda{index}"
        number = (TextRun(f"{index + 1:02d}"),)
        canvas.words(
            f"{identifier}.number", number, Box(body.x, top, numbers, 0.0), size=size,
            weight=canvas.deck.title_weight, role="tone-1-stroke", title=True,
        )
        used = canvas.words(
            identifier, other.title_runs, Box(body.x + numbers, top, body.width - numbers, 0.0), size=size,
            weight=canvas.deck.title_weight, title=True,
        )
        if other.subtitle_runs:
            canvas.words(
                f"{identifier}.subtitle", other.subtitle_runs,
                Box(body.x + numbers, top + used + 2.0, body.width - numbers, 0.0),
                size=size * 0.72, role="muted-ink",
            )
        top += height
        if index < len(rows) - 1:
            _paint_rect(
                canvas, f"{identifier}.rule", Box(body.x, top + size * 0.45, body.width, 0.75), "muted-ink",
                opacity=0.35,
            )
            top += size * 0.9 + 0.75


def _agenda_rows(canvas: _Canvas, sections: list[Slide], size: float, width: float):
    weight = canvas.deck.title_weight
    numbers = canvas.measure((TextRun("00"),), size, None, weight, title=True).width + size * 1.1
    rows = []
    for other in sections:
        height = canvas.measure(other.title_runs, size, width - numbers, weight, title=True).height
        if other.subtitle_runs:
            height += 2.0 + canvas.measure(other.subtitle_runs, size * 0.72, width - numbers).height
        rows.append((numbers, height, other))
    total = sum(height for _, height, _ in rows) + (size * 0.9 + 0.75) * (len(rows) - 1)
    return rows, total


def _regions(canvas: _Canvas, slide: Slide, body: Box) -> None:
    """The slide's regions side by side, each set from its top, then aligned together.

    Each region is drawn in a group of its own, so aligning moves it whole: words
    stay at the top; pictures standing alone are centred in the room they have; a
    column of pictures shorter than the column of words beside it is centred
    against it, and a taller one starts level with the words.
    """

    style = canvas.deck.style
    names = list(slide.regions)
    available = body.width - style.column_gap * (len(names) - 1)
    boxes = []
    x = body.x
    for share in slide.shares:
        boxes.append(Box(x, body.y, available * share, body.height))
        x += available * share + style.column_gap
    # Figures side by side on one slide set their words at one size: the largest
    # at which every one of them fits its own place.
    shared = None
    figured = [
        (slide.regions[name], box)
        for name, box in zip(names, boxes, strict=True)
        if any(isinstance(block, _Figure) for block in slide.regions[name].blocks)
    ]
    if len(figured) > 1:
        shared = min(_figure_words(canvas, region, box) for region, box in figured)
    placed = []
    outer = canvas.layer
    for name, box in zip(names, boxes, strict=True):
        region = slide.regions[name]
        group = element(outer, "g", id=f"{slide.id}.{name}", data__flexo__talk="region")
        lists, tables = len(canvas.lists), len(canvas.tables)
        canvas.layer = group
        try:
            used = _region(canvas, region, box, words=shared)
        finally:
            canvas.layer = outer
        pictures = bool(region.blocks) and all(isinstance(block, _PICTURES) for block in region.blocks)
        placed.append((group, used, pictures, bool(region.blocks), lists, tables))
    align = slide.align or style.align
    filled = [item for item in placed if item[3]]
    if align == "top" or not filled:
        return
    band = max(used for _, used, *_ in filled)
    worded = [used for _, used, pictures, full, *_ in filled if not pictures]
    words = max(worded, default=0.0)
    lead = max(body.height - band, 0.0) / 2.0 if align == "middle" else 0.0
    for group, used, pictures, full, lists, tables in placed:
        if not full:
            continue
        if not worded:
            # Pictures alone: each centred in the body.
            shift = max(body.height - used, 0.0) / 2.0
        elif pictures:
            shift = lead + (band - used) / 2.0
        elif align == "middle":
            # Words share one top, so columns of words stay aligned with each other.
            shift = lead + (band - words) / 2.0
        else:
            # Words start where the body starts on every slide, beside a taller
            # picture too: the eye finds them in the same place each time.
            shift = 0.0
        if shift > 0.01:
            _shift(canvas, group, shift, lists, tables)


_PICTURES = (_Figure, _Image, _Plot, _Gallery, _Quote, _Table, _Code, _Stats)
"""Blocks that stand on their own -- pictures, and the graphics made of words: a table,
a listing, a row of numbers -- centred in the room they have when nothing else shares it."""


def _shift(canvas: _Canvas, group: ET.Element, down: float, lists: int, tables: int) -> None:
    """Move a drawn region down, with the native lists and tables set in it."""

    group.set("transform", f"translate(0 {number(down)})")
    for layout in canvas.lists[lists:]:
        layout.y += down
        layout.items = [(level, runs, baseline + down) for level, runs, baseline in layout.items]
    for table in canvas.tables[tables:]:
        table.y += down


def _furniture(canvas: _Canvas, slide: Slide) -> None:
    """The slide number and the footer, small and quiet."""

    deck, style = canvas.deck, canvas.deck.style
    if slide.layout in {"title", "section", "statement"}:
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


def _figure_words(canvas: _Canvas, region: Region, box: Box) -> float:
    """The size a region's figures would set their words at on their own, in points."""

    # A trial: what it would note or warn of is said when the region is set.
    diagnostics, notes = len(canvas.diagnostics), len(canvas.notes)
    blocks = _fitted(canvas, region, box)
    prepared, scale, _ = _plan_figures(canvas, blocks, box, None)
    del canvas.diagnostics[diagnostics:], canvas.notes[notes:]
    return min(item.size for item in prepared.values()) * scale


def _plan_figures(
    canvas: _Canvas, blocks: list, box: Box, words: float | None
) -> tuple[dict[int, _Prepared], float, float]:
    """The region's figures laid out for their places, the one scale they take,
    and the height each other picture has."""

    style = canvas.deck.style
    worded = [block for block in blocks if not isinstance(block, _Figure | _Image | _Plot)]  # and tables
    pictures = [block for block in blocks if isinstance(block, _Figure | _Image | _Plot)]
    # Words take what they need; pictures share the height that is left.
    needed = sum(_height(canvas, block, box.width) for block in worded)
    gaps = style.block_gap * max(0, len(blocks) - 1)
    room = box.height - needed - gaps
    share = room / len(pictures) if pictures else 0.0
    # Figures in one place share one scale, so their words are one size: the
    # largest at which all of them fit the room figures have together.
    count = sum(isinstance(block, _Figure) for block in blocks)
    figure_room = max(room * count / len(pictures), 40.0 * count) if count else 0.0
    # Each figure is laid out for its share of the place -- turned or spaced
    # closer if that lets its words be larger -- then all take one scale.
    place = Box(box.x, 0.0, box.width, figure_room / count) if count else box

    def laid(largest: float) -> tuple[dict[int, _Prepared], float]:
        prepared = {
            index: _prepare(canvas, block, place, largest)
            for index, block in enumerate(blocks)
            if isinstance(block, _Figure)
        }
        if not prepared:
            return prepared, 0.0
        return prepared, min(
            min(item.most for item in prepared.values()),
            min(box.width / item.width for item in prepared.values()),
            figure_room / sum(item.height for item in prepared.values()),
        )

    diagnostics, notes = len(canvas.diagnostics), len(canvas.notes)
    prepared, scale = laid(min(style.body_size, words) if words else style.body_size)
    if words and prepared and min(item.size for item in prepared.values()) * scale < words * 0.97:
        # Held to the size of the figures beside them, these fall short of it as
        # laid out for that size: take the layout that reaches it (folded, say),
        # drawn at that size.
        del canvas.diagnostics[diagnostics:], canvas.notes[notes:]
        prepared, scale = laid(style.body_size)
        scale = min(scale, words / max(item.size for item in prepared.values()))
    return prepared, scale, share


def _region(canvas: _Canvas, region: Region, box: Box, *, words: float | None = None) -> float:
    """Set a region's blocks one under the other from the top of ``box``; return
    the height they took. ``words`` caps the size of its figures' words (points),
    so they match the figures beside them."""

    style = canvas.deck.style
    blocks = _fitted(canvas, region, box)
    # A block with its place to itself is centred across it (a table narrower than the place).
    canvas.alone = len(blocks) == 1
    prepared, scale, share = _plan_figures(canvas, blocks, box, words)
    if prepared:
        _check_legible(canvas, prepared.values(), scale)
    top = box.y
    for index, block in enumerate(blocks):
        identifier = f"{canvas.slide.id}.{region.name}.{index}"
        if isinstance(block, _Bullets):
            top += _bullets(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Words):
            size = block.size or style.body_size
            role, fill = _paint_of(block.colour, "muted-ink" if block.muted else "ink")
            top += canvas.words(
                identifier, block.runs, Box(box.x, top, box.width, 0.0), size=size,
                align=block.align, role=role, fill=fill,
            )
        elif isinstance(block, _Gallery):
            top += _gallery(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Figure):
            height = prepared[index].height * scale
            top += _place_figure(canvas, identifier, prepared[index], Box(box.x, top, box.width, height), scale)
        elif isinstance(block, _Image):
            top += _image(canvas, identifier, block, Box(box.x, top, box.width, max(share, 40.0)))
        elif isinstance(block, _Plot):
            top += _plot(canvas, identifier, block, Box(box.x, top, box.width, max(share, 60.0)))
        elif isinstance(block, _Table):
            top += _table(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Code):
            top += _code(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Quote):
            top += _quote(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Stats):
            top += _stats(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Callout):
            top += _callout(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        elif isinstance(block, _Math):
            top += _equation(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
        top += style.block_gap
    return max(top - box.y - style.block_gap, 0.0)


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
    if scale == 1.0 or not isinstance(
        block, _Bullets | _Words | _Table | _Code | _Quote | _Stats | _Callout | _Math
    ):
        return block
    if isinstance(block, _Table):
        base = _table_size(block, style)
    elif isinstance(block, _Code):
        base = _code_size(block, style)
    elif isinstance(block, _Quote):
        base = _quote_size(block, style)
    elif isinstance(block, _Stats):
        base = _stats_size(block, style)
    else:
        base = block.size or style.body_size
    return replace(block, size=base * scale)


def _table_size(block: _Table, style) -> float:
    return block.size or style.body_size * 0.85


def _table_plan(canvas: _Canvas, block: _Table, width: float) -> TableLayout:
    """Column widths and row heights: each column as wide as its widest cell,
    the table set smaller if that is wider than its place."""

    style = canvas.deck.style
    size = _table_size(block, style)
    for _ in range(3):
        pad = size * 0.6
        measured = [
            [canvas.measure(cell, size, None, 700 if block.header and r == 0 else None) for cell in row]
            for r, row in enumerate(block.rows)
        ]
        columns = len(block.rows[0]) if block.rows else 0
        # A little slack, so a slide program measuring a hair wider keeps each cell on one line.
        widths = [
            max((row[c].width for row in measured), default=0.0) + 2 * pad + size * 0.2
            for c in range(columns)
        ]
        if sum(widths) <= width or size <= style.small_size:
            break
        size = max(style.small_size, size * width / sum(widths))
    line = max((m.line_height for row in measured for m in row if m.lines), default=size * 1.2)
    baseline = max((m.baseline for row in measured for m in row if m.lines), default=size)
    lines = [max((len(m.lines) for m in row), default=1) or 1 for row in measured]
    vertical = size * 0.35
    heights = [line * count + 2 * vertical for count in lines]
    return TableLayout(
        0.0, 0.0, widths, heights, block.rows, block.align, size, line, vertical + baseline,
        pad, block.header, (1.1, 0.6, 1.1), palette=canvas.palette,
    )


def _table(canvas: _Canvas, identifier: str, block: _Table, box: Box) -> float:
    plan = _table_plan(canvas, block, box.width)
    total = sum(plan.widths)
    # A table headed in a right-to-left script reads from the right: its first
    # column on the right, the table against the right edge, cells set from the right.
    plan.rtl = bool(plan.cells) and _rtl(tuple(run for cell in plan.cells[0] for run in cell))
    left = box.x + box.width - total if plan.rtl else box.x
    if canvas.alone:
        left = box.x + (box.width - total) / 2.0
    plan.x, plan.y, plan.id = left, box.y, identifier
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="table")
    ink = canvas.palette.get("ink")
    mirrored = {"start": "end", "end": "start", "middle": "middle"}
    y = box.y
    for r, row in enumerate(plan.cells):
        for c, cell in enumerate(row):
            if cell:
                x = left + total - sum(plan.widths[: c + 1]) if plan.rtl else left + sum(plan.widths[:c])
                inner = Box(x + plan.pad, y + plan.baseline, plan.widths[c] - 2 * plan.pad, 0.0)
                metrics = canvas.measure(cell, plan.size, None, 700 if plan.header and r == 0 else None)
                align = mirrored[plan.align[c]] if plan.rtl else plan.align[c]
                anchor = {"start": inner.x, "middle": inner.x + inner.width / 2.0, "end": inner.x + inner.width}
                render_runs(
                    group, f"{identifier}.{r}.{c}", metrics, x=anchor[align], y=inner.y,
                    typography=canvas.deck.typography(plan.size), palette=canvas.palette,
                    fill_role="ink", anchor=align,
                    weight=700 if plan.header and r == 0 else None,
                )
        y += plan.heights[r]
    top_rule, mid_rule, bottom_rule = plan.rules
    rules = [(box.y, top_rule), (y, bottom_rule)]
    if plan.header and len(plan.heights) > 1:
        rules.insert(1, (box.y + plan.heights[0], mid_rule))
    for index, (level, weight) in enumerate(rules):
        element(
            group, "path", id=f"{identifier}.rule{index}",
            d=f"M {number(left)} {number(level)} H {number(left + total)}",
            stroke=ink, stroke_width=weight, fill="none", data__flexo__stroke="ink",
        )
    canvas.tables.append(plan)
    return y - box.y


def _code_size(block: _Code, style) -> float:
    return block.size or style.body_size * 0.72


def _code(canvas: _Canvas, identifier: str, block: _Code, box: Box, *, draw: bool = True) -> float:
    """A listing: each line one text in the monospace family, on a tinted panel."""

    size = _code_size(block, canvas.deck.style)
    pad = size * 0.9
    line = size * 1.35
    height = line * len(block.lines) + 2 * pad
    if not draw:
        return height
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="code")
    widths = [
        canvas.measure((TextRun(text, code=True),), size, None).width for text in block.lines if text.strip()
    ]
    width = min(box.width, max(widths, default=0.0) + 2 * pad)
    element(
        group, "rect", id=f"{identifier}.panel", x=box.x, y=box.y, width=width, height=height,
        rx=size * 0.35, fill=canvas.palette.get("tone-1-fill"), data__flexo__fill="tone-1-fill",
    )
    for index, text in enumerate(block.lines):
        if not text.strip():
            continue
        comment = text.lstrip().startswith(("#", "//", "--", "%"))
        canvas.words(
            f"{identifier}.{index}", (TextRun(text, code=True),),
            Box(box.x + pad, box.y + pad + line * index + (line - size * 1.2) / 2.0, width, 0.0),
            size=size, role="muted-ink" if comment else "ink", parent=group, wrap=False,
        )
    return height


def _quote_size(block: _Quote, style) -> float:
    return block.size or style.body_size * 1.3


def _quote(canvas: _Canvas, identifier: str, block: _Quote, box: Box, *, draw: bool = True) -> float:
    """A quotation in the title face, its opening mark hung in the margin in the accent."""

    style = canvas.deck.style
    size = _quote_size(block, style)
    rtl = _rtl(block.runs)
    mark = (TextRun("\u201d" if rtl else "\u201c"),)
    big = size * 3.6
    metrics = canvas.measure(mark, big, None, title=True)
    # The mark hangs in the margin beside the words, as wide as its ink (a
    # slanted hand's reaches past its advance) and a gap.
    hang = max(metrics.width, _ink_right(canvas, mark[0].text, big)) + size * 0.3
    inner = Box(box.x if rtl else box.x + hang, box.y, box.width - hang, 0.0)
    words = canvas.measure(block.runs, size, inner.width, title=True)
    by_size = max(size * 0.62, style.small_size)
    by = canvas.measure(block.by, by_size, inner.width) if block.by else None
    height = words.height + (size * 0.45 + by.height if by else 0.0)
    if not draw:
        return height
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="quote")
    # The mark's top stands level with the tops of the words' capitals.
    cap, big_cap = words.cap_height or size * 0.7, metrics.cap_height or big * 0.7
    top = box.y + words.baseline - cap + big_cap - metrics.baseline
    canvas.words(
        f"{identifier}.mark", mark, Box(box.x + box.width if rtl else box.x, top, 0.0, 0.0), size=big,
        role="tone-1-stroke", title=True, parent=group, align="end" if rtl else "start",
    )
    canvas.words(f"{identifier}.words", block.runs, inner, size=size, title=True, parent=group)
    if by is not None:
        canvas.words(
            f"{identifier}.by", block.by, replace(inner, y=box.y + words.height + size * 0.45), size=by_size,
            role="muted-ink", parent=group,
        )
    return height


def _ink_right(canvas: _Canvas, character: str, size: float) -> float:
    """How far right of its pen position a character of the title face draws."""

    import uharfbuzz as hb
    from flexo.fonts import hb_font, load_face
    from flexo.text import FontStack

    face = FontStack(canvas.deck.typography(size, title=True)).face(400, False)
    font = hb_font(face, 400)
    buffer = hb.Buffer()
    buffer.add_str(character)
    buffer.guess_segment_properties()
    hb.shape(font, buffer)
    extents = font.get_glyph_extents(buffer.glyph_infos[0].codepoint)
    if extents is None:
        return 0.0
    return (extents.x_bearing + extents.width) * size / load_face(face).upem


def _stats_size(block: _Stats, style) -> float:
    return block.size or style.title_size * 2.0


def _stats(canvas: _Canvas, identifier: str, block: _Stats, box: Box, *, draw: bool = True) -> float:
    """Numbers side by side, each very large in the accent with its label under it."""

    style = canvas.deck.style
    count = len(block.items)
    gap = style.column_gap
    cell = (box.width - gap * (count - 1)) / count
    weight = canvas.deck.title_weight
    size = _stats_size(block, style)
    widest = max(canvas.measure(value, size, None, weight, title=True).width for value, _ in block.items)
    if widest > cell:
        # Every value one size: the size at which the widest fits its cell.
        size *= cell / widest
    label_size = max(size * 0.3, style.small_size * 0.9)
    values = [canvas.measure(value, size, cell, weight, title=True) for value, _ in block.items]
    labels = [canvas.measure(label, label_size, cell) for _, label in block.items]
    tall = max(metrics.height for metrics in values)
    height = tall + size * 0.06 + max(metrics.height for metrics in labels)
    if not draw:
        return height
    align = "middle" if style.title_align == "middle" else "start"
    role, fill = _paint_of(block.colour, "tone-1-stroke")
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="stats")
    rtl = any(_rtl(label) for _, label in block.items)
    for index, (value, label) in enumerate(block.items):
        # Right-to-left labels read their figures from the right.
        slot = count - 1 - index if rtl else index
        x = box.x + slot * (cell + gap)
        canvas.words(
            f"{identifier}.{index}", value, Box(x, box.y, cell, 0.0), size=size, weight=weight, role=role,
            fill=fill, title=True, align=align, parent=group,
        )
        canvas.words(
            f"{identifier}.{index}.label", label, Box(x, box.y + tall + size * 0.06, cell, 0.0),
            size=label_size, role="muted-ink", align=align, parent=group,
        )
    return height


def _callout(canvas: _Canvas, identifier: str, block: _Callout, box: Box, *, draw: bool = True) -> float:
    """Words on a panel tinted in a tone, a bar of the tone along its edge."""

    style = canvas.deck.style
    size = block.size or style.body_size
    pad, bar = size * 0.8, 4.0
    rtl = _rtl(block.runs)
    inner = Box(box.x + pad if rtl else box.x + bar + pad, box.y + pad, box.width - bar - 2 * pad, 0.0)
    heading = canvas.measure(block.title, size, inner.width).height + size * 0.2 if block.title else 0.0
    # The words fill the panel line by line; balanced lines would leave it ragged.
    height = 2 * pad + heading + canvas.measure(block.runs, size, inner.width, balance=False).height
    if not draw:
        return height
    role = f"tone-{block.colour[6:] or 1}-stroke"
    paint = canvas.palette.get(role)
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="callout")
    element(
        group, "rect", id=f"{identifier}.panel", x=box.x, y=box.y, width=box.width, height=height, fill=paint,
        fill_opacity=0.12, data__flexo__fill=role,
    )
    element(
        group, "rect", id=f"{identifier}.bar", x=box.x + box.width - bar if rtl else box.x, y=box.y,
        width=bar, height=height, fill=paint, data__flexo__fill=role,
    )
    top = inner.y
    if block.title:
        top += canvas.words(f"{identifier}.title", block.title, inner, size=size, role=role, parent=group)
        top += size * 0.2
    canvas.words(f"{identifier}.words", block.runs, replace(inner, y=top), size=size, parent=group, balance=False)
    return height


def _paint_of(colour: str | None, default: str) -> tuple[str, str | None]:
    """A block colour as ``(role, literal fill)``: a role or friendly name, or a hex."""

    if not colour:
        return default, None
    if colour.startswith("#"):
        return default, colour
    if colour.startswith("accent"):
        return f"tone-{colour[6:] or 1}-stroke", None
    return {"muted": "muted-ink"}.get(colour, colour), None


def _gallery_plan(canvas: _Canvas, block: _Gallery, width: float) -> tuple[int, float, float, float]:
    """``columns, cell width, picture height, caption height`` of a gallery."""

    style = canvas.deck.style
    count = len(block.items)
    columns = block.columns or (count if count <= 5 else -(-count // 2))
    gap = style.column_gap * 0.6
    cell = (width - gap * (columns - 1)) / columns
    picture = min(block.height or cell, cell)
    size = block.size or style.small_size
    captions = [
        canvas.measure(runs, size, cell, balance=True).height for _, runs in block.items if runs
    ]
    return columns, cell, picture, max(captions, default=0.0)


def _gallery(canvas: _Canvas, identifier: str, block: _Gallery, box: Box, *, draw: bool = True) -> float:
    """Pictures in a grid, each fitted to its cell and centred, a caption under it."""

    style = canvas.deck.style
    columns, cell, picture, caption = _gallery_plan(canvas, block, box.width)
    gap = style.column_gap * 0.6
    under = style.small_size * 0.5 if caption else 0.0
    row_height = picture + under + caption
    rows = -(-len(block.items) // columns)
    height = rows * row_height + (rows - 1) * gap
    if not draw:
        return height
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="gallery")
    # One column stands flush with the words above it; a grid is centred.
    align = block.align or ("start" if columns == 1 else "middle")
    for index, (source, runs) in enumerate(block.items):
        row, column = divmod(index, columns)
        in_row = min(columns, len(block.items) - row * columns)
        # A last row shorter than the others is centred under them.
        shift = (columns - in_row) * (cell + gap) / 2.0 if align == "middle" else 0.0
        x = box.x + shift + column * (cell + gap)
        y = box.y + row * (row_height + gap)
        _fitted_picture(
            canvas, f"{identifier}.{index}", source, Box(x, y, cell, picture), block.crop, group, align=align
        )
        if runs:
            canvas.words(
                f"{identifier}.{index}.caption", runs, Box(x, y + picture + under, cell, 0.0),
                size=block.size or style.small_size, align=align, parent=group,
            )
    return height


def _fitted_picture(
    canvas: _Canvas, identifier: str, source: str, box: Box, crop: str | None, parent: ET.Element,
    *, align: str = "middle",
) -> None:
    """A picture fitted inside ``box``, centred there (or at its left, ``align="start"``),
    and cropped to a circle or square."""

    def across(width: float) -> float:
        return box.x + ((box.width - width) / 2.0 if align == "middle" else 0.0)

    art = load_artwork(identifier, source)
    if art.format == "svg" and _drawable(art.markup):
        # Vectors flexo draws exactly: placed as shapes and live text, fitted and centred.
        natural_w, natural_h = art.width or box.width, art.height or box.height
        scale = min(box.width / natural_w, box.height / natural_h)
        view = [float(v) for v in re.split(r"[ ,]+", ET.fromstring(art.markup).get("viewBox", "").strip()) if v]
        units = (natural_w / view[2]) if len(view) == 4 and view[2] else 1.0
        x = across(natural_w * scale)
        y = box.y + (box.height - natural_h * scale) / 2.0
        _place_svg(canvas, identifier, art.markup, x, y, scale * units)
        return
    if crop and art.format != "svg":
        href, natural_w, natural_h = _cropped(source, crop, Path(source).stat().st_mtime_ns)
    elif art.format == "svg":
        import base64

        href = "data:image/svg+xml;base64," + base64.b64encode(art.markup.encode()).decode()
        natural_w, natural_h = art.width or box.width, art.height or box.height
    else:
        href, natural_w, natural_h = picture_href(art), art.width or box.width, art.height or box.height
    scale = min(box.width / natural_w, box.height / natural_h)
    width, height = natural_w * scale, natural_h * scale
    element(
        parent, "image", id=identifier, x=across(width),
        y=box.y + (box.height - height) / 2.0, width=width, height=height, href=href,
    )


@functools.lru_cache(maxsize=32)
def _cropped(source: str, crop: str, stamp: int = 0) -> tuple[str, float, float]:
    """A photograph cut to a centred square, and to a circle within it: a PNG data URI
    (made once for each version of the file, not each time the slide is drawn)."""

    import base64
    import io

    try:
        from PIL import Image, ImageDraw
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ValueError("cropping pictures needs Pillow: pip install pillow") from error
    with Image.open(source) as opened:
        picture = opened.convert("RGBA")
    side = min(picture.size)
    left, top = (picture.width - side) // 2, (picture.height - side) // 2
    picture = picture.crop((left, top, left + side, top + side)).resize((min(side, 600),) * 2)
    if crop == "circle":
        mask = Image.new("L", picture.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, picture.width - 1, picture.height - 1), fill=255)
        picture.putalpha(mask)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(), 100.0, 100.0


def _equation(canvas: _Canvas, identifier: str, block: _Math, box: Box, *, draw: bool = True) -> float:
    """An equation on its own line, in display style: at the words' size, or as much
    smaller as it takes to fit its place."""

    from flexo.render_common import paint_attributes, run_colour, run_role
    from flexo.texmath import draw as draw_formula
    from flexo.texmath import typeset

    style = canvas.deck.style
    size = block.size or style.body_size
    formula = typeset(block.source, canvas.deck.typography(size), size, display=True)
    if formula.width > box.width > 0:
        size *= box.width / formula.width
        formula = typeset(block.source, canvas.deck.typography(size), size, display=True)
    canvas.say_maths(block.source, formula.problems)
    if draw:
        x = {"start": box.x, "middle": box.x + (box.width - formula.width) / 2.0,
             "end": box.x + box.width - formula.width}.get(block.align, box.x)
        role, fill = _paint_of(block.colour, "ink")

        def paint(colour: str) -> tuple[str | None, str | None]:
            run = TextRun("", color=colour)
            return run_colour(run, canvas.palette) or colour, run_role(run)

        draw_formula(
            canvas.layer, formula, x, box.y + formula.height, colour=paint,
            attributes={"id": identifier, "data__flexo__talk": "math",
                        **paint_attributes(palette=canvas.palette, fill_role=role, fill=fill)},
        )
    return formula.height + formula.depth


def _height(canvas: _Canvas, block, width: float) -> float:
    style = canvas.deck.style
    if isinstance(block, _Gallery):
        return _gallery(canvas, "", block, Box(0.0, 0.0, width, 0.0), draw=False)
    if isinstance(block, _Code):
        return _code(canvas, "", block, Box(0.0, 0.0, width, 0.0), draw=False)
    if isinstance(block, _Quote):
        return _quote(canvas, "", block, Box(0.0, 0.0, width, 0.0), draw=False)
    if isinstance(block, _Stats):
        return _stats(canvas, "", block, Box(0.0, 0.0, width, 0.0), draw=False)
    if isinstance(block, _Callout):
        return _callout(canvas, "", block, Box(0.0, 0.0, width, 0.0), draw=False)
    if isinstance(block, _Math):
        return _equation(canvas, "", block, Box(0.0, 0.0, width, 0.0), draw=False)
    if isinstance(block, _Table):
        return sum(_table_plan(canvas, block, width).heights)
    if isinstance(block, _Words):
        return canvas.measure(block.runs, block.size or style.body_size, width).height
    if isinstance(block, _Bullets):
        size = block.size or style.body_size
        layout = _list_layout(canvas, block, Box(0.0, 0.0, width, 0.0))
        total = 0.0
        for level, runs in block.items:
            offset = layout.offset(level)
            metrics = canvas.measure(runs, size, width - offset, balance=False)
            total += metrics.height + style.paragraph_gap * size
        return total
    return 0.0


def _dark_slide(deck: Deck, slide: Slide) -> bool:
    if slide.dark is not None:
        return slide.dark
    backdrop = slide.backdrop
    if not backdrop:
        return False
    if backdrop.startswith("#"):
        from flexo.colour import is_dark

        return is_dark(backdrop)
    # A picture is as dark as it looks under its shade.
    return _lightness(backdrop) * (1.0 - min(max(slide.shade, 0.0), 1.0)) < 0.45


def _is_picture(page: object) -> bool:
    return isinstance(page, str) and bool(page) and not page.startswith("#")


_PAGE_PICTURES: dict[tuple[str, int, bool], tuple[str, float]] = {}


def _picture(source: str) -> tuple[str, float]:
    """A picture's data URI and its mean lightness (0 to 1), read once for each version of it."""

    path = Path(source)
    stamp = path.stat().st_mtime_ns if path.is_file() else 0
    key = (source, stamp, picture_link.get() is not None)
    known = _PAGE_PICTURES.get(key)
    if known:
        return known
    art = load_artwork("picture", source)
    if art.format == "svg":
        import base64

        href = "data:image/svg+xml;base64," + base64.b64encode(art.markup.encode()).decode()
        lightness = 1.0
    else:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            image.draft("L", (64, 64))  # a JPEG is decoded small, not whole
            lightness = ImageStat.Stat(image.convert("L").resize((32, 32))).mean[0] / 255
        href = picture_href(art)
    if len(_PAGE_PICTURES) > 64:
        _PAGE_PICTURES.clear()
    _PAGE_PICTURES[key] = (href, lightness)
    return href, lightness


def _picture_href(source: str) -> str:
    return _picture(source)[0]


def _lightness(source: str) -> float:
    return _picture(source)[1]


def _slide_palette(deck: Deck, slide: Slide):
    """The deck's paints, or paints for words over this slide's own backdrop: light
    words on a dark one, dark words on a light one when the deck's page is dark."""

    from flexo.colour import is_dark, with_lightness

    palette = deck.palette
    page_dark = is_dark(palette.get("canvas"))
    dark = _dark_slide(deck, slide)
    if (not slide.backdrop and slide.dark is None) or (not dark and not page_dark):
        return palette
    light, deep = {"ink": "#f7f5f0", "muted-ink": "#d4d0c8"}, {"ink": "#1c1c1e", "muted-ink": "#55555a"}
    paints = light if dark else deep
    for role, colour in palette.paints.items():
        # Accents drawn for the page read poorly on a backdrop of the other kind.
        if role.startswith("tone-") and role.endswith("-stroke") and is_dark(colour) == dark:
            paints[role] = with_lightness(colour, 0.78 if dark else 0.45, 0.14)
    return palette.with_overrides(paints)


def _slide_background(canvas: _Canvas, slide: Slide) -> None:
    """A slide's own background: a colour over the page, or a picture filling it
    (cropped to the slide, never stretched) under an optional dark shade."""

    style = canvas.deck.style
    source = slide.backdrop or ""
    if source.startswith("#"):
        canvas.root.find(f".//{{{SVG_NS}}}rect[@id='canvas.background']").set("fill", source)  # type: ignore[union-attr]
        return
    href = _picture_href(source)
    element(
        canvas.layer, "image", id=f"{slide.id}.backdrop", x=0.0, y=0.0, width=style.width,
        height=style.height, preserveAspectRatio="xMidYMid slice", href=href,
    )
    if slide.shade > 0:
        element(
            canvas.layer, "rect", id=f"{slide.id}.shade", x=0.0, y=0.0, width=style.width,
            height=style.height, fill="#000000", fill_opacity=min(slide.shade, 1.0),
        )


def _rtl(runs: tuple[TextRun, ...]) -> bool:
    """Whether words read right to left (their first strong letter does)."""

    from flexo.bidi import base_level

    return base_level("".join(run.text for run in runs)) == 1


def _list_layout(canvas: _Canvas, block: _Bullets, box: Box) -> ListLayout:
    """The geometry of a list: sizes, gaps, and where numbers and words start."""

    style = canvas.deck.style
    size = block.size or style.body_size
    layout = ListLayout(
        box.x, box.y, box.width, size, size * style.line_height, style.paragraph_gap * size,
        style.indent, numbered=block.numbered, reveal=block.reveal, palette=canvas.palette,
    )
    if block.numbered:
        count = sum(level == 0 for level, _ in block.items)
        widest = max(canvas.measure((TextRun(f"{n}."),), size, None).width for n in range(1, count + 1))
        layout.number_room = widest + size * 0.45
    return layout


def _bullets(canvas: _Canvas, identifier: str, block: _Bullets, box: Box) -> float:
    style = canvas.deck.style
    size = block.size or style.body_size
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="bullets")
    layout = _list_layout(canvas, block, box)
    top = box.y
    number = 0
    step = 0
    for index, (level, runs) in enumerate(block.items):
        if level == 0:
            step += 1
        # A revealed item (with the items under it) is its own group, tagged with its step.
        item = element(group, "g", data__flexo__step=step + 1) if block.reveal else group
        if block.reveal:
            canvas.steps = max(canvas.steps, step + 1)
        offset = layout.offset(level)
        metrics = canvas.measure(runs, size, box.width - offset, balance=False)
        layout.line_height = metrics.line_height
        baseline = top + metrics.baseline
        role = "tone-1-stroke" if level == 0 else "muted-ink"
        rtl = _rtl(runs)

        def across(distance: float, rtl: bool = rtl) -> float:
            """A distance in from the list's start edge: the left, or the right for RTL."""

            return box.x + box.width - distance if rtl else box.x + distance
        if block.numbered and level == 0:
            number += 1
            label = (TextRun(f"{number}."),)
            canvas.words(
                f"{identifier}.{index}.mark", label,
                Box(across(0.0), top + metrics.baseline - canvas.measure(label, size, None).baseline, 0.0, 0.0),
                size=size, role=role, parent=item, align="end" if rtl else "start",
            )
        else:
            radius = size * (0.15 if level == 0 else 0.12)
            cx = across(style.indent * level + size * 0.3)
            cy = baseline - (metrics.cap_height or size * 0.7) / 2.0
            element(
                item, "circle", id=f"{identifier}.{index}.mark", cx=cx, cy=cy, r=radius,
                fill=canvas.palette.get(role), data__flexo__fill=role,
            )
        render_runs(
            item, f"{identifier}.{index}", metrics, x=across(offset), y=baseline,
            typography=canvas.deck.typography(size), palette=canvas.palette, fill_role="ink",
            anchor="end" if rtl else None,
        )
        layout.items.append((level, runs, baseline))
        layout.steps.append(metrics.line_height)
        layout.id = identifier
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
    """The largest scale: words no larger than the body text (or the figures' beside it)."""
    size: float
    """The size of its words, unscaled."""
    id: str


LEGIBLE = 7.0
"""Words on a slide smaller than this (points) are reported: they will not read."""


def _prepare(canvas: _Canvas, block: _Figure, box: Box, largest: float) -> _Prepared:
    """A figure laid out for ``box`` by flexo (``flexo.fit_in_box``): at the width
    that sets its words at the deck's figure size, as written or turned, spaced
    as the theme says or closer -- whichever lets its words be largest there,
    though never larger than ``largest`` (the body text, or the words of the
    figures beside it)."""

    deck = canvas.deck
    figure = made(block.figure)
    spec = figure.spec if isinstance(figure, flexo.Figure) else figure
    if not isinstance(figure, flexo.Figure) or spec.style != deck.theme:
        # A figure made elsewhere is redrawn in the deck's look.
        spec = replace(
            spec, style=deck.theme, palette=deck.palette_name,
            font=deck.figure_font or deck.font or spec.font,
        )
    style = figure_style(spec)
    base = style.typography.size.points
    # The palette is in the key too: a theme file's colours can change under the same name.
    key = (
        spec, style, repr(figure_palette(spec)), box.width, box.height, deck.style.figure_size,
        largest, block.turn,
    )
    laid = _cached_fit(key)
    if laid is None:
        fit = flexo.fit_in_box(
            spec, box.width, box.height, words=min(deck.style.figure_size, largest), largest=largest,
            turn=block.turn,
        )
        codes = [
            diagnostic.code
            for diagnostic in lint_compilation(fit.compilation, style=fit.style).diagnostics
            # The figure is laid out for its place and scaled to it: a grown width is moot.
            if diagnostic.code != "layout.width.grown"
        ]
        laid = {"svg": fit.compilation.document.text, "ink": list(fit.ink), "layout": fit.layout, "codes": codes}
        _store_fit(key, laid)
    for code in laid["codes"]:
        canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}: {code}")
    if laid["layout"] != "as written":
        canvas.notes.append(f"{canvas.slide.id} {spec.id}: laid out {laid['layout']} to fit the slide")
    left, top, width, height = laid["ink"]
    return _Prepared(laid["svg"], left, top, width, height, largest / base, base, spec.id)


# -- the figure cache --------------------------------------------------------------------

_FLEXO_FINGERPRINT: list[str] = []


def _fingerprint() -> str:
    """A hash of flexo's own source: any change to the engine makes cached layouts stale."""

    if not _FLEXO_FINGERPRINT:
        import hashlib

        digest = hashlib.sha256()
        root = Path(flexo.__file__).parent
        for path in sorted(root.rglob("*.py")):
            digest.update(path.read_bytes())
        _FLEXO_FINGERPRINT.append(digest.hexdigest()[:16])
    return _FLEXO_FINGERPRINT[0]


def _cache_path(key: tuple) -> Path | None:
    """Where a figure laid out for a box is kept between builds (``FLEXO_TALK_CACHE=0``
    turns the cache off; ``FLEXO_TALK_CACHE=/some/dir`` moves it)."""

    import hashlib
    import os
    import sys

    setting = os.environ.get("FLEXO_TALK_CACHE", "")
    if setting == "0":
        return None
    if setting:
        folder = Path(setting)
    elif sys.platform == "darwin":
        folder = Path.home() / "Library/Caches/flexo-talk"
    else:
        folder = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "flexo-talk"
    name = hashlib.sha256(repr((key, _fingerprint())).encode("utf-8")).hexdigest()[:32]
    return folder / "fits" / f"{name}.json"


def _cached_fit(key: tuple) -> dict | None:
    import json

    path = _cache_path(key)
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _store_fit(key: tuple, laid: dict) -> None:
    import json

    path = _cache_path(key)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(laid), encoding="utf-8")
    except OSError:
        return


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

    from flexo_talk.worker import RemotePlot

    figure = made(block.figure)
    width = box.width
    height = min(box.height, width / block.aspect) if block.aspect else box.height
    family = canvas.deck.layout_style.typography.family
    if isinstance(figure, RemotePlot):
        svg = figure.svg(width, height, family, identifier)
    else:
        svg = plot_svg(figure, width, height, family, identifier)
    _place_svg(canvas, identifier, svg, box.x, box.y, 1.0)
    return height


def plot_svg(figure: Any, width: float, height: float, family: str, identifier: str) -> str:
    """A matplotlib figure as SVG, laid out again at ``width`` by ``height`` points, its
    words set in ``family`` and kept as text; the figure is closed after."""

    import io

    import matplotlib
    import matplotlib.text

    register_fonts_with_matplotlib()
    figure.set_size_inches(width / 72.0, height / 72.0)
    if figure.get_layout_engine() is None:
        figure.set_layout_engine("constrained")
    texts = figure.findobj(matplotlib.text.Text)
    # Characters the deck's face lacks (a plot labelled in Persian) get an installed
    # family that has them, so matplotlib measures the words it lays out.
    from flexo.fonts import family_covering, family_faces, load_face, select_face

    faces = family_faces(family)
    primary = load_face(select_face(faces, 400, False)) if faces else None
    missing = {
        ch for text in texts for ch in text.get_text() if not ch.isspace() and ch.isalpha()
        and (primary is None or not primary.has(ch))
    }
    covering = family_covering(missing) if missing else None
    families = [family, covering] if covering else [family]
    for text in texts:
        text.set_fontfamily(families)
    settings = {
        "svg.fonttype": "none",
        "svg.hashsalt": identifier,
        "mathtext.fontset": "custom",
        "mathtext.rm": family,
        "mathtext.it": f"{family}:italic",
        "mathtext.bf": f"{family}:bold",
        "mathtext.fallback": "stix",
    }
    import logging

    # matplotlib reports every face it substitutes; the deck sets the words itself.
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    buffer = io.StringIO()
    with matplotlib.rc_context(settings):
        try:
            figure.savefig(buffer, format="svg", transparent=True, metadata={"Date": None})
        except (ZeroDivisionError, ValueError) as error:
            said = _plot_maths(figure, error)
            if said:
                import matplotlib.pyplot as plt

                plt.close(figure)
                raise ValueError(said) from None
            # Constrained layout cannot take over a figure built without it
            # (a colour bar made first): lay it out tightly instead.
            figure.set_layout_engine("tight")
            buffer = io.StringIO()
            figure.savefig(buffer, format="svg", transparent=True, metadata={"Date": None})
    # Drawn: pyplot need not keep it open (each redraw makes the plot afresh).
    import matplotlib.pyplot as plt

    plt.close(figure)
    return buffer.getvalue()


def _plot_maths(figure: Any, error: Exception) -> str | None:
    """A plot's words matplotlib could not set as maths, said plainly: which words, and
    why, as flexo reads the formula -- not matplotlib's parser's own report."""

    import matplotlib.text

    message = str(error)
    if "Parse" not in message and "Unknown symbol" not in message:
        return None
    formula = next((line.strip() for line in message.splitlines() if line.strip()), "")
    words = next(
        (text.get_text() for text in figure.findobj(matplotlib.text.Text) if formula and formula in text.get_text()),
        f"${formula}$",
    )
    from flexo.texmath import problems_in

    problems = problems_in(formula)
    if problems:
        reason = problems[0]
    elif "\\begin" in formula:
        reason = "matplotlib's maths has no environments (matrices, cases): set the formula on the slide instead"
    else:
        reason = "matplotlib's maths does not know all of it: set the formula on the slide instead"
    shown = words if len(words) <= 60 else words[:59] + "\u2026"
    return f"the plot's words \u201c{shown}\u201d are maths matplotlib cannot set: {reason}"


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
        href = picture_href(art)
    element(
        canvas.layer, "image", id=identifier, x=box.x + (box.width - width) / 2.0, y=box.y,
        width=width, height=height, href=href,
    )
    return height
