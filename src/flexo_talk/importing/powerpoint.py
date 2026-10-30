# Adapted from DeckWerk's importers/pptx/import_pptx.py, by Vincent Sitzmann, under the MIT
# License: Copyright (c) 2026 Vincent Sitzmann. Its full text is in LICENSE-DeckWerk beside this
# file. Flexo's changes are under the Apache License 2.0, as the rest of it.
"""A PowerPoint deck (``.pptx``) read into a ``Presentation``, from its file alone.

A ``.pptx`` is a zip of OOXML parts: DrawingML for the shapes, PresentationML for the slides,
their layouts and masters. Each slide's shapes are read with what they inherit -- a
placeholder's place, words and look from its layout and master, a shape's paint from the
theme's styles, a colour from the theme's scheme through the master's colour map and its
modifiers -- and kept as they are drawn: words with their lists, levels, bold, italic,
scripts, colours and links; pictures with their crops; shapes with their geometry and paint;
lines and connectors with their arrowheads and what they are glued to; tables; equations
(Office Math, read back as TeX: ``omml_tex``); notes, skipped slides, the slide's size and
the theme's colours and faces. Nothing is ever refused: what cannot be read becomes an
``Unknown`` where it was (a chart, SmartArt, a movie, an object of another program), with a
picture of itself where the deck has one.
"""

from __future__ import annotations

import contextlib
import copy
import math
import posixpath
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from flexo_talk.importing import ole, presets
from flexo_talk.importing.model import (
    Box,
    Cell,
    Colour,
    Connector,
    Element,
    Frame,
    Gradient,
    Group,
    Media,
    Paragraph,
    Picture,
    Presentation,
    Run,
    Shape,
    Slide,
    Stroke,
    Table,
    TextBox,
    Theme,
    Unknown,
)
from flexo_talk.importing.omml_tex import omml_tex
from flexo_talk.importing.reading import faces, title_look
from flexo_talk.importing.report import Progress, Report, quiet

EMU = 12700.0
"""EMUs in a point."""

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "dsp": "http://schemas.microsoft.com/office/drawing/2008/diagram",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
}
R_ID = f"{{{NS['r']}}}id"
R_EMBED = f"{{{NS['r']}}}embed"
R_LINK = f"{{{NS['r']}}}link"
UNDERSTOOD = {"a14", "p14", "a16", "asvg", "p15", "a15"}
"""Prefixes of what a part's ``mc:Choice`` may need for it to be read rather than its
fallback (Office Math is ``a14``)."""

REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
LARGEST_PART = 256 * 1024 * 1024
"""More bytes than any part of a deck has once unpacked: one larger is not read (a zip bomb)."""


def q(name: str) -> str:
    prefix, _, local = name.partition(":")
    return f"{{{NS[prefix]}}}{local}"


def child(element: etree._Element | None, *path: str) -> etree._Element | None:
    current = element
    for step in path:
        if current is None:
            return None
        current = current.find(q(step))
    return current


def local(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def number(element: etree._Element | None, name: str, default: float | None = None) -> float | None:
    if element is None:
        return default
    raw = element.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def flag(element: etree._Element | None, name: str, default: bool = False) -> bool:
    if element is None or element.get(name) is None:
        return default
    return element.get(name) in ("1", "true", "on")


_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=True, huge_tree=True)


# -- the package -------------------------------------------------------------------------------


class Package:
    """The deck's zip, its parts read once and its relationships followed."""

    def __init__(self, path: Path) -> None:
        self.zip = zipfile.ZipFile(path)
        self.names = {info.filename: info for info in self.zip.infolist()}
        self._xml: dict[str, etree._Element] = {}
        self._rels: dict[str, dict[str, tuple[str, str, bool]]] = {}

    def close(self) -> None:
        self.zip.close()

    def has(self, name: str) -> bool:
        return name in self.names

    def read(self, name: str) -> bytes:
        info = self.names.get(name)
        if info is None:
            raise KeyError(name)
        if info.file_size > LARGEST_PART:
            raise ValueError(f"{name} is too large to read")
        return self.zip.read(info)

    def xml(self, name: str) -> etree._Element:
        found = self._xml.get(name)
        if found is None:
            found = etree.fromstring(self.read(name), _PARSER)
            self._xml[name] = found
        return found

    def rels(self, part: str) -> dict[str, tuple[str, str, bool]]:
        """``id -> (target, type, external)`` for a part's relationships."""

        found = self._rels.get(part)
        if found is not None:
            return found
        folder, base = posixpath.split(part)
        name = posixpath.join(folder, "_rels", base + ".rels")
        table: dict[str, tuple[str, str, bool]] = {}
        if self.has(name):
            with contextlib.suppress(etree.XMLSyntaxError, ValueError):
                for rel in etree.fromstring(self.read(name), _PARSER):
                    ident, target = rel.get("Id"), rel.get("Target")
                    if not ident or not target:
                        continue
                    external = rel.get("TargetMode") == "External"
                    if not external:
                        target = target[1:] if target.startswith("/") else posixpath.normpath(
                            posixpath.join(folder, target))
                    table[ident] = (target, rel.get("Type", ""), external)
        self._rels[part] = table
        return table

    def related(self, part: str, kind: str) -> list[str]:
        return [target for target, of, external in self.rels(part).values()
                if of.endswith("/" + kind) and not external and self.has(target)]

    def target(self, part: str, ident: str | None) -> str | None:
        entry = self.rels(part).get(ident or "")
        if entry is None or entry[2] or not self.has(entry[0]):
            return None
        return entry[0]


# -- colour ------------------------------------------------------------------------------------


PRESET_COLOURS = {
    "black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000", "blue": "0000FF",
    "yellow": "FFFF00", "gray": "808080", "grey": "808080", "silver": "C0C0C0", "orange": "FFA500",
    "purple": "800080", "navy": "000080", "teal": "008080", "maroon": "800000", "lime": "00FF00",
    "aqua": "00FFFF", "cyan": "00FFFF", "magenta": "FF00FF", "fuchsia": "FF00FF", "olive": "808000",
    "darkGray": "A9A9A9", "darkGrey": "A9A9A9", "lightGray": "D3D3D3", "lightGrey": "D3D3D3",
    "dimGray": "696969", "darkBlue": "00008B", "darkRed": "8B0000", "darkGreen": "006400", "gold": "FFD700",
    "brown": "A52A2A", "pink": "FFC0CB", "violet": "EE82EE",
}


def _rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    r, g, b = r / 255, g / 255, b / 255
    high, low = max(r, g, b), min(r, g, b)
    lum = (high + low) / 2
    if high == low:
        return 0.0, 0.0, lum
    delta = high - low
    sat = delta / (2 - high - low) if lum > 0.5 else delta / (high + low)
    if high == r:
        hue = (g - b) / delta + (6 if g < b else 0)
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue / 6, sat, lum


def _hsl_to_rgb(h: float, s: float, lum: float) -> tuple[float, float, float]:
    if s == 0:
        return lum * 255, lum * 255, lum * 255

    def channel(p: float, qq: float, t: float) -> float:
        t %= 1
        if t < 1 / 6:
            return p + (qq - p) * 6 * t
        if t < 1 / 2:
            return qq
        if t < 2 / 3:
            return p + (qq - p) * (2 / 3 - t) * 6
        return p

    qq = lum * (1 + s) if lum < 0.5 else lum + s - lum * s
    p = 2 * lum - qq
    return channel(p, qq, h + 1 / 3) * 255, channel(p, qq, h) * 255, channel(p, qq, h - 1 / 3) * 255


def _linear(channel: float) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _srgb(linear: float) -> float:
    linear = min(max(linear, 0.0), 1.0)
    value = linear * 12.92 if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055
    return value * 255


def _byte(value: float) -> int:
    return max(0, min(255, round(value)))


@dataclass
class Colours:
    """What a scheme colour's name is on a slide: the theme's colours, the master's map from
    ``bg1``/``tx1`` to them, and what a style's ``phClr`` stands for."""

    theme: dict[str, str]
    mapping: dict[str, str]
    placeholder: Colour | None = None

    def with_placeholder(self, colour: Colour | None) -> Colours:
        return Colours(self.theme, self.mapping, colour)


