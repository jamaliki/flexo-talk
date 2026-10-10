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
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import flexo
from flexo.artwork import load_artwork, picture_href, picture_link
from flexo.draft import GivenUp, give_up_if_newer
from flexo.ir.measured import TextMetrics
from flexo.ir.semantic import TextRun
from flexo.lint import lint_compilation
from flexo.render_common import displayed_alone, render_runs
from flexo.structures import structure_problem
from flexo.style import Palette, TypographyStyle
from flexo.svg import SVG_NS, element, inkscape_attr, layer, local_name, number, svg_tag, xml_document
from flexo.svg_resources import embed_fonts
from flexo.text import TextMeasurer
from flexo.themes import figure_palette, figure_style
from flexo.units import MILLIMETRES_PER_INCH, POINTS_PER_INCH

from flexo_talk.deck import (
    PLACED,
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
    _Missing,
    _Plot,
    _Quote,
    _Stats,
    _Table,
    _Words,
    accent_field,
    inline,
    link_colour,
    list_numbers,
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
        self.hinted: dict[str, str] = {}
        """The placeholders standing in for what is empty, by id (render_slide)."""
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
        self.built: list[tuple[int, str]] = []
        """``(step, id)`` of each block that builds in (see ``Region.builds``)."""
        self.alone = False
        """Whether the block being set has its region to itself."""
        self.centred = True
        """Whether a picture is centred across its region, or starts at its edge (beside a list)."""
        self.place: float | None = None
        """Where the block being set was asked to stand across its place (``Region.across``):
        the share of the room to spare on its left; None, where the slide puts it."""
        self.span = (0.0, 0.0)
        """Where across the slide the picture or table set last is drawn: ``(left, width)``."""
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
        family: str | None = None,
    ) -> TextMetrics:
        """Words set at ``size`` in ``width``. A list wraps greedily (``balance=False``),
        as the slide program that edits it will; a title or caption is balanced.
        ``title`` sets them in the deck's title font, ``family`` in another."""

        typography = self._typography(size, title, family)
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

    def _typography(self, size: float, title: bool, family: str | None) -> TypographyStyle:
        typography = self.deck.typography(size, title=title)
        return typography.with_family(family) if family else typography

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
            said = (f"{self.slide.id}: Text shortened from {total:,} to {MOST_CHARACTERS:,} characters, "
                    "the most a slide can show.")
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
        return (f"{self.slide.id}: No available font can display {' '.join(sorted(self.lost))}, so "
                f"{'it is' if len(self.lost) == 1 else 'they are'} left out of the slide. Emoji are not supported; "
                "use a picture instead.")

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
        family: str | None = None,
    ) -> float:
        """Set ``runs`` in ``box`` from its top; return the height they took.
        ``wrap=False`` keeps each line whole (code keeps its indentation);
        ``balance=False`` fills each line before the next (words on a panel);
        ``family`` sets them in a family of their own."""

        if not runs:
            return 0.0
        strong_colour = None
        if (weight or 400) >= 600:
            # Words strong in words already bold (a title, a statement) would look like the
            # rest: they are drawn in the accent instead (in the ink, words already in the
            # accent) -- the same in the PowerPoint and PDF, made from what is drawn here.
            def plain(run: TextRun) -> bool:
                return not (run.color or run.math or run.code or run.maths)

            own = str(fill or self.palette.get(role) or "").lower()
            strong = "ink" if own == str(self.palette.get("tone-1-stroke") or "").lower() else "accent"
            runs = tuple(replace(run, color=strong) if run.weight >= 600 and plain(run) else run for run in runs)
            strong_colour = self.palette.get("tone-1-stroke" if strong == "accent" else "ink")
        if align == "start" and _rtl(runs):
            # Right-to-left words start at the right.
            align = "end"
        metrics = self.measure(
            runs, size, box.width if wrap else None, weight, title=title, balance=balance, family=family,
        )
        x = {"start": box.x, "middle": box.x + box.width / 2.0, "end": box.x + box.width}[align]
        # A formula displayed on a line of its own ($$...$$) is centred in the room the words
        # are set in, as LaTeX centres one: in the PowerPoint, the box is that room too.
        room = box.width if wrap and any(displayed_alone(line.runs) for line in metrics.lines) else None
        # A tall formula opens only its own line, not every line of its words (a heading's
        # lines, which the slide program wraps as one paragraph, stay as they are).
        spaced = None if title else self.spaced(metrics, size, weight)
        if any(run.math for run in runs):
            typography = self._typography(size, title, family)
            colour = fill or self.palette.get(role)
            self.worded.append(WordsLayout(
                identifier, x, box.y + metrics.baseline, room or metrics.width, metrics.line_height,
                [line.runs for line in metrics.lines], size, align, typography.family, weight, colour,
                downs=spaced[1] if spaced else None,
                heights=[one.line_height for one in spaced[0]] if spaced else None,
            ))
        options = dict(
            typography=self._typography(size, title, family), palette=self.palette, fill_role=role, fill=fill,
            anchor=None if align == "start" else align, weight=weight, width=room,
        )
        if spaced:
            # Each line set on its own baseline, as one object still.
            drawn = element(parent if parent is not None else self.layer, "g", id=identifier)
            for number, (one, down) in enumerate(zip(spaced[0], spaced[1], strict=True), 1):
                render_runs(drawn, f"{identifier}.{number}", one, x=x, y=box.y + metrics.baseline + down, **options)
        else:
            drawn = render_runs(
                parent if parent is not None else self.layer, identifier, metrics, x=x,
                y=box.y + metrics.baseline, **options,
            )
        # How wide the words may run before they wrap, and whether their lines are evened
        # out: the studio's editor wraps them there too.
        if wrap and drawn is not None:
            drawn.set("data-flexo-wrap", f"{box.width:g}{' balance' if balance else ''}")
        # And the colour their own strong words are drawn in, for its bold to show so there too.
        if strong_colour and drawn is not None and PLACEHOLDERS.get():
            drawn.set("data-flexo-strong", strong_colour)
        return spaced[2] if spaced else metrics.height

    def spaced(
        self, metrics: TextMetrics, size: float, weight: int | None = None
    ) -> tuple[list[TextMetrics], list[float], float] | None:
        """Lines a tall formula opened (``metrics`` opens every line by its rise and fall)
        each spaced as its own: each line's measure, its baseline below the first's, and
        their height -- a formula displayed alone set apart by ``DISPLAY_GAP`` too. None
        where the lines are evenly spaced as they are."""

        if len(metrics.lines) < 2 or metrics.rise + metrics.fall <= 0.01:
            return None
        own = []
        for line in metrics.lines:
            # A line left empty on purpose (a blank line typed) is as tall as a line of words.
            shown = line.runs if any(run.text.strip() or run.math for run in line.runs) else (TextRun(" "),)
            alone = self.measure(shown, size, None, weight, balance=False)
            own.append(TextMetrics(
                line.width, alone.line_height, alone.ascent, alone.descent, alone.baseline, alone.line_height,
                (line,), alone.cap_height, alone.rise, alone.fall,
            ))
        downs: list[float] = []
        top = 0.0
        for index, (line, one) in enumerate(zip(metrics.lines, own, strict=True)):
            shown = displayed_alone(line.runs)
            top += DISPLAY_GAP * size if shown and index else 0.0
            downs.append(top + one.baseline - own[0].baseline)
            top += one.line_height + (DISPLAY_GAP * size if shown and index < len(own) - 1 else 0.0)
        return own, downs, top


def render_slide(deck: Deck, slide: Slide) -> RenderedSlide:
    # A title (subtitle, statement) or a text or list left empty holds its place, as
    # Keynote's placeholders do: laid out as its placeholder's words, drawn faint for an
    # editor, and not at all when presented or exported -- what is around it stays where
    # it was either way.
    empty: dict[str, str] = {}
    kept: list[tuple[object, str, object]] = []

    def stand_in(owner: object, attribute: str, value: object, identifier: str, words: str) -> None:
        kept.append((owner, attribute, getattr(owner, attribute)))
        setattr(owner, attribute, value)
        empty[identifier] = words

    # A footnote added and not yet written: "Footnote", faintly, in its place.
    if any(not _worded(runs) for runs in slide.footnotes):
        kept.append((slide, "footnotes", slide.footnotes))
        slide.footnotes = [runs if _worded(runs) else (TextRun("Footnote"),) for runs in slide.footnotes]
        for index, runs in enumerate(kept[-1][2]):
            if not _worded(runs):
                empty[f"{slide.id}.footnote{index}"] = "Footnote"
    for field, attribute in _PLACEHOLDER_RUNS.items():
        if field in slide.placeholders and not getattr(slide, attribute):
            words = PLACEHOLDER_WORDS[field]
            name = "title" if field == "words" else field
            stand_in(slide, attribute, (TextRun(words),), f"{slide.id}.{name}", words)
    for name, region in slide.regions.items():
        for index, block in enumerate(region.blocks):
            # A sample (a new table, figure or equation) stands in for what will be made of
            # it, as itself: faint for an editor, and left out until it is changed.
            if index in region.placeholders:
                empty[f"{slide.id}.{name}.{index}"] = "Placeholder"
            elif isinstance(block, _Words) and not _worded(block.runs):
                stand_in(block, "runs", (TextRun("Text"),), f"{slide.id}.{name}.{index}", "Text")
            elif isinstance(block, _Bullets) and not any(_worded(runs) for _, runs in block.items):
                stand_in(block, "items", [(0, (TextRun("Text"),))], f"{slide.id}.{name}.{index}", "Text")
            # A quote, callout, code or numbers with nothing in them yet: placeholders too.
            elif isinstance(block, _Quote) and not _worded(block.runs) and not _worded(block.by):
                stand_in(block, "runs", (TextRun("Quote"),), f"{slide.id}.{name}.{index}", "Quote")
            elif isinstance(block, _Callout) and not _worded(block.runs) and not _worded(block.title):
                stand_in(block, "runs", (TextRun("Text"),), f"{slide.id}.{name}.{index}", "Text")
                # Its heading too, put there to be written (a new callout's), where it will be.
                if block.held:
                    stand_in(block, "title", HEADING_HINT, f"{slide.id}.{name}.{index}.title", "Heading")
            # A heading put there empty, the words written: its placeholder, only while editing.
            elif isinstance(block, _Callout) and block.held and not _worded(block.title) and PLACEHOLDERS.get():
                stand_in(block, "title", HEADING_HINT, f"{slide.id}.{name}.{index}.title", "Heading")
            elif isinstance(block, _Code) and not any(line.strip() for line in block.lines):
                stand_in(block, "lines", ["Code"], f"{slide.id}.{name}.{index}", "Code")
            # A table with nothing in it yet: its header names its columns, faintly.
            elif isinstance(block, _Table) and block.rows and not any(
                _worded(cell) for row in block.rows for cell in row
            ):
                header = [_column_hint(column) for column in range(len(block.rows[0]))]
                stand_in(block, "rows", [header, *block.rows[1:]], f"{slide.id}.{name}.{index}", "Table")
            elif isinstance(block, _Math) and not block.source.strip():
                stand_in(block, "source", "E = mc^2", f"{slide.id}.{name}.{index}", "Equation")
            elif isinstance(block, _Stats) and not any(_worded(value) or _worded(label) 
                                                       for value, label in block.items):
                stand_in(block, "items", [(STAT_HINT, LABEL_HINT)] * len(block.items),
                         f"{slide.id}.{name}.{index}", "Numbers")
            # A number added beside others and not yet written, or half written (its value
            # and not its label, or its label alone): the same hint for what is missing,
            # faintly, only while editing (_stats draws it).
            elif isinstance(block, _Stats) and PLACEHOLDERS.get() and any(
                not _worded(value) or not _worded(label) for value, label in block.items
            ):
                kept.append((block, "items", block.items))
                for at, (value, label) in enumerate(block.items):
                    if not _worded(value):
                        empty[f"{slide.id}.{name}.{index}.{at}"] = "Number"
                    if not _worded(label):
                        empty[f"{slide.id}.{name}.{index}.{at}.label"] = "Label"
                block.items = [(value if _worded(value) else STAT_HINT, label if _worded(label) else LABEL_HINT)
                               for value, label in block.items]
            # Who said a quote, or a caption, put there empty to be written (``by: ""``,
            # ``caption: ""``): its placeholder, only while editing, where its words will go --
            # what is under it moved down for it, as it will be.
            own = f"{slide.id}.{name}.{index}"
            held = [("by", BY_HINT, "Who said it")] if isinstance(block, _Quote) and block.held else []
            if getattr(block, "caption_held", False):
                held.append(("caption", CAPTION_HINT, "Caption"))
            for attribute, hint, words in held if PLACEHOLDERS.get() else ():
                if not _worded(getattr(block, attribute)):
                    stand_in(block, attribute, hint, f"{own}.{attribute}", words)
                    # (In an object faint as a whole already, as a new quote is: faint once.)
                    if own in empty:
                        del empty[f"{own}.{attribute}"]
    try:
        # A figure that fails as it is laid out for its place (what flexo did not foresee),
        # or any object that fails as it is drawn (a plot whose Python fails), is a box where
        # it would be, as one that can't be read is: the slide is drawn, and why is said
        # under it, naming the object where it is (``left.0``).
        failed: list[str] = []
        for _ in range(sum(len(region.blocks) for region in slide.regions.values()) + 1):
            try:
                rendered = _render_slide(deck, slide, empty)
            except _FigureFailed as failure:
                place = _swap_failed(slide, failure)
                if place is None:
                    raise failure.error from None
                failed.append(f"{slide.id} {place}: {failure.diagnostic}")
                continue
            rendered.diagnostics.extend(failed)
            return rendered
        raise RuntimeError("A slide's figures could not be drawn.")
    finally:
        for owner, attribute, value in kept:
            setattr(owner, attribute, value)


