"""Maths in a plot's words, set by flexo rather than by matplotlib.

matplotlib's own maths (mathtext) knows part of LaTeX -- no matrices, no ``cases``, no
``\\le`` -- and sets it in fonts of its own. A plot's words with maths in them are set
here instead, as a slide's are (``flexo.texmath``): the words in the deck's face, the
maths in the maths font that suits it, all of LaTeX that flexo reads. matplotlib still
places them: each such text is given flexo's measure for its layout (so constrained
layout, legends and titles leave room for a fraction) and draws flexo's outlines.
"""

from __future__ import annotations

import math
import types
from functools import lru_cache
from typing import Any

from flexo.markup import math_spans
from flexo.style import TypographyStyle
from flexo.texmath import GlyphItem, Typeset, typeset
from flexo.units import pt

_TEXT_ESCAPES = {"\\": r"\textbackslash ", "{": r"\{", "}": r"\}", "$": r"\$", "%": r"\%",
                 "#": r"\#", "&": r"\&", "_": r"\_"}


def formula_of(words: str) -> str:
    """Words with maths in them (``Loss $\\theta_t$ (nats)``) as one formula: the words
    as ``\\text{...}``, the maths as written."""

    pieces: list[str] = []
    at = 0
    for start, end in math_spans(words):
        if start > at:
            pieces.append(_text(words[at:start]))
        inner = words[start:end]
        for opening, closing in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
            if inner.startswith(opening) and inner.endswith(closing):
                inner = inner[len(opening) : len(inner) - len(closing)]
                break
        pieces.append("{" + inner + "}")
        at = end
    if at < len(words):
        pieces.append(_text(words[at:]))
    return "".join(pieces)


def _text(words: str) -> str:
    words = words.replace("\\$", "$")
    return r"\text{" + "".join(_TEXT_ESCAPES.get(ch, ch) for ch in words) + "}"


def set_by_flexo(figure: Any, family: str, maths: str) -> int:
    """Hand every text of ``figure`` with maths in its words to flexo; how many.

    Tick labels and an axis's offset (``1e3``) are left to matplotlib: they are made
    afresh as the figure is drawn (a log axis's as ``$\\mathdefault{10^{2}}$``), and
    ticks out of view keep the words of the last drawing.
    """

    import matplotlib.text

    every = [*figure.get_axes()]
    every += [child for axes in every for child in getattr(axes, "child_axes", [])]  # secondary axes
    ticks = {
        id(label)
        for axes in every
        for axis in getattr(axes, "_axis_map", {"x": axes.xaxis, "y": axes.yaxis}).values()
        for label in (
            *axis.get_ticklabels(), *axis.get_ticklabels(minor=True), axis.offsetText,
            *(tick.label1 for tick in (*axis.majorTicks, *axis.minorTicks)),
            *(tick.label2 for tick in (*axis.majorTicks, *axis.minorTicks)),
        )
    }
    count = 0
    for text in figure.findobj(matplotlib.text.Text):
        words = text.get_text()
        if id(text) in ticks or ("$" not in words and "\\(" not in words) or not math_spans(words):
            continue
        weight = 700 if str(text.get_fontweight()) in {"bold", "heavy", "black", "700", "800", "900"} else 400
        typography = TypographyStyle(family=family, size=pt(float(text.get_fontsize())), math_family=maths)
        lines = [typeset(formula_of(line), typography, float(text.get_fontsize()), weight=weight)
                 for line in words.split("\n")]
        text._get_layout = types.MethodType(_layout(lines), text)
        text.draw = types.MethodType(_draw(lines), text)
        text._flexo_problems = [(words, problem) for line in lines for problem in line.problems]
        count += 1
    return count


def problems(figure: Any) -> list[tuple[str, str]]:
    """What flexo could not read in a figure's maths, in words: ``(the text, what)``."""

    import matplotlib.text

    return [problem for text in figure.findobj(matplotlib.text.Text)
            for problem in getattr(text, "_flexo_problems", [])]


# -- where each line goes ------------------------------------------------------------------


def _placed(text: Any, lines: list[Typeset], scale: float) -> tuple[list[tuple[float, float]], tuple]:
    """Each line's baseline start and the text's box, in display units relative to its
    anchor, as matplotlib places a text of that shape (its alignment, rotation, and
    rotation mode)."""

    spacing = text.get_linespacing()
    # matplotlib's line spacing is a multiple of the size, or "normal" (the face's own).
    step = float(text.get_fontsize()) * (spacing if isinstance(spacing, int | float) else 1.2)
    width = max(line.width for line in lines)
    top = lines[0].height
    bottom = -((len(lines) - 1) * step + lines[-1].depth)
    align = getattr(text, "_multialignment", None) or text.get_horizontalalignment()
    starts = [
        ({"left": 0.0, "center": (width - line.width) / 2.0, "right": width - line.width}.get(align, 0.0),
         -index * step)
        for index, line in enumerate(lines)
    ]
    angle = math.radians(text.get_rotation())
    cos, sin = math.cos(angle), math.sin(angle)

    def rotate(x: float, y: float) -> tuple[float, float]:
        return x * cos - y * sin, x * sin + y * cos

    ha, va = text.get_horizontalalignment(), text.get_verticalalignment()
    corners = [rotate(x, y) for x, y in ((0.0, bottom), (width, bottom), (width, top), (0.0, top))]
    if text.get_rotation_mode() == "anchor":
        # Aligned as it is written, then turned about its anchor.
        dx = {"left": 0.0, "center": -width / 2.0, "right": -width}.get(ha, 0.0)
        dy = {"top": -top, "bottom": -bottom, "center": -(top + bottom) / 2.0,
              "center_baseline": -top / 2.0}.get(va, 0.0)
        shift = rotate(dx, dy)
    else:
        # Turned first; its turned box aligned.
        xs, ys = [x for x, _ in corners], [y for _, y in corners]
        dx = {"left": -min(xs), "center": -(min(xs) + max(xs)) / 2.0, "right": -max(xs)}.get(ha, -min(xs))
        dy = {"top": -max(ys), "bottom": -min(ys), "center": -(min(ys) + max(ys)) / 2.0,
              "center_baseline": -rotate(0.0, top / 2.0)[1]}.get(va, 0.0)
        shift = (dx, dy)
    placed = [tuple((value + offset) * scale for value, offset in zip(rotate(x, y), shift, strict=True))
              for x, y in starts]
    box = [((x + shift[0]) * scale, (y + shift[1]) * scale) for x, y in corners]
    return placed, (box, width * scale, top * scale, -bottom * scale)