def colour_of(element: etree._Element | None, colours: Colours) -> Colour | None:
    """A DrawingML colour choice as a ``Colour``, its modifiers applied in order."""

    if element is None:
        return None
    kind = local(element)
    hex6: str | None = None
    alpha = 1.0
    scheme: str | None = None
    if kind == "srgbClr":
        hex6 = (element.get("val") or "").strip()
    elif kind == "schemeClr":
        name = element.get("val") or ""
        if name == "phClr":
            if colours.placeholder is None:
                return None
            hex6, alpha, scheme = colours.placeholder.hex.lstrip("#"), colours.placeholder.alpha, \
                colours.placeholder.scheme
        else:
            mapped = colours.mapping.get(name, name)
            hex6 = colours.theme.get(mapped) or colours.theme.get(name)
            scheme = name if name.startswith(("accent", "tx", "bg", "dk", "lt")) else None
            if scheme in ("dk1", "lt1", "dk2", "lt2"):
                # (Written as a colour itself, not by the role it plays: a role when it is mapped.)
                scheme = {value: key for key, value in colours.mapping.items()
                          if key in ("tx1", "bg1", "tx2", "bg2")}.get(name, name)
    elif kind == "sysClr":
        hex6 = element.get("lastClr") or ("000000" if element.get("val") == "windowText" else "FFFFFF")
    elif kind == "prstClr":
        hex6 = PRESET_COLOURS.get(element.get("val") or "")
    elif kind == "scrgbClr":
        try:
            hex6 = "".join(f"{_byte(float(element.get(c, '0')) / 100000 * 255):02X}" for c in "rgb")
        except ValueError:
            return None
    elif kind == "hslClr":
        try:
            r, g, b = _hsl_to_rgb(float(element.get("hue", "0")) / 21600000, float(element.get("sat", "0")) / 100000,
                                  float(element.get("lum", "0")) / 100000)
            hex6 = f"{_byte(r):02X}{_byte(g):02X}{_byte(b):02X}"
        except ValueError:
            return None
    else:
        return None
    if not hex6 or len(hex6) < 6:
        return None
    try:
        r, g, b = (float(int(hex6[i : i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return None
    modified = False
    for modifier in element:
        name = local(modifier)
        raw = modifier.get("val")
        try:
            value = int(raw) / 100000 if raw is not None else None
        except ValueError:
            value = None
        if name == "alpha" and value is not None:
            alpha = max(0.0, min(1.0, value))
            continue
        if value is None and name not in ("comp", "inv", "gray"):
            continue
        modified = True
        if name == "tint":
            # (In linear light, as PowerPoint tints: a 75% tint of black is a mid grey.)
            r, g, b = (_srgb(1 - (1 - _linear(c)) * value) for c in (r, g, b))
        elif name == "shade":
            r, g, b = (_srgb(_linear(c) * value) for c in (r, g, b))
        elif name in ("lumMod", "lumOff", "satMod", "satOff", "hueMod", "hueOff"):
            h, s, lum = _rgb_to_hsl(r, g, b)
            if name == "lumMod":
                lum *= value
            elif name == "lumOff":
                lum += value
            elif name == "satMod":
                s *= value
            elif name == "satOff":
                s += value
            elif name == "hueMod":
                h = (h * value) % 1
            elif name == "hueOff":
                h = (h + int(raw or 0) / 21600000) % 1
            r, g, b = _hsl_to_rgb(h, max(0.0, min(1.0, s)), max(0.0, min(1.0, lum)))
        elif name == "comp":
            h, s, lum = _rgb_to_hsl(r, g, b)
            r, g, b = _hsl_to_rgb((h + 0.5) % 1, s, lum)
        elif name == "inv":
            r, g, b = 255 - r, 255 - g, 255 - b
        elif name == "gray":
            grey = 0.299 * r + 0.587 * g + 0.114 * b
            r = g = b = grey
        else:
            modified = False
    return Colour(f"#{_byte(r):02x}{_byte(g):02x}{_byte(b):02x}", alpha, None if modified else scheme)


def first_colour(element: etree._Element | None, colours: Colours) -> Colour | None:
    if element is None:
        return None
    for candidate in element:
        found = colour_of(candidate, colours)
        if found is not None:
            return found
    return None


# -- paint -------------------------------------------------------------------------------------


FILLS = ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")
_NONE = object()
"""A fill said to be none (as against one not said, which is inherited)."""


def fill_of(parent: etree._Element | None, colours: Colours, part: str, package: Package) -> object:
    """The fill said on ``parent``: a Colour, a Gradient, a Media, ``_NONE``, or ``None``
    (not said: inherited)."""

    if parent is None:
        return None
    for element in parent:
        name = local(element)
        if name not in FILLS:
            continue
        if name == "noFill":
            return _NONE
        if name == "solidFill":
            return first_colour(element, colours) or _NONE
        if name == "gradFill":
            stops = []
            for stop in element.iterfind(f"{q('a:gsLst')}/{q('a:gs')}"):
                found = first_colour(stop, colours)
                if found is not None:
                    stops.append((min(max((number(stop, "pos", 0) or 0) / 100000, 0.0), 1.0), found))
            stops.sort(key=lambda pair: pair[0])
            if not stops:
                return _NONE
            linear = child(element, "a:lin")
            angle = (number(linear, "ang", 0) or 0) / 60000 if linear is not None else 90.0
            return Gradient(stops, angle, radial=child(element, "a:path") is not None)
        if name == "blipFill":
            blip = child(element, "a:blip")
            target = package.target(part, blip.get(R_EMBED) if blip is not None else None)
            if target is None:
                return _NONE
            with contextlib.suppress(KeyError, ValueError):
                return Media(posixpath.basename(target), package.read(target))
            return _NONE
        if name == "pattFill":
            return first_colour(child(element, "a:fgClr"), colours) or first_colour(child(element, "a:bgClr"),
                                                                                  colours) or _NONE
        if name == "grpFill":
            return None
    return None


HEADS = {"triangle": "triangle", "stealth": "stealth", "arrow": "open", "oval": "dot", "diamond": "diamond",
         "none": "none"}
HEAD_SIZES = {"sm": 0.7, "med": 1.0, "lg": 1.4}


@dataclass
class _Line:
    width: float | None = None
    fill: object = None
    head: str | None = None
    tail: str | None = None
    head_size: float | None = None
    dash: str | None = None
    cap: str | None = None
    join: str | None = None

    def under(self, other: _Line) -> None:
        for name in ("width", "fill", "head", "tail", "head_size", "dash", "cap", "join"):
            if getattr(self, name) is None:
                setattr(self, name, getattr(other, name))


def line_of(element: etree._Element | None, colours: Colours, part: str, package: Package) -> _Line | None:
    if element is None:
        return None
    line = _Line(width=(number(element, "w") / EMU) if element.get("w") is not None else None)
    line.fill = fill_of(element, colours, part, package)
    sizes = []
    for end, name in ((child(element, "a:headEnd"), "head"), (child(element, "a:tailEnd"), "tail")):
        if end is not None:
            setattr(line, name, HEADS.get(end.get("type") or "none", "triangle"))
            sizes += [HEAD_SIZES.get(end.get("w") or "med", 1.0), HEAD_SIZES.get(end.get("len") or "med", 1.0)]
    if sizes:
        line.head_size = sum(sizes) / len(sizes)
    dash = child(element, "a:prstDash")
    if dash is not None:
        value = dash.get("val") or "solid"
        line.dash = "solid" if value == "solid" else "dotted" if value in ("dot", "sysDot") else "dashed"
    elif child(element, "a:custDash") is not None:
        line.dash = "dashed"
    cap = element.get("cap")
    if cap:
        line.cap = {"rnd": "round", "sq": "square", "flat": "butt"}.get(cap)
    for name, join in (("round", "round"), ("bevel", "bevel"), ("miter", "miter")):
        if child(element, f"a:{name}") is not None:
            line.join = join
    return line


# -- the theme ---------------------------------------------------------------------------------


@dataclass
class _Theme:
    colours: dict[str, str]
    major: str
    minor: str
    fills: list[etree._Element] = field(default_factory=list)
    lines: list[etree._Element] = field(default_factory=list)
    backgrounds: list[etree._Element] = field(default_factory=list)

    @staticmethod
    def default() -> _Theme:
        return _Theme(
            {"dk1": "000000", "lt1": "FFFFFF", "dk2": "44546A", "lt2": "E7E6E6", "accent1": "4472C4",
             "accent2": "ED7D31", "accent3": "A5A5A5", "accent4": "FFC000", "accent5": "5B9BD5",
             "accent6": "70AD47", "hlink": "0563C1", "folHlink": "954F72"},
            "Calibri Light", "Calibri")


def theme_of(package: Package, part: str | None) -> _Theme:
    theme = _Theme.default()
    if part is None or not package.has(part):
        return theme
    root = package.xml(part)
    scheme = child(root, "a:themeElements", "a:clrScheme")
    for entry in scheme if scheme is not None else []:
        found = first_colour(entry, Colours(theme.colours, {}))
        if found is not None:
            theme.colours[local(entry)] = found.hex.lstrip("#").upper()
    fonts = child(root, "a:themeElements", "a:fontScheme")
    major, minor = child(fonts, "a:majorFont", "a:latin"), child(fonts, "a:minorFont", "a:latin")
    if major is not None and major.get("typeface"):
        theme.major = major.get("typeface") or theme.major
    if minor is not None and minor.get("typeface"):
        theme.minor = minor.get("typeface") or theme.minor
    styles = child(root, "a:themeElements", "a:fmtScheme")
    theme.fills = list(child(styles, "a:fillStyleLst") if child(styles, "a:fillStyleLst") is not None else [])
    theme.lines = list(child(styles, "a:lnStyleLst") if child(styles, "a:lnStyleLst") is not None else [])
    theme.backgrounds = list(child(styles, "a:bgFillStyleLst") if child(styles, "a:bgFillStyleLst") is not None
                             else [])
    return theme


MAP = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2", **{f"accent{n}": f"accent{n}" for n in range(1, 7)},
       "hlink": "hlink", "folHlink": "folHlink"}


# -- words ---------------------------------------------------------------------------------------


@dataclass
class _RunLook:
    size: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike: bool | None = None
    font: str | None = None
    colour: Colour | None = None
    baseline: float | None = None
    caps: bool | None = None

    def under(self, other: _RunLook) -> None:
        for name in ("size", "bold", "italic", "underline", "strike", "font", "colour", "baseline", "caps"):
            if getattr(self, name) is None:
                setattr(self, name, getattr(other, name))


def run_look(properties: etree._Element | None, colours: Colours) -> _RunLook:
    look = _RunLook()
    if properties is None:
        return look
    size = number(properties, "sz")
    if size:
        look.size = size / 100
    if properties.get("b") is not None:
        look.bold = flag(properties, "b")
    if properties.get("i") is not None:
        look.italic = flag(properties, "i")
    if properties.get("u") is not None:
        look.underline = properties.get("u") != "none"
    if properties.get("strike") is not None:
        look.strike = properties.get("strike") != "noStrike"
    if properties.get("cap") is not None:
        look.caps = properties.get("cap") == "all"
    baseline = number(properties, "baseline")
    if baseline is not None:
        look.baseline = baseline / 100000
    latin = child(properties, "a:latin")
    if latin is not None and latin.get("typeface"):
        look.font = latin.get("typeface")
    for element in properties:
        if local(element) == "solidFill":
            look.colour = first_colour(element, colours)
        elif local(element) == "gradFill":
            stops = list(element.iterfind(f"{q('a:gsLst')}/{q('a:gs')}"))
            if stops:
                look.colour = first_colour(stops[len(stops) // 2], colours)
    return look


@dataclass
class _ParagraphLook:
    align: str | None = None
    bullet: str | None = None
    indent: float | None = None
    margin: float | None = None
    line_spacing: float | None = None
    line_points: float | None = None
    before: float | None = None
    after: float | None = None
    before_share: float | None = None
    after_share: float | None = None
    bullet_colour: Colour | None = None
    run: _RunLook = field(default_factory=_RunLook)

    def under(self, other: _ParagraphLook) -> None:
        for name in ("align", "bullet", "indent", "margin", "line_spacing", "line_points", "before", "after",
                     "before_share", "after_share", "bullet_colour"):
            if getattr(self, name) is None:
                setattr(self, name, getattr(other, name))
        self.run.under(other.run)


ALIGNS = {"l": "start", "ctr": "middle", "r": "end", "just": "justify", "justLow": "justify", "dist": "justify",
          "thaiDist": "justify"}


def paragraph_look(properties: etree._Element | None, colours: Colours) -> _ParagraphLook:
    look = _ParagraphLook()
    if properties is None:
        return look
    if properties.get("algn"):
        look.align = ALIGNS.get(properties.get("algn") or "")
    if properties.get("marL") is not None:
        look.margin = (number(properties, "marL") or 0) / EMU
    if properties.get("indent") is not None:
        look.indent = (number(properties, "indent") or 0) / EMU
    for element in properties:
        name = local(element)
        if name == "buNone":
            look.bullet = "none"
        elif name in ("buChar", "buBlip"):
            look.bullet = "bullet"
        elif name == "buAutoNum":
            look.bullet = "number"
        elif name == "buClr":
            look.bullet_colour = first_colour(element, colours)
        elif name == "lnSpc":
            percent, points = child(element, "a:spcPct"), child(element, "a:spcPts")
            if percent is not None:
                look.line_spacing = (number(percent, "val", 100000) or 100000) / 100000
            elif points is not None:
                look.line_points = (number(points, "val", 0) or 0) / 100
        elif name in ("spcBef", "spcAft"):
            percent, points = child(element, "a:spcPct"), child(element, "a:spcPts")
            prefix = "before" if name == "spcBef" else "after"
            if points is not None:
                setattr(look, prefix, (number(points, "val", 0) or 0) / 100)
                setattr(look, f"{prefix}_share", 0.0)
            elif percent is not None:
                setattr(look, f"{prefix}_share", (number(percent, "val", 0) or 0) / 100000)
                setattr(look, prefix, 0.0)
        elif name == "defRPr":
            look.run = run_look(element, colours)
    return look


class Inheritance:
    """The list styles a paragraph's look is found through, nearest first: its shape's own,
    its layout's placeholder's, its master's placeholder's, the master's text styles (or the
    deck's default, for words in no placeholder)."""

    def __init__(self, sources: list[etree._Element | None], colours: Colours) -> None:
        self.sources = [source for source in sources if source is not None]
        self.colours = colours
        self._found: dict[tuple[int, int], _ParagraphLook] = {}

    def level(self, index: int, level: int) -> _ParagraphLook:
        key = (index, level)
        found = self._found.get(key)
        if found is None:
            source = self.sources[index]
            properties = child(source, f"a:lvl{level + 1}pPr")
            if properties is None and level > 0:
                properties = child(source, "a:lvl1pPr")
            if properties is None:
                properties = child(source, "a:defPPr")
            found = paragraph_look(properties, self.colours)
            self._found[key] = found
        return found

    def resolved(self, own: _ParagraphLook, level: int) -> _ParagraphLook:
        out = _ParagraphLook()
        out.under(own)
        for index in range(len(self.sources)):
            out.under(self.level(index, level))
        return out


# -- geometry ----------------------------------------------------------------------------------


@dataclass
class _Turn:
    """How a group maps its members' places into its parent's."""

    off: tuple[float, float]
    child_off: tuple[float, float]
    scale: tuple[float, float]
    rotate: float
    flip_h: bool
    flip_v: bool
    ext: tuple[float, float]

    def apply(self, box: Box) -> Box:
        x = self.off[0] + (box.x - self.child_off[0]) * self.scale[0]
        y = self.off[1] + (box.y - self.child_off[1]) * self.scale[1]
        w, h = box.w * self.scale[0], box.h * self.scale[1]
        rotate, flip_h, flip_v = box.rotate, box.flip_h, box.flip_v
        if self.flip_h:
            x = self.off[0] + (self.off[0] + self.ext[0] - (x + w))
            rotate, flip_h = -rotate, not flip_h
        if self.flip_v:
            y = self.off[1] + (self.off[1] + self.ext[1] - (y + h))
            rotate, flip_v = -rotate, not flip_v
        if abs(self.rotate) > 0.001:
            gx, gy = self.off[0] + self.ext[0] / 2, self.off[1] + self.ext[1] / 2
            cx, cy = x + w / 2, y + h / 2
            theta = math.radians(self.rotate)
            dx, dy = cx - gx, cy - gy
            cx, cy = gx + dx * math.cos(theta) - dy * math.sin(theta), gy + dx * math.sin(theta) + dy * math.cos(theta)
            x, y = cx - w / 2, cy - h / 2
            rotate += self.rotate
        return Box(x, y, w, h, rotate % 360, flip_h, flip_v)

    def point(self, x: float, y: float) -> tuple[float, float]:
        moved = self.apply(Box(x, y, 0.0, 0.0))
        return moved.x, moved.y


def box_of(xfrm: etree._Element | None) -> Box | None:
    if xfrm is None:
        return None
    off, ext = child(xfrm, "a:off"), child(xfrm, "a:ext")
    if off is None or ext is None:
        return None
    return Box((number(off, "x", 0) or 0) / EMU, (number(off, "y", 0) or 0) / EMU, (number(ext, "cx", 0) or 0) / EMU,
               (number(ext, "cy", 0) or 0) / EMU, ((number(xfrm, "rot", 0) or 0) / 60000) % 360,
               flag(xfrm, "flipH"), flag(xfrm, "flipV"))


def in_box(box: Box, u: float, v: float) -> tuple[float, float]:
    """A point given in a box's own units (0 to its width across), on the slide: mirrored and
    turned as the box is."""

    if box.flip_h:
        u = box.w - u
    if box.flip_v:
        v = box.h - v
    theta = math.radians(box.rotate)
    dx, dy = u - box.w / 2, v - box.h / 2
    cx, cy = box.centre
    return cx + dx * math.cos(theta) - dy * math.sin(theta), cy + dx * math.sin(theta) + dy * math.cos(theta)


# -- the reader --------------------------------------------------------------------------------


@dataclass
class _Context:
    """What one slide's shapes are read against."""

    part: str
    layout: str | None
    master: str | None
    theme: _Theme
    colours: Colours
    number: int


ROLES = {"title": "title", "ctrTitle": "title", "subTitle": "subtitle", "body": "body", "obj": "body",
         "dt": "date", "ftr": "footer", "sldNum": "number", "pic": "body", "tbl": "body", "chart": "body",
         "media": "body", "clipArt": "body", "dgm": "body"}
KINDS = {
    "http://schemas.openxmlformats.org/drawingml/2006/chart": "Chart",
    "http://schemas.microsoft.com/office/drawing/2014/chartex": "Chart",
    "http://schemas.openxmlformats.org/drawingml/2006/diagram": "SmartArt",
    "http://schemas.openxmlformats.org/presentationml/2006/ole": "Embedded object",
}


class Reader:
    def __init__(self, package: Package, report: Report, progress: Progress = quiet) -> None:
        self.package = package
        self.report = report
        self.progress = progress
        self._themes: dict[str, _Theme] = {}
        self._decorations: dict[tuple[str | None, str | None], list[Element]] = {}
        self.default_text: etree._Element | None = None
        self.unknown: set[str] = set()
        """PowerPoint's shapes Flexo has no outline for, drawn as their boxes."""
        self.bullets: Counter = Counter()
        """The colours its lists' bullets are set in, by how often."""

    # -- the deck --

    def presentation(self, name: str) -> Presentation:
        package = self.package
        main = next((target for target, kind, external in package.rels("").values()
                     if kind.endswith("/officeDocument") and not external), "ppt/presentation.xml")
        if not package.has(main):
            raise ValueError("This file holds no PowerPoint presentation.")
        root = package.xml(main)
        size = child(root, "p:sldSz")
        width = (number(size, "cx", 12192000) or 12192000) / EMU
        height = (number(size, "cy", 6858000) or 6858000) / EMU
        self.default_text = child(root, "p:defaultTextStyle")
        rels = package.rels(main)
        parts = []
        for slide in root.iterfind(f"{q('p:sldIdLst')}/{q('p:sldId')}"):
            entry = rels.get(slide.get(R_ID) or "")
            if entry and package.has(entry[0]):
                parts.append(entry[0])
        out = Presentation(width, height, name=name)
        masters = package.related(main, "slideMaster")
        master = masters[0] if masters else None
        theme = self.theme_for(master)
        out.theme = Theme({key: f"#{value.lower()}" for key, value in theme.colours.items()}, theme.major, theme.minor)
        out.theme.dark = self._dark(master, theme)
        for index, part in enumerate(parts):
            self.progress(0.1 + 0.5 * index / max(len(parts), 1), f"Reading slide {index + 1} of {len(parts)}")
            try:
                out.slides.append(self.slide(part, index + 1))
            except Exception as error:  # a slide that cannot be read is kept, empty, and said
                self.report.placeholder(index + 1, "Slide", f"could not be read ({error})")
                out.slides.append(Slide(index + 1, layout="blank"))
        self._title_look(out, master, theme)
        faces(out)
        if self.bullets:
            out.accent = self.bullets.most_common(1)[0][0]
        if self.unknown:
            named = ", ".join(sorted(self.unknown))
            self.report.note(f"PowerPoint\u2019s {named} shape{'s are' if len(self.unknown) > 1 else ' is'} drawn as "
                             f"{'rectangles' if len(self.unknown) > 1 else 'a rectangle'}.")
        return out

    def _dark(self, master: str | None, theme: _Theme) -> bool:
        """Whether the master's slides are dark: its background, or its map of tx1 to lt1."""

        if master is None:
            return False
        mapping = self._mapping(master)
        if mapping.get("bg1") == "dk1":
            return True
        background = self.background(_Context(master, None, master, theme, Colours(theme.colours, mapping), 0), master)
        if isinstance(background, Colour):
            value = background.hex.lstrip("#")
            r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4
        return False

    def _mapping(self, master: str) -> dict[str, str]:
        mapping = dict(MAP)
        found = child(self.package.xml(master), "p:clrMap")
        if found is not None:
            mapping.update(found.attrib)
        return mapping

    def _title_look(self, out: Presentation, master: str | None, theme: _Theme) -> None:
        """How the deck's titles are set: as most of its slides' titles are, else as its
        master's title placeholder says."""

        look = title_look(out)
        if not look and master is not None:
            styles = child(self.package.xml(master), "p:txStyles", "p:titleStyle", "a:lvl1pPr")
            colours = Colours(theme.colours, self._mapping(master))
            found = paragraph_look(styles, colours)
            if found.run.size:
                look["size"] = found.run.size
            if found.run.bold is not None:
                look["bold"] = found.run.bold
            look["align"] = found.align or "start"
        out.title_style = look

    def theme_for(self, master: str | None) -> _Theme:
        if master is None:
            return _Theme.default()
        found = self._themes.get(master)
        if found is None:
            themes = self.package.related(master, "theme")
            found = theme_of(self.package, themes[0] if themes else None)
            self._themes[master] = found
        return found

    def context(self, part: str, number: int) -> _Context:
        layouts = self.package.related(part, "slideLayout")
        layout = layouts[0] if layouts else None
        masters = self.package.related(layout, "slideMaster") if layout else []
        master = masters[0] if masters else None
        theme = self.theme_for(master)
        mapping = self._mapping(master) if master else dict(MAP)
        for over in (layout, part):
            if over is None:
                continue
            found = child(self.package.xml(over), "p:clrMapOvr", "a:overrideClrMapping")
            if found is not None:
                mapping.update(found.attrib)
        return _Context(part, layout, master, theme, Colours(theme.colours, mapping), number)

    # -- a slide --

    def slide(self, part: str, number: int) -> Slide:
        context = self.context(part, number)
        root = self.package.xml(part)
        slide = Slide(number)
        layout_root = self.package.xml(context.layout) if context.layout else None
        kind = layout_root.get("type") if layout_root is not None else None
        tree = child(root, "p:cSld", "p:spTree")
        slide.elements = self.tree(tree, context, part, [])
        has_centred = any(isinstance(element, TextBox) and element.name == "\x00ctrTitle" for element in
                          slide.elements)
        if kind == "title" or has_centred:
            slide.layout = "title"
        for element in slide.elements:
            if element.name == "\x00ctrTitle":
                element.name = "Title"
        background = self.background(context, part)
        slide.background = background
        if flag(root, "showMasterSp", True):
            slide.decorations = self.decorations(context, layout_root)
        slide.notes = self.notes(part)
        slide.skip = root.get("show") in ("0", "false")
        name = child(root, "p:cSld")
        slide.name = (name.get("name") if name is not None else "") or ""
        return slide

    def decorations(self, context: _Context, layout_root: etree._Element | None) -> list[Element]:
        """What the slide's master and layout draw on it that is no placeholder: a logo, a band."""

        key = (context.layout, context.master)
        found = self._decorations.get(key)
        if found is not None:
            return found
        found = []
        with contextlib.suppress(Exception):
            if context.master and flag(layout_root, "showMasterSp", True):
                tree = child(self.package.xml(context.master), "p:cSld", "p:spTree")
                found += self.tree(tree, context, context.master, [], placeholders=False)
            if context.layout:
                tree = child(layout_root, "p:cSld", "p:spTree")
                found += self.tree(tree, context, context.layout, [], placeholders=False)
        self._decorations[key] = found
        return found

    def background(self, context: _Context, part: str) -> object:
        for source in (part, context.layout, context.master):
            if source is None:
                continue
            found = child(self.package.xml(source), "p:cSld", "p:bg")
            if found is None:
                continue
            fill = fill_of(child(found, "p:bgPr"), context.colours, source, self.package)
            reference = child(found, "p:bgRef")
            if fill is None and reference is not None:
                index = int(number(reference, "idx", 0) or 0)
                placeholder = first_colour(reference, context.colours)
                styles = context.theme.backgrounds if index >= 1001 else context.theme.fills
                position = index - 1001 if index >= 1001 else index - 1
                if 0 <= position < len(styles):
                    holder = etree.Element("holder")
                    holder.append(copy.deepcopy(styles[position]))
                    fill = fill_of(holder, context.colours.with_placeholder(placeholder), source, self.package)
                elif placeholder is not None:
                    fill = placeholder
            if fill is None or fill is _NONE:
                continue
            return fill
        return None

    def notes(self, part: str) -> str:
        found = self.package.related(part, "notesSlide")
        if not found:
            return ""
        with contextlib.suppress(Exception):
            tree = child(self.package.xml(found[0]), "p:cSld", "p:spTree")
            for shape in self.shapes(tree):
                holder = self.placeholder_of(shape)
                if holder is not None and holder.get("type") == "body":
                    body = child(shape, "p:txBody")
                    lines = []
                    for paragraph in body.iterfind(q("a:p")) if body is not None else []:
                        words = "".join(
                            (node.findtext(q("a:t")) or "") if local(node) in ("r", "fld") else
                            "\n" if local(node) == "br" else "" for node in paragraph)
                        lines.append(words)
                    return "\n".join(lines).strip()
        return ""

    # -- shape trees --

    def shapes(self, tree: etree._Element | None) -> list[etree._Element]:
        """A tree's drawn members, a part's newer encoding (``mc:Choice``) read where it is one
        Flexo understands (Office Math), else its fallback."""

        if tree is None:
            return []
        out = []
        for node in tree:
            name = local(node)
            if name in ("sp", "pic", "grpSp", "cxnSp", "graphicFrame", "contentPart"):
                out.append(node)
            elif name == "AlternateContent":
                out.extend(self.shapes(alternative(node)))
        return out

    def tree(self, tree: etree._Element | None, context: _Context, part: str, turns: list[_Turn], *,
             placeholders: bool = True) -> list[Element]:
        elements: list[Element] = []
        for node in self.shapes(tree):
            holder = self.placeholder_of(node)
            if not placeholders and holder is not None:
                continue
            try:
                elements.extend(self.node(node, context, part, turns))
            except Exception as error:
                box = self.box(node, context, turns) or Box(0, 0, 100, 60)
                self.report.note(f"Slide {context.number}: a {local(node)} could not be read ({error}).")
                elements.append(Unknown(box, kind="Object", why="could not be read"))
        return elements

    @staticmethod
    def placeholder_of(node: etree._Element) -> etree._Element | None:
        for path in (("p:nvSpPr", "p:nvPr", "p:ph"), ("p:nvPicPr", "p:nvPr", "p:ph"),
                     ("p:nvGraphicFramePr", "p:nvPr", "p:ph"), ("p:nvCxnSpPr", "p:nvPr", "p:ph")):
            found = child(node, *path)
            if found is not None:
                return found
        return None

    def find_placeholder(self, part: str | None, holder: etree._Element,
                         by_type: bool = False) -> etree._Element | None:
        """The layout's (or master's) shape a slide's placeholder takes what it does not say from."""

        if part is None:
            return None
        kind = holder.get("type") or "body"
        index = holder.get("idx")
        tree = child(self.package.xml(part), "p:cSld", "p:spTree")
        candidates = [(node, self.placeholder_of(node)) for node in self.shapes(tree)]
        candidates = [(node, found) for node, found in candidates if found is not None]
        titles = {"title", "ctrTitle"}
        bodies = {"body", "subTitle", "obj", "tbl", "chart", "dgm", "media", "clipArt", "pic"}
        if index is not None and not by_type:
            for node, found in candidates:
                if found.get("idx") == index:
                    return node
        for node, found in candidates:
            other = found.get("type") or "body"
            if other == kind or (kind in titles and other in titles) or (kind in bodies and other in bodies
                                                                             and kind == "body"):
                return node
        for node, found in candidates:
            other = found.get("type") or "body"
            if (kind in titles and other in titles) or (kind in bodies and other in bodies):
                return node
        return None

    def chain(self, node: etree._Element, context: _Context) -> list[etree._Element]:
        """The slide placeholder's layout placeholder, then its master's, where they are."""

        holder = self.placeholder_of(node)
        if holder is None:
            return []
        out = []
        layout_node = self.find_placeholder(context.layout, holder)
        if layout_node is not None:
            out.append(layout_node)
        master_holder = self.placeholder_of(layout_node) if layout_node is not None else holder
        master_node = self.find_placeholder(context.master, master_holder if master_holder is not None else holder,
                                            by_type=True)
        if master_node is not None:
            out.append(master_node)
        return out

    def box(self, node: etree._Element, context: _Context, turns: list[_Turn]) -> Box | None:
        name = local(node)
        if name == "grpSp":
            xfrm = child(node, "p:grpSpPr", "a:xfrm")
        elif name == "graphicFrame":
            xfrm = child(node, "p:xfrm")
        else:
            xfrm = child(node, "p:spPr", "a:xfrm")
        found = box_of(xfrm)
        if found is None and name in ("sp", "pic", "graphicFrame"):
            for ancestor in self.chain(node, context):
                found = box_of(child(ancestor, "p:spPr", "a:xfrm"))
                if found is not None:
                    break
        if found is None:
            return None
        for turn in reversed(turns):
            found = turn.apply(found)
        return found

    def node(self, node: etree._Element, context: _Context, part: str, turns: list[_Turn]) -> list[Element]:
        name = local(node)
        if name == "grpSp":
            return [self.group(node, context, part, turns)]
        box = self.box(node, context, turns)
        if box is None:
            if name == "sp" and self.placeholder_of(node) is not None:
                return []  # a placeholder with no place anywhere is not drawn
            box = Box(0, 0, 100, 60)
        common = self.common(node)
        if name == "pic":
            return [self.picture(node, context, part, box, common)]
        if name == "cxnSp":
            found = self.connector(node, context, part, box, turns, common)
            return [found] if found is not None else []
        if name == "graphicFrame":
            return [self.frame(node, context, part, box, common)]
        if name == "contentPart":
            return [Unknown(box, kind="Ink", why="drawn by hand")]
        return self.shape(node, context, part, box, common)

    def common(self, node: etree._Element) -> dict[str, object]:
        properties = node.find(f".//{q('p:cNvPr')}")
        if properties is None:
            return {}
        return {"name": properties.get("name") or "", "ident": properties.get("id") or "",
                "hidden": flag(properties, "hidden"), "description": properties.get("descr") or ""}

    def group(self, node: etree._Element, context: _Context, part: str, turns: list[_Turn]) -> Element:
        xfrm = child(node, "p:grpSpPr", "a:xfrm")
        off, ext = child(xfrm, "a:off"), child(xfrm, "a:ext")
        child_off, child_ext = child(xfrm, "a:chOff"), child(xfrm, "a:chExt")
        ext_w, ext_h = (number(ext, "cx", 0) or 0) / EMU, (number(ext, "cy", 0) or 0) / EMU
        child_w, child_h = (number(child_ext, "cx", 0) or 0) / EMU, (number(child_ext, "cy", 0) or 0) / EMU
        turn = _Turn(
            ((number(off, "x", 0) or 0) / EMU, (number(off, "y", 0) or 0) / EMU),
            ((number(child_off, "x", 0) or 0) / EMU, (number(child_off, "y", 0) or 0) / EMU),
            (ext_w / child_w if child_w else 1.0, ext_h / child_h if child_h else 1.0),
            (number(xfrm, "rot", 0) or 0) / 60000, flag(xfrm, "flipH"), flag(xfrm, "flipV"), (ext_w, ext_h),
        )
        members = self.tree(node, context, part, [*turns, turn])
        box = self.box(node, context, turns) or Box(0, 0, ext_w, ext_h)
        return Group(box, children=members, **self.common(node))

    # -- paint --

    def paint(self, node: etree._Element, context: _Context, part: str) -> tuple[object, _Line, Colour | None, bool]:
        """A shape's fill, outline, words' colour (its style's) and shadow, its theme style
        under what it says itself."""

        properties = child(node, "p:spPr")
        colours = context.colours
        fill = fill_of(properties, colours, part, self.package)
        line = line_of(child(properties, "a:ln"), colours, part, self.package) or _Line()
        style = child(node, "p:style")
        words: Colour | None = None
        shadow = child(properties, "a:effectLst", "a:outerShdw") is not None
        if style is not None:
            reference = child(style, "a:fillRef")
            if fill is None and reference is not None:
                index = int(number(reference, "idx", 0) or 0)
                placeholder = first_colour(reference, colours)
                styles = context.theme.fills if index < 1000 else context.theme.backgrounds
                position = index - 1 if index < 1000 else index - 1001
                if 0 <= position < len(styles):
                    holder = etree.Element("holder")
                    holder.append(copy.deepcopy(styles[position]))
                    fill = fill_of(holder, colours.with_placeholder(placeholder), part, self.package)
                elif index == 0:
                    fill = _NONE
            reference = child(style, "a:lnRef")
            if reference is not None:
                index = int(number(reference, "idx", 0) or 0)
                placeholder = first_colour(reference, colours)
                if 0 < index <= len(context.theme.lines):
                    themed = line_of(context.theme.lines[index - 1], colours.with_placeholder(placeholder), part,
                                     self.package)
                    if themed is not None:
                        line.under(themed)
                elif index == 0 and line.fill is None:
                    line.fill = _NONE
            reference = child(style, "a:fontRef")
            if reference is not None:
                words = first_colour(reference, colours)
        return fill, line, words, shadow

    @staticmethod
    def stroke(line: _Line) -> Stroke | None:
        if line.fill is None or line.fill is _NONE:
            return None
        colour = line.fill if isinstance(line.fill, Colour) else (
            line.fill.stops[len(line.fill.stops) // 2][1] if isinstance(line.fill, Gradient) else None)
        if colour is None:
            return None
        return Stroke(colour, line.width if line.width is not None else 0.75, line.dash or "solid",
                      line.head or "none", line.tail or "none", line.head_size or 1.0, line.cap, line.join)

    # -- shapes --

    def shape(self, node: etree._Element, context: _Context, part: str, box: Box,
              common: dict[str, object]) -> list[Element]:
        holder = self.placeholder_of(node)
        role = ROLES.get(holder.get("type") or "body") if holder is not None else None
        fill, line, words, shadow = self.paint(node, context, part)
        body = child(node, "p:txBody")
        frame = self.frame_of(node, body, context, words) if body is not None else None
        properties = child(node, "p:spPr")
        geometry = child(properties, "a:prstGeom")
        custom = child(properties, "a:custGeom")
        preset = geometry.get("prst") if geometry is not None else ("custom" if custom is not None else "rect")
        stroke = self.stroke(line)
        painted = fill not in (None, _NONE) or stroke is not None
        if frame is not None and holder is not None and frame.empty and not painted:
            return []  # an empty placeholder shows only while editing in a slide program
        if frame is not None and frame.empty and not painted:
            return []
        if frame is not None and number_text(frame, context.number, common.get("name")):
            role = "number"
        boxed = holder is not None or flag(child(node, "p:nvSpPr", "p:cNvSpPr"), "txBox") or not painted
        if frame is not None and (preset in presets.RECTANGLES or preset is None) and not frame.empty and boxed:
            if role == "title" and holder is not None and holder.get("type") == "ctrTitle":
                common = {**common, "name": "\x00ctrTitle"}
            text = TextBox(box, frame=frame, role=role, fill=fill if fill is not _NONE else None,
                           stroke=stroke, **common)
            text.box.rotate %= 360
            return [text]
        if preset in presets.LINES:
            if stroke is None:
                return []
            start, end = in_box(box, 0, 0), in_box(box, box.w, box.h)
            if preset == "lineInv":
                start, end = in_box(box, 0, box.h), in_box(box, box.w, 0)
            return [Connector(Box(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]),
                                  abs(end[1] - start[1])), start=start, end=end, stroke=stroke, frame=frame, **common)]
        shape = Shape(box, fill=fill if fill is not _NONE else None, stroke=stroke, frame=frame, shadow=shadow,
                      **common)
        adjust = presets.adjustments(geometry)
        mapped = presets.flexo_kind(preset, adjust, box.w, box.h) if preset != "custom" else None
        if mapped is not None:
            shape.kind, shape.parameters = mapped
            if shape.kind == "bubble":
                tail = shape.parameters["tail"]
                shape.parameters["tail"] = list(in_box(box, tail[0], tail[1]))
            return [shape]
        path = None
        if custom is not None:
            found = presets.custom_path(custom, max(box.w, 1e-3), max(box.h, 1e-3))
            if found is not None:
                path, filled = found
                if not filled:
                    shape.fill = None
                    shape.closed = False
        else:
            path = presets.preset_path(preset or "rect", max(box.w, 1e-3), max(box.h, 1e-3), adjust)
            if path is None:
                self.unknown.add(preset or "")
                shape.kind = "rectangle"
                return [shape]
            if preset in presets.OPEN:
                shape.closed = False
                shape.fill = None
        if not path:
            return [shape] if frame is not None and not frame.empty else []
        shape.kind = "path"
        shape.path = path
        return [shape]

    def connector(self, node: etree._Element, context: _Context, part: str, box: Box, turns: list[_Turn],
                  common: dict[str, object]) -> Connector | None:
        _, line, _, _ = self.paint(node, context, part)
        stroke = self.stroke(line)
        if stroke is None:
            if line.fill is _NONE:
                return None
            ink = context.theme.colours.get(context.colours.mapping.get("tx1", "dk1"), "000000")
            stroke = Stroke(Colour(f"#{ink.lower()}", scheme="tx1"), line.width or 0.75, line.dash or "solid",
                            line.head or "none", line.tail or "none", line.head_size or 1.0)
        geometry = child(node, "p:spPr", "a:prstGeom")
        preset = geometry.get("prst") if geometry is not None else "straightConnector1"
        adjust = presets.adjustments(geometry)
        w, h = box.w, box.h
        made = Connector(box, stroke=stroke, **common)
        made.start, made.end = in_box(box, 0, 0), in_box(box, w, h)
        if preset.startswith("bentConnector"):
            made.route = "elbow"
            a1 = adjust.get("adj1", 50000) / 100000
            a2 = adjust.get("adj2", 50000) / 100000
            a3 = adjust.get("adj3", 50000) / 100000
            corners = {
                "bentConnector2": [(w, 0)],
                "bentConnector3": [(a1 * w, 0), (a1 * w, h)],
                "bentConnector4": [(a1 * w, 0), (a1 * w, a2 * h), (w, a2 * h)],
                "bentConnector5": [(a1 * w, 0), (a1 * w, a2 * h), (a3 * w, a2 * h), (a3 * w, h)],
            }.get(preset, [])
            made.points = [in_box(box, u, v) for u, v in corners]
        elif preset.startswith("curvedConnector"):
            made.route = "path"
            a1 = adjust.get("adj1", 50000) / 100000
            x2 = a1 * w
            pieces = [(0, 0), (x2 / 2, 0), (x2, h / 4), (x2, h / 2), (x2, 3 * h / 4), ((w + x2) / 2, h), (w, h)] \
                if preset != "curvedConnector2" else [(0, 0), (w, 0), (w, 0), (w, h)]
            points = [in_box(box, u, v) for u, v in pieces]
            data = f"M {points[0][0]:.2f} {points[0][1]:.2f}"
            for at in range(1, len(points) - 2, 3):
                data += " C " + " ".join(f"{x:.2f} {y:.2f}" for x, y in points[at : at + 3])
            made.path = data
        cxn = child(node, "p:nvCxnSpPr", "p:cNvCxnSpPr")
        start, end = child(cxn, "a:stCxn"), child(cxn, "a:endCxn")
        made.start_glue = start.get("id") if start is not None else None
        made.end_glue = end.get("id") if end is not None else None
        return made

    # -- pictures --

    def picture(self, node: etree._Element, context: _Context, part: str, box: Box,
                common: dict[str, object]) -> Element:
        details = child(node, "p:nvPicPr", "p:nvPr")
        video = child(details, "a:videoFile")
        audio = child(details, "a:audioFile") if child(details, "a:audioFile") is not None else child(
            details, "a:wavAudioFile")
        media_ext = details.find(f".//{q('p14:media')}") if details is not None else None
        blip_fill = child(node, "p:blipFill")
        blip = child(blip_fill, "a:blip")
        picture = Picture(box, media=self.blip_media(blip, part), **common)
        source = child(blip_fill, "a:srcRect")
        if source is not None:
            picture.crop = tuple((number(source, side, 0) or 0) / 100000 for side in "ltrb")  # type: ignore[assignment]
        geometry = child(node, "p:spPr", "a:prstGeom")
        if geometry is not None and geometry.get("prst") in presets.ELLIPSES:
            picture.mask = "circle"
        alpha = child(blip, "a:alphaModFix")
        if alpha is not None:
            picture.opacity = min(max((number(alpha, "amt", 100000) or 100000) / 100000, 0.0), 1.0)
        _, line, _, _ = self.paint(node, context, part)
        picture.stroke = self.stroke(line)
        if audio is not None:
            return Unknown(box, kind="Sound", why="sound is not brought across", **common)
        if video is not None or media_ext is not None:
            return Unknown(box, kind="Movie", why="its first frame is kept as a picture", picture=picture, **common)
        if picture.media is None:
            return Unknown(box, kind="Picture", why="its file is not in the deck", **common)
        return picture

    def blip_media(self, blip: etree._Element | None, part: str) -> Media | None:
        """The picture a blip shows: its SVG where the deck keeps one beside the bitmap."""

        if blip is None:
            return None
        for extension in blip.iterfind(f"{q('a:extLst')}/{q('a:ext')}"):
            svg = child(extension, "asvg:svgBlip")
            target = self.package.target(part, svg.get(R_EMBED)) if svg is not None else None
            if target is not None:
                with contextlib.suppress(KeyError, ValueError):
                    return Media(posixpath.basename(target), self.package.read(target))
        target = self.package.target(part, blip.get(R_EMBED))
        if target is None:
            return None
        with contextlib.suppress(KeyError, ValueError):
            return Media(posixpath.basename(target), self.package.read(target))
        return None

    # -- graphic frames: tables, charts, SmartArt, objects --

    def frame(self, node: etree._Element, context: _Context, part: str, box: Box,
              common: dict[str, object]) -> Element:
        data = child(node, "a:graphic", "a:graphicData")
        uri = (data.get("uri") if data is not None else "") or ""
        if uri.endswith("/table"):
            table = child(data, "a:tbl")
            if table is not None:
                return self.table(table, context, box, common)
        kind = KINDS.get(uri, "Object")
        if kind == "SmartArt":
            drawn = self.smartart(data, context, part, box, common)
            if drawn is not None:
                return drawn
        found = data.find(f".//{q('p:oleObj')}") if data is not None else None
        if found is not None:
            program = found.get("progId") or ""
            target = self.package.target(part, found.get(R_ID))
            if target is not None:
                with contextlib.suppress(Exception):
                    pdf = ole.embedded_pdf(self.package.read(target))
                    if pdf is not None:
                        return Picture(box, media=Media(f"{Path(target).stem}.pdf", pdf), **common)
            picture = None
            inner = found.find(f".//{q('p:pic')}")
            if inner is not None:
                made = self.picture(inner, context, part, box, common)
                picture = made if isinstance(made, Picture) else None
            name = "Equation" if "Equation" in program else f"{program.split('.')[0] or 'Embedded'} object"
            return Unknown(box, kind=name, why="an object of another program", picture=picture, **common)
        return Unknown(box, kind=kind, why="not brought across" if kind != "Chart" else "charts are not brought across",
                       **common)

    def smartart(self, data: etree._Element, context: _Context, part: str, box: Box,
                 common: dict[str, object]) -> Element | None:
        """SmartArt as the shapes PowerPoint drew it in (its drawing part), grouped."""

        ids = child(data, "dgm:relIds")
        if ids is None:
            return None
        model = self.package.target(part, ids.get(q("r:dm")))
        if model is None:
            return None
        drawing = None
        for extension in self.package.xml(model).iter(q("dsp:dataModelExt")):
            drawing = self.package.target(part, extension.get("relId"))
        if drawing is None:
            return None
        tree = child(self.package.xml(drawing), "dsp:spTree")
        if tree is None:
            return None
        # Its shapes are the slide's own kind under another name, placed from the frame's corner.
        copied = copy.deepcopy(tree)
        for element in copied.iter():
            if isinstance(element.tag, str) and etree.QName(element).namespace == NS["dsp"]:
                element.tag = f"{{{NS['p']}}}{etree.QName(element).localname}"
        for shape in copied.iter(q("p:sp")):
            text_xfrm = child(shape, "p:txXfrm")
            if text_xfrm is not None:
                shape.remove(text_xfrm)
        turn = _Turn((box.x, box.y), (0.0, 0.0), (1.0, 1.0), 0.0, False, False, (box.w, box.h))
        members = self.tree(copied, context, drawing, [turn])
        if not members:
            return None
        self.report.made["SmartArt as shapes"] += 1
        return Group(box, children=members, **common)

    def table(self, table: etree._Element, context: _Context, box: Box, common: dict[str, object]) -> Table:
        grid = table.iterfind(f"{q('a:tblGrid')}/{q('a:gridCol')}")
        columns = [(number(column, "w", 0) or 0) / EMU for column in grid]
        inheritance = Inheritance([self.default_text], context.colours)
        rows = []
        for row in table.iterfind(q("a:tr")):
            cells = []
            for cell in row.iterfind(q("a:tc")):
                body = child(cell, "a:txBody")
                frame = self.read_frame(body, inheritance, context, None, [], False) if body is not None \
                    else Frame([])
                fill = fill_of(child(cell, "a:tcPr"), context.colours, context.part, self.package)
                cells.append(Cell(frame, (int(number(cell, "gridSpan", 1) or 1), int(number(cell, "rowSpan", 1) or 1)),
                                  flag(cell, "hMerge") or flag(cell, "vMerge"),
                                  fill if isinstance(fill, Colour) else None))
            rows.append(cells)
        properties = child(table, "a:tblPr")
        header = flag(properties, "firstRow", True) if properties is not None else True
        borders = [line for line in table.iter(*(q(f"a:{side}") for side in ("lnL", "lnR", "lnT", "lnB")))]
        if borders:
            ruled = any(child(line, "a:noFill") is None and (number(line, "w", 12700) or 0) > 0 for line in borders)
        else:
            ruled = child(properties, "a:tableStyleId") is not None or properties is None
        return Table(box, rows=rows, columns=columns, header=header, ruled=ruled, **common)

    # -- words --

    def frame_of(self, node: etree._Element, body: etree._Element, context: _Context,
                 colour: Colour | None) -> Frame:
        chain = self.chain(node, context)
        holder = self.placeholder_of(node)
        sources: list[etree._Element | None] = [child(body, "a:lstStyle")]
        sources += [child(ancestor, "p:txBody", "a:lstStyle") for ancestor in chain]
        styles = child(self.package.xml(context.master), "p:txStyles") if context.master else None
        if holder is None:
            sources.append(child(styles, "p:otherStyle"))
            sources.append(self.default_text)
        elif (holder.get("type") or "body") in ("title", "ctrTitle"):
            sources.append(child(styles, "p:titleStyle"))
        elif (holder.get("type") or "body") in ("dt", "ftr", "sldNum"):
            sources.append(child(styles, "p:otherStyle"))
        else:
            sources.append(child(styles, "p:bodyStyle"))
        inheritance = Inheritance(sources, context.colours)
        bodies = [child(body, "a:bodyPr")] + [child(ancestor, "p:txBody", "a:bodyPr") for ancestor in chain]
        return self.read_frame(body, inheritance, context, colour, bodies, True)

    def read_frame(self, body: etree._Element, inheritance: Inheritance, context: _Context,
                   colour: Colour | None, bodies: list[etree._Element | None], boxed: bool) -> Frame:
        bodies = bodies or [child(body, "a:bodyPr")]

        def said(name: str) -> str | None:
            for properties in bodies:
                if properties is not None and properties.get(name) is not None:
                    return properties.get(name)
            return None

        scale = 1.0
        for properties in bodies:
            fit = child(properties, "a:normAutofit")
            if fit is not None:
                scale = (number(fit, "fontScale", 100000) or 100000) / 100000
                break
            if properties is not None and (child(properties, "a:spAutoFit") is not None
                                           or child(properties, "a:noAutofit") is not None):
                break
        insets = []
        for name, default in (("lIns", 91440), ("tIns", 45720), ("rIns", 91440), ("bIns", 45720)):
            raw = said(name)
            try:
                insets.append((int(raw) if raw is not None else default) / EMU)
            except ValueError:
                insets.append(default / EMU)
        anchor = {"t": "top", "ctr": "middle", "b": "bottom"}.get(said("anchor") or "t", "top")
        paragraphs = [self.paragraph(paragraph, inheritance, context, colour)
                      for paragraph in body.iterfind(q("a:p"))]
        _levels(paragraphs)
        vertical = (said("vert") or "horz") not in ("horz", "")
        return Frame(paragraphs, tuple(insets), anchor, said("wrap") != "none", max(min(scale, 1.0), 0.1),  # type: ignore[arg-type]
                     vertical)

    def paragraph(self, node: etree._Element, inheritance: Inheritance, context: _Context,
                  colour: Colour | None) -> Paragraph:
        properties = child(node, "a:pPr")
        own = paragraph_look(properties, context.colours)
        level = int(number(properties, "lvl", 0) or 0)
        look = inheritance.resolved(own, level)
        base = _RunLook()
        base.under(look.run)
        runs: list[Run] = []
        display = None
        for element in node:
            name = local(element)
            if name == "AlternateContent":
                chosen = alternative(element)
                inner = list(chosen) if chosen is not None else []
            else:
                inner = [element]
            for piece in inner:
                kind = local(piece)
                if kind in ("r", "fld"):
                    runs.append(self.run(piece, base, context, colour))
                elif kind == "br":
                    runs.append(Run("\n"))
                elif kind == "m":
                    para = piece.find(q("m:oMathPara"))
                    tex = omml_tex(para if para is not None else piece)
                    size, tint = _maths_look(piece, context)
                    if para is not None:
                        display = tex
                    else:
                        runs.append(Run("", tex=tex, size=size or base.size, colour=tint))
        end = run_look(child(node, "a:endParaRPr"), context.colours)
        end.under(base)
        bullet = look.bullet if look.bullet in ("bullet", "number") else None
        if bullet and look.bullet_colour is not None:
            self.bullets[look.bullet_colour.hex] += 1
        size = end.size or base.size
        paragraph = Paragraph(runs, level, bullet, look.align, display, size=size)
        if display is not None:
            maths_size = next((run_look(found, context.colours).size for found in node.iter(q("a:rPr"))), None)
            paragraph.size = maths_size or size
            if not runs or all(not run.text.strip() and run.tex is None for run in runs):
                paragraph.runs = []
            else:
                # Words beside a displayed formula: the formula among them.
                paragraph.runs.append(Run("", tex=display, size=paragraph.size))
                paragraph.display = None
        reference = size or 18.0
        paragraph.space_before = look.before if look.before else (look.before_share or 0.0) * reference
        paragraph.space_after = look.after if look.after else (look.after_share or 0.0) * reference
        paragraph.line_spacing = look.line_spacing
        paragraph.line_points = look.line_points
        paragraph.indent = look.margin
        return paragraph

    def run(self, node: etree._Element, base: _RunLook, context: _Context, colour: Colour | None) -> Run:
        text = node.findtext(q("a:t")) or ""
        properties = child(node, "a:rPr")
        look = run_look(properties, context.colours)
        look.under(base)
        field = None
        if local(node) == "fld":
            kind = node.get("type") or ""
            if kind == "slidenum":
                field = "slide-number"
                text = str(context.number)
            elif kind.startswith("datetime"):
                field = "date"
        link = None
        click = child(properties, "a:hlinkClick")
        if click is not None:
            entry = self.package.rels(context.part).get(click.get(R_ID) or "")
            if entry is not None and entry[2]:
                link = entry[0]
        font = look.font
        if font in ("+mj-lt", "+mj-ea", "+mj-cs"):
            font = context.theme.major
        elif font in ("+mn-lt", "+mn-ea", "+mn-cs"):
            font = context.theme.minor
        return Run(text, bold=look.bold, italic=look.italic, underline=bool(look.underline),
                   strike=bool(look.strike), baseline=look.baseline or 0.0, size=look.size,
                   colour=look.colour or colour, font=font, link=link, field=field, caps=bool(look.caps))


def alternative(node: etree._Element) -> etree._Element | None:
    """The part of an ``mc:AlternateContent`` to read: its choice where all it needs is
    understood here (Office Math), else its fallback."""

    for choice in node.iterfind(q("mc:Choice")):
        needs = set((choice.get("Requires") or "").split())
        if needs and needs <= UNDERSTOOD:
            return choice
    fallback = node.find(q("mc:Fallback"))
    if fallback is not None:
        return fallback
    return node.find(q("mc:Choice"))


def _levels(paragraphs: list[Paragraph]) -> None:
    """A list's levels where its paragraphs say them by how far in they stand, not by their
    level (a deck that indents its items by hand): each distinct indent a level deeper."""

    listed = [paragraph for paragraph in paragraphs if paragraph.bullet and paragraph.words.strip()]
    if len(listed) < 2 or any(paragraph.level for paragraph in listed):
        return
    indents = sorted({round(paragraph.indent or 0.0) for paragraph in listed})
    if len(indents) < 2:
        return
    for paragraph in listed:
        paragraph.level = indents.index(round(paragraph.indent or 0.0))


def _maths_look(maths: etree._Element, context: _Context) -> tuple[float | None, Colour | None]:
    """A formula's size and colour, from its first run's."""

    for properties in maths.iter(q("a:rPr")):
        look = run_look(properties, context.colours)
        return look.size, look.colour
    return None, None


def number_text(frame: Frame, number: int, name: object) -> bool:
    """Whether a text box is a slide's number written as words (Flexo's own decks name it)."""

    words = frame.words.strip()
    if name == "Slide Number" and words.isdigit():
        return True
    return any(run.field == "slide-number" for paragraph in frame.paragraphs for run in paragraph.runs) \
        and re.fullmatch(r"\d+", words) is not None and int(words) == number


def read(path: Path, report: Report, progress: Progress = quiet) -> Presentation:
    """The PowerPoint deck at ``path`` as a ``Presentation``."""

    try:
        package = Package(path)
    except zipfile.BadZipFile:
        raise ValueError(f"{path.name} is not a PowerPoint file (it is not a zip).") from None
    try:
        progress(0.05, f"Reading {path.name}")
        return Reader(package, report, progress).presentation(path.stem)
    finally:
        package.close()