STANDING_ASIDE = contextvars.ContextVar("flexo_talk_standing_aside", default=False)
"""Whether an object that fails as it is drawn -- a plot whose Python fails -- stands aside,
as the studio has it (a box while editing, nothing presented or exported, and said), or
stops the build, as on the command line. (A figure flexo fails to lay out always stands
aside: it is no fault of the deck's.)"""

CANT_DRAW = "can\u2019t be drawn as it is"
FIGURE_FAILED = f"This figure {CANT_DRAW}"
"""How an object that failed as it was drawn for its slide is said ("This plot can't be
drawn as it is"): the export's note finds it by these words."""

_NOUNS = {
    _Bullets: "list", _Words: "text", _Figure: "figure", _Image: "picture", _Plot: "plot", _Table: "table",
    _Gallery: "gallery", _Code: "code", _Quote: "quote", _Callout: "callout", _Math: "equation",
}
"""What a person calls each object, in what is said of one that can't be drawn."""


class _FigureFailed(Exception):
    """An object -- a figure, most often -- that failed as it was laid out (``error``):
    what its box says, and what is said under the slide (``diagnostic``)."""

    def __init__(self, block: object, error: BaseException, said: str, diagnostic: str) -> None:
        super().__init__(said)
        self.block, self.error, self.said, self.diagnostic = block, error, said, diagnostic


def _object_failed(block: object, error: BaseException) -> _FigureFailed:
    """An object that failed as it was made or drawn (a plot whose Python fails, a picture
    that does not read): its box says so, and why is said under the slide."""

    from flexo.studio.plain import explain

    from flexo_talk.document import DeckDocumentError

    said = f"This {_NOUNS.get(type(block), 'object')} {CANT_DRAW}"
    why = error.message if isinstance(error, DeckDocumentError) else explain(error)
    return _FigureFailed(block, error, said, f"{said}: {why}")


def _swap_failed(slide: Slide, failure: _FigureFailed) -> str | None:
    """The failed object's place given to a box saying so -- for good: drawn again (as it is
    presented), it would only fail again, as slowly (a plot stopped after its time) -- and
    where it is (``left.0``), or None should it be in none."""

    for region in slide.regions.values():
        for index, block in enumerate(region.blocks):
            if block is failure.block:
                region.blocks = [*region.blocks[:index], _Missing("figure", "", said=failure.said),
                                 *region.blocks[index + 1:]]
                return f"{region.name}.{index}"
    return None


STAT_HINT = (TextRun("93%"),)
LABEL_HINT = (TextRun("Label"),)
"""What a number not yet written shows while editing, as the inspector's fields hint it."""
HEADING_HINT = (TextRun("Heading", weight=700),)
"""What a callout's heading put there empty shows while editing, bold as its heading is."""
BY_HINT = (TextRun("\u2014 Who said it"),)
CAPTION_HINT = (TextRun("Caption"),)
"""What who said a quote, and a caption, put there empty show while editing."""


def _worded(runs: tuple[TextRun, ...]) -> bool:
    return any(run.text.strip() for run in runs)


def _placeholders(root: ET.Element, empty: dict[str, str]) -> None:
    """The placeholders' words marked faint for an editor, or taken out."""

    parents = {child: parent for parent in root.iter() for child in parent}
    for node in list(root.iter()):
        words = empty.get(node.get("id", ""))
        if words is None:
            continue
        if PLACEHOLDERS.get():
            node.set("data-flexo-placeholder", words)
            node.set("opacity", "0.38")
        else:
            parents[node].remove(node)


PLACEHOLDERS = contextvars.ContextVar("flexo_talk_placeholders", default=False)
"""Whether an empty title's placeholder is drawn (faintly, for an editor) or left out."""

PLACEHOLDER_WORDS = {"title": "Title", "subtitle": "Subtitle", "words": "Text"}
"""The words a placeholder shows."""

_PLACEHOLDER_RUNS = {"title": "title_runs", "subtitle": "subtitle_runs", "words": "title_runs"}
"""Where each field's words are kept on a slide (a statement's words are its title's)."""


