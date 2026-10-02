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

import contextlib
import contextvars
import functools
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, NamedTuple

import flexo
from flexo.artwork import load_artwork, picture_href, picture_link
from flexo.ir.measured import TextMetrics
from flexo.ir.semantic import TextRun
from flexo.lint import lint_compilation
from flexo.render_common import render_runs
from flexo.style import Palette, TypographyStyle
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
    WordsLayout,
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
    link_colour,
    made,
    paint_role,
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


MOST_CHARACTERS = 20_000
"""The most characters one passage of words is set with (a page of a paper is ~3,000)."""


class _Canvas:
    """The slide's SVG under construction, and what writers need beside it."""

    def __init__(self, deck: Deck, slide: Slide) -> None:
        style = deck.style
        self.deck = deck
        self.slide = slide
        self.palette = deck.palette
        self.palette = _slide_palette(deck, slide)
        self.link = link_colour(self.palette)
        """What links are painted in where the accent would not tell them from the words."""
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
        self.worded: list[WordsLayout] = []
        self.diagnostics: list[str] = []
        self.lost: set[str] = set()
        """Characters no font here draws, left out of the slide's drawing."""
        if slide.backdrop:
            _words_over_picture(self, slide)
        self.tables: list[TableLayout] = []
        self.notes: list[str] = []
        self.held: list[str] = []
        self.settled = True
        """False when a figure on the slide kept its layout while being edited (``EDITING``)."""
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
        runs = self._drawable(runs, typography)
        if self.link and any(run.link and not run.color for run in runs):
            runs = tuple(replace(run, color=self.link) if run.link and not run.color else run for run in runs)
        # A word wider than the slide (a URL) breaks rather than running off it. A width
        # made by adding and taking away the words' own (a table's column) can fall a
        # rounding error short of them: that is room enough, not a reason to break a word.
        return TextMeasurer(typography).measure(
            runs, max_width=width + 1e-6 if width else width, weight=weight, balance=balance,
            break_words=True,
        )

    def _drawable(self, runs: tuple[TextRun, ...], typography: object) -> tuple[TextRun, ...]:
        """The runs with what no font here draws (emoji, pictographs) left out, and said
        once for the slide; the PowerPoint keeps them, for its own fonts to draw."""

        from flexo.text import font_stack

        stack = font_stack(typography)
        lost: set[str] = set()
        kept: list[TextRun] = []
        total = sum(len(run.text) for run in runs)
        if total > MOST_CHARACTERS:
            # More than any slide holds (a pasted file): cut, so it is drawn (and said) at once.
            said = (f"{self.slide.id}: words of {total:,} characters cut to {MOST_CHARACTERS:,} -- "
                    "more than a slide can show")
            if said not in self.diagnostics:
                self.diagnostics.append(said)
            cut, left = [], MOST_CHARACTERS
            for run in runs:
                if left <= 0:
                    break
                cut.append(replace(run, text=run.text[:left]))
                left -= len(run.text)
            runs = tuple(cut)
        for run in runs:
            missing = set() if run.math else stack.missing(run.text, run.italic)
            if missing and stack.adopt(missing):
                missing = stack.missing(run.text, run.italic)
            if missing:
                lost |= missing
                run = replace(run, text="".join(ch for ch in run.text if ch not in missing))
            kept.append(run)
        if lost - self.lost:
            # One line for the slide, however many of its words lost something.
            before = self._lost_said()
            self.lost |= lost
            if before in self.diagnostics:
                self.diagnostics[self.diagnostics.index(before)] = self._lost_said()
            else:
                self.diagnostics.append(self._lost_said())
        return tuple(kept)

    def _lost_said(self) -> str:
        return (f"{self.slide.id}: no font here draws {' '.join(sorted(self.lost))} -- left out of "
                "the slide's drawing (emoji are not drawn: a picture can show one)")

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
        if any(run.math for run in runs):
            typography = self.deck.typography(size, title=title)
            colour = fill or self.palette.get(role)
            self.worded.append(WordsLayout(
                identifier, x, box.y + metrics.baseline, metrics.width, metrics.line_height,
                [line.runs for line in metrics.lines], size, align, typography.family, weight, colour,
            ))
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
        # Down the edge the slide's words start from: the right, for a right-to-left title.
        x = width - 6.0 if slide.title_runs and _rtl(slide.title_runs) else 0.0
        _paint_rect(canvas, f"{slide.id}.edge", Box(x, 0.0, 6.0, height), "tone-1-stroke")
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
    # One line for each thing said, however many places on the slide said it.
    return RenderedSlide(
        slide, xml_document(canvas.root), canvas.lists, list(dict.fromkeys(canvas.diagnostics)), canvas.tables,
        canvas.notes,
        canvas.steps, canvas.held, canvas.worded, canvas.settled,
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


@contextlib.contextmanager
def _on_field(canvas: _Canvas):
    """Words set on the accent field (a band): an accent word or a link in them is lifted
    off the field, rather than drawn in its colour on it."""

    from flexo.colour import with_contrast

    field = accent_field(canvas.deck.palette)
    saved, link = canvas.palette, canvas.link
    canvas.palette = saved.with_overrides({
        role: with_contrast(colour, field, 3.0)
        for role, colour in saved.paints.items() if role.endswith(("-stroke", "-motif"))
    })
    canvas.link = link and link_colour(saved, field)
    try:
        yield
    finally:
        canvas.palette, canvas.link = saved, link


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
    with _on_field(canvas) if style.header == "band" else contextlib.nullcontext():
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
    # A right-to-left title stands flush right, its accent bar to its right.
    rtl = opening != "centred" and _rtl(slide.title_runs)
    if rtl:
        left = width - left - width * 0.72
    box = Box(margin * 2, 0.0, width - 4 * margin, 0.0) if opening == "centred" else Box(left, 0.0, width * 0.72, 0.0)
    align = "middle" if opening == "centred" else "start"
    for scale in _SHRINK:
        title = canvas.measure(slide.title_runs, size * scale, box.width, bold, title=True)
        subtitle = (canvas.measure(slide.subtitle_runs, subtitle_size * scale, box.width)
                    if slide.subtitle_runs else None)
        byline = (canvas.measure(slide.byline_runs, style.subtitle_size * scale, box.width)
                  if slide.byline_runs else None)
        block = title.height + (subtitle.height + 14.0 if subtitle else 0.0)
        needed = block + (byline.height + 34.0 if byline else 0.0) + (margin * 1.6 if opening == "band" else 0.0)
        if needed <= height - 2 * margin:
            break
    _said_shrunk(canvas, slide, scale)
    size, subtitle_size = size * scale, subtitle_size * scale
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
            bar = width - margin * 1.5 - 5.0 if rtl else margin * 1.5
            _paint_rect(canvas, f"{slide.id}.bar", Box(bar, top + 4.0, 5.0, block - 4.0), "tone-1-stroke")
    first = top
    with _on_field(canvas) if opening == "band" else contextlib.nullcontext():
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
            f"{slide.id}.byline", slide.byline_runs, replace(box, y=after), size=style.subtitle_size * scale,
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
    # A right-to-left title stands at the right: its rule and its number with it.
    rtl = align == "start" and _rtl(slide.title_runs)
    left = width / 2.0 - 30.0 if align == "middle" else (box.x + box.width - 60.0 if rtl else box.x)
    figure_align = "end" if rtl else align
    bold = deck.title_weight
    for scale in _SHRINK:
        size = style.title_size * 1.25 * scale
        title = canvas.measure(slide.title_runs, size, box.width, bold, title=True)
        subtitle = (canvas.measure(slide.subtitle_runs, style.subtitle_size, box.width)
                    if slide.subtitle_runs else None)
        # Set about the middle of the slide, with the number or rule above it.
        needed = 2 * title.height + (subtitle.height + 10.0 if subtitle else 0.0) + style.title_size * 2.6
        if needed <= height - 2 * margin:
            break
    _said_shrunk(canvas, slide, scale)
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
            align=figure_align,
        )
        top += figure.height + 6.0
    elif sections == "fill":
        small = style.subtitle_size
        figure = canvas.measure(number, small, None, 700)
        total = figure.height + 16.0 + title.height + (subtitle.height + 10.0 if subtitle else 0.0)
        top = (height - total) / 2.0
        canvas.words(
            f"{slide.id}.number", number, replace(box, y=top), size=small, weight=700, role="muted-ink",
            align=figure_align,
        )
        _paint_rect(canvas, f"{slide.id}.rule", Box(left, top + figure.height + 6.0, 60.0, 3.0), "ink")
        top += figure.height + 16.0
    else:
        top = max(height / 2.0 - title.height, margin + 22.0)
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


_SHRINK = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
"""The sizes a title, section or statement slide tries, of its own, to fit its words."""


def _said_shrunk(canvas: _Canvas, slide: Slide, scale: float) -> None:
    if scale < 1.0:
        canvas.diagnostics.append(f"{slide.id}: words set at {round(scale * 100)}% to fit")
    if scale == _SHRINK[-1]:
        canvas.diagnostics.append(f"{slide.id}: the words do not fit even at half their size -- shorten them")