def _layout(lines: list[Typeset]):
    def layout(self, renderer):
        from matplotlib.transforms import Bbox

        scale = renderer.points_to_pixels(1.0)
        placed, (box, width, top, depth) = _placed(self, lines, scale)
        xs, ys = [x for x, _ in box], [y for _, y in box]
        bbox = Bbox.from_extents(min(xs), min(ys), max(xs), max(ys))
        info = [
            ("", (line.width * scale, line.height * scale, line.depth * scale), xy)
            for line, xy in zip(lines, placed, strict=True)
        ]
        # As matplotlib's: the turned lower-left corner of the box as written, and its size.
        return bbox, info, (box[0], (width, top + depth))

    return layout


def _draw(lines: list[Typeset]):
    def draw(self, renderer):
        from matplotlib.text import Annotation

        if renderer is not None:
            self._renderer = renderer
        if not self.get_visible():
            return
        if isinstance(self, Annotation):
            # An annotation's arrow, drawn as matplotlib draws it, to the box of these words.
            if not self._check_xy(renderer):
                return
            self.update_positions(renderer)
            self.update_bbox_position_size(renderer)
            if self.arrow_patch is not None:
                if self.arrow_patch.figure is None and self.figure is not None:
                    self.arrow_patch.figure = self.figure
                self.arrow_patch.draw(renderer)
        if not self.get_text():
            return
        if self.get_bbox_patch() is not None:
            # A box behind the words (``bbox=dict(...)``), sized to flexo's measure.
            self.update_bbox_position_size(renderer)
            self.get_bbox_patch().draw(renderer)
        from matplotlib.colors import to_rgba
        from matplotlib.path import Path
        from matplotlib.transforms import Affine2D

        scale = renderer.points_to_pixels(1.0)
        placed, _ = _placed(self, lines, scale)
        x0, y0 = self.get_transform().transform(self.get_unitless_position())
        angle = self.get_rotation()
        colour = to_rgba(self.get_color(), self.get_alpha())
        renderer.open_group("text", self.get_gid())
        gc = renderer.new_gc()
        gc.set_linewidth(0)
        gc.set_url(self.get_url())
        if self.get_clip_on() and self.get_clip_box() is not None:
            gc.set_clip_rectangle(self.get_clip_box())
        for line, (dx, dy) in zip(lines, placed, strict=True):
            for ix, iy, item in line.box.items:
                fill = colour
                if item.colour:
                    try:
                        fill = to_rgba(item.colour)
                    except ValueError:
                        fill = colour
                place = Affine2D().translate(ix, iy).scale(scale).rotate_deg(angle).translate(x0 + dx, y0 + dy)
                if isinstance(item, GlyphItem):
                    outline = _outline(item.face, item.gid, item.slant)
                    if outline is None:
                        continue
                    em = item.size / item.face.upem
                    renderer.draw_path(gc, outline, Affine2D().scale(em) + place, fill)
                else:
                    rect = Path([(0, 0), (item.width, 0), (item.width, item.height), (0, item.height), (0, 0)],
                                [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY])
                    renderer.draw_path(gc, rect, place, fill)
        gc.restore()
        renderer.close_group("text")
        self.stale = False

    return draw


class _Pen:
    def __init__(self) -> None:
        from matplotlib.path import Path

        self.Path = Path
        self.vertices: list[tuple[float, float]] = []
        self.codes: list[int] = []

    def moveTo(self, point):
        self.vertices.append(point)
        self.codes.append(self.Path.MOVETO)

    def lineTo(self, point):
        self.vertices.append(point)
        self.codes.append(self.Path.LINETO)

    def curveTo(self, *points):
        for point in points:
            self.vertices.append(point)
            self.codes.append(self.Path.CURVE4)

    def qCurveTo(self, *points):
        *controls, end = points
        for index, control in enumerate(controls):
            following = controls[index + 1] if index + 1 < len(controls) else None
            target = ((control[0] + following[0]) / 2, (control[1] + following[1]) / 2) if following else end
            self.vertices += [control, target]
            self.codes += [self.Path.CURVE3, self.Path.CURVE3]

    def closePath(self):
        self.vertices.append((0.0, 0.0))
        self.codes.append(self.Path.CLOSEPOLY)

    def endPath(self):
        pass


@lru_cache(maxsize=4096)
def _outline(face: Any, gid: int, slant: bool):
    """A glyph's outline as a matplotlib path, in font units, y up (slanted by hand when
    its family has no italic)."""

    from matplotlib.path import Path

    pen = _Pen()
    face.hb.draw_glyph_with_pen(gid, pen)
    if not pen.vertices:
        return None
    shear = math.tan(math.radians(12.0)) if slant else 0.0
    vertices = [(x + y * shear, y) for x, y in pen.vertices]
    return Path(vertices, pen.codes)