def _render_slide(deck: Deck, slide: Slide, empty: dict[str, str]) -> RenderedSlide:
    canvas = _Canvas(deck, slide)
    canvas.hinted = empty
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
    # Set first, for the body to end above them, footnotes are read after it: they follow it
    # in the drawing (which the PDF's reading order and the PowerPoint's follow).
    notes = [child for child in canvas.layer if child.get("id", "").startswith(f"{slide.id}.footnote")]
    for note in notes:
        canvas.layer.remove(note)
        canvas.layer.append(note)
    _furniture(canvas, slide)
    if f"{slide.id}.title" in empty and (not slide.subtitle_runs or f"{slide.id}.subtitle" in empty):
        # With no heading shown, the band or rule a heading is set on is not shown either.
        # While editing it stays, round the title's place, but marked as a placeholder is,
        # so Present (which shows the editor's drawing) leaves it out as an export does.
        marks = {f"{slide.id}.{mark}" for mark in ("band", "rule")}
        if PLACEHOLDERS.get():
            for node in canvas.root.iter():
                if node.get("id") in marks:
                    node.set("data-flexo-placeholder", "")
        else:
            empty |= dict.fromkeys(marks, "Title")
    if empty:
        _placeholders(canvas.root, empty)
        if not PLACEHOLDERS.get():
            # Nor are they written natively (PowerPoint's own lists and tables).
            canvas.lists = [layout for layout in canvas.lists if layout.id not in empty]
            canvas.tables = [layout for layout in canvas.tables if layout.id not in empty]
    stylesheet = element(canvas.defs, "style", id=f"{slide.id}.fonts", type="text/css")
    embed_fonts(stylesheet, canvas.root, deck.layout_style)
    if deck.title_font:
        headings = element(canvas.defs, "style", id=f"{slide.id}.title-fonts", type="text/css")
        embed_fonts(headings, canvas.root, replace(deck.layout_style, typography=deck.typography(12, title=True)))
    # One line for each thing said, however many places on the slide said it.
    return RenderedSlide(
        slide, xml_document(canvas.root), canvas.lists, list(dict.fromkeys(canvas.diagnostics)), canvas.tables,
        canvas.notes,
        canvas.steps, canvas.held, canvas.worded, canvas.settled, builds=canvas.built,
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
                # Named as the person wrote it, not as a reference ("spread from plots.py").
                file, _, function = str(reference.target).rpartition(":")
                named = f"*{function}* from {file}" if file and function else f"*{reference.target}*"
                region.blocks[index] = _Words(
                    inline(f"{named} will appear when you trust this folder"),
                    align="middle", muted=True,
                )
            except Exception as error:
                # Python that fails (a function there is none of) stands aside in its place, as
                # an object that fails as it is drawn does (render_slide) -- not run again as the
                # slide is drawn again -- or stops the build where nothing can stand aside.
                if not STANDING_ASIDE.get():
                    raise
                failure = _object_failed(block, error)
                canvas.diagnostics.append(f"{slide.id} {region.name}.{index}: {failure.diagnostic}")
                region.blocks[index] = _Missing("figure", "", said=failure.said)


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
    off the field, rather than drawn in its colour on it -- a link, being words to read, as
    far as words must be (4.5:1), its accent or its blue."""

    from flexo.colour import with_contrast

    field = accent_field(canvas.deck.palette)
    saved, link = canvas.palette, canvas.link
    canvas.palette = saved.with_overrides({
        role: with_contrast(colour, field, 3.0)
        for role, colour in saved.paints.items() if role.endswith(("-stroke", "-motif"))
    })
    canvas.link = link_colour(saved, field) or with_contrast(saved.get("tone-1-stroke"), field, 4.5)
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


def _skipped(slide: Slide) -> bool:
    """Whether a slide is skipped (Keynote's Skip Slide): kept and edited, but neither
    presented nor exported -- nor counted among the deck's sections."""

    return bool((getattr(slide, "source", None) or {}).get("skip"))


def _upto(slide: Slide) -> list[Slide]:
    """The deck's slides up to and with this one, where it is among the slides there are:
    an export has none of those skipped."""

    slides = slide.deck.slides
    return slides[: slides.index(slide) + 1 if slide in slides else slide.index]


def _section_number(slide: Slide) -> int:
    return sum(other.layout == "section" and not _skipped(other) for other in _upto(slide))


def _slide_number(slide: Slide) -> int | None:
    """The number a slide is shown with, as Keynote numbers them: its place among the slides
    presented, those skipped not counted -- so the show, the PDF and the PowerPoint agree.
    A slide skipped has none."""

    return None if _skipped(slide) else sum(not _skipped(other) for other in _upto(slide))


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
        canvas.diagnostics.append(f"{slide.id}: Text size reduced to {round(scale * 100)}% to fit the slide.")
    if scale == _SHRINK[-1]:
        canvas.diagnostics.append(f"{slide.id}: Text does not fit, even at half size. Try shortening it.")


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
    sections = [other for other in slide.deck.slides if other.layout == "section" and not _skipped(other)]
    hinted = not sections and PLACEHOLDERS.get()
    if hinted:
        # No sections yet while editing -- an agenda is often put in before them: the rows
        # they will make, faintly, and a note of what fills them, not a warning.
        canvas.notes.append(f"{slide.id}: The agenda lists the deck's section slides. Add a Section slide to fill it.")
        sections = [AGENDA_HINT] * 3
    elif not sections:
        canvas.diagnostics.append(f"{slide.id}: The agenda is empty because the deck has no section slides.")
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
            f"{slide.id}: The {len(sections)} sections do not fit in the agenda, even in two columns. "
            "Try fewer sections or shorter titles."
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
    if hinted:
        for node in canvas.root.iter():
            if node.get("id", "").startswith(f"{slide.id}.agenda"):
                node.set("data-flexo-placeholder", "Section")
                node.set("opacity", "0.38")


AGENDA_HINT = SimpleNamespace(title_runs=(TextRun("Section"),), subtitle_runs=())
"""What stands in an agenda's rows while the deck has no sections, faintly, as it is edited."""


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
        # Placed as presented: an empty object, never shown, is no part of the decision.
        hidden = _aside(canvas, region)
        shown = [block for index, block in enumerate(region.blocks) if index not in hidden]
        pictures = bool(shown) and (
            all(isinstance(block, _PICTURES) for block in shown) or _placing(shown) == "captioned"
        )
        # What this region set natively (its lists, tables, words with maths): moved with it,
        # and nothing a column after it sets.
        owned = (canvas.lists[lists:], canvas.tables[tables[0]:], canvas.worded[tables[1]:])
        placed.append((group, used, pictures, bool(shown), owned))
    align = slide.align or style.align
    filled = [item for item in placed if item[3]]
    if align == "top" or not filled:
        return
    band = max(used for _, used, *_ in filled)
    worded = [used for _, used, pictures, full, *_ in filled if not pictures]
    words = max(worded, default=0.0)
    lead = max(body.height - band, 0.0) / 2.0 if align == "middle" else 0.0
    for group, used, pictures, full, owned in placed:
        if not full:
            continue
        if not worded:
            # Pictures alone: a little above the middle of the body, where the eye takes the
            # middle to be, so a short one stays with its title -- columns of them sharing
            # one top (the tallest's), so pictures or tables side by side line up, as Keynote's.
            shift = max(body.height - band, 0.0) * (0.5 if align == "middle" else OPTICAL)
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
            _shift(group, shift, *owned)


OPTICAL = 0.4
"""The share of the free room left above a picture standing alone: its optical centre
is above the middle, as a page's text block is set above its middle."""

_PICTURES = (_Figure, _Image, _Plot, _Gallery, _Missing, _Quote, _Table, _Code, _Stats)
"""Blocks that stand on their own -- pictures, and the graphics made of words: a table,
a listing, a row of numbers -- set in the room they have when nothing else shares it."""

_CAPTIONED = (_Figure, _Image, _Plot, _Gallery, _Missing, _Table)
"""What words of its own (a text, a caption) are set with as one group, centred."""


def _placing(blocks: list) -> str:
    """How a region's things are placed across it: ``"listed"`` beside a list or under
    words, starting at their edge as the words do; ``"captioned"`` pictures or tables with
    texts of their own after them, a group centred, the texts centred under them; else
    ``"alone"``, each centred."""

    if any(isinstance(block, _Bullets) for block in blocks):
        return "listed"
    graphics = [block for block in blocks if isinstance(block, _CAPTIONED)]
    words = [block for block in blocks if isinstance(block, _Words)]
    if graphics and words and len(graphics) + len(words) == len(blocks):
        return "captioned" if isinstance(blocks[0], _CAPTIONED) else "listed"
    return "alone"


def _aside(canvas: _Canvas, region: Region) -> list[int]:
    """A region's placeholders that take no room: presented or exported, every one (it is
    not there at all); while edited, a sample (a new figure, table or equation), drawn after
    the rest -- empty words keep their place there, to be typed in where they are."""

    editing = PLACEHOLDERS.get()
    ids = [f"{canvas.slide.id}.{region.name}.{index}" for index in range(len(region.blocks))]
    aside = [index for index, identifier in enumerate(ids) if identifier in canvas.hinted and (
        not editing or canvas.hinted[identifier] == "Placeholder")]
    return [] if editing and len(aside) == len(ids) else aside


def _shift(
    group: ET.Element, down: float, lists: list[ListLayout], tables: list[TableLayout], worded: list[WordsLayout]
) -> None:
    """Move a drawn region down, with the native lists, tables and words set in it."""

    group.set("transform", f"translate(0 {number(down)})")
    for layout in lists:
        layout.y += down
        layout.items = [(level, runs, baseline + down) for level, runs, baseline in layout.items]
    for table in tables:
        table.y += down
    for words in worded:
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
    number = _slide_number(slide)
    if style.numbers and number is not None:
        x = style.margin if rtl else style.width - style.margin - 60.0
        canvas.words(
            f"{slide.id}.number", (TextRun(str(number)),),
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
    worded = [block for block in blocks if not isinstance(block, _Figure | _Image | _Plot | _Gallery | _Missing)]
    pictures = [block for block in blocks if isinstance(block, _Figure | _Image | _Plot | _Gallery | _Missing)]
    # Words take what they need (a picture's caption too); pictures share the height left.
    needed = sum(_height(canvas, block, box.width) for block in worded)
    needed += sum(_captioned(canvas, block, box.width) for block in pictures)
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
    # A placeholder takes no room from what is really there: presented or exported it is
    # not there at all, and a sample (a new figure, table or equation) is drawn for an
    # editor after the rest, so they are set as they will be presented. (Empty words keep
    # their place while edited: they are typed in where they are.)
    ids = [f"{canvas.slide.id}.{region.name}.{index}" for index in range(len(blocks))]
    aside = _aside(canvas, region)
    shown = [index for index in range(len(blocks)) if index not in aside]
    # One rule for where a region's things go: pictures and tables alone, or with words of
    # their own (a caption), are a group centred in the place (the words centred under
    # them); beside a list they start at its edge, as its words do.
    placing = _placing([blocks[index] for index in shown])
    canvas.alone, canvas.centred = placing != "listed", placing != "listed"
    planned, fits, share = _plan_figures(canvas, [blocks[index] for index in shown], box, words)
    prepared = {shown[at]: item for at, item in planned.items()}
    scales = {shown[at]: scale for at, scale in fits.items()}
    _check_legible(canvas, prepared, scales, box)
    top = box.y
    used = None
    marks: list[tuple[int, int, int, int, int]] = []
    for index in [*shown, *(aside if PLACEHOLDERS.get() else [])]:
        if used is None and index in aside:
            # The rest is set: the placeholders go after it, in what room is left, taking none.
            used = max(top - box.y - style.block_gap, 0.0)
            room = Box(box.x, 0.0, box.width, max(box.y + box.height - top, 80.0))
            planned, fits, share = _plan_figures(canvas, [blocks[at] for at in aside], room, words)
            prepared |= {aside[at]: item for at, item in planned.items()}
            scales |= {aside[at]: scale for at, scale in fits.items()}
        block, identifier = blocks[index], ids[index]
        canvas.place = region.across.get(index)
        # (What it draws, for it to be moved down its place after: see _stand.)
        marks.append((index, len(canvas.layer), len(canvas.lists), len(canvas.tables), len(canvas.worded)))
        try:
            top = _block(canvas, region, index, block, identifier, box, top, placing, prepared, scales, share, panel)
        except _FigureFailed:
            raise
        except Exception as error:
            # One object that fails as it is drawn is a box where it would be, not a slide
            # that is not drawn (render_slide) -- where it can stand aside.
            if not STANDING_ASIDE.get():
                raise
            raise _object_failed(region.blocks[index], error) from error
        built = index in region.builds and index not in aside and not getattr(block, "reveal", False)
        if built and (drawn := _drawn(canvas, identifier)) is not None:
            # It appears on a click of its own, after what is on the slide before it.
            canvas.steps += 1
            canvas.built.append((canvas.steps, identifier))
            drawn.set("data-flexo-step", str(canvas.steps))
        canvas.place = None
        top += style.block_gap
    used = used if used is not None else max(top - box.y - style.block_gap, 0.0)
    # The room it has to spare, for an editor to say where its objects would stand down it.
    canvas.layer.set("data-flexo-spare", number(max(box.height - used, 0.0)))
    if any(index in region.down for index in shown):
        _stand(canvas, region, marks, shown, max(box.height - used, 0.0))
        # It fills its place: the slide sets it where it is, moving it no further.
        return max(box.height, used)
    return used


def _block(
    canvas: _Canvas, region: Region, index: int, block: object, identifier: str, box: Box, top: float,
    placing: str, prepared: dict, scales: dict, share: float, panel: float,
) -> float:
    """One of a region's blocks drawn from ``top`` down: where the next starts."""

    style = canvas.deck.style
    # Asked to stand across its place, an object narrower than it is set in a box as wide
    # as it is, there (a figure, picture or table moves in its own place: _across).
    left, wide = box.x, box.width
    asked = canvas.place is not None and not isinstance(block, PLACED)
    natural = _natural(canvas, block, box.width, share) if asked else None
    if natural is not None and natural < box.width - 0.5:
        wide = natural + 0.01
        left = box.x + (box.width - wide) * canvas.place
    if isinstance(block, _Bullets):
        top += _bullets(canvas, identifier, block, Box(left, top, wide, 0.0))
    elif isinstance(block, _Words):
        size = block.size or style.body_size
        role, fill = _paint_of(block.colour, "muted-ink" if block.muted else "ink")
        # Words under a picture (its caption) are centred under it, unless set otherwise.
        given = index < len(region.sources) and "align" in region.sources[index]
        align = "middle" if placing == "captioned" and not given else block.align
        top += canvas.words(
            identifier, block.runs, Box(left, top, wide, 0.0), size=size,
            align=align, role=role, fill=fill,
        )
        if align != block.align and (drawn := _drawn(canvas, identifier)) is not None:
            # What is drawn, for an editor to say so.
            drawn.set("data-flexo-align", align)
    elif isinstance(block, _Gallery):
        top += _gallery(canvas, identifier, block, Box(left, top, wide, max(share, 40.0)))
    elif isinstance(block, _Figure):
        scale = scales[index]
        height = prepared[index].height * scale
        top += _place_figure(canvas, identifier, prepared[index], Box(box.x, top, box.width, height), scale)
    elif isinstance(block, _Image):
        top += _image(canvas, identifier, block, Box(box.x, top, box.width, max(share, 40.0)))
    elif isinstance(block, _Plot):
        top += _plot(canvas, identifier, block, Box(left, top, wide, max(share, 60.0)))
    elif isinstance(block, _Missing):
        top += _missing(canvas, identifier, block, Box(box.x, top, box.width, max(share, 40.0)))
    elif isinstance(block, _Table):
        top += _table(canvas, identifier, block, Box(box.x, top, box.width, 0.0))
    elif isinstance(block, _Code):
        top += _code(canvas, identifier, block, Box(left, top, wide, 0.0))
    elif isinstance(block, _Quote):
        top += _quote(canvas, identifier, block, Box(left, top, wide, 0.0))
    elif isinstance(block, _Stats):
        top += _stats(canvas, identifier, block, Box(left, top, wide, 0.0))
    elif isinstance(block, _Callout):
        least = panel if index == 0 else 0.0
        top += _callout(canvas, identifier, block, Box(left, top, wide, 0.0), least=least)
    elif isinstance(block, _Math):
        top += _equation(canvas, identifier, block, Box(left, top, wide, 0.0))
    if isinstance(block, _Figure | _Image | _Table | _Missing) and getattr(block, "caption", ()):
        top += _caption(canvas, identifier, block.caption, box, top)
    return top


def _stand(canvas: _Canvas, region: Region, marks: list, shown: list[int], spare: float) -> None:
    """The region's blocks asked to stand down their place (``Region.down``) moved down it,
    each with the share of the room it has to spare (``spare``) above it -- and what comes
    after it with it, never above it -- the native lists, tables and words they set with
    them."""

    ends = [*marks[1:], (None, len(canvas.layer), len(canvas.lists), len(canvas.tables), len(canvas.worded))]
    down = 0.0
    for (index, first, lists, tables, worded), (_, *after) in zip(marks, ends, strict=True):
        if index not in shown:
            continue
        down = max(down, region.down.get(index, 0.0) * spare)
        if down < 0.01:
            continue
        children = list(canvas.layer)[first:after[0]]
        if not children:
            continue
        # (How far down it moved, for an editor: where it would stand were it not.)
        group = ET.Element("g", {"data-flexo-down": number(down)})
        for child in children:
            canvas.layer.remove(child)
            group.append(child)
        canvas.layer.insert(first, group)
        owned = canvas.lists[lists:after[1]], canvas.tables[tables:after[2]], canvas.worded[worded:after[3]]
        _shift(group, down, *owned)


def _drawn(canvas: _Canvas, identifier: str) -> ET.Element | None:
    """What a block was drawn as (its group, or its words), if anything."""

    found = [item for item in canvas.layer if item.get("id") == identifier]
    return found[-1] if found else None


CAPTION_GAP = 0.5
"""The room between a picture or table and its caption, in the caption's ems."""


def _captioned(canvas: _Canvas, block, width: float) -> float:
    """The room a picture's or table's caption takes under it, set ``width`` wide."""

    runs = getattr(block, "caption", ())
    if not runs or not isinstance(block, _Figure | _Image | _Table | _Missing):
        return 0.0
    size = canvas.deck.style.small_size
    return size * CAPTION_GAP + canvas.measure(runs, size, width).height


def _caption(canvas: _Canvas, identifier: str, runs: tuple[TextRun, ...], box: Box, top: float) -> float:
    """A picture's or table's caption, under it, centred under it and a size smaller -- as
    the words under a gallery's pictures are -- and part of it: in its group, so it is
    chosen, moved, grouped in the PowerPoint and tagged in the PDF with it. Returns the
    height it took."""

    size = canvas.deck.style.small_size
    left, width = canvas.span
    middle = left + width / 2.0
    # As wide as it can be while centred under it, within the region.
    reach = max(min(middle - box.x, box.x + box.width - middle), width / 2.0, 1.0)
    holder = _drawn(canvas, identifier)
    if holder is None:
        return 0.0
    if local_name(holder.tag) != "g":
        # A picture by itself: it and its caption, one group of the picture's id.
        inner = ET.Element(holder.tag, dict(holder.attrib))
        inner[:] = list(holder)
        inner.set("id", f"{identifier}.picture")
        holder.clear()
        holder.tag = svg_tag("g")
        holder.set("id", identifier)
        holder.set("data-flexo-talk", "picture")
        if inner.get("data-flexo-width"):
            holder.set("data-flexo-width", str(inner.get("data-flexo-width")))
        holder.append(inner)
    found = re.fullmatch(r"translate\(([-\d.e]+),([-\d.e]+)\) scale\(([-\d.e]+)\)", holder.get("transform") or "")
    if found and float(found.group(3)):
        # Within a drawing placed scaled: undone, so the caption is set in the slide's units.
        x, y, scale = (float(value) for value in found.groups())
        holder = element(holder, "g", transform=f"scale({number(1.0 / scale)}) translate({number(-x)},{number(-y)})")
    return size * CAPTION_GAP + canvas.words(
        f"{identifier}.caption", runs, Box(middle - reach, top + size * CAPTION_GAP, 2.0 * reach, 0.0),
        size=size, align="middle", parent=holder,
    )


PICTURE_LEAST = 120.0
"""The height a figure, plot, or picture keeps when words crowd its place."""

PICTURE_SMALLEST = 70.0
"""The least it gives up to, before the words around it shrink below ``WORDS_KEPT``."""

WORDS_KEPT = 0.85
"""How far a slide's words shrink, at most, to make room for a picture added to it."""

QUIET_SHRINK = 0.9
"""Words set this much of their size or more to fit go unsaid: a few per cent smaller is
not seen, and is not worth a warning on a slide."""


def _fitted(canvas: _Canvas, region: Region, box: Box) -> list:
    """The region's blocks, their words set smaller if that is what it takes to fit.

    Words shrink together, down to the deck's small size; a slide that still
    does not fit is reported, since it has more on it than a slide can hold.
    """

    style = canvas.deck.style
    blocks = [_capped(canvas, block) for block in region.blocks]
    # A placeholder (a sample, drawn for an editor and never shown) takes no room from what
    # is really there: the words are fitted, and said to be, as if it were not.
    real = [block for index, block in enumerate(blocks) if index not in region.placeholders]
    shown = [block for block in real if isinstance(block, _Figure | _Image | _Plot | _Gallery | _Missing)]
    pictures = len(shown)
    gaps = style.block_gap * max(0, len(real) - 1)

    def needed(scale: float) -> float:
        # Pictures (and galleries) take what is left: only words are fitted here.
        return sum(
            _height(canvas, _sized(block, scale, style), box.width)
            for block in real if not isinstance(block, _Gallery)
        )

    def largest(least: float) -> float:
        """The largest scale (down to the small size) at which the words leave each
        picture ``least`` of height."""

        room = box.height - gaps - least * pictures
        low, high = style.small_size / style.body_size, 1.0
        if needed(1.0) <= room:
            return 1.0
        if needed(low) > room:
            return 0.0
        for _ in range(10):
            middle = (low + high) / 2.0
            low, high = (middle, high) if needed(middle) <= room else (low, middle)
        return low

    scale = largest(PICTURE_LEAST)
    if pictures and scale < WORDS_KEPT:
        # A picture added to a full slide gives up room before the words around it do:
        # they shrink to WORDS_KEPT at most while it can still be PICTURE_SMALLEST tall.
        scale = max(scale, min(WORDS_KEPT, largest(PICTURE_SMALLEST)))
    if scale >= 1.0:
        return blocks
    if scale <= 0.0:
        canvas.diagnostics.append(
            f"{canvas.slide.id}: Text does not fit, even at the smallest size. "
            "Duplicate the slide and keep part of the text on each."
        )
        return [_sized(block, style.small_size / style.body_size, style) for block in blocks]
    if scale >= QUIET_SHRINK:
        return [_sized(block, scale, style) for block in blocks]
    # The advice names what is there: a figure is not a picture.
    kinds = list(dict.fromkeys(
        "figure" if isinstance(block, _Figure) else "plot" if isinstance(block, _Plot)
        else "pictures" if isinstance(block, _Gallery) else "picture" for block in shown
    ))
    named = " and ".join(kinds)
    own = "a column of its own" if len(shown) == 1 else "a column of their own"
    advice = (
        f" For full-size text, give the {named} {own} (Two Columns) or a slide of its own."
        if shown and canvas.slide.layout in {"content", "blank"} else ""
    )
    canvas.diagnostics.append(
        f"{canvas.slide.id}: Text size reduced to {round(scale * 100)}% to fit the slide.{advice}"
    )
    return [_sized(block, scale, style) for block in blocks]


MOST_ITEMS = 300
"""The most items of a list, rows of a table or lines of code drawn on one slide (500
lines of code): more than any slide shows, cut so the slide is drawn (and said) at once."""


def _capped(canvas: _Canvas, block):
    """``block``, cut to what a slide can hold if it is far past it, and said."""

    if isinstance(block, _Bullets) and len(block.items) > MOST_ITEMS:
        kept, what = replace(block, items=block.items[:MOST_ITEMS]), ("List", len(block.items), MOST_ITEMS, "items")
    elif isinstance(block, _Table) and len(block.rows) > MOST_ITEMS:
        kept, what = replace(block, rows=block.rows[:MOST_ITEMS]), ("Table", len(block.rows), MOST_ITEMS, "rows")
    elif isinstance(block, _Code) and len(block.lines) > MOST_ITEMS * 5 // 3:
        most = MOST_ITEMS * 5 // 3
        kept, what = replace(block, lines=block.lines[:most]), ("Code", len(block.lines), most, "lines")
    else:
        return block
    kind, count, most, unit = what
    canvas.diagnostics.append(
        f"{canvas.slide.id}: {kind} shortened from {count:,} to {most:,} {unit}, the most a slide can show. "
        "Duplicate the slide and keep part of it on each."
    )
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
        # A column with nothing in it yet (one just added) is as wide as a short word, so
        # there is somewhere to click and type.
        widths = [(max((row[c].width for row in measured), default=0.0) or size * 2.5) + slack for c in range(columns)]
        # While editing, a column still being filled in (a cell of it empty) is at least as wide
        # as the name an empty header shows there faintly ("Column 2"): typed into, it neither
        # narrows nor moves the cells. A column filled in is as its words make it.
        if PLACEHOLDERS.get() and block.header and block.rows:
            widths = [
                max(widths[c], canvas.measure(_column_hint(c), size, None, 700).width + slack)
                if any(not _worded(row[c]) for row in block.rows) else widths[c]
                for c in range(columns)
            ]
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
                    f"{canvas.slide.id}: A table with {columns} columns is too wide to fit, even at the smallest "
                    "size, so words are broken across lines. Shorten its cells, or move some columns to a second table."
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
        pad, block.header, (1.1, 0.6, 1.1) if block.outline else (0.0, 0.6, 0.0), palette=canvas.palette,
        measured=measured,
    )


def _column_hint(column: int) -> tuple[TextRun, ...]:
    """What an empty header cell shows while editing: its column's name, "Column 2"."""

    return (TextRun(f"Column {column + 1}"),)


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
            f"{canvas.slide.id}: Table rows have different numbers of cells. Empty cells were added to the "
            "end of the shorter rows."
        )
    plan = _table_plan(canvas, block, box.width, said=True)
    total = sum(plan.widths)
    # A table headed in a right-to-left script reads from the right: its first
    # column on the right, the table against the right edge, cells set from the right.
    plan.rtl = bool(plan.cells) and _rtl(tuple(run for cell in plan.cells[0] for run in cell))
    left = box.x + box.width - total if plan.rtl else box.x
    if canvas.place is not None:
        left = _across(canvas, box, total)
    elif canvas.alone:
        left = box.x + (box.width - total) / 2.0
    plan.x, plan.y, plan.id, plan.room = left, box.y, identifier, (box.x, box.width)
    canvas.span = (left, total)
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="table")
    ink = canvas.palette.get("ink")
    mirrored = {"start": "end", "end": "start", "middle": "middle"}
    y = box.y
    for r, row in enumerate(plan.cells):
        for c, cell in enumerate(row):
            x = left + total - sum(plan.widths[: c + 1]) if plan.rtl else left + sum(plan.widths[:c])
            if not cell and PLACEHOLDERS.get():
                # An empty cell, for an editor: where it is, to click and type in, framed faintly
                # (a row with nothing in it yet keeps its place), an empty header cell naming its
                # column -- as Keynote's empty cells show. Never presented (present.js hides
                # placeholders) nor exported (drawn only for an editor).
                element(
                    group, "rect", id=f"{identifier}.{r}.{c}", x=x, y=y, width=plan.widths[c],
                    height=plan.heights[r], fill="none", stroke=ink, stroke_opacity=0.22, stroke_width=0.6,
                    stroke_dasharray="2 2", data__flexo__placeholder="",
                )
                if plan.header and r == 0:
                    hint = canvas.measure(_column_hint(c), plan.size, None, 700, balance=False)
                    align = mirrored[plan.align[c]] if plan.rtl else plan.align[c]
                    start = x + plan.pad
                    anchor = {"start": start, "middle": x + plan.widths[c] / 2.0, "end": x + plan.widths[c] - plan.pad}
                    drawn = render_runs(
                        group, f"{identifier}.{r}.{c}.hint", hint, x=anchor[align], y=y + plan.baseline,
                        typography=canvas.deck.typography(plan.size), palette=canvas.palette,
                        fill_role="ink", anchor=align, weight=700,
                    )
                    if drawn is not None:
                        drawn.set("opacity", "0.38")
                        drawn.set("data-flexo-placeholder", "Column")
            if cell and PLACEHOLDERS.get():
                # Where a cell is, for an editor: its words are typed in a frame just its size.
                element(
                    group, "rect", id=f"{identifier}.{r}.{c}.cell", x=x, y=y, width=plan.widths[c],
                    height=plan.heights[r], fill="none",
                )
            if cell:
                inner = Box(x + plan.pad, y + plan.baseline, plan.widths[c] - 2 * plan.pad, 0.0)
                # Set as the plan measured it: measured again at the width that gave, a line can
                # come out a hair wider (kerning across a space) and wrap below a row one line tall.
                metrics = plan.measured[r][c] if plan.measured else canvas.measure(
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
        if not weight:
            continue  # (no outline)
        element(
            group, "path", id=f"{identifier}.rule{index}",
            d=f"M {number(left)} {number(level)} H {number(left + total)}",
            stroke=ink, stroke_width=weight, fill="none", data__flexo__stroke="ink",
        )
    plan.measured = None
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
    if identifier in canvas.hinted:
        # Code not yet written: its panel as wide as its place, to be typed in (not a chip
        # round its placeholder's word).
        width = box.width
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
            f"{canvas.slide.id}: {wrapped} line{'s' if wrapped > 1 else ''} of code wrapped to fit the slide. "
            f"Try shortening or breaking {'them' if wrapped > 1 else 'it'}."
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
    mark, big, family, metrics, hang = _quote_mark(canvas, block, size)
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
        role="tone-1-stroke", title=True, parent=group, align="end" if rtl else "start", family=family,
    )
    drawn = group.find(f".//*[@id='{identifier}.mark']")
    if family and drawn is not None:
        # Its face, which the slide's own faces are not, carried with it to a browser.
        from flexo.svg_resources import embed_fonts

        typography = canvas.deck.typography(big, title=True).with_family(family)
        style = replace(canvas.deck.layout_style, typography=typography)
        embed_fonts(element(group, "style", type="text/css"), drawn, style)
    canvas.words(f"{identifier}.words", block.runs, inner, size=size, title=True, parent=group)
    if by is not None:
        canvas.words(
            f"{identifier}.by", block.by, replace(inner, y=box.y + words.height + size * 0.45), size=by_size,
            role="muted-ink", parent=group,
        )
    return height