def _statement_slide(canvas: _Canvas, slide: Slide) -> None:
    """One sentence, large, in the middle of the slide; who said it under it."""

    deck, style = canvas.deck, canvas.deck.style
    width, height = style.width, style.height
    box = Box(width * 0.14, 0.0, width * 0.72, 0.0)
    for scale in _SHRINK:
        size = style.title_size * 1.3 * scale
        words = canvas.measure(slide.title_runs, size, box.width, deck.title_weight, title=True)
        byline = canvas.measure(slide.byline_runs, style.subtitle_size, box.width) if slide.byline_runs else None
        if words.height + (byline.height + 24.0 if byline else 0.0) <= height - 2 * style.margin:
            break
    _said_shrunk(canvas, slide, scale)
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
    """The deck's sections, numbered, one to a row with hairlines between them: in two
    columns when one would run past the slide even set smaller."""

    style = canvas.deck.style
    sections = [other for other in slide.deck.slides if other.layout == "section"]
    if not sections:
        canvas.diagnostics.append(f"{slide.id}: the agenda lists section slides, and the deck has none")
        return
    size = style.body_size * 1.1
    gap = style.column_gap
    for columns in (1, 2):
        width = (body.width - gap * (columns - 1)) / columns
        per = -(-len(sections) // columns)
        for scale in (1.0, 0.9, 0.8, 0.7):
            parts = [_agenda_rows(canvas, sections[at : at + per], size * scale, width)
                     for at in range(0, len(sections), per)]
            total = max(part_total for _, part_total in parts)
            if total <= body.height:
                break
        if total <= body.height:
            break
    else:
        canvas.diagnostics.append(
            f"{slide.id}: the agenda's {len(sections)} sections do not fit even in two columns -- "
            "fewer sections, or shorter titles"
        )
    size *= scale
    first = body.y
    if (slide.align or style.align) == "middle":
        first += max(body.height - total, 0.0) / 2.0
    index = 0
    for column, (rows, _) in enumerate(parts):
        left = body.x + column * (width + gap)
        top = first
        for position, (numbers, height, other) in enumerate(rows):
            identifier = f"{slide.id}.agenda{index}"
            number = (TextRun(f"{index + 1:02d}"),)
            # A right-to-left section's number stands at the right of its row.
            rtl = _rtl(other.title_runs)
            at = left + width - numbers if rtl else left
            words_at = left if rtl else left + numbers
            canvas.words(
                f"{identifier}.number", number, Box(at, top, numbers, 0.0), size=size,
                weight=canvas.deck.title_weight, role="tone-1-stroke", title=True,
                align="end" if rtl else "start",
            )
            used = canvas.words(
                identifier, other.title_runs, Box(words_at, top, width - numbers, 0.0), size=size,
                weight=canvas.deck.title_weight, title=True,
            )
            if other.subtitle_runs:
                canvas.words(
                    f"{identifier}.subtitle", other.subtitle_runs,
                    Box(words_at, top + used + 2.0, width - numbers, 0.0),
                    size=size * 0.72, role="muted-ink",
                )
            top += height
            index += 1
            if position < len(rows) - 1:
                _paint_rect(
                    canvas, f"{identifier}.rule", Box(left, top + size * 0.45, width, 0.75), "muted-ink",
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
    stay at the top; pictures standing alone stand at the room's optical centre
    (``OPTICAL``), its middle with ``align="middle"``; a column of pictures shorter
    than the column of words beside it is centred against it, and a taller one
    starts level with the words.
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
        sizes = [size for region, box in figured if (size := _figure_words(canvas, region, box))]
        shared = min(sizes) if sizes else None
    panels = _panel_row(canvas, slide, names, boxes)
    placed = []
    outer = canvas.layer
    for name, box in zip(names, boxes, strict=True):
        region = slide.regions[name]
        # Its room, in the slide's units: where an editor drops a part into it, empty too.
        room = " ".join(number(value) for value in (box.x, box.y, box.width, box.height))
        group = element(
            outer, "g", id=f"{slide.id}.{name}", data__flexo__talk="region", data__flexo__box=room
        )
        lists, tables = len(canvas.lists), (len(canvas.tables), len(canvas.worded))
        canvas.layer = group
        try:
            used = _region(canvas, region, box, words=shared, panel=panels.get(name, 0.0))
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
            # Pictures alone: each a little above the middle of the body, where the eye
            # takes the middle to be, so a short one stays with its title.
            shift = max(body.height - used, 0.0) * (0.5 if align == "middle" else OPTICAL)
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


OPTICAL = 0.4
"""The share of the free room left above a picture standing alone: its optical centre
is above the middle, as a page's text block is set above its middle."""

_PICTURES = (_Figure, _Image, _Plot, _Gallery, _Quote, _Table, _Code, _Stats)
"""Blocks that stand on their own -- pictures, and the graphics made of words: a table,
a listing, a row of numbers -- set in the room they have when nothing else shares it."""


def _shift(canvas: _Canvas, group: ET.Element, down: float, lists: int, tables: tuple[int, int]) -> None:
    """Move a drawn region down, with the native lists, tables and words set in it."""

    group.set("transform", f"translate(0 {number(down)})")
    for layout in canvas.lists[lists:]:
        layout.y += down
        layout.items = [(level, runs, baseline + down) for level, runs, baseline in layout.items]
    for table in canvas.tables[tables[0]:]:
        table.y += down
    for words in canvas.worded[tables[1]:]:
        words.baseline += down


def _furniture(canvas: _Canvas, slide: Slide) -> None:
    """The slide number and the footer, small and quiet."""

    deck, style = canvas.deck, canvas.deck.style
    if slide.layout in {"title", "section", "statement"}:
        return
    size = style.small_size * 0.8
    y = style.height - style.margin + size * 0.2
    footer = inline(deck.footer) if deck.footer else ()
    # A footer in a right-to-left script stands at the right, the number at the left.
    rtl = bool(footer) and _rtl(footer)
    if style.numbers:
        x = style.margin if rtl else style.width - style.margin - 60.0
        canvas.words(
            f"{slide.id}.number", (TextRun(str(slide.index)),),
            Box(x, y, 60.0, 0.0), size=size, align="start" if rtl else "end", role="muted-ink",
        )
    if footer:
        half = style.width / 2.0
        place = Box(half, y, half - style.margin, 0.0) if rtl else Box(style.margin, y, half, 0.0)
        canvas.words(
            f"{slide.id}.footer", footer, place, size=size, role="muted-ink", align="end" if rtl else "start",
        )


# -- regions ---------------------------------------------------------------------------


def _panel_row(canvas: _Canvas, slide: Slide, names: list[str], boxes: list[Box]) -> dict[str, float]:
    """The height of each column's opening callout, where columns side by side open with
    one: the tallest's, so they stand as a row of panels, as cards in a row do."""

    # A trial: what it would note or warn of is said when the region is set.
    diagnostics, notes = len(canvas.diagnostics), len(canvas.notes)
    heights = {}
    for name, box in zip(names, boxes, strict=True):
        region = slide.regions[name]
        if region.blocks and isinstance(region.blocks[0], _Callout):
            heights[name] = _callout(canvas, "", _fitted(canvas, region, box)[0], box, draw=False)
    del canvas.diagnostics[diagnostics:], canvas.notes[notes:]
    return dict.fromkeys(heights, max(heights.values())) if len(heights) > 1 else {}


def _figure_words(canvas: _Canvas, region: Region, box: Box) -> float | None:
    """The size a region's figures would set their words at on their own, in points
    (``None`` when every one is drawn at a width of its own)."""

    # A trial: what it would note or warn of is said when the region is set.
    diagnostics, notes = len(canvas.diagnostics), len(canvas.notes)
    blocks = _fitted(canvas, region, box)
    prepared, scales, _ = _plan_figures(canvas, blocks, box, None)
    del canvas.diagnostics[diagnostics:], canvas.notes[notes:]
    sizes = [item.size * scales[index] for index, item in prepared.items() if blocks[index].width is None]
    return min(sizes) if sizes else None


def _plan_figures(
    canvas: _Canvas, blocks: list, box: Box, words: float | None
) -> tuple[dict[int, _Prepared], dict[int, float], float]:
    """The region's figures laid out for their places, the scale each takes, and the
    height each other picture has."""

    style = canvas.deck.style
    worded = [block for block in blocks if not isinstance(block, _Figure | _Image | _Plot | _Gallery)]
    pictures = [block for block in blocks if isinstance(block, _Figure | _Image | _Plot | _Gallery)]
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

    def laid(largest: float) -> tuple[dict[int, _Prepared], dict[int, float]]:
        prepared = {
            index: _prepare(canvas, block, place, largest)
            for index, block in enumerate(blocks)
            if isinstance(block, _Figure)
        }
        # A figure given a width is drawn that wide, as far as its place allows, its
        # words whatever size that makes them; the others share the height it leaves.
        sized = {index: item for index, item in prepared.items() if blocks[index].width is not None}
        free = {index: item for index, item in prepared.items() if index not in sized}
        scales = {
            index: min(blocks[index].width, box.width) / item.width for index, item in sized.items()
        }
        tall = sum(item.height * scales[index] for index, item in sized.items())
        most = figure_room - 40.0 * len(free)
        if sized and tall > most:
            scales = {index: scale * max(most, 1.0) / tall for index, scale in scales.items()}
        if free:
            left = figure_room - sum(item.height * scales[index] for index, item in sized.items())
            scale = min(
                min(item.most for item in free.values()),
                min(box.width / item.width for item in free.values()),
                max(left, 40.0 * len(free)) / sum(item.height for item in free.values()),
            )
            scales |= dict.fromkeys(free, scale)
        return prepared, scales

    # A figure's words are the size of the words around it at most; a figure slide's,
    # its title's, so a small figure there fills the slide rather than floating in it.
    most = style.title_size if canvas.slide.layout == "figure" else style.body_size
    diagnostics, notes = len(canvas.diagnostics), len(canvas.notes)
    prepared, scales = laid(min(most, words) if words else most)
    free = [index for index in prepared if blocks[index].width is None]
    if words and free and min(prepared[index].size * scales[index] for index in free) < words * 0.97:
        # Held to the size of the figures beside them, these fall short of it as
        # laid out for that size: take the layout that reaches it (folded, say),
        # drawn at that size.
        del canvas.diagnostics[diagnostics:], canvas.notes[notes:]
        prepared, scales = laid(most)
        cap = words / max(prepared[index].size for index in free)
        scales |= {index: min(scales[index], cap) for index in free}
    return prepared, scales, share


def _region(
    canvas: _Canvas, region: Region, box: Box, *, words: float | None = None, panel: float = 0.0
) -> float:
    """Set a region's blocks one under the other from the top of ``box``; return
    the height they took. ``words`` caps the size of its figures' words (points),
    so they match the figures beside them; ``panel`` is the least height of a callout
    it opens with, so it matches the callouts beside it."""

    style = canvas.deck.style
    blocks = _fitted(canvas, region, box)
    # A block with its place to itself is centred across it (a table narrower than the place).
    canvas.alone = len(blocks) == 1
    prepared, scales, share = _plan_figures(canvas, blocks, box, words)
    _check_legible(canvas, prepared, scales)
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
            top += _gallery(canvas, identifier, block, Box(box.x, top, box.width, max(share, 40.0)))
        elif isinstance(block, _Figure):
            scale = scales[index]
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
            least = panel if index == 0 else 0.0
            top += _callout(canvas, identifier, block, Box(box.x, top, box.width, 0.0), least=least)
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
    blocks = [_capped(canvas, block) for block in region.blocks]
    pictures = sum(isinstance(block, _Figure | _Image | _Plot | _Gallery) for block in blocks)
    room = box.height - style.block_gap * max(0, len(blocks) - 1) - PICTURE_LEAST * pictures

    def needed(scale: float) -> float:
        # Pictures (and galleries) take what is left: only words are fitted here.
        return sum(
            _height(canvas, _sized(block, scale, style), box.width)
            for block in blocks if not isinstance(block, _Gallery)
        )

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


MOST_ITEMS = 300
"""The most items of a list, rows of a table or lines of code drawn on one slide (500
lines of code): more than any slide shows, cut so the slide is drawn (and said) at once."""


def _capped(canvas: _Canvas, block):
    """``block``, cut to what a slide can hold if it is far past it, and said."""

    if isinstance(block, _Bullets) and len(block.items) > MOST_ITEMS:
        kept, what = replace(block, items=block.items[:MOST_ITEMS]), f"a list of {len(block.items):,} items"
    elif isinstance(block, _Table) and len(block.rows) > MOST_ITEMS:
        kept, what = replace(block, rows=block.rows[:MOST_ITEMS]), f"a table of {len(block.rows):,} rows"
    elif isinstance(block, _Code) and len(block.lines) > MOST_ITEMS * 5 // 3:
        kept, what = replace(block, lines=block.lines[: MOST_ITEMS * 5 // 3]), f"{len(block.lines):,} lines of code"
    else:
        return block
    canvas.diagnostics.append(f"{canvas.slide.id}: {what} cut to what a slide can show -- split them across slides")
    return kept


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


def _table_plan(canvas: _Canvas, block: _Table, width: float, *, said: bool = False) -> TableLayout:
    """Column widths and row heights: each column as wide as its widest cell when the
    table fits its place; else its long cells wrap (a column as narrow as its longest
    word at least), and the table is set smaller only when even its words do not fit.
    ``said``: say on the slide when its words had to be broken."""

    style = canvas.deck.style
    size = _table_size(block, style)
    columns = len(block.rows[0]) if block.rows else 0

    def weight(r: int) -> int | None:
        return 700 if block.header and r == 0 else None

    while True:
        pad = size * 0.6
        # A little slack, so a slide program measuring a hair wider keeps each cell's lines.
        slack = 2 * pad + size * 0.2
        measured = [[canvas.measure(cell, size, None, weight(r)) for cell in row] for r, row in enumerate(block.rows)]
        widths = [max((row[c].width for row in measured), default=0.0) + slack for c in range(columns)]
        if sum(widths) <= width:
            break
        least = [
            max((_longest_word(canvas, row[c], size, weight(r)) for r, row in enumerate(block.rows)), default=0.0)
            + slack for c in range(columns)
        ]
        if sum(least) <= width or size <= style.small_size:
            widths = _shared(widths, least, width)
            if sum(least) > width and said:
                canvas.diagnostics.append(
                    f"{canvas.slide.id}: a table of {columns} columns is too wide for its place even at the "
                    "small size -- its words are broken; split it, or shorten its cells"
                )
            measured = [
                [canvas.measure(cell, size, widths[c] - slack, weight(r), balance=False) for c, cell in enumerate(row)]
                for r, row in enumerate(block.rows)
            ]
            break
        size = max(style.small_size, size * 0.9)
    line = max((m.line_height for row in measured for m in row if m.lines), default=size * 1.2)
    baseline = max((m.baseline for row in measured for m in row if m.lines), default=size)
    lines = [max((len(m.lines) for m in row), default=1) or 1 for row in measured]
    vertical = size * 0.35
    heights = [line * count + 2 * vertical for count in lines]
    return TableLayout(
        0.0, 0.0, widths, heights, block.rows, block.align, size, line, vertical + baseline,
        pad, block.header, (1.1, 0.6, 1.1), palette=canvas.palette,
    )


def _longest_word(canvas: _Canvas, cell: tuple[TextRun, ...], size: float, weight: int | None) -> float:
    """The widest thing in a cell that cannot be broken: a word, or a formula."""

    widest = 0.0
    for run in cell:
        pieces = [run] if run.math else [replace(run, text=word) for word in run.text.split()]
        for piece in pieces:
            widest = max(widest, canvas.measure((piece,), size, None, weight).width)
    return widest


def _shared(natural: list[float], least: list[float], width: float) -> list[float]:
    """Columns given ``width`` between: each its least, and what is left shared among
    those that want more, in proportion to what they want, none past its natural width."""

    if sum(least) >= width:
        return [width * share / sum(least) for share in least] if sum(least) else least
    widths, left = list(least), width - sum(least)
    for _ in range(len(widths)):
        wanting = [c for c in range(len(widths)) if natural[c] - widths[c] > 1e-6]
        want = sum(natural[c] - widths[c] for c in wanting)
        if not wanting or left <= 1e-6:
            break
        given = min(left, want)
        for c in wanting:
            widths[c] += given * (natural[c] - widths[c]) / want
        left -= given
    return widths


def _table(canvas: _Canvas, identifier: str, block: _Table, box: Box) -> float:
    if block.ragged:
        canvas.diagnostics.append(
            f"{canvas.slide.id}: a table's rows have different numbers of cells -- the short ones are "
            "filled with empty cells at their end"
        )
    plan = _table_plan(canvas, block, box.width, said=True)
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
                metrics = canvas.measure(
                    cell, plan.size, plan.widths[c] - 2 * plan.pad - plan.size * 0.2,
                    700 if plan.header and r == 0 else None, balance=False,
                )
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
    """A listing: each line one text in the monospace family, on a tinted panel; set
    smaller to fit its place, and a line still too long wrapped (said on the slide)."""

    if not any(text.strip() for text in block.lines):
        return 0.0  # an empty listing is no panel
    size, lines = _code_lines(canvas, block, box.width, said=draw)
    pad = size * 0.9
    line = size * 1.35
    height = line * len(lines) + 2 * pad
    if not draw:
        return height
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="code")
    widths = [
        canvas.measure((TextRun(text, code=True),), size, None).width for text, _ in lines if text.strip()
    ]
    width = min(box.width, max(widths, default=0.0) + 2 * pad)
    panel, role, ink, muted = _code_paints(canvas.palette)
    element(
        group, "rect", id=f"{identifier}.panel", x=box.x, y=box.y, width=width, height=height,
        rx=size * 0.35, fill=panel, **({"data__flexo__fill": role} if role else {}),
    )
    for index, (text, comment) in enumerate(lines):
        if not text.strip():
            continue
        canvas.words(
            f"{identifier}.{index}", (TextRun(text, code=True),),
            Box(box.x + pad, box.y + pad + line * index + (line - size * 1.2) / 2.0, width, 0.0),
            size=size, role="muted-ink" if comment else "ink", fill=muted if comment else ink,
            parent=group, wrap=False,
        )
    return height


def _code_lines(
    canvas: _Canvas, block: _Code, width: float, *, said: bool = False
) -> tuple[float, list[tuple[str, bool]]]:
    """The size a listing is set at in ``width`` -- smaller, down to near the small size,
    when its longest line would run past its panel -- and its lines, each marked whether
    it is a comment; a line still too long is wrapped, the rest of it indented under it."""

    style = canvas.deck.style
    size = _code_size(block, style)
    texts = [text for text in block.lines if text.strip()]

    def widest(at: float) -> float:
        return max((canvas.measure((TextRun(text, code=True),), at, None).width for text in texts), default=0.0)

    room = width - 2 * size * 0.9
    longest = widest(size)
    if longest > room > 0:
        # The face is monospace: the width of a line is in proportion to its size.
        size = max(min(size, style.small_size * 0.85), size * room / longest * 0.99)
        room = width - 2 * size * 0.9
    advance = canvas.measure((TextRun("M" * 20, code=True),), size, None).width / 20 or size * 0.6
    fits = max(12, int(room / advance))
    lines: list[tuple[str, bool]] = []
    wrapped = 0
    for text in block.lines:
        comment = text.lstrip().startswith(("#", "//", "--", "%"))
        if len(text) <= fits:
            lines.append((text, comment))
            continue
        wrapped += 1
        indent = " " * (len(text) - len(text.lstrip()) + 4)
        rest, first = text, True
        while len(rest) > (fits if first else fits - len(indent)):
            limit = fits if first else fits - len(indent)
            cut = rest.rfind(" ", int(limit * 0.6), limit)
            cut = limit if cut <= 0 else cut + 1
            lines.append((rest[:cut] if first else indent + rest[:cut], comment))
            rest, first = rest[cut:], False
        lines.append((rest if first else indent + rest, comment))
    if wrapped and said:
        canvas.diagnostics.append(
            f"{canvas.slide.id}: {wrapped} line{'s' if wrapped > 1 else ''} of code too long for the slide, "
            "wrapped -- shorten or break them"
        )
    return size, lines


def _code_paints(palette: Palette) -> tuple[str, str | None, str, str]:
    """A code panel's fill (and its role, when it is one) and the paints of its code and
    comments: the theme's first tint when its words read on it, else a quiet panel of
    the page (swiss's tint is its red), the words kept readable either way."""

    from flexo.colour import contrast, mix, with_contrast

    ink, muted = palette.get("ink"), palette.get("muted-ink")
    panel, role = palette.get("tone-1-fill"), "tone-1-fill"
    if contrast(ink, panel) < 7.0 or contrast(muted, panel) < 4.5:
        page = palette.get("canvas")
        panel, role = palette.get("inset-fill"), "inset-fill"
        if panel.lower() == page.lower():
            panel, role = mix(page, ink, 0.06), None
    return panel, role, with_contrast(ink, panel, 7.0), with_contrast(muted, panel, 4.5)


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
    # A figure has no direction of its own (۹۳٪): over a right-to-left label it stands
    # at the right, as the label does.
    value_align = "end" if rtl and align == "start" else align
    for index, (value, label) in enumerate(block.items):
        # Right-to-left labels read their figures from the right.
        slot = count - 1 - index if rtl else index
        x = box.x + slot * (cell + gap)
        canvas.words(
            f"{identifier}.{index}", value, Box(x, box.y, cell, 0.0), size=size, weight=weight, role=role,
            fill=fill, title=True, align=value_align, parent=group,
        )
        canvas.words(
            f"{identifier}.{index}.label", label, Box(x, box.y + tall + size * 0.06, cell, 0.0),
            size=label_size, role="muted-ink", align=align, parent=group,
        )
    return height


def _callout(
    canvas: _Canvas, identifier: str, block: _Callout, box: Box, *, draw: bool = True, least: float = 0.0
) -> float:
    """Words on a panel tinted in a tone, a bar of the tone along its edge; the panel is
    ``least`` high at least (the words at its top), to match the panels beside it."""

    style = canvas.deck.style
    size = block.size or style.body_size
    pad, bar = size * 0.8, 4.0
    rtl = _rtl(block.runs)
    inner = Box(box.x + pad if rtl else box.x + bar + pad, box.y + pad, box.width - bar - 2 * pad, 0.0)
    heading = canvas.measure(block.title, size, inner.width).height + size * 0.2 if block.title else 0.0
    # The words fill the panel line by line; balanced lines would leave it ragged.
    height = max(2 * pad + heading + canvas.measure(block.runs, size, inner.width, balance=False).height, least)
    if not draw:
        return height
    role = paint_role(block.colour)
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
    return paint_role(colour), None


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
    rows = -(-len(block.items) // columns)
    if box.height > 0 and rows * (picture + under + caption) + (rows - 1) * gap > box.height:
        # Taller than its place: the pictures smaller, each still fitted to its cell.
        fitted = (box.height - (rows - 1) * gap) / rows - under - caption
        if fitted < 24.0 and draw:
            canvas.diagnostics.append(
                f"{canvas.slide.id}: the gallery's {len(block.items)} pictures do not fit their place -- "
                "split the slide, or give it more columns"
            )
        picture = max(fitted, 24.0)
    row_height = picture + under + caption
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
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ValueError("cropping pictures needs Pillow: pip install pillow") from error
    with Image.open(source) as opened:
        # Upright as the camera meant it (a phone photograph is stored on its side).
        picture = ImageOps.exif_transpose(opened).convert("RGBA")
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

    from flexo.render_common import formula_paint, paint_attributes
    from flexo.texmath import draw as draw_formula
    from flexo.texmath import typeset

    style = canvas.deck.style
    size = block.size or style.body_size
    formula = typeset(block.source, canvas.deck.typography(size), size, display=True)
    if formula.width > box.width > 0:
        wanted = size
        size *= box.width / formula.width
        formula = typeset(block.source, canvas.deck.typography(size), size, display=True)
        if draw and size < min(style.small_size, wanted * 0.7):
            canvas.diagnostics.append(
                f"{canvas.slide.id}: an equation set at {size:.0f} pt to fit its place -- break it "
                "into lines (\\\\, in aligned) or give it more room"
            )
    canvas.say_maths(block.source, formula.problems)
    if draw:
        x = {"start": box.x, "middle": box.x + (box.width - formula.width) / 2.0,
             "end": box.x + box.width - formula.width}.get(block.align, box.x)
        role, fill = _paint_of(block.colour, "ink")

        draw_formula(
            canvas.layer, formula, x, box.y + formula.height, colour=formula_paint(canvas.palette),
            attributes={"id": identifier, "data__flexo__talk": "math", "data__flexo__size": number(size),
                        "data__flexo__align": block.align,
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
    shade = min(max(slide.shade, 0.0), 1.0)
    _, mean, darkest, _ = _picture(backdrop)
    if shade > 0:
        # A picture is darkened for words over it: light words, unless even its darkest
        # parts stay light under the shade.
        return darkest * (1.0 - shade) < 0.6
    return mean < 0.45


def _words_over_picture(canvas: _Canvas, slide: Slide) -> None:
    """Say when light words over a picture will not read where it is bright, and the
    shade that would make them."""

    if not _is_picture(slide.backdrop or "") or not _dark_slide(canvas.deck, slide):
        return
    from flexo.colour import contrast, to_hex

    shade = min(max(slide.shade, 0.0), 1.0)
    brightest = _picture(slide.backdrop)[3] * (1.0 - shade)
    ink = canvas.palette.get("ink")
    ratio = contrast(ink, to_hex((brightest, brightest, brightest)))
    if ratio < 3.0:
        needed = min(0.9, math.ceil((1.0 - 0.5 / max(_picture(slide.backdrop)[3], 0.5)) * 20) / 20)
        canvas.diagnostics.append(
            f"{slide.id}: words over the picture are hard to read where it is bright (contrast "
            f"{ratio:.1f}:1) -- a shade of {needed:g} would make them read"
        )


def _is_picture(page: object) -> bool:
    return isinstance(page, str) and bool(page) and not page.startswith("#")


_PAGE_PICTURES: dict[tuple[str, int, bool], tuple[str, float]] = {}


def _picture(source: str) -> tuple[str, float, float, float]:
    """A picture's data URI and its lightness (0 to 1) -- its mean, and that of its
    darkest and brightest tenths -- read once for each version of it."""

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
        lightness = darkest = brightest = 1.0
    else:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            image.draft("L", (64, 64))  # a JPEG is decoded small, not whole
            small = image.convert("L").resize((32, 32))
            lightness = ImageStat.Stat(small).mean[0] / 255
            values = sorted(small.tobytes())
            darkest, brightest = values[len(values) // 10] / 255, values[len(values) * 9 // 10] / 255
        href = picture_href(art)
    if len(_PAGE_PICTURES) > 64:
        _PAGE_PICTURES.clear()
    _PAGE_PICTURES[key] = (href, lightness, darkest, brightest)
    return href, lightness, darkest, brightest


def _picture_href(source: str) -> str:
    return _picture(source)[0]


def _lightness(source: str) -> float:
    return _picture(source)[1]


def _slide_palette(deck: Deck, slide: Slide):
    """The deck's paints, or paints for words over this slide's own backdrop: light
    words on a dark one, dark words on a light one when the deck's page is dark."""

    from flexo.colour import is_dark, with_contrast, with_lightness

    palette = deck.palette
    page_dark = is_dark(palette.get("canvas"))
    dark = _dark_slide(deck, slide)
    colour = slide.backdrop if (slide.backdrop or "").startswith("#") else None
    if not slide.backdrop and slide.dark is None:
        return palette
    if not dark and not page_dark:
        # A light backdrop in a light deck (a mid grey): the deck's words, kept readable on it.
        if colour is None:
            return palette
        return palette.with_overrides({
            "ink": with_contrast(palette.get("ink"), colour, 7.0),
            "muted-ink": with_contrast(palette.get("muted-ink"), colour, 4.5),
        })
    light, deep = {"ink": "#f7f5f0", "muted-ink": "#d4d0c8"}, {"ink": "#1c1c1e", "muted-ink": "#55555a"}
    paints = light if dark else deep
    backdrop = slide.backdrop or ""
    if backdrop.startswith("#"):
        paints["canvas"] = backdrop
    for role, colour in palette.paints.items():
        if role in {"canvas", "ink", "muted-ink", "shadow"}:
            continue
        if role.endswith("-ink"):
            paints[role] = paints["ink"]
        elif role.endswith("-fill"):
            # Tints (a code panel, a callout, a figure's boxes) for the page are glaring,
            # or swallow light words, on a backdrop of the other kind: a quiet tint of it.
            if is_dark(colour) != dark:
                paints[role] = with_lightness(colour, 0.34 if dark else 0.94, 0.06)
        elif is_dark(colour) == dark:
            # Accents, strokes and connectors drawn for the page read poorly over it.
            paints[role] = with_lightness(colour, 0.78 if dark else 0.45, 0.14)
    if backdrop.startswith("#"):
        paints["ink"] = with_contrast(paints["ink"], backdrop, 7.0)
        paints["muted-ink"] = with_contrast(paints["muted-ink"], backdrop, 4.5)
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
        widest = max(canvas.measure((TextRun(f"{n}."),), size, None).width for n in range(1, max(count, 1) + 1))
        layout.number_room = widest + size * 0.45
    return layout


def _bullets(canvas: _Canvas, identifier: str, block: _Bullets, box: Box) -> float:
    style = canvas.deck.style
    size = block.size or style.body_size
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="bullets")
    layout = _list_layout(canvas, block, box)
    top = box.y
    number = 0
    # A revealed list's steps follow those of the lists revealed before it on the slide,
    # as the PowerPoint's clicks do: the left list, then the right.
    step = canvas.steps - 1 if block.reveal else 0
    # A list reads one way, as most of its items do: an item that starts otherwise (an
    # English name leading a Persian line) takes the list's direction, by an invisible mark.
    leaning = sum(1 if _rtl(runs) else -1 for _, runs in block.items if any(run.text.strip() for run in runs))
    mark = "\u200f" if leaning > 0 else "\u200e"
    for index, (level, runs) in enumerate(block.items):
        if leaning and _rtl(runs) != (leaning > 0) and any(run.text.strip() for run in runs):
            runs = (TextRun(mark), *runs)
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
        layout.opened.append((metrics.rise, metrics.fall, len(metrics.lines)))
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


EDITING = contextvars.ContextVar("flexo_talk_editing", default=False)
"""Whether slides are drawn for an editor while they are changed: a figure on one then
keeps the layout it last had (``flexo.fit_in_box``'s ``keep``), drawn in one compile
rather than every way it could be, and the slide says it is not settled."""

_LAYOUTS: dict[tuple[str, str], str] = {}
"""The layout each figure (by slide and figure) was last drawn in."""


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
    where = (canvas.slide.id, spec.id)
    if laid is None:
        # Drawn for an editor while it is changed, a figure keeps the layout it had, in
        # one compile; the best of every layout is found once the changes stop.
        keep = _LAYOUTS.get(where) if EDITING.get() else None
        fit = flexo.fit_in_box(
            spec, box.width, box.height, words=min(deck.style.figure_size, largest), largest=largest,
            turn=block.turn, keep=keep,
        )
        codes = [
            diagnostic.code
            for diagnostic in lint_compilation(fit.compilation, style=fit.style).diagnostics
            # The figure is laid out for its place and scaled to it: a grown width is moot.
            if diagnostic.code != "layout.width.grown"
        ]
        laid = {"svg": fit.compilation.document.text, "ink": list(fit.ink), "layout": fit.layout, "codes": codes}
        if keep is not None and fit.layout == keep:
            canvas.settled = False
        else:
            _store_fit(key, laid)
    _LAYOUTS[where] = laid["layout"]
    for code in laid["codes"]:
        canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}: {code}")
    for text in block.said:
        canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}: {text}")
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


def _check_legible(canvas: _Canvas, prepared: dict[int, _Prepared], scales: dict[int, float]) -> None:
    for index, item in prepared.items():
        drawn = item.size * scales[index]
        if drawn < LEGIBLE:
            canvas.diagnostics.append(
                f"{canvas.slide.id} {item.id}: its words are {drawn:.1f}pt, too small to read -- "
                "give the figure a slide of its own, a wider layout, or fewer parts"
            )


def _place_figure(canvas: _Canvas, identifier: str, item: _Prepared, box: Box, scale: float) -> float:
    """Put a prepared figure in ``box`` at ``scale``: centred across, and down if it has room."""

    x = box.x + (box.width - item.width * scale) / 2.0 - item.left * scale
    y = box.y + (box.height - item.height * scale) / 2.0 - item.top * scale
    inks = _slide_inks(item.svg, canvas.deck.palette, canvas.palette, black=False)
    _place_svg(canvas, identifier, inks, x, y, scale, item.width * scale)
    return box.height


def _drawable(markup: str) -> bool:
    """Whether an SVG file is placed as shapes (editable in the PowerPoint): only when it
    holds nothing the drawing reader draws other than its viewers would. Anything more is
    placed as a picture, drawn exactly by every output."""

    from flexo.drawing import _drawable as drawable

    root = ET.fromstring(markup)
    if not drawable(root):
        return False
    fitting = (root.get("preserveAspectRatio") or "xMidYMid meet").split()
    if fitting[0] not in {"xMidYMid"} or (len(fitting) > 1 and fitting[1] != "meet"):
        return False
    for item in root.iter():
        tag = local_name(item.tag)
        if tag in _PICTURE_ONLY or (item is not root and tag == "svg"):
            return False
        if tag == "style" and re.search(r"(?:^|})\s*[^*\s{][^{]*\{", item.text or ""):
            return False  # CSS beyond *{...} (which is applied): classes, selectors
        if tag == "clipPath" and any(local_name(shape.tag) not in {"rect"} for shape in item):
            return False
        if item.get("class") or item.get("letter-spacing") or item.get("word-spacing"):
            return False
        if tag == "tspan" and item.get("dy"):
            return False
        if tag in {"text", "tspan"} and item.get("clip-path"):
            return False
        if any(item.get(name) for name in ("marker-start", "marker-mid", "marker-end")):
            return False
        if "currentcolor" in " ".join(item.attrib.values()).lower():
            return False
        if tag == "g" and item.get("opacity") not in {None, "1", "1.0"} and len(item) > 1:
            return False  # a group's opacity is the group's, not each shape's
        transform = item.get("transform") or ""
        if re.search(r"scale\(\s*-|matrix\(\s*-", transform):
            return False  # mirrored
    return True


_PICTURE_ONLY = frozenset({"symbol", "marker", "switch", "textPath"})
"""Elements an SVG file is placed as a picture for: the shape reader does not draw them as
the file's viewers do."""


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
    from flexo.text import maths_family

    typography = canvas.deck.layout_style.typography
    family, maths = typography.family, maths_family(typography)
    said: list[tuple[str, str]] = []
    options = {"inks": plot_inks(canvas.deck.palette, canvas.palette), "faces": plot_faces(typography)}
    if isinstance(figure, RemotePlot):
        svg = figure.svg(width, height, family, identifier, maths=maths, **options)
        said = figure.said
    else:
        svg = plot_svg(figure, width, height, family, identifier, maths=maths, said=said, **options)
    for words, problem in said:
        # Maths it could not read is said with its formula; anything else, as it is.
        if words:
            canvas.say_maths(words, [problem])
        else:
            canvas.diagnostics.append(f"{canvas.slide.id}: {problem}")
    block.drawn = svg
    _place_svg(canvas, identifier, _slide_inks(svg, canvas.deck.palette, canvas.palette), box.x, box.y, 1.0)
    return height


def _slide_inks(svg: str, deck: Palette, slide: Palette, *, black: bool = True) -> str:
    """A plot or figure drawn in the deck's paints, put on a slide of its own (a dark
    slide in a light deck, a light one in a dark deck): each paint the slide changes
    (words, axes, tints, connectors) as the slide has it. On a dark slide, black
    (matplotlib's error bars) is the slide's ink, unless ``black`` is False. Words a
    plot set on its cells keep the paint chosen for the cell (``_words_on_cells``)."""

    swaps = _ink_swaps(deck, slide, black=black)
    if not swaps:
        return svg
    if "#000000" in swaps:
        # matplotlib writes no fill on black words (black is what SVG draws without
        # one): they are black all the same, and take the slide's ink as black does.
        svg = re.sub(r"<text\b(?![^>]*\bfill)", f'<text fill="{swaps["#000000"]}"', svg)
    kept = rf'(<g id="{_ON_CELL}-\d+">.*?</g>)|'
    pattern = re.compile(kept + "|".join(re.escape(colour) for colour in swaps), re.IGNORECASE | re.DOTALL)
    return pattern.sub(lambda match: match.group(1) or swaps[match.group(0).lower()], svg)


def _ink_swaps(deck: Palette, slide: Palette, *, black: bool = True) -> dict[str, str]:
    """Each paint of the deck the slide shows otherwise, and how it shows it."""

    from flexo.colour import is_dark

    swaps: dict[str, str] = {}
    for role in ("ink", "muted-ink", *deck.paints):
        made, shown = deck.get(role).lower(), slide.get(role).lower()
        if made != shown:
            swaps.setdefault(made, shown)
    if black and is_dark(slide.get("canvas")):
        swaps.setdefault("#000000", slide.get("ink").lower())
    return swaps


class PlotInks(NamedTuple):
    """What a plot is told of the slide it is put on, as plain values (a worker draws it)."""

    ink: str
    """The deck's ink: the colour of a plot's words left as they were made."""
    dark: str
    light: str
    """The slide's dark and light inks: words on a plot's cells take the one that reads."""
    canvas: str
    """The slide's page, seen through a cell that is not opaque."""
    swaps: dict[str, str]
    """Each paint of the deck the slide shows otherwise (``_ink_swaps``), for what a plot
    draws as a picture: its shapes are given the slide's paints as an SVG."""


def plot_inks(deck: Palette, slide: Palette) -> PlotInks:
    """What a plot made in the ``deck``'s paints is told of the ``slide`` it is put on:
    its dark ink is its ink or its page, whichever is dark (else a near black), and its
    light ink likewise."""

    from flexo.colour import is_dark

    ink, page = slide.get("ink"), slide.get("canvas")
    dark = next(colour for colour in (ink, page, "#1c1c1e") if is_dark(colour))
    light = next(colour for colour in (ink, page, "#f7f5f0") if not is_dark(colour))
    return PlotInks(deck.get("ink"), dark, light, page, _ink_swaps(deck, slide))


_ON_CELL = "flexo-cell"
"""The id of a plot's words set on a cell: the slide leaves the paint chosen for it."""


def _words_on_cells(figure: Any, inks: PlotInks) -> None:
    """A plot's words on its cells (an annotated heatmap's numbers) read on them: words left
    in the deck's ink take whichever of the slide's dark and light inks reads on the cell
    beneath, as seaborn's annotations do; words their author coloured keep their colour."""

    from flexo.colour import contrast
    from matplotlib.colors import to_hex, to_rgb

    count = 0
    for axes in figure.get_axes():
        grounds = sorted((artist for artist in (*axes.images, *axes.collections) if _has_cells(artist)),
                         key=lambda artist: artist.get_zorder())
        if not grounds:
            continue
        to_data = axes.transData.inverted()
        for text in axes.texts:
            if text.get_gid() is not None or not text.get_text().strip():
                continue
            try:
                x, y = to_data.transform(text.get_transform().transform(text.get_unitless_position()))
            except Exception:  # placed in terms that need the plot drawn first
                continue
            cells = (_cell(ground, x, y) for ground in reversed(grounds))
            cell = next((colour for colour in cells if colour is not None and colour[3] > 0.0), None)
            if cell is None:
                continue
            seen = to_hex([cell[3] * part + (1.0 - cell[3]) * page for part, page in
                           zip(cell[:3], to_rgb(inks.canvas), strict=True)])
            if to_hex(text.get_color()) == to_hex(inks.ink):
                text.set_color(max((inks.dark, inks.light), key=lambda ink: contrast(ink, seen)))
            text.set_gid(f"{_ON_CELL}-{count}")
            count += 1


def _has_cells(artist: Any) -> bool:
    """Whether an artist is a grid of cells: an image (``imshow``) or a rectangular mesh."""

    from matplotlib.image import AxesImage, NonUniformImage

    if isinstance(artist, AxesImage):
        return not isinstance(artist, NonUniformImage)
    return hasattr(artist, "get_coordinates")


def _cell(ground: Any, x: float, y: float) -> tuple[float, float, float, float] | None:
    """The colour of an image's or mesh's cell at ``(x, y)`` (in data), or None off it (or
    on a mesh not of rows and columns)."""

    import numpy as np

    if hasattr(ground, "get_extent"):
        array = ground.get_array()
        if array is None:
            return None
        left, right, bottom, top = ground.get_extent()
        first, last = (top, bottom) if ground.origin == "upper" else (bottom, top)
        rows, columns = array.shape[:2]
        row = math.floor((y - first) / (last - first) * rows)
        column = math.floor((x - left) / (right - left) * columns)
        if not (0 <= row < rows and 0 <= column < columns):
            return None
        colour = ground.to_rgba(array[row : row + 1, column : column + 1])[0, 0]
    else:
        corners = ground.get_coordinates()
        xs, ys = corners[0, :, 0], corners[:, 0, 1]
        if not (np.allclose(corners[..., 0], xs) and np.allclose(corners[..., 1], ys[:, None])):
            return None
        row, column = _between(ys, y), _between(xs, x)
        ground.update_scalarmappable()
        colours = ground.get_facecolor()
        if row is None or column is None or len(colours) not in (1, (len(ys) - 1) * (len(xs) - 1)):
            return None
        colour = colours[row * (len(xs) - 1) + column if len(colours) > 1 else 0]
    alpha = ground.get_alpha()
    alpha = alpha if isinstance(alpha, int | float) else 1.0
    return float(colour[0]), float(colour[1]), float(colour[2]), float(colour[3]) * alpha


def _between(edges: Any, value: float) -> int | None:
    """Which of the spans between ``edges`` (in order, up or down) holds ``value``."""

    import numpy as np

    rising = edges[0] <= edges[-1]
    index = int(np.searchsorted(edges if rising else edges[::-1], value, side="right")) - 1
    if not 0 <= index < len(edges) - 1:
        return None
    return index if rising else len(edges) - 2 - index


def plot_svg(
    figure: Any, width: float, height: float, family: str, identifier: str, *,
    maths: str = "Latin Modern Math", said: list[tuple[str, str]] | None = None,
    inks: PlotInks | None = None, faces: dict[str, str] | None = None,
) -> str:
    """A matplotlib figure as SVG, laid out again at ``width`` by ``height`` points, its
    words set in ``family`` and kept as text; the figure is closed after. Its maths is
    set as the deck's is: letters in ``family``, and Greek, signs and script capitals
    in the deck's maths font (``maths``) rather than matplotlib's STIX. ``inks`` tell
    it the slide it is put on, so words on its cells read there; words that ask for
    monospace or serif are set in the deck's ``faces`` for them (``plot_faces``)."""

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

    own = family_faces(family)
    primary = load_face(select_face(own, 400, False)) if own else None
    missing = {
        ch for text in texts for ch in text.get_text() if not ch.isspace() and ch.isalpha()
        and (primary is None or not primary.has(ch))
    }
    covering = family_covering(missing) if missing else None
    families = [family, covering] if covering else [family]
    from flexo_talk.plotmaths import problems, set_by_flexo

    kinds = faces or plot_faces(TypographyStyle(family=family))
    for text in texts:
        asked = _asked_face(text)
        text.set_fontfamily(list(dict.fromkeys([kinds[asked], *families])) if asked else families)
    # Maths in its words is set by flexo, as on a slide; what matplotlib still sets
    # (tick labels, made as it draws) is said in its terms.
    set_by_flexo(figure, family, maths)
    if said is not None:
        said.extend(problems(figure))
    for text in texts:
        words = text.get_text()
        if "$" in words and not hasattr(text, "_flexo_problems"):
            text.set_text(_matplotlib_maths(words))
    clear_backgrounds(figure)
    _seamless(figure)
    marks = _rasterised(figure, inks.swaps if inks is not None else {})
    if marks and said is not None:
        said.append(("", f"the plot's {marks:,} marks are drawn as a picture, not as shapes -- "
                         "plot them with rasterized=True to choose so yourself"))
    if inks is not None:
        _words_on_cells(figure, inks)
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
            figure.savefig(buffer, format="svg", metadata={"Date": None}, dpi=RASTER_DPI)
        except (ZeroDivisionError, ValueError) as error:
            unset = _plot_maths(figure, error)
            if unset:
                import matplotlib.pyplot as plt

                plt.close(figure)
                raise ValueError(unset) from None
            # Constrained layout cannot take over a figure built without it
            # (a colour bar made first): lay it out tightly instead.
            figure.set_layout_engine("tight")
            buffer = io.StringIO()
            figure.savefig(buffer, format="svg", metadata={"Date": None}, dpi=RASTER_DPI)
        fitted = _fit_words(figure, family, maths)
        if fitted:
            # Drawn again with its words fitted to it.
            buffer = io.StringIO()
            figure.savefig(buffer, format="svg", metadata={"Date": None}, dpi=RASTER_DPI)
            if said is not None:
                said.extend(("", line) for line in fitted)
    # Drawn: pyplot need not keep it open (each redraw makes the plot afresh).
    import matplotlib.pyplot as plt

    plt.close(figure)
    return _maths_fonts(buffer.getvalue(), maths)


def plot_faces(typography: TypographyStyle) -> dict[str, str]:
    """The families a plot's words that ask for a kind of face are set in: monospace in the
    deck's code face, serif in its own face when that is a serif, else in Latin Modern
    Roman (flexo's serif, the face of its maths)."""

    from flexo.text import FontStack

    mono = FontStack(typography).mono()
    return {
        "monospace": mono[0].family if mono else typography.family,
        "serif": typography.family if typography.generic == "serif" else "Latin Modern Roman",
    }


def _asked_face(text: Any) -> str | None:
    """The kind of face a plot's text asks for: ``monospace`` (by that name, or a monospace
    family's), ``serif``, or None -- the deck's face, for its words in any other."""

    from flexo.text import MONO_FAMILIES

    asked = next(iter(text.get_fontfamily()), "").casefold()
    if asked == "monospace" or asked in {name.casefold() for name in MONO_FAMILIES}:
        return "monospace"
    return "serif" if asked == "serif" else None


MANY_MARKS = 5_000
"""Marks (points, cells, segments) beyond which one artist of a plot is drawn as a picture:
so many shapes make a slide slow to draw and to open, and are too small to edit one by one."""

RASTER_DPI = 200.0
"""The resolution of a plot's pictures (its images, and its artists of very many marks):
sharp on a slide shown full screen."""


def _seamless(figure: Any) -> None:
    """Each cell of a mesh (``pcolormesh``, ``pcolor``, ``contourf``) edged in its own colour,
    half a point wide: two cells side by side, each smoothed at its edge, otherwise let a
    hairline of the slide through between them in the PNG. A mesh given edges of its own,
    or seen through, is left as it is."""

    from matplotlib.contour import ContourSet

    for axes in figure.get_axes():
        for artist in axes.collections:
            mesh = hasattr(artist, "get_coordinates") or (isinstance(artist, ContourSet) and artist.filled)
            if mesh and len(artist.get_edgecolor()) == 0 and artist.get_alpha() in (None, 1.0):
                artist.set_edgecolor("face")
                artist.set_linewidth(0.5)


def _rasterised(figure: Any, swaps: dict[str, str]) -> int:
    """Artists of very many marks (a scatter of 100,000 points, a fine mesh) drawn as one
    picture each, as ``rasterized=True`` draws them, not as so many shapes; how many marks
    were turned so. A picture is given the slide's paints (``swaps``) as the shapes are."""

    turned = 0
    for axes in figure.get_axes():
        for artist in (*axes.collections, *axes.lines):
            if not artist.get_rasterized():
                marks = _marks(artist)
                if marks <= MANY_MARKS:
                    continue
                artist.set_rasterized(True)
                turned += marks
            _recolour(artist, swaps)
    return turned


def _marks(artist: Any) -> int:
    """How many marks an artist draws: a line's markers, a mesh's cells, a collection's
    points or shapes."""

    from matplotlib.lines import Line2D

    if isinstance(artist, Line2D):
        marked = artist.get_marker() not in {None, "", " ", "None", "none"}
        return len(artist.get_xdata()) if marked else 0
    if hasattr(artist, "get_coordinates"):
        rows, columns = artist.get_coordinates().shape[:2]
        return (rows - 1) * (columns - 1)
    return max(len(artist.get_offsets()), len(artist.get_paths()))


def _recolour(artist: Any, swaps: dict[str, str]) -> None:
    """An artist drawn as a picture in the slide's paints, as its shapes would be given
    them (``_slide_inks``); colours from a colour map are the data's, and stay."""

    if not swaps:
        return
    from matplotlib.lines import Line2D

    parts = ("color", "markerfacecolor", "markeredgecolor") if isinstance(artist, Line2D) else (
        ("edgecolor",) if artist.get_array() is not None else ("facecolor", "edgecolor"))
    for part in parts:
        colours = _swapped(getattr(artist, f"get_{part}")(), swaps)
        if colours is not None:
            getattr(artist, f"set_{part}")(colours if len(colours) > 1 else colours[0])


def _swapped(colours: Any, swaps: dict[str, str]) -> Any:
    """``colours`` with each the slide shows otherwise as it shows it; None if none is."""

    import numpy as np
    from matplotlib.colors import to_hex, to_rgb, to_rgba_array

    try:
        colours = to_rgba_array(colours)
    except ValueError:
        return None
    unique, where = np.unique(colours[:, :3], axis=0, return_inverse=True)
    changed = False
    for index, colour in enumerate(unique):
        shown = swaps.get(to_hex(colour))
        if shown is not None:
            colours[where.ravel() == index, :3] = to_rgb(shown)
            changed = True
    return colours if changed else None


LEAST_FITTED = 0.7
"""The smallest share of its own size a plot's words too long for it are set at."""

ATTEMPTS = 6
"""How many times a plot is laid out again as its words are fitted to it."""

FITTED_TO = 0.97
"""The share of their room words set smaller or cut take: a little air is left between
them and the plot's edge, as its layout leaves beside its labels."""


def _fit_words(figure: Any, family: str, maths: str) -> list[str]:
    """Words longer than their plot (an axis label longer than its axis, a title wider
    than the slide) would run over the slide: each is wrapped onto more lines, else set
    smaller (to ``LEAST_FITTED`` of its size), else cut short, until it fits; what was
    done to each, said. Tick labels are left to the plot's layout, which makes room."""

    import io

    import matplotlib.text
    from matplotlib.backends.backend_svg import RendererSVG

    from flexo_talk.plotmaths import set_by_flexo, tick_labels

    ticks = tick_labels(figure)
    # Measured as the SVG was drawn: at 72 dpi (matplotlib places some words, an axis
    # label, in the pixels of the last drawing), its words unhinted.
    figure.dpi = 72.0
    fitted: dict[int, list] = {}  # each text's words as written, its size, and what was done
    for attempt in range(ATTEMPTS):
        renderer = RendererSVG(figure.bbox.width, figure.bbox.height, io.StringIO())
        room = figure.bbox.padded(1.0)  # a point's grace
        over = []
        for text in figure.findobj(matplotlib.text.Text):
            # Words drawn (matplotlib clears ``stale`` as it draws them), not a tick's.
            if text.stale or id(text) in ticks or not text.get_visible() or not text.get_text().strip():
                continue
            share = _room_share(text, text.get_window_extent(renderer), room)
            if share < 1.0:
                over.append((text, share))
        if not over or attempt == ATTEMPTS - 1:
            break
        fresh = [text for text, _ in over if id(text) not in fitted]
        if fresh:
            # Laid out without them first: the plot gets back the room they squeezed it out
            # of (constrained layout shrinks a plot to make room for its words), to wrap to.
            for text in fresh:
                text.set_in_layout(False)
            figure.draw_without_rendering()
            for text in fresh:
                text.set_in_layout(True)
            renderer = RendererSVG(figure.bbox.width, figure.bbox.height, io.StringIO())
        for text, share in over:
            words, size, done = fitted.setdefault(id(text), [text.get_text(), text.get_fontsize(), []])
            flexo_set = hasattr(text, "_flexo_problems")
            if not done and " " in words.strip() and not flexo_set:
                line = _line_room(text)
                if line:
                    text.set_text(_wrapped(text, line, renderer))
                else:
                    text.set_wrap(True)  # to the edge of the plot, as matplotlib wraps
                done.append("wrapped onto more lines")
            elif "set smaller" not in done and text.get_fontsize() > size * LEAST_FITTED:
                text.set_fontsize(max(text.get_fontsize() * share * FITTED_TO, size * LEAST_FITTED))
                done.append("set smaller")
            elif not flexo_set and share > 0.2:
                # Cut at the end (and wrapped again, if it was): the words shrink about where
                # they are placed, as when set smaller.
                shown = " ".join(text.get_text().removesuffix("\u2026").split())
                text.set_text(shown[: max(1, int(len(shown) * share * FITTED_TO) - 1)].rstrip() + "\u2026")
                if "wrapped onto more lines" in done and (line := _line_room(text)):
                    text.set_text(_wrapped(text, line, renderer))
                if "cut short" not in done:
                    done.append("cut short")
        if any(hasattr(text, "_flexo_problems") for text, _ in over):
            set_by_flexo(figure, family, maths)  # its maths set again, at its size now
        figure.draw_without_rendering()
    unfitted = {id(text) for text, _ in over}
    for text, _ in over:
        fitted.setdefault(id(text), [text.get_text(), text.get_fontsize(), []])
    said = []
    for key, (words, _, done) in fitted.items():
        shown = words if len(words) <= 60 else words[:59] + "\u2026"
        if key in unfitted:
            said.append(f"the plot's words \u201c{shown}\u201d run outside it -- shorten them")
        elif done:
            how = " and ".join([", ".join(done[:-1]), done[-1]] if len(done) > 1 else done)
            said.append(f"the plot's words \u201c{shown}\u201d are too long for it, {how} -- shorten them")
    return said


def _line_room(text: Any) -> float | None:
    """The length of the line a title or axis label stands along: its plot's width (its
    height, for a label up the side), or the figure's for the figure's own; None for words
    placed anywhere else."""

    axes, figure = text.axes, text.get_figure(root=False)
    if axes is not None:
        if text in (axes.title, getattr(axes, "_left_title", None), getattr(axes, "_right_title", None),
                    axes.xaxis.label):
            return axes.bbox.width
        if text is axes.yaxis.label:
            return axes.bbox.height
    if figure is not None:
        if text in (getattr(figure, "_suptitle", None), getattr(figure, "_supxlabel", None)):
            return figure.bbox.width
        if text is getattr(figure, "_supylabel", None):
            return figure.bbox.height
    return None


def _wrapped(text: Any, length: float, renderer: Any) -> str:
    """A text's words broken onto lines of at most ``length`` (in display units), each line
    as full as it goes -- but onto three or so at most: a column of a word a line is no
    title (one squeezed narrow is set smaller instead)."""

    def width(words: str) -> float:
        return renderer.get_text_width_height_descent(words, text.get_fontproperties(), ismath=False)[0]

    length = max(length, width(text.get_text()) / 3.0)
    lines: list[str] = []
    for word in text.get_text().split():
        trial = f"{lines[-1]} {word}" if lines else word
        if lines and width(trial) <= length:
            lines[-1] = trial
        else:
            lines.append(word)
    return "\n".join(lines)


def _room_share(text: Any, box: Any, room: Any) -> float:
    """The share of its size a text's words may take and stay in ``room``: 1 or more when
    they fit in it. Set smaller (or cut), words shrink towards where they are placed."""

    try:
        x, y = text.get_transform().transform(text.get_unitless_position())
    except Exception:  # placed in terms that need the plot drawn first
        x, y = (box.x0 + box.x1) / 2.0, (box.y0 + box.y1) / 2.0
    share = math.inf
    for low, high, start, end, at in ((box.x0, box.x1, room.x0, room.x1, x), (box.y0, box.y1, room.y0, room.y1, y)):
        if high > at:
            share = min(share, (end - at) / (high - at))
        if low < at:
            share = min(share, (at - start) / (at - low))
    return max(share, 0.0)


def clear_backgrounds(figure: Any) -> None:
    """The figure's background, and each plot's white one, cleared so the plot sits on
    the slide; a background chosen for a plot (set_facecolor, a style's grey panel) is
    kept, as is an inset's, which hides what is under it."""

    from matplotlib.colors import to_rgba

    figure.patch.set_alpha(0.0)
    insets = {id(child) for axes in figure.get_axes() for child in getattr(axes, "child_axes", [])}
    for axes in figure.get_axes():
        red, green, blue, alpha = to_rgba(axes.get_facecolor())
        if id(axes) not in insets and (alpha == 0.0 or min(red, green, blue) > 0.995):
            axes.patch.set_alpha(0.0)


_MATPLOTLIB_NAMES = {
    "le": "leq", "ge": "geq", "gets": "leftarrow", "implies": "Longrightarrow",
    "impliedby": "Longleftarrow", "iff": "Longleftrightarrow", "land": "wedge", "lor": "vee",
    "lnot": "neg", "lVert": "Vert", "rVert": "Vert", "lvert": "vert", "rvert": "vert",
    "tfrac": "frac", "bm": "boldsymbol", "coloneqq": ":=",
}
"""LaTeX's names matplotlib's maths knows by others."""


def _matplotlib_maths(words: str) -> str:
    """Maths in a plot's words, said in terms matplotlib's maths reads: its names for
    ``\\le`` and the like, no ``\\big`` sizes, and script, blackboard and fraktur
    capitals as the letters themselves (so they are drawn in the deck's maths font)."""

    from flexo.texmath import alphabet

    def renamed(match: re.Match[str]) -> str:
        name = _MATPLOTLIB_NAMES.get(match.group(1))
        if name is None:
            return match.group(0)
        return "\\" + name if name.isalpha() else name

    def lettered(match: re.Match[str]) -> str:
        font = {"mathscr": "cal"}.get(match.group(1), match.group(1).removeprefix("math"))
        return alphabet(match.group(2), font)

    def maths(match: re.Match[str]) -> str:
        source = re.sub(r"\\(?:big|Big|bigg|Bigg)[lrm]?(?![A-Za-z])", "", match.group(0))
        source = re.sub(r"\\(mathcal|mathscr|mathbb|mathfrak)\s*\{([A-Za-z])\}", lettered, source)
        return re.sub(r"\\([A-Za-z]+)(?![A-Za-z])", renamed, source)

    return re.sub(r"(?<!\\)\$[^$]+\$", maths, words)


_FALLBACK_FAMILY = re.compile(r"font-family: '(STIX[^']*|DejaVu Sans|DejaVu Serif|cm[a-z]+10|Apple Chancery)'")


def _maths_fonts(svg: str, maths: str) -> str:
    """matplotlib draws the maths its words' family lacks in STIX (and script capitals in
    whatever cursive face it finds): each such glyph is set in the deck's maths font
    instead, lower-case Greek as TeX's italic, so a plot's maths matches its slide's."""

    from flexo.fonts import family_faces, load_face, select_face
    from flexo.markup import _MATH_ITALIC

    faces = [load_face(select_face(family_faces(name), 400, False))
             for name in dict.fromkeys((maths, "Latin Modern Math")) if family_faces(name)]

    def glyph(match: re.Match[str]) -> str:
        attributes, char = match.group(1), match.group(2)
        found = _FALLBACK_FAMILY.search(attributes)
        if not found:
            return match.group(0)
        italic = _MATH_ITALIC.get(char, char)
        face = next((face for face in faces if face.has(italic)), None)
        if face is None:
            return match.group(0)
        attributes = attributes.replace(found.group(0), f"font-family: '{face.face.family}'")
        attributes = re.sub(r"font-style: italic;\s*|font-weight: 0;\s*", "", attributes)
        return f"<tspan{attributes}>{italic}</tspan>"

    return re.sub(r"<tspan([^>]*)>([^<])</tspan>", glyph, svg)


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


def _place_svg(
    canvas: _Canvas, identifier: str, svg: str, x: float, y: float, scale: float, width: float | None = None
) -> None:
    """Put an SVG on the slide at ``(x, y)``, scaled; its ids take a prefix.

    A ``*`` rule in its stylesheet (matplotlib writes one) becomes attributes on
    the group, so it applies to this drawing only, not to the whole slide. ``width``
    is the width it is drawn at, as its ``width`` option means it: an editor sizing it
    starts from that.
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
        data__flexo__talk="figure", data__flexo__width=None if width is None else number(width),
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
        elif tag in {"title", "desc", "metadata", "style"} or child.get("id") == f"{prefix}layer.background":
            # A flexo figure's own canvas; a layer someone named Background keeps its content.
            continue
        else:
            child.attrib.pop(inkscape_attr("groupmode"), None)
            group.append(child)


def _image(canvas: _Canvas, identifier: str, block: _Image, box: Box) -> float:
    art = load_artwork(identifier, block.source)
    natural_w = art.width or box.width
    natural_h = art.height or box.height
    # A width asked for is the most it takes: never wider than its place.
    scale = min(min(block.width or box.width, box.width) / natural_w, box.height / natural_h)
    width, height = natural_w * scale, natural_h * scale
    if art.format == "svg" and _drawable(art.markup):
        # Vectors the drawing reader draws exactly: placed as shapes and text.
        view = [float(v) for v in re.split(r"[ ,]+", ET.fromstring(art.markup).get("viewBox", "").strip()) if v]
        units = (natural_w / view[2]) if len(view) == 4 and view[2] else 1.0
        _place_svg(canvas, identifier, art.markup, box.x + (box.width - width) / 2.0, box.y, scale * units, width)
        return height
    if art.format == "svg":
        import base64

        href = "data:image/svg+xml;base64," + base64.b64encode(art.markup.encode()).decode()
    else:
        href = picture_href(art)
    element(
        canvas.layer, "image", id=identifier, x=box.x + (box.width - width) / 2.0, y=box.y,
        width=width, height=height, href=href, data__flexo__width=number(width),
    )
    return height