def _quote_mark(
    canvas: _Canvas, block: _Quote, size: float
) -> tuple[tuple[TextRun, ...], float, str | None, TextMetrics, float]:
    """A quotation's opening mark: its runs, size, family, metrics, and how far it hangs
    before the words -- as wide as its ink (a slanted hand's reaches past its advance) and a
    gap."""

    mark = (TextRun("\u201d" if _rtl(block.runs) else "\u201c"),)
    big = size * 3.6
    family = _mark_family(canvas, mark[0].text, big)
    metrics = canvas.measure(mark, big, None, title=True, family=family)
    hang = max(metrics.width, _ink_right(canvas, mark[0].text, big, family)) + size * 0.3
    return mark, big, family, metrics, hang


def _natural(canvas: _Canvas, block: object, width: float, share: float) -> float | None:
    """How wide ``block`` is drawn in a place ``width`` wide, no wider than it must be: its
    widest line and what stands before it (a bullet, a quotation's mark, a panel's edges and
    bar), the numbers side by side, the equation -- for it to stand at the left, middle or
    right of its place (``Region.places``). None where it fills its place (a gallery, a plot
    of no aspect of its own, a stand-in)."""

    style = canvas.deck.style
    if isinstance(block, _Words):
        return canvas.measure(block.runs, block.size or style.body_size, width).width
    if isinstance(block, _Bullets):
        size = block.size or style.body_size
        layout = _list_layout(canvas, block, Box(0.0, 0.0, width, 0.0))
        return max(
            (layout.offset(level) + canvas.measure(runs, size, width - layout.offset(level), balance=False).width
             for level, runs in block.items), default=0.0,
        )
    if isinstance(block, _Code):
        if not any(text.strip() for text in block.lines):
            return None
        size, lines = _code_lines(canvas, block, width)
        widths = [canvas.measure((TextRun(text, code=True),), size, None).width for text, _ in lines if text.strip()]
        return min(width, max(widths, default=0.0) + 2 * size * 0.9)
    if isinstance(block, _Quote):
        size = _quote_size(block, style)
        hang = _quote_mark(canvas, block, size)[4]
        words = canvas.measure(block.runs, size, width - hang, title=True).width
        by = canvas.measure(block.by, max(size * 0.62, style.small_size), width - hang).width if block.by else 0.0
        return hang + max(words, by)
    if isinstance(block, _Callout):
        size = block.size or style.body_size
        pad, bar = size * 0.8, 4.0
        room = width - bar - 2 * pad
        title = canvas.measure(block.title, size, room).width if block.title else 0.0
        return bar + 2 * pad + max(title, canvas.measure(block.runs, size, room, balance=False).width)
    if isinstance(block, _Stats):
        count, gap = len(block.items), style.column_gap
        cell = (width - gap * (count - 1)) / count
        weight, size = canvas.deck.title_weight, _stats_size(block, style)
        widest = max(canvas.measure(value, size, None, weight, title=True).width for value, _ in block.items)
        if widest > cell:
            size *= cell / widest
        label_size = max(size * 0.3, style.small_size * 0.9)
        labels = max(min(canvas.measure(label, label_size, None).width, cell) for _, label in block.items)
        return count * max(min(widest, cell), labels) + gap * (count - 1)
    if isinstance(block, _Math):
        from flexo.texmath import typeset

        size = block.size or style.body_size
        return min(width, typeset(block.source, canvas.deck.typography(size), size, display=True).width)
    if isinstance(block, _Plot) and block.aspect:
        return min(width, max(share, 60.0) * block.aspect)
    return None


MARK_FAMILY = "Liberation Sans"
"""The face a quotation's mark is drawn in where the title face's is no quotation mark
to the eye: as Helvetica draws it, two curled commas."""


def _mark_family(canvas: _Canvas, character: str, size: float) -> str | None:
    """The family a quotation's large mark is drawn in where the title face's own would not
    read as one: a mark of straight strokes only (Figtree's two wedges) reads as "//" set
    so large. None: in the title face, whose mark is curled."""

    from flexo.fonts import hb_font
    from flexo.outline import _outline
    from flexo.text import FontStack

    face = FontStack(canvas.deck.typography(size, title=True)).face(400, False)
    gid = hb_font(face, 400).get_nominal_glyph(ord(character))
    if gid is None or any(segment.kind == "C" for segment in _outline(face, 400, gid)):
        return None
    return MARK_FAMILY


def _ink_right(canvas: _Canvas, character: str, size: float, family: str | None = None) -> float:
    """How far right of its pen position a character of the title face (or ``family``) draws."""

    import uharfbuzz as hb
    from flexo.fonts import hb_font, load_face
    from flexo.text import FontStack

    typography = canvas.deck.typography(size, title=True)
    face = FontStack(typography.with_family(family) if family else typography).face(400, False)
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
    if canvas.place in {0.5, 1.0}:
        # Numbers set at the middle (the right) of their place stand so in their cells too.
        align = "middle" if canvas.place == 0.5 else "end"
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
                f"{canvas.slide.id}: The {len(block.items)} pictures in the gallery do not fit. "
                "Give it more columns, or put some of the pictures on a slide of their own."
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
        raise ValueError("Cropping pictures requires Pillow (pip install pillow).") from error
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
                f"{canvas.slide.id}: Equation reduced to {size:.0f} pt to fit. Try breaking it into lines "
                "(\\\\ inside aligned) or giving it more room."
            )
    canvas.say_maths(block.source, formula.problems)
    # Space above and below, as LaTeX sets a displayed equation apart from the words.
    skip = size * DISPLAY_SKIP
    if draw:
        x = {"start": box.x, "middle": box.x + (box.width - formula.width) / 2.0,
             "end": box.x + box.width - formula.width}.get(block.align, box.x)
        role, fill = _paint_of(block.colour, "ink")

        draw_formula(
            canvas.layer, formula, x, box.y + skip + formula.height, colour=formula_paint(canvas.palette),
            attributes={"id": identifier, "data__flexo__talk": "math", "data__flexo__size": number(size),
                        "data__flexo__align": block.align,
                        **paint_attributes(palette=canvas.palette, fill_role=role, fill=fill)},
        )
    return skip + formula.height + formula.depth + skip


DISPLAY_SKIP = 0.4
"""The space above and below a displayed equation, in ems of its size."""


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
        return sum(_table_plan(canvas, block, width).heights) + _captioned(canvas, block, width)
    if isinstance(block, _Figure | _Image | _Missing):
        # A picture takes the room left over; its caption, what it needs.
        return _captioned(canvas, block, width)
    if isinstance(block, _Words):
        size = block.size or style.body_size
        metrics = canvas.measure(block.runs, size, width)
        spaced = canvas.spaced(metrics, size)
        return spaced[2] if spaced else metrics.height
    if isinstance(block, _Bullets):
        size = block.size or style.body_size
        layout = _list_layout(canvas, block, Box(0.0, 0.0, width, 0.0))
        total = 0.0
        for index, (level, runs) in enumerate(block.items):
            offset = layout.offset(level)
            metrics = canvas.measure(runs, size, width - offset, balance=False)
            total += metrics.height + style.paragraph_gap * size + sum(_apart(block.items, index, size))
        return total
    return 0.0


def _dark_slide(deck: Deck, slide: Slide) -> bool:
    """Whether the slide's words are light: as its Text asks (Light, Dark), else (Auto) as
    reads best on its backdrop."""

    if slide.dark is not None:
        return slide.dark
    backdrop = slide.backdrop
    if not backdrop:
        return False
    if backdrop.startswith("#"):
        from flexo.colour import contrast

        # The words that read better on it -- light ones where they read about as well (within
        # a tenth), as Keynote sets words on a theme's mid blue; dark on a yellow or a grey.
        return contrast(LIGHT_WORDS["ink"], backdrop) >= 0.9 * contrast(DARK_WORDS["ink"], backdrop)
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
            f"{slide.id}: Text over the background picture is hard to read where the picture is bright "
            f"(contrast {ratio:.1f}:1). Darken the picture by {needed:.0%} (shade {needed:g}) to make the text "
            "readable."
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


LIGHT_WORDS = {"ink": "#f7f5f0", "muted-ink": "#d4d0c8"}
DARK_WORDS = {"ink": "#1c1c1e", "muted-ink": "#55555a"}
"""The words of a slide set on a backdrop of its own: light, or dark."""


def _readable(colour: str, backdrop: str, ratio: float, light: bool) -> str:
    """``colour`` made lighter (``light``) or darker until it reads on ``backdrop`` at
    ``ratio`` -- as far as it goes that way: words asked to be light stay light."""

    from flexo.colour import contrast, from_oklab, to_hex, to_oklab, to_rgb

    lightness, a, b = to_oklab(colour)
    result = to_hex(to_rgb(colour))
    for _ in range(50):
        if contrast(result, backdrop) >= ratio or not 0.0 < lightness < 1.0:
            break
        lightness = min(max(lightness + (0.02 if light else -0.02), 0.0), 1.0)
        result = from_oklab((lightness, a, b))
    return result


def _marks_on(palette: Palette, paints: dict[str, str], backdrop: str, light: bool) -> dict[str, str]:
    """The slide's accents (its title's rule, accented words, a figure's lines) that would not
    be seen on its own colour -- an accent on a slide of that accent -- made to show on it."""

    from flexo.colour import contrast

    marks = {}
    for role, colour in palette.paints.items():
        if role in {"canvas", "ink", "muted-ink", "shadow"} or role.endswith(("-ink", "-fill")):
            continue
        now = paints.get(role, colour)
        if contrast(now, backdrop) < 4.5:
            marks[role] = _readable(now, backdrop, 4.5, light)
    return marks


def _slide_palette(deck: Deck, slide: Slide):
    """The deck's paints, or paints for words over this slide's own backdrop: light
    words on a dark one, dark words on a light one when the deck's page is dark -- or as
    the slide's Text asks."""

    from flexo.colour import is_dark, with_lightness

    palette = deck.palette
    page_dark = is_dark(palette.get("canvas"))
    dark = _dark_slide(deck, slide)
    colour = slide.backdrop if (slide.backdrop or "").startswith("#") else None
    if not slide.backdrop and slide.dark is None:
        return palette
    if not dark and not page_dark:
        # A light backdrop in a light deck (a mid grey): the deck's words, kept readable on it
        # -- and dark, as asked, however dark the colour.
        if colour is None:
            return palette
        paints = {
            "ink": _readable(palette.get("ink"), colour, 7.0, False),
            "muted-ink": _readable(palette.get("muted-ink"), colour, 4.5, False),
        }
        return palette.with_overrides(paints | _marks_on(palette, paints, colour, False))
    paints = dict(LIGHT_WORDS if dark else DARK_WORDS)
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
        # As light (or dark) as it takes to read, never the other: the slide's Text is kept.
        paints["ink"] = _readable(paints["ink"], backdrop, 7.0, dark)
        paints["muted-ink"] = _readable(paints["muted-ink"], backdrop, 4.5, dark)
        paints |= _marks_on(palette, paints, backdrop, dark)
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
        style.indent, numbered=block.numbered, reveal=block.reveal, plain=block.plain, palette=canvas.palette,
    )
    if block.numbered:
        numbers = list(zip(list_numbers([level for level, _ in block.items]), block.items, strict=True))

        def widest(labels: list[str]) -> float:
            return max((canvas.measure((TextRun(label),), size, None).width for label in labels), default=0.0)

        layout.number_room = widest([n for n, (level, _) in numbers if level == 0] or ["1."]) + size * 0.45
        below = [n for n, (level, _) in numbers if level > 0]
        layout.sub_room = widest(below) + size * 0.4 if below else 0.0
    return layout


DISPLAY_GAP = 0.4
"""The room (in ems) a list's item that is one formula displayed has above and below it,
beyond the gap between items: as LaTeX sets a displayed formula apart from its words."""


def _apart(items: list, index: int, size: float) -> tuple[float, float]:
    """The room set before and after a list's item that is a displayed formula alone: none
    before the first item, nor after the last."""

    if not displayed_alone(items[index][1]):
        return 0.0, 0.0
    return (DISPLAY_GAP * size if index else 0.0), (DISPLAY_GAP * size if index < len(items) - 1 else 0.0)


def _bullets(canvas: _Canvas, identifier: str, block: _Bullets, box: Box) -> float:
    style = canvas.deck.style
    size = block.size or style.body_size
    group = element(canvas.layer, "g", id=identifier, data__flexo__talk="bullets")
    if PLACEHOLDERS.get():
        # How wide its items may run before they wrap: the studio's editor wraps them there too.
        group.set("data-flexo-wrap", f"{box.width:g}")
    layout = _list_layout(canvas, block, box)
    # Its words in its colour, if it has one; the bullets and numbers in the theme's.
    ink_role, ink_fill = _paint_of(block.colour, "ink")
    if block.colour:
        layout.ink = ink_fill or canvas.palette.get(ink_role)
    top = box.y
    numbers = list_numbers([level for level, _ in block.items]) if block.numbered else []
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
        # An item that is one formula displayed ($$...$$) is set apart from the items around it.
        apart = _apart(block.items, index, size)
        top += apart[0]
        # A revealed item (with the items under it) is its own group, tagged with its step.
        item = element(group, "g", data__flexo__step=step + 1) if block.reveal else group
        if block.reveal:
            canvas.steps = max(canvas.steps, step + 1)
            if level == 0:
                layout.stepped.append(step + 1)
        offset = layout.offset(level)
        metrics = canvas.measure(runs, size, box.width - offset, balance=False)
        layout.line_height = metrics.line_height
        baseline = top + metrics.baseline
        role = "tone-1-stroke" if level == 0 else "muted-ink"
        rtl = _rtl(runs)

        def across(distance: float, rtl: bool = rtl) -> float:
            """A distance in from the list's start edge: the left, or the right for RTL."""

            return box.x + box.width - distance if rtl else box.x + distance
        if block.numbered:
            label = (TextRun(numbers[index]),)
            canvas.words(
                f"{identifier}.{index}.mark", label,
                Box(across(layout.mark_at(level)), top + metrics.baseline - canvas.measure(label, size, None).baseline,
                    0.0, 0.0),
                size=size, role=role, parent=item, align="end" if rtl else "start",
            )
        elif not block.plain:
            radius = size * (0.15 if level == 0 else 0.12)
            cx = across(style.indent * level + size * 0.3)
            cy = baseline - (metrics.cap_height or size * 0.7) / 2.0
            element(
                item, "circle", id=f"{identifier}.{index}.mark", cx=cx, cy=cy, r=radius,
                fill=canvas.palette.get(role), data__flexo__fill=role,
            )
        # A formula displayed in an item sits after its bullet, as the item's words do: centred
        # in the column, it would stand far from the bullet it belongs to.
        render_runs(
            item, f"{identifier}.{index}", metrics, x=across(offset), y=baseline,
            typography=canvas.deck.typography(size), palette=canvas.palette, fill_role=ink_role, fill=ink_fill,
            anchor="end" if rtl else None,
        )
        layout.items.append((level, runs, baseline))
        layout.steps.append(metrics.line_height)
        layout.opened.append((metrics.rise, metrics.fall, len(metrics.lines)))
        layout.id = identifier
        top += metrics.height + style.paragraph_gap * size + apart[1]
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
    turned: Any = None
    """For a figure kept as its person arranged it (not turned to fit): how many times larger
    it would be drawn turned to fit its place, asked only when it is drawn small."""
    alone: Any = None
    """The scale it would be drawn at with a place ``(width, height)`` to itself (a slide of
    its own), laid out for it: asked only when it is drawn small."""


LEGIBLE = 7.0
"""Words on a slide smaller than this (points) are reported: they will not read."""

SMALL = 11.0
"""Words on a slide smaller than this (points) are noted: they read close to, not from the
back of a room."""


EDITING = contextvars.ContextVar("flexo_talk_editing", default=False)
"""Whether slides are drawn for an editor while they are changed: a figure on one then
keeps the layout it last had (``flexo.fit_in_box``'s ``keep``), drawn in one compile
rather than every way it could be, and the slide says it is not settled."""

_LAYOUTS: dict[tuple[str, str, str], str] = {}
"""The layout each figure (by deck, slide and figure) was last drawn in."""

_SCALES: dict[tuple[str, str, str], float] = {}
"""The scale each figure was last drawn at, beside its layout."""

_SHOWN: dict[tuple[str, str, str], str] = {}
"""The way each figure's outermost group was last drawn, a row or a column, beside its
layout: as written, or the other way when the figure was turned to fit."""

_PLACES: dict[tuple[str, str, str], tuple[float, float, float]] = {}
"""The place each figure was last drawn in: its width and height, and how large its words
could be there (a figure slide's, as large as its title's)."""

SAME_PLACE = 0.15
"""How much a figure's place may change (a line of words added over it) and still be the
place it was seen in, kept the way it was drawn there."""

_ASKED: dict[tuple[str, str, str], bool | None] = {}
"""What each figure's own Turn to Fit the Slide said when it was last drawn (``None``: as
the deck decides): only its person changing it turns a figure they have seen the other way."""

_TURNS: dict[tuple[str, str, str], bool] = {}
"""Whether each figure was last drawn free to turn, beside its layout: one just let turn
("Turn to Fit the Slide") is laid out afresh, not kept as it was."""


def _arranged(spec: object) -> bool:
    """Whether a figure's parts were arranged by hand: a column of parts set in a row
    beside others, or a row in a column (one part put under another, a line of its own) --
    not one row or column holding them all."""

    groups = {group.id: group for group in spec.groups}
    for holder in spec.groups:
        if holder.layout.kind not in ("row", "column") or len(holder.children) < 2:
            continue
        for child in holder.children:
            inner = groups.get(child)
            across = inner is not None and inner.layout.kind in ("row", "column")
            if across and inner.layout.kind != holder.layout.kind and len(inner.children) > 1:
                return True
    return False


def _root_kind(spec: object) -> str | None:
    """Whether a figure's outermost group is written as a row or a column."""

    root = next((group for group in spec.groups if group.id == spec.root), None)
    kind = getattr(getattr(root, "layout", None), "kind", None)
    return kind if kind in ("row", "column") else None


def _kept_as_written(where: tuple[str, str, str], spec: object) -> None:
    """A figure drawn turned (or folded), and since written the way it was drawn (as the
    studio writes one before moving a part where it is seen, under or beside another), is
    kept as it is now written: turned again, each of its rows would be drawn as a column,
    the part moved under another beside it."""

    layout = _LAYOUTS.get(where)
    if layout and "folded" in layout and _arranged(spec):
        # Drawn folded onto lines, and since written so -- each line a row (column) of its
        # own, as the studio writes the lines it puts a part among -- it is drawn as written:
        # turned and folded again, its lines would be turned and folded in their turn.
        spacing = layout.removeprefix("turned within").removeprefix("turned").removeprefix("as written")
        for suffix, _ in flexo.boxfit.FOLDS:
            spacing = spacing.removesuffix(suffix)
        _LAYOUTS[where] = "as written" + spacing
        return
    if not layout or not layout.startswith("turned") or layout.startswith("turned within"):
        return
    if _SHOWN.get(where) is not None and _SHOWN.get(where) == _root_kind(spec):
        _LAYOUTS[where] = "as written" + layout.removeprefix("turned")

REFIT = 1.0
"""Seconds a figure's best layout may have taken to find, last time, for it to be found
again while the figure is changed (``SHRUNK``): longer, and the changes would wait on it."""

_FINDING: dict[tuple[str, str, str], float] = {}
"""How long each figure's best layout took to find, the last time it was."""

SHRUNK = 0.9
"""How much smaller a figure kept in its layout while edited may be drawn before its best
layout is found at once (see ``_prepare``)."""

STEADY = 1.3
"""How much larger another layout must set a figure for it to leave the one it is shown in."""


def _layout_said(layout: str, spec: object = None) -> str:
    """The note for a figure drawn in a layout other than as written: ``flexo.fit_in_box``
    names it (``turned``, ``turned within, tighter``, ``as written, folded``...). Said as a
    person sees it: a chart turned to run across, wrapped onto two lines."""

    # Steps joined by lines are a chart; anything else, a figure.
    noun = "chart" if getattr(spec, "edges", None) or getattr(spec, "nets", None) else "figure"
    # Turned whole, it runs the other way to the way it is written.
    written = _root_kind(spec) if spec is not None else None
    way = {"column": "across", "row": "down"}.get(written or "")
    done = []
    if layout.startswith("turned within"):
        done.append(f"the {noun}'s groups were turned the other way")
    elif layout.startswith("turned"):
        done.append(f"the {noun} was turned to run {way}" if way else f"the {noun} was turned")
    if "tighter" in layout:
        done.append("set a little closer together" if done else f"the {noun} was set a little closer together")
    if "folded" in layout:
        done.append("wrapped onto two lines" if done else f"the {noun} was wrapped onto two lines")
    if not done:
        return f"The {noun} was rearranged to fit the slide."
    how = done[0] if len(done) == 1 else f"{', '.join(done[:-1])} and {done[-1]}"
    return f"To fit the slide, {how}."


def _fit_in_box(*args, draft: bool = True, **options) -> object:
    """``flexo.fit_in_box`` for a slide: the figure's words are set in the slide's own fonts,
    embedded once for the slide, so the figure's own copies -- cut down for each layout
    tried -- are not made only to be thrown away. While the slide is changed (``EDITING``)
    a figure kept in its layout is drawn as a draft (``flexo.draft``, unless not to be a
    ``draft``): its lines as they were, but for those about what changed -- drawn in full
    once the changes stop."""

    from flexo.draft import drafting
    from flexo.svg_resources import fonts_linked

    with fonts_linked(), drafting(EDITING.get() and draft):
        return flexo.fit_in_box(*args, **options)


def _prepare(canvas: _Canvas, block: _Figure, box: Box, largest: float) -> _Prepared:
    """A figure laid out for ``box`` by flexo (``flexo.fit_in_box``): at the width
    that sets its words at the deck's figure size, as written or turned, spaced
    as the theme says or closer -- whichever lets its words be largest there,
    though never larger than ``largest`` (the body text, or the words of the
    figures beside it). One that fails so is said (``_FigureFailed``), not the slide's end."""

    try:
        return _prepared(canvas, block, box, largest)
    except Exception as error:
        from flexo.studio.plain import explain

        from flexo_talk.document import DeckDocumentError, UntrustedCode

        if isinstance(error, UntrustedCode):
            raise  # (Python not yet trusted: said in its place, as the folder waits)
        if isinstance(error, DeckDocumentError):
            # Made by the deck's Python, which failed (a function there is none of): it stands
            # aside where it can (the studio), and stops the build where it can't.
            if not STANDING_ASIDE.get():
                raise
            raise _FigureFailed(block, error, FIGURE_FAILED, f"{FIGURE_FAILED}: {error.message}") from error
        spec = getattr(block.figure, "spec", block.figure)
        # Only some of its shapes at fault (a plasmid of -5 bp, a tree whose Newick does not
        # read): those drawn as plain boxes of their words, the rest as written -- each said,
        # its place naming it ("#p:length"), to be chosen and put right.
        # (Drawn, a shape may fail only once the one before it is a box: tried till none do.)
        figure, failure, told = spec, error, []
        for _ in getattr(spec, "nodes", ()):
            stood = _stood_in(figure, failure)
            if stood is None:
                break
            figure, said = stood
            told += said
            try:
                prepared = _prepared(canvas, replace(block, figure=figure), box, largest)
            except Exception as again:
                failure = again
                continue
            canvas.diagnostics.extend(f"{canvas.slide.id} {spec.id}{text}" for text in told)
            return prepared
        raise _FigureFailed(block, error, FIGURE_FAILED, f"{FIGURE_FAILED}: {_named(spec, explain(error))}") from error


def _stood_in(spec: object, error: BaseException) -> tuple[object, list[str]] | None:
    """``spec`` with each shape ``error`` blames drawn as a plain box of its words, and what
    to say of each (``#id:what: “Name” can't be drawn yet: ...``); None should it name none,
    or something else."""

    from flexo.components import normalize_node
    from flexo.diagnostics import FlexoError

    nodes = {node.id: node for node in getattr(spec, "nodes", ())}
    if not isinstance(error, FlexoError) or not error.diagnostics:
        return None
    wrong = [item for item in error.diagnostics if item.entity_id in nodes]
    if len(wrong) != len(error.diagnostics):
        return None
    bad = {item.entity_id for item in wrong}
    plain = tuple(
        normalize_node(replace(node, kind="block", properties=(), ports=(), width=None, height=None))
        if node.id in bad else node
        for node in spec.nodes
    )
    said = []
    for item in wrong:
        words = "".join(run.text for run in nodes[item.entity_id].label).strip()
        message = item.message.strip()
        first = message.split(" ", 1)[0]
        lower = message if len(first) > 1 and first.isupper() else message[:1].lower() + message[1:]
        called = f"\u201c{words}\u201d" if words else "A shape"
        what = str(item.code or "").rsplit(".", 1)[-1]
        said.append(
            f"#{item.entity_id}:{what}: {called} can\u2019t be drawn yet: {lower} Choose it to set this in its panel."
        )
    try:
        return replace(spec, nodes=plain), said
    except Exception:
        return None


def _named(spec: object, said: str) -> str:
    """What is said of a figure, its shapes named by their words, not their ids."""

    for node in getattr(spec, "nodes", ()):
        words = "".join(run.text for run in node.label).strip() if node.label else ""
        if words and re.search(rf"(?<![\w.-]){re.escape(node.id)}(?![\w-])", said):
            said = re.sub(rf"(?<![\w.-]){re.escape(node.id)}(?![\w-])", f"\u201c{words}\u201d", said)
    return said


def _prepared(canvas: _Canvas, block: _Figure, box: Box, largest: float) -> _Prepared:
    deck = canvas.deck
    figure = made(block.figure)
    spec = figure.spec if isinstance(figure, flexo.Figure) else figure
    if not isinstance(figure, flexo.Figure) or spec.style != deck.theme:
        # A figure made elsewhere is redrawn in the deck's look.
        spec = replace(
            spec, style=deck.theme, palette=deck.palette_name,
            font=deck.figure_font or deck.font or spec.font,
        )
        if deck.conventions:
            # The deck's conventions (its arrowheads, say), the figure's own over them.
            from flexo.conventions import parse_conventions

            ours = parse_conventions(deck.conventions)
            spec = replace(spec, conventions=ours.with_updates(spec.conventions) if spec.conventions else ours)
    style = figure_style(spec)
    base = style.typography.size.points
    # A figure its person arranged by hand -- a part put under another, or on a line of its
    # own -- is drawn as arranged, made smaller to fit rather than turned round, unless they
    # ask for it to be turned.
    turn = block.turn if block.turn is not None else not _arranged(spec)
    # Kept from turning by its person (Turn to Fit the Slide off), it is still folded onto two
    # lines to fit as one left to the deck is: kept the way it runs is not kept from folding
    # (flexo's fit_in_box), and the switch never unwraps it. (Arranged by hand, it is drawn
    # as arranged.)
    fold = turn or (block.turn is False and not _arranged(spec))
    where = (deck.id, canvas.slide.id, spec.id)
    _kept_as_written(where, spec)
    # A figure its person has seen keeps the way it was drawn -- turned to fit the slide, or
    # as written -- however it is changed (a shape added to a long column, a part put under
    # another), until they ask for the other way with Turn to Fit the Slide: it never turns,
    # or stops turning, under them. (Settled, it is kept so too, and so is found so again
    # when the deck is opened next.) Given another place -- the slide's layout changed, the
    # figure made wider -- it is laid out for it afresh. Kept from turning, it may still be
    # folded onto two lines as ever (``fold``): that is no turn.
    asked = where in _ASKED and _ASKED[where] != block.turn
    seen = _LAYOUTS.get(where)
    placed = _PLACES.get(where)
    same = placed is not None and all(
        abs(was - now) <= SAME_PLACE * max(now, 1.0)
        for was, now in zip(placed, (box.width, box.height, largest), strict=True)
    )
    free = seen.startswith("turned") if seen is not None and same and not asked else turn
    # The palette is in the key too: a theme file's colours can change under the same name.
    # (So is whether its person asked it to turn, or left it to the deck; and, once it has
    # been seen, whether it is free to turn. Opened again, it is found as it was last seen.)
    opened = (
        spec, style, repr(figure_palette(spec)), box.width, box.height, deck.style.figure_size,
        largest, turn, block.turn,
    )
    key = opened if seen is None else (*opened, free)
    laid = _cached_fit(key)
    if laid is None:
        # Drawn for an editor while it is changed, a figure keeps the layout it had, in
        # one compile; the best of every layout is found once the changes stop.
        # (Not one just let turn, or kept from turning: its person asked for the other way.)
        keep = seen if EDITING.get() and not asked else None
        started = time.perf_counter()
        try:
            fit = _fit_in_box(
                spec, box.width, box.height, words=min(deck.style.figure_size, largest), largest=largest,
                turn=free, fold=fold, keep=keep,
            )
        except GivenUp:
            # Given up for a change: it takes at least this long to find, however long it took
            # when the figure was smaller.
            if keep is None:
                _FINDING[where] = max(_FINDING.get(where, 0.0), time.perf_counter() - started)
            raise
        if keep is None:
            _FINDING[where] = time.perf_counter() - started
        shown = _SCALES.get(where)
        # Kept folded, its lines might now cross (a loop added across the fold): a fold is
        # the layout's own doing, so a better way is looked for at once too.
        crossed = keep is not None and fit.layout == keep and "folded" in keep and any(
            item.code == "routing.connector.crossing"
            for item in lint_compilation(fit.compilation, style=fit.style).diagnostics
        )
        # (Unless finding it takes a while -- a large figure -- when the changes would wait on
        # it: it is found once they stop. So too if how long is not known.)
        quick = _FINDING.get(where, math.inf) <= REFIT
        if keep is not None and fit.layout == keep and ((shown and fit.scale < shown * SHRUNK) or crossed) and quick:
            # Kept, the figure would shrink a good deal (a shape added to a long row): its
            # best layout is found now, in one drawing, rather than a moment later, when it
            # would jump under its person's eyes.
            keep = None
            started = time.perf_counter()
            fit = _fit_in_box(
                spec, box.width, box.height, words=min(deck.style.figure_size, largest), largest=largest,
                turn=free, fold=fold,
            )
            _FINDING[where] = time.perf_counter() - started
        give_up_if_newer()  # (a settling given up for a change: flexo.draft)
        codes = [
            diagnostic.code
            for diagnostic in lint_compilation(fit.compilation, style=fit.style).diagnostics
            # The figure is laid out for its place and scaled to it: a grown width is moot.
            if diagnostic.code != "layout.width.grown"
        ]
        # (Only while it is changed: settled, a figure is drawn as its document says, the same
        # way whatever came before -- after an undo, after a reload.)
        previous = _LAYOUTS.get(where) if EDITING.get() and not asked else None
        if (keep is None or fit.layout != keep) and previous and fit.layout != previous:
            # A figure already shown one way stays that way unless another is clearly
            # larger: it doesn't turn under its person for a little more room.
            # (Drawn in full: kept, it is the figure as settled.)
            held = _fit_in_box(
                spec, box.width, box.height, words=min(deck.style.figure_size, largest), largest=largest,
                turn=free, fold=fold, keep=previous, draft=False,
            )
            kept = [
                diagnostic.code
                for diagnostic in lint_compilation(held.compilation, style=held.style).diagnostics
                if diagnostic.code != "layout.width.grown"
            ]
            # Nor does it stay a way that now makes lines cross (a fold, its parts changed)
            # when the way found does not.
            crossing = "routing.connector.crossing"
            calm = kept.count(crossing) <= codes.count(crossing)
            if held.layout == previous and fit.scale < held.scale * STEADY and calm:
                fit = held
                codes = kept
        laid = {
            "svg": fit.compilation.document.text, "ink": list(fit.ink), "layout": fit.layout, "codes": codes,
            "scale": fit.scale, "finding": _FINDING.get(where),
        }
        if keep is not None and fit.layout == keep:
            canvas.settled = False
        else:
            # (Found again as it is seen -- by the next drawing, free to turn as this one is
            # turned or not; and by the deck opened next, drawn as it was last seen.)
            for also in dict.fromkeys((key, (*opened, fit.layout.startswith("turned")), opened)):
                _store_fit(also, laid)
    elif laid.get("finding") is not None:
        # (Found before, in another session: how long it took then.)
        _FINDING[where] = laid["finding"]
    _LAYOUTS[where] = laid["layout"]
    _TURNS[where] = turn
    _ASKED[where] = block.turn
    _PLACES[where] = (box.width, box.height, largest)
    written = _root_kind(spec)
    turned_whole = laid["layout"].startswith("turned") and not laid["layout"].startswith("turned within")
    _SHOWN[where] = {"row": "column", "column": "row"}.get(written) if turned_whole else written
    if laid.get("scale"):
        _SCALES[where] = laid["scale"]
    for said in dict.fromkeys(filter(None, (_figure_check(code) for code in laid["codes"]))):
        canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}: {said}")
    for text in block.said:
        # (One about a part of it -- a line -- names it: "#edge.2.b-to-nowhere: ...".)
        canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}{text if text.startswith('#') else ': ' + text}")
    # A structure that can't be drawn as written is a panel saying why: said under the slide too,
    # naming it and its file, to be chosen and put right.
    for node in spec.nodes:
        problem = structure_problem(node, style) if node.kind == "structure" else None
        if problem is not None:
            canvas.diagnostics.append(f"{canvas.slide.id} {spec.id}#{node.id}:source: {problem.message}")
    # Spaced a little closer is no news; swapped or folded, the figure reads differently.
    if "turned" in laid["layout"] or "folded" in laid["layout"]:
        canvas.notes.append(f"{canvas.slide.id} {spec.id}: {_layout_said(laid['layout'], spec)}")
    left, top, width, height = laid["ink"]
    # Its headings (a protein's name, in bold) no larger than the body's words, however large
    # its words are let be: never as large as the slide's own title.
    heading = _heading_size(laid["svg"], base)
    most = min(largest / base, deck.style.body_size / heading) if heading else largest / base

    def larger_turned() -> float:
        # Laid out as the switch "Turn to Fit the Slide" would have it, for the same place.
        try:
            fit = _fit_in_box(
                spec, box.width, box.height, words=min(deck.style.figure_size, largest), largest=largest, turn=True,
            )
        except Exception:
            return 1.0
        _, _, wide, high = fit.ink
        now = min(box.width / max(width, 1e-6), box.height / max(height, 1e-6))
        return min(box.width / max(wide, 1e-6), box.height / max(high, 1e-6)) / max(now, 1e-6)

    def alone(wide: float, high: float) -> float:
        # Laid out for a place of its own as it is for this one, its words no larger.
        try:
            fit = _fit_in_box(
                spec, wide, high, words=min(deck.style.figure_size, largest), largest=largest, turn=turn,
                fold=fold,
            )
        except Exception:
            return 0.0
        _, _, ink_wide, ink_high = fit.ink
        return min(wide / max(ink_wide, 1e-6), high / max(ink_high, 1e-6), most)

    # (Turned off by its person, or arranged by hand: either way, said if turning would help.)
    turnable = _settled_only(where, "turned", larger_turned, 1.0) if not free else None
    return _Prepared(
        laid["svg"], left, top, width, height, most, base, spec.id, turnable, _settled_only(where, "alone", alone, 0.0)
    )


_ASIDE: dict[tuple, float] = {}
"""What laying a figure out another way would give it (turned, or with a slide of its own),
as last found once its changes stopped: kept for while it is changed again (``_settled_only``)."""


def _settled_only(where: tuple, what: str, find, otherwise: float):
    """``find``, which lays a figure out afresh another way, done only once its changes
    stop: while it is changed (``EDITING``), what it found then -- or ``otherwise`` -- so a
    figure being dragged is not laid out twice over at every move."""

    def answer(*args) -> float:
        key = (where, what, args)
        if EDITING.get():
            return _ASIDE.get(key, otherwise)
        _ASIDE[key] = value = find(*args)
        while len(_ASIDE) > 256:
            _ASIDE.pop(next(iter(_ASIDE)))
        return value

    return answer


def _heading_size(svg: str, base: float) -> float:
    """The size of a figure's headings, in its own units: its bold words, or words larger
    than its own (``base``). None (0) where it has no heading."""

    sizes = []
    for tag in re.findall(r"<text [^>]*>", svg):
        size = re.search(r'font-size="([\d.]+)"', tag)
        if size and (float(size.group(1)) > base * 1.01 or re.search(r'font-weight="([6-9]00|bold)"', tag)):
            sizes.append(float(size.group(1)))
    return max(sizes, default=0.0)


_FIGURE_CHECKS = {
    "layout.text.overflow": "Some text doesn't fit its shape in this figure.",
    "layout.sibling.overlap": "Some shapes overlap in this figure.",
    "layout.child.outside": "A shape sticks out of its group in this figure.",
    "layout.canvas.clipped": "Part of this figure is cut off.",
    "routing.connector.crossing": "Lines cross in this figure.",
    "routing.obstacle.intersection": "A line passes through a shape in this figure.",
    "routing.net.obstacle.intersection": "A line passes through a shape in this figure.",
    "routing.caption.overlap": "A line's label overlaps something in this figure.",
    "routing.caption.covers-line": "A line's label covers a line in this figure.",
    "routing.canvas.clipped": "A line is cut off in this figure.",
    "routing.net.canvas.clipped": "A line is cut off in this figure.",
    "routing.container.clipped": "A line is cut off by its group in this figure.",
    "routing.track.separation": "Lines run too close together in this figure.",
    "label.math": "Some maths in this figure can't be typeset.",
    "layout.size.grown": "A shape is drawn larger than the size it was given, to fit its words.",
    "layout.overflow": "A group in this figure is too small for what it holds.",
    "layout.grid.overflow": "A grid in this figure is too small for what it holds.",
    "publication.type.small": "Some words in this figure are very small.",
    "routing.lane.unknown": "A line is asked to run beside a group this figure doesn't have.",
    "routing.lane.syntax": "A line is asked to run along a side this figure can't read.",
    "routing.waypoint.unknown": "A line is asked to pass a part this figure doesn't have.",
    "routing.via.clamped": "A line can't run on the side it was asked to in this figure.",
    "routing.net.rail-at.clamped": "Joined lines can't meet where they were asked to in this figure.",
}
"""What a figure's checks found, said under its slide (flexo's codes, by their meaning)."""

_UNSAID_CHECKS = ("svg.", "publication.stroke.", "publication.size.")
"""Checks of the drawing's file (its layers, its ids, a print's hairlines): nothing a person
can put right on the slide, so nothing said under it."""


def _figure_check(code: str) -> str | None:
    """What a figure's check found, in plain words -- never its code -- or ``None`` when it
    is about the drawing's file rather than anything a person can change."""

    if code in _FIGURE_CHECKS:
        return _FIGURE_CHECKS[code]
    if code.startswith(_UNSAID_CHECKS):
        return None
    if code.startswith("routing.") and code.endswith((".arrow", ".clearance", ".orientation")):
        return "A line or arrowhead is cramped in this figure."
    if code.startswith("routing."):
        return "A line doesn't meet its shape cleanly in this figure."
    if code.startswith("layout."):
        return "Some shapes in this figure don't fit where they are."
    return "Part of this figure isn't drawn quite as written."


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


TURNED_LARGER = "Turned to fit the slide, it would be larger."
"""Said of a figure drawn small as its person arranged it, that turning would draw larger:
the studio offers to turn it (``figure.small.turn``)."""
OWN_SLIDE = "On a slide of its own, it would be larger."
"""Said of a figure drawn small beside other objects on its slide, that the whole of a slide
would draw larger: the studio offers to give it one (``figure.small.own``)."""


def _check_legible(
    canvas: _Canvas, prepared: dict[int, _Prepared], scales: dict[int, float], box: Box
) -> None:
    # What would make a figure drawn small larger, as it is: turned (kept as arranged, it
    # may be one turn from larger), else a slide of its own (it shares this one: the whole
    # of ``box``, its region, as wide as the slide), else fewer shapes or words -- said so,
    # for the studio to offer what it can do in one click.
    style = canvas.deck.style
    shared = sum(len(region.blocks) for region in canvas.slide.regions.values()) > 1
    whole = (max(box.width, style.width - 2 * style.margin), box.height)
    for index, item in prepared.items():
        drawn = item.size * scales[index]
        turning = drawn < SMALL and item.turned is not None and item.turned() > 1.15
        alone = item.alone(*whole) if drawn < SMALL and shared and not turning and item.alone else 0.0
        larger = (
            TURNED_LARGER if turning else OWN_SLIDE if alone > scales[index] * 1.15
            else "Fewer shapes, or fewer words in them, would make it larger."
        )
        if drawn < LEGIBLE:
            canvas.diagnostics.append(
                f"{canvas.slide.id} {item.id}: Text in this figure is {drawn:.1f} pt, too small to read. {larger}"
            )
        elif drawn < SMALL:
            canvas.notes.append(
                f"{canvas.slide.id} {item.id}: Text in this figure is {drawn:.0f} pt, small for a talk. {larger}"
            )


def _place_figure(canvas: _Canvas, identifier: str, item: _Prepared, box: Box, scale: float) -> float:
    """Put a prepared figure in ``box`` at ``scale``: centred across, and down if it has room."""

    x = _across(canvas, box, item.width * scale) - item.left * scale
    y = box.y + (box.height - item.height * scale) / 2.0 - item.top * scale
    canvas.span = (_across(canvas, box, item.width * scale), item.width * scale)
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
        said.append(("", f"The {marks:,} marks in the plot are drawn as an image, not as shapes. "
                         "To choose this yourself, plot them with rasterized=True."))
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

_FITTED_SAID = {"wrapped onto more lines": "wrapped", "set smaller": "reduced in size", "cut short": "truncated"}
"""What was done to a plot's words too long for it, as the message under the slide says it."""


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
            said.append(f"Text \u201c{shown}\u201d in the plot runs outside it. Try shortening it.")
        elif done:
            steps = [_FITTED_SAID[step] for step in done]
            how = " and ".join([", ".join(steps[:-1]), steps[-1]] if len(steps) > 1 else steps)
            said.append(f"Text \u201c{shown}\u201d in the plot is too long, so it was {how}. Try shortening it.")
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
        reason = "it has no environments, such as matrices or cases; set the formula on the slide instead"
    else:
        reason = "it supports only part of LaTeX; set the formula on the slide instead"
    shown = words if len(words) <= 60 else words[:59] + "\u2026"
    return f"Matplotlib cannot render the maths in the plot text \u201c{shown}\u201d: {reason}."


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


def _missing(canvas: _Canvas, identifier: str, block: _Missing, box: Box) -> float:
    """A dashed box where a picture or figure whose file is not there would be, saying so."""

    style = canvas.deck.style
    height = min(box.height, max(box.width * 0.6, 40.0))
    canvas.span = (box.x, box.width)
    ink = canvas.palette.get("muted-ink")
    # An object that can't be drawn, or whose file is not there, keeps its place, presented
    # and exported, but shows nothing there -- not a box of nothing: why is said on the
    # editing stage alone, not to the audience.
    quiet = not PLACEHOLDERS.get()
    group = element(
        canvas.layer, "g", id=identifier, data__flexo__talk="invalid" if block.said is not None else "missing"
    )
    if quiet:
        return height
    element(
        group, "rect", id=f"{identifier}.box", x=box.x, y=box.y, width=box.width, height=height, rx=6.0,
        fill=ink, fill_opacity=0.06, stroke=ink, stroke_opacity=0.6, stroke_width=1.5, stroke_dasharray="6 4",
    )
    # The name as the document writes it, not read as markup.
    runs = (TextRun(block.said or f"Missing {block.what}: {block.name}"),)
    size, pad = style.small_size, style.small_size
    words = canvas.measure(runs, size, max(box.width - 2 * pad, 1.0))
    place = Box(box.x + pad, box.y + max((height - words.height) / 2.0, 0.0), max(box.width - 2 * pad, 1.0), 0.0)
    canvas.words(f"{identifier}.words", runs, place, size=size, align="middle", role="muted-ink", parent=group)
    return height


def _across(canvas: _Canvas, box: Box, width: float) -> float:
    """Where a picture ``width`` wide starts across ``box``: where it was asked to stand
    (``canvas.place``), else centred in it, or at its start beside a list
    (``canvas.centred``), its left edge with the list's."""

    share = canvas.place if canvas.place is not None else 0.5 if canvas.centred else 0.0
    return box.x + (box.width - width) * share


def _image(canvas: _Canvas, identifier: str, block: _Image, box: Box) -> float:
    art = load_artwork(identifier, block.source)
    # Cropped, it is the part kept: its size and proportions are that part's.
    left, top, kept_w, kept_h = block.crop or (0.0, 0.0, 1.0, 1.0)
    natural_w = (art.width or box.width) * kept_w
    natural_h = (art.height or box.height) * kept_h
    # A width asked for is the most it takes: never wider than its place.
    scale = min(min(block.width or box.width, box.width) / natural_w, box.height / natural_h)
    width, height = natural_w * scale, natural_h * scale
    canvas.span = (_across(canvas, box, width), width)
    if block.crop is not None or block.mask is not None:
        _cropped_image(canvas, identifier, block, art, Box(_across(canvas, box, width), box.y, width, height),
                       (left, top, kept_w, kept_h))
        return height
    if art.format == "svg" and _drawable(art.markup):
        # Vectors the drawing reader draws exactly: placed as shapes and text.
        view = [float(v) for v in re.split(r"[ ,]+", ET.fromstring(art.markup).get("viewBox", "").strip()) if v]
        units = (natural_w / view[2]) if len(view) == 4 and view[2] else 1.0
        _place_svg(canvas, identifier, art.markup, _across(canvas, box, width), box.y, scale * units, width)
        _described(canvas.layer[-1], block.description)
        _whole(canvas.layer[-1], Box(_across(canvas, box, width), box.y, width, height))
        return height
    if art.format == "svg":
        import base64

        href = "data:image/svg+xml;base64," + base64.b64encode(art.markup.encode()).decode()
    else:
        href = picture_href(art)
    picture = element(
        canvas.layer, "image", id=identifier, x=_across(canvas, box, width), y=box.y,
        width=width, height=height, href=href, data__flexo__width=number(width),
    )
    _described(picture, block.description)
    _whole(picture, Box(_across(canvas, box, width), box.y, width, height))
    return height


def _cropped_image(
    canvas: _Canvas, identifier: str, block: _Image, art: Any, kept: Box, crop: tuple[float, float, float, float]
) -> None:
    """A picture cropped, as Keynote masks one: the part of it kept, a rectangle (or an oval,
    drawn round) filled with the whole picture placed so that part shows -- clipped, never
    stretched. The slide draws only what is kept, and an editor finds it the size of that
    part; the rest is there still, to be shown again (a native crop in a slide program). An
    SVG is drawn as a picture of its vectors, which a slide program crops as it does a photograph."""

    import base64

    left, top, kept_w, kept_h = crop
    whole_w, whole_h = kept.width / kept_w, kept.height / kept_h
    if art.format == "svg":
        href = "data:image/svg+xml;base64," + base64.b64encode(art.markup.encode()).decode()
    else:
        href = picture_href(art)
    # One tile, as large as the picture: drawn once, where the crop puts it.
    pattern = element(
        canvas.layer, "pattern", id=f"{identifier}.crop", patternUnits="userSpaceOnUse",
        x=kept.x - left * whole_w, y=kept.y - top * whole_h, width=whole_w, height=whole_h,
    )
    element(pattern, "image", width=whole_w, height=whole_h, href=href)
    filled = f"url(#{identifier}.crop)"
    if block.mask == "circle":
        picture = element(
            canvas.layer, "ellipse", id=identifier, cx=kept.x + kept.width / 2.0, cy=kept.y + kept.height / 2.0,
            rx=kept.width / 2.0, ry=kept.height / 2.0, fill=filled, data__flexo__width=number(kept.width),
        )
    else:
        picture = element(
            canvas.layer, "rect", id=identifier, x=kept.x, y=kept.y, width=kept.width, height=kept.height,
            fill=filled, data__flexo__width=number(kept.width),
        )
    _described(picture, block.description)
    _whole(picture, Box(kept.x - left * whole_w, kept.y - top * whole_h, whole_w, whole_h))


def _whole(picture: ET.Element, box: Box) -> None:
    """Where the whole of a picture is drawn, cropped or not (``x y width height``, in the
    units it is placed in): for an editor to show it whole as it is cropped, and to know
    its proportions."""

    picture.set("data-flexo-whole", " ".join(number(value) for value in (box.x, box.y, box.width, box.height)))


def _described(picture: ET.Element, description: str) -> None:
    """A picture's description, as a screen reader reads it (and PowerPoint's alt text)."""

    if description:
        picture.set("role", "img")
        picture.set("aria-label", description)
