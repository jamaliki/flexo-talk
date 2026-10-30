# Adapted from DeckWerk's importers/keynote/import_keynote.py, by Vincent Sitzmann, under the
# MIT License: Copyright (c) 2026 Vincent Sitzmann. Permission is hereby granted, free of charge,
# to any person obtaining a copy of that software, to deal in it without restriction, provided
# this notice is kept; it is provided "as is", without warranty of any kind. Flexo's changes are
# under the Apache License 2.0, as the rest of it. DeckWerk reads Keynote's messages with
# keynote-parser's schemas; this reads them with none (``iwa``), by the fields' numbers.
"""A Keynote deck (``.key``) read into a ``Presentation``, from its file alone.

A ``.key`` -- one file (a zip), or a package (a folder, its ``Index`` zipped) -- holds objects
(``iwa``): the show, its slides in order, each slide's drawables (shapes with their words,
pictures with their masks, groups, lines and their connections, movies, equations) and the
styles they take what they do not say from (a style's parent, up to the theme). Each is kept
as it is drawn: words with their lists and levels, bold, italic, scripts, colours and links;
pictures with their crops; shapes with their outlines and paint; equations as TeX (MathML made
TeX: ``mathml_tex``). Notes, skipped slides, the slide's size and its background come too.
What cannot be read -- a table, a chart, a movie -- is an ``Unknown`` where it was, with a
picture of itself where there is one. Fields are named here by their numbers in Keynote's
schemas (``TSD.GeometryArchive`` is position 1, size 2, flags 3, angle 4...).
"""

from __future__ import annotations

import contextlib
import io
import itertools
import math
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

from flexo_talk.importing.iwa import Archive, Damaged, Message, archives
from flexo_talk.importing.mathml_tex import equation_tex
from flexo_talk.importing.model import (
    Box,
    Colour,
    Connector,
    Element,
    Equation,
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
    TextBox,
    Theme,
    Unknown,
)
from flexo_talk.importing.reading import faces, title_look
from flexo_talk.importing.report import Progress, Report, quiet

# Message types, as Keynote registers them.
DOCUMENT, SHOW, SLIDE_NODE, SLIDE, TEMPLATE_SLIDE = 1, 2, 4, 5, 6
PLACEHOLDERS = {7, 12}
NOTE, SLIDE_STYLE, SLIDE_NUMBER = 15, 9, 22
STORAGES = {2001, 2005}
SHAPE_INFO, CHARACTER_STYLE, PARAGRAPH_STYLE, LIST_STYLE, TEXT_SHAPE_STYLE = 2011, 2021, 2022, 2023, 2025
DRAWABLE_ATTACHMENT, NUMBER_ATTACHMENT, HYPERLINK = 2003, 2043, 2032
TEXTUAL_ATTACHMENTS = {14, 2004, 2007, 2009}
DRAWABLE, SHAPE, IMAGE, MASK, MOVIE, GROUP, CONNECTION = 3002, 3004, 3005, 3006, 3007, 3008, 3009
SHAPE_STYLE, MEDIA_STYLE = 3015, 3016
TABLE, CHART = 6000, 5021
METADATA = 11006

SUPER_DEPTH = {DRAWABLE: 0, SHAPE: 1, SHAPE_INFO: 2, 7: 3, 12: 3, IMAGE: 1, MASK: 1, MOVIE: 1, GROUP: 1,
               CONNECTION: 2, TABLE: 1, CHART: 1}
"""How deep each drawable's ``TSD.DrawableArchive`` is under its supers (field 1 each)."""

FLIP_H, FLIP_V = 4, 8
LINE_ENDS = {"simple arrow": "open", "filled arrow": "triangle", "inverted arrow": "triangle", "filled circle": "dot",
             "open circle": "circle", "filled diamond": "diamond", "open diamond": "diamond", "filled square": "bar",
             "open square": "bar", "line": "bar", "square": "bar", "circle": "dot", "arrow": "open"}
ALIGNS = {0: "start", 1: "end", 2: "middle", 3: "justify", 4: "start"}


class Package:
    """A ``.key`` in whichever shape it travels: one zip, or a folder (its index zipped)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zips: list[zipfile.ZipFile] = []
        self.members: dict[str, tuple[zipfile.ZipFile | None, str]] = {}
        if path.is_dir():
            for member in path.rglob("*"):
                if member.is_file():
                    stored = str(member.relative_to(path))
                    self.members[_canonical(stored)] = (None, stored)
        else:
            self._add(zipfile.ZipFile(path))
        self._strip_folder()
        index = self.members.pop("Index.zip", None)
        if index is not None:
            self._add(zipfile.ZipFile(io.BytesIO(self._read(*index))), under="Index/")

    def _add(self, archive: zipfile.ZipFile, under: str = "") -> None:
        self._zips.append(archive)
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = _canonical(_member_name(info))
            if under and not name.startswith(under):
                name = under + name
            self.members.setdefault(name, (archive, info.filename))

    def _strip_folder(self) -> None:
        """The ``<name>.key/`` folder a zipped-up package sits in, taken off its names."""

        names = [name for name in self.members if not name.startswith("__MACOSX/")]
        if not names or any(name == "Index.zip" or name.startswith("Index/") for name in names):
            return
        tops = {name.split("/", 1)[0] for name in names}
        if len(tops) != 1 or not all("/" in name for name in names):
            return
        prefix = tops.pop() + "/"
        inner = {name[len(prefix) :]: member for name, member in self.members.items() if name.startswith(prefix)}
        if any(name == "Index.zip" or name.startswith("Index/") for name in inner):
            self.members = inner

    def has(self, name: str) -> bool:
        return _canonical(name) in self.members

    def read(self, name: str) -> bytes:
        return self._read(*self.members[_canonical(name)])

    def _read(self, archive: zipfile.ZipFile | None, stored: str) -> bytes:
        if archive is not None:
            info = archive.getinfo(stored)
            if info.file_size > 1 << 31:
                raise ValueError(f"{stored} is too large to read")
            return archive.read(info)
        return (self.path / stored).read_bytes()

    def close(self) -> None:
        for archive in self._zips:
            archive.close()


def _member_name(info: zipfile.ZipInfo) -> str:
    """A member's name as written: Keynote writes UTF-8 names without saying so."""

    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except UnicodeError:
        return info.filename


def _canonical(name: str) -> str:
    return unicodedata.normalize("NFC", name)


# -- messages ----------------------------------------------------------------------------------


def colour(message: Message | None) -> Colour | None:
    """A ``TSP.Color``: model 1, r 3, g 4, b 5, a 6 (cmyk 7 to 10, white 11)."""

    if message is None:
        return None
    model = message.int(1, 1)
    alpha = message.float(6, 1.0) or 0.0
    if model == 2:
        c, m, y, k = (message.float(n, 0.0) or 0.0 for n in (7, 8, 9, 10))
        r, g, b = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    elif model == 3:
        r = g = b = message.float(11, 0.0) or 0.0
    else:
        r, g, b = (message.float(n, 0.0) or 0.0 for n in (3, 4, 5))
    hexed = "#" + "".join(f"{max(0, min(255, round(value * 255))):02x}" for value in (r, g, b))
    return Colour(hexed, max(0.0, min(1.0, alpha)))


def point(message: Message | None) -> tuple[float, float]:
    if message is None:
        return 0.0, 0.0
    return message.float(1, 0.0) or 0.0, message.float(2, 0.0) or 0.0


def path_data(path: Message | None, sx: float = 1.0, sy: float = 1.0) -> tuple[str, list[tuple[float, float]]]:
    """A ``TSP.Path`` (elements 1: type 1, points 2) as SVG path data, scaled, and its points."""

    if path is None:
        return "", []
    out, every = [], []
    for element in path.messages(1):
        kind = element.int(1, 0)
        points = [(x * sx, y * sy) for x, y in (point(item) for item in element.messages(2))]
        every.extend(points)
        letter, count = {1: ("M", 1), 2: ("L", 1), 3: ("Q", 2), 4: ("C", 3), 5: ("Z", 0)}.get(kind, ("", -1))
        if count < 0 or len(points) < count:
            continue
        out.append(letter if not count else letter + " " + " ".join(f"{x:.2f} {y:.2f}" for x, y in points[:count]))
    return " ".join(out), every


def family_of(name: str | None) -> tuple[str | None, bool, bool]:
    """A face's PostScript name (``HelveticaNeue-Bold``) as its family, and whether it is bold
    and italic."""

    if not name:
        return None, False, False
    base, _, style = name.partition("-")
    style = style.lower()
    bold = any(word in style for word in ("bold", "black", "heavy", "semibold", "demi"))
    italic = "italic" in style or "oblique" in style
    base = re.sub(r"(PSMT|MT|PS)$", "", base)
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base)
    return spaced or name, bold, italic


# -- the reader --------------------------------------------------------------------------------


class Reader:
    def __init__(self, package: Package, report: Report, progress: Progress = quiet) -> None:
        self.package = package
        self.report = report
        self.progress = progress
        self.objects: dict[int, Archive] = {}
        self.datas: dict[int, str] = {}
        self.number = 0
        self.unknown: Counter = Counter()

    def load(self) -> None:
        streams = [name for name in self.package.members if name.endswith(".iwa")]
        if not streams:
            raise ValueError("it holds no Keynote document (is it a Keynote \u201909 file? Open it in Keynote and "
                             "save it again).")
        for done, name in enumerate(streams):
            self.progress(0.05 + 0.15 * done / len(streams), "Reading the deck")
            try:
                for item in archives(self.package.read(name)):
                    self.objects[item.ident] = item
            except (Damaged, ValueError, KeyError, zipfile.BadZipFile) as error:
                self.report.note(f"Part of the deck could not be read ({Path(name).name}: {error}).")
        files = {name.rsplit("-", 1)[-1].split(".")[0]: name for name in self.package.members
                 if name.startswith("Data/")}
        for item in self.objects.values():
            if item.type != METADATA:
                continue
            for entry in item.message.messages(4):
                ident = entry.int(1)
                if not ident:
                    continue
                named = entry.text(4)
                if named and self.package.has(f"Data/{named}"):
                    self.datas[ident] = f"Data/{named}"
                elif str(ident) in files:
                    self.datas[ident] = files[str(ident)]

    def get(self, ident: int | None) -> Archive | None:
        return self.objects.get(ident) if ident else None

    def media(self, ident: int | None, name: str = "") -> Media | None:
        """The file a data reference names, read."""

        found = self.datas.get(ident or 0)
        if found is None:
            return None
        with contextlib.suppress(KeyError, ValueError, OSError):
            data = self.package.read(found)
            stored = Path(found).name
            stem, ending = Path(stored).stem, Path(stored).suffix
            stem = re.sub(rf"-{ident}$", "", stem)
            return Media(f"{name or stem}{ending}", data)
        return None

    # -- the deck --

    def presentation(self, title: str) -> Presentation:
        document = next((item for item in self.objects.values() if item.type == DOCUMENT), None)
        show = self.get(document.message.reference(2)) if document is not None else None
        if show is None:
            show = next((item for item in self.objects.values() if item.type == SHOW), None)
        if show is None:
            raise ValueError("it holds no Keynote show.")
        width, height = point(show.message.message(4))
        out = Presentation(width or 1920.0, height or 1080.0, name=title)
        nodes = show.message.message(3).references(2) if show.message.message(3) is not None else []
        numbered = show.message.bool(6)
        for index, ident in enumerate(nodes):
            self.progress(0.2 + 0.4 * index / max(len(nodes), 1), f"Reading slide {index + 1} of {len(nodes)}")
            self.number = index + 1
            try:
                out.slides.append(self.slide(ident, index + 1, numbered))
            except Exception as error:  # a slide that cannot be read is kept, empty, and said
                self.report.placeholder(index + 1, "Slide", f"could not be read ({error})")
                out.slides.append(Slide(index + 1, layout="blank"))
        out.theme = Theme({}, None, None)
        faces(out)
        out.title_style = title_look(out)
        backgrounds = Counter(slide.background.hex if isinstance(slide.background, Colour) else "#ffffff"
                              for slide in out.slides)
        if backgrounds:
            page = backgrounds.most_common(1)[0][0]
            value = page.lstrip("#")
            r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
            out.theme.dark = 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4
            out.theme.colours = {"lt1" if not out.theme.dark else "dk1": page}
        if self.unknown:
            kinds = ", ".join(sorted(self.unknown))
            self.report.note(f"Keynote objects not understood here were kept as their places: {kinds}.")
        return out

    def slide(self, ident: int, number: int, numbered: bool) -> Slide:
        node = self.get(ident)
        if node is None:
            raise ValueError("its slide is missing")
        found = self.get(node.message.reference(2))
        if found is None:
            raise ValueError("its slide is missing")
        message = found.message
        slide = Slide(number, skip=node.message.bool(4), name=message.text(10) or "")
        visible = self._visibility(message.reference(1))
        title, body, slide_number = message.reference(5), message.reference(6), message.reference(20)
        order = message.references(42) or message.references(7)
        for drawable in order:
            item = self.get(drawable)
            if item is None:
                continue
            if item.type in PLACEHOLDERS:
                kind = item.message.int(2, 0)
                if (kind == 2 and not visible.get(4, True)) or (kind == 3 and not visible.get(5, True)) or (
                        kind == 1 and not (visible.get(6, numbered))) or (kind == 4 and not visible.get(7, True)):
                    continue
            role = "title" if drawable == title else "body" if drawable == body else (
                "number" if drawable == slide_number else None)
            for element in self.drawable(item, (0.0, 0.0)):
                if isinstance(element, TextBox) and role:
                    element.role = role
                slide.elements.append(element)
        slide.elements = _connections_first(slide.elements)
        template = self.get(message.reference(17))
        if template is not None:
            for drawable in template.message.references(42) or template.message.references(7):
                item = self.get(drawable)
                if item is None or item.type in PLACEHOLDERS:
                    continue
                slide.decorations.extend(self.drawable(item, (0.0, 0.0)))
        slide.background = self._background(message.reference(1))
        if slide.background is None and template is not None:
            slide.background = self._background(template.message.reference(1))
        note = self.get(message.reference(27))
        if note is not None:
            storage = self.get(note.message.reference(1))
            if storage is not None:
                slide.notes = "\n".join(paragraph.words for paragraph in self.paragraphs(storage)).strip()
        return slide

    def _chain(self, ident: int | None) -> list[Archive]:
        """A style and its parents, nearest first."""

        out, seen = [], set()
        while ident and ident not in seen and len(out) < 12:
            seen.add(ident)
            found = self.get(ident)
            if found is None:
                break
            out.append(found)
            base = found.message.message(1)
            if found.type == TEXT_SHAPE_STYLE and base is not None:
                base = base.message(1)
            ident = base.reference(3) if base is not None else None
        return out

    def _visibility(self, style: int | None) -> dict[int, bool]:
        """Which of the slide's placeholders it shows (title 4, body 5, number 6, object 7)."""

        out: dict[int, bool] = {}
        for found in self._chain(style):
            properties = found.message.message(11)
            for number in (4, 5, 6, 7):
                if properties is not None and properties.has(number) and number not in out:
                    out[number] = properties.bool(number)
        return out

    def _background(self, style: int | None) -> object:
        for found in self._chain(style):
            properties = found.message.message(11)
            fill = properties.message(1) if properties is not None else None
            if fill is not None:
                return self.fill(fill)
        return None

    # -- paint --

    def fill(self, fill: Message | None) -> object:
        """A ``TSD.FillArchive`` (colour 1, gradient 2, image 3) as the model's fill."""

        if fill is None:
            return None
        if fill.has(1):
            found = colour(fill.message(1))
            return found if found is not None and found.alpha > 0.001 else None
        gradient = fill.message(2)
        if gradient is not None:
            stops = [(min(max(stop.float(2, 0.0) or 0.0, 0.0), 1.0), colour(stop.message(1)))
                     for stop in gradient.messages(2)]
            stops = [(at, found) for at, found in stops if found is not None]
            angle = gradient.message(5)
            degrees = math.degrees(angle.float(2, 0.0) or 0.0) if angle is not None else 0.0
            return Gradient(sorted(stops, key=lambda pair: pair[0]), -degrees % 360, radial=gradient.int(1, 0) == 1) \
                if stops else None
        image = fill.message(3)
        if image is not None:
            return self.media(image.reference(6) or image.reference(1))
        return None

    def paint(self, style: int | None) -> dict[str, object]:
        """A shape's paint through its style's chain: fill, stroke, opacity, shadow, arrowheads,
        and its words' room (padding, where they stand down it)."""

        found: dict[str, object] = {}
        for item in self._chain(style):
            if item.type == TEXT_SHAPE_STYLE:
                words = item.message.message(11)
                if words is not None:
                    if "anchor" not in found and words.has(2):
                        found["anchor"] = {0: "top", 1: "middle", 2: "bottom"}.get(words.int(2, 0), "top")
                    padding = words.message(6)
                    if "padding" not in found and padding is not None:
                        found["padding"] = tuple(padding.float(n, 0.0) or 0.0 for n in (1, 2, 3, 4))
                    if "vertical" not in found and words.has(8):
                        found["vertical"] = words.bool(8)
                shape = item.message.message(1)
                properties = shape.message(11) if shape is not None else None
            else:
                properties = item.message.message(11)
            if properties is None:
                continue
            if "fill" not in found and properties.has(1):
                found["fill"] = self.fill(properties.message(1))
            if "stroke" not in found and properties.has(2):
                found["stroke"] = self.stroke(properties.message(2))
            if "opacity" not in found and properties.has(3):
                found["opacity"] = min(max(properties.float(3, 1.0) or 0.0, 0.0), 1.0)
            if "shadow" not in found and properties.has(4):
                shadow = properties.message(4)
                found["shadow"] = shadow is not None and shadow.bool(6, True) and shadow.has(1)
            for number, key in ((6, "head"), (7, "tail")):
                if key not in found and properties.has(number):
                    end = properties.message(number)
                    name = (end.text(5) or "").strip().lower() if end is not None else ""
                    found[key] = LINE_ENDS.get(name, "triangle" if name and name != "none" else "none")
        return found

    def stroke(self, stroke: Message | None) -> Stroke | None:
        """A ``TSD.StrokeArchive`` (colour 1, width 2, cap 3, join 4, pattern 6)."""

        if stroke is None:
            return None
        pattern = stroke.message(6)
        if pattern is not None and pattern.int(1, 1) == 2:
            return None
        found = colour(stroke.message(1))
        if found is None or found.alpha <= 0.001:
            return None
        dash: str | list[float] = "solid"
        if pattern is not None and pattern.int(1, 1) == 0:
            lengths = pattern.floats(4)[: max(pattern.int(3, 0) or 0, 0)]
            dash = "dotted" if lengths and max(lengths) <= 1.5 else "dashed"
        cap = {1: "round", 2: "square"}.get(stroke.int(3, 0) or 0)
        join = {1: "round", 2: "bevel"}.get(stroke.int(4, 0) or 0)
        return Stroke(found, stroke.float(2, 1.0) or 1.0, dash, cap=cap, join=join)

    # -- drawables --

    def drawable_of(self, item: Archive) -> Message | None:
        message = item.message
        for _ in range(SUPER_DEPTH.get(item.type, 0)):
            message = message.message(1) if message is not None else None
        return message

    def box(self, item: Archive, offset: tuple[float, float]) -> Box:
        drawable = self.drawable_of(item)
        geometry = drawable.message(1) if drawable is not None else None
        if geometry is None:
            return Box(offset[0], offset[1], 0.0, 0.0)
        x, y = point(geometry.message(1))
        w, h = point(geometry.message(2))
        flags = geometry.int(3, 0) or 0
        return Box(x + offset[0], y + offset[1], w, h, (-(geometry.float(4, 0.0) or 0.0)) % 360,
                   bool(flags & FLIP_H), bool(flags & FLIP_V))

    def drawable(self, item: Archive, offset: tuple[float, float]) -> list[Element]:
        """One drawable as the model's elements (a group as one, its members in it)."""

        box = self.box(item, offset)
        try:
            if item.type == GROUP:
                return [self.group(item, box)]
            if item.type == IMAGE:
                return [self.image(item, box)]
            if item.type == MOVIE:
                return [self.movie(item, box)]
            if item.type in (SHAPE, SHAPE_INFO, CONNECTION) or item.type in PLACEHOLDERS:
                return self.shape(item, box)
            if item.type == TABLE:
                return [Unknown(box, kind="Table", why="Keynote's tables are not brought across",
                                ident=str(item.ident))]
            if item.type == CHART:
                return [Unknown(box, kind="Chart", why="charts are not brought across", ident=str(item.ident))]
        except Exception as error:
            self.report.note(f"Slide {self.number}: a Keynote object could not be read ({error}).")
            return [Unknown(box if box.w > 1 else Box(box.x, box.y, 100, 60), kind="Object", why="could not be read")]
        self.unknown[str(item.type)] += 1
        return [Unknown(box if box.w > 1 else Box(box.x, box.y, 100, 60), kind="Object", why="not understood")]

    def group(self, item: Archive, box: Box) -> Group:
        members: list[Element] = []
        for child in item.message.references(2):
            found = self.get(child)
            if found is not None:
                members.extend(self.drawable(found, (box.x, box.y)))
        if box.rotate % 360:
            _turn(members, box)
        return Group(box, children=_connections_first(members), ident=str(item.ident))

    def image(self, item: Archive, box: Box) -> Element:
        message = item.message
        source = message.text(103) or message.text(100)
        if source:
            tex = equation_tex(source)
            if tex is not None:
                properties = message.message(101)
                size = properties.float(3) if properties is not None else None
                return Equation(box, tex=tex, size=size, colour=colour(properties.message(7)) if properties else None,
                                ident=str(item.ident))
        media = self.media(message.reference(13)) or self.media(message.reference(11)) or self.media(
            message.reference(12))
        drawable = self.drawable_of(item)
        description = (drawable.text(8) or "") if drawable is not None else ""
        picture = Picture(box, media=media, ident=str(item.ident), description=description)
        if media is None:
            return Unknown(box, kind="Picture", why="its file is not in the deck")
        mask = self.get(message.reference(5))
        if mask is not None:
            mask_drawable = self.drawable_of(mask)
            geometry = mask_drawable.message(1) if mask_drawable is not None else None
            if geometry is not None:
                mx, my = point(geometry.message(1))
                mw, mh = point(geometry.message(2))
                if box.flip_h:
                    mx = box.w - mx - mw
                if box.flip_v:
                    my = box.h - my - mh
                if box.w > 0 and box.h > 0 and mw > 0 and mh > 0:
                    picture.crop = (max(mx / box.w, 0.0), max(my / box.h, 0.0), max(1 - (mx + mw) / box.w, 0.0),
                                    max(1 - (my + mh) / box.h, 0.0))
                    # The picture shows where its mask is.
                    cx, cy = box.centre
                    turn = math.radians(box.rotate)
                    dx, dy = (box.x + mx + mw / 2) - cx, (box.y + my + mh / 2) - cy
                    nx = cx + dx * math.cos(turn) - dy * math.sin(turn)
                    ny = cy + dx * math.sin(turn) + dy * math.cos(turn)
                    picture.box = Box(nx - mw / 2, ny - mh / 2, mw, mh, box.rotate, box.flip_h, box.flip_v)
            source = mask.message.message(2)
            if source is not None and _is_circle(source):
                picture.mask = "circle"
        picture.opacity = self._media_opacity(message.reference(3))
        return picture

    def _media_opacity(self, style: int | None) -> float:
        for found in self._chain(style):
            properties = found.message.message(11)
            if properties is not None and properties.has(2):
                return min(max(properties.float(2, 1.0) or 0.0, 0.0), 1.0)
        return 1.0

    def movie(self, item: Archive, box: Box) -> Element:
        message = item.message
        movie = self.media(message.reference(14))
        if movie is not None and Path(movie.name).suffix.lower() == ".gif":
            return Picture(box, media=movie, ident=str(item.ident))
        poster = self.media(message.reference(15))
        picture = Picture(box, media=poster) if poster is not None else None
        return Unknown(box, kind="Movie", why="its poster frame is kept as a picture" if picture else "",
                       picture=picture, ident=str(item.ident))

    def shape(self, item: Archive, box: Box) -> list[Element]:
        message = item.message
        shape = message
        for _ in range({SHAPE: 0, SHAPE_INFO: 1, CONNECTION: 1}.get(item.type, 2)):
            shape = shape.message(1) if shape is not None else None
        info = message if item.type == SHAPE_INFO else message.message(1) if item.type in PLACEHOLDERS else None
        paint = self.paint(shape.reference(2) if shape is not None else None)
        source = shape.message(3) if shape is not None else None
        storage = self.get(info.reference(4) or info.reference(2)) if info is not None else None
        paragraphs = self.paragraphs(storage) if storage is not None else []
        frame = None
        if any(paragraph.words.strip() or paragraph.display for paragraph in paragraphs):
            padding = paint.get("padding") or (4.0, 4.0, 4.0, 4.0)
            text_box = info is not None and info.bool(6)
            frame = Frame(paragraphs, tuple(padding), str(paint.get("anchor") or ("top" if text_box else "middle")),  # type: ignore[arg-type]
                          True, 1.0, bool(paint.get("vertical")))
            if box.w <= 1 or box.h <= 1:
                box = self._sized(box, frame, source)
        fill = paint.get("fill")
        stroke = paint.get("stroke") if isinstance(paint.get("stroke"), Stroke) else None
        if stroke is not None:
            stroke.head = str(paint.get("tail") or "none")
            stroke.tail = str(paint.get("head") or "none")
        flip_h, flip_v = (source.bool(1), source.bool(2)) if source is not None else (False, False)
        box.flip_h, box.flip_v = box.flip_h != flip_h, box.flip_v != flip_v
        if item.type == CONNECTION:
            return [self.connection(item, box, source, stroke, frame)]
        outline = self.outline(source, box)
        common = {"ident": str(item.ident)}
        if (outline is None or (outline[0] == "rectangle" and not outline[1])) and frame is not None:
            return [TextBox(box, frame=frame, fill=fill, stroke=stroke, **common)]
        if fill is None and stroke is None and frame is None:
            return []
        made = Shape(box, fill=fill, stroke=stroke, frame=frame, opacity=float(paint.get("opacity") or 1.0),
                     shadow=bool(paint.get("shadow")), **common)
        if outline is None:
            made.kind = "rectangle"
        else:
            kind, settings, data, closed = outline
            made.kind, made.parameters, made.path, made.closed = kind, settings, data, closed
            if not closed:
                made.fill = None
        return [made]

    def outline(self, source: Message | None, box: Box) -> tuple[str, dict, str, bool] | None:
        """A path source (point 3, scalar 4, bezier 5, callout 6, editable 8) as Flexo's kind
        and settings, or a path in the box's units."""

        if source is None:
            return None
        scalar = source.message(4)
        if scalar is not None:
            kind = scalar.int(1, 0) or 0
            value = scalar.float(2, 0.0) or 0.0
            if kind == 0:
                if value <= 0.01:
                    return "rectangle", {}, "", True
                return "rounded-rectangle", {"corner": min(value, min(box.w, box.h) / 2)}, "", True
            if kind == 1:
                return "polygon", {"sides": max(3, min(round(value), 24))}, "", True
            if kind == 2:
                return "chevron", {"point": min(max(value / max(min(box.w, box.h), 1e-6), 0.0), 2.0)}, "", True
        point_source = source.message(3)
        if point_source is not None:
            kind = point_source.int(1, 0) or 0
            px, py = point(point_source.message(2))
            nw, nh = point(point_source.message(3))
            if kind in (0, 1, 10) and nw > 0 and nh > 0:
                head = min(max(px / max(min(nw, nh), 1e-6), 0.0), 2.0)
                shaft = min(max(py, 0.0), 1.0)
                name = {0: "arrow-left", 1: "arrow-right", 10: "arrow-left-right"}[kind]
                return name, {"shaft": round(shaft, 3), "head": round(head, 3)}, "", True
            if kind == 100:
                # (Its point: how deep its inner corners are, and how many tips it has.)
                tips, ratio = (py, px) if py >= px else (px, py)
                return "star", {"tips": max(3, min(round(tips), 40)),
                                "ratio": round(min(max(ratio, 0.05), 0.95), 3)}, "", True
            if kind == 200:
                return "plus", {"arm": round(min(max(px, 0.05), 0.5), 3)}, "", True
        callout = source.message(6)
        if callout is not None:
            tx, ty = point(callout.message(2))
            nw, nh = point(callout.message(1))
            sx, sy = (box.w / nw if nw else 1.0), (box.h / nh if nh else 1.0)
            return "bubble", {"tail": [box.x + tx * sx, box.y + ty * sy],
                              "corner": callout.float(4, 0.0) or 0.0}, "", True
        bezier = source.message(5)
        editable = source.message(8)
        if bezier is not None:
            nw, nh = point(bezier.message(2))
            data, points = path_data(bezier.message(3))
            if not points:
                return None
            left, top = min(x for x, _ in points), min(y for _, y in points)
            right, bottom = max(x for x, _ in points), max(y for _, y in points)
            nw = nw if nw > 0 else right - left
            nh = nh if nh > 0 else bottom - top
            sx, sy = (box.w / nw if nw else 1.0), (box.h / nh if nh else 1.0)
            data, points = path_data(bezier.message(3), sx, sy)
            if _rectangle(bezier.message(3)):
                return "rectangle", {}, "", True
            if _circle(bezier.message(3)):
                return "ellipse", {}, "", True
            closed = "Z" in data
            return "path", {}, data, closed
        if editable is not None:
            nw, nh = point(editable.message(2))
            sx, sy = (box.w / nw if nw else 1.0), (box.h / nh if nh else 1.0)
            out, closed_any = [], False
            for subpath in editable.messages(1):
                nodes = subpath.messages(1)
                if not nodes:
                    continue
                coords = [(point(node.message(1)), point(node.message(2)), point(node.message(3))) for node in nodes]
                coords = [tuple((x * sx, y * sy) for x, y in triple) for triple in coords]
                out.append(f"M {coords[0][1][0]:.2f} {coords[0][1][1]:.2f}")
                pairs = list(itertools.pairwise(coords))
                closed = subpath.bool(2)
                if closed:
                    pairs.append((coords[-1], coords[0]))
                for before, after in pairs:
                    out.append(f"C {before[2][0]:.2f} {before[2][1]:.2f} {after[0][0]:.2f} {after[0][1]:.2f} "
                               f"{after[1][0]:.2f} {after[1][1]:.2f}")
                if closed:
                    out.append("Z")
                    closed_any = True
            return ("path", {}, " ".join(out), closed_any) if out else None
        return None

    def connection(self, item: Archive, box: Box, source: Message | None, stroke: Stroke | None,
                   frame: Frame | None) -> Element:
        line = source.message(7) if source is not None else None
        bezier = line.message(1) if line is not None else None
        made = Connector(box, stroke=stroke, frame=frame, ident=str(item.ident))
        made.start_glue = str(item.message.reference(2) or "") or None
        made.end_glue = str(item.message.reference(3) or "") or None
        if bezier is None:
            made.start, made.end = (box.x, box.y), (box.x + box.w, box.y + box.h)
            return made
        nw, nh = point(bezier.message(2))
        _, points = path_data(bezier.message(3))
        if not points:
            made.start, made.end = (box.x, box.y), (box.x + box.w, box.y + box.h)
            return made
        sx = box.w / nw if nw else 1.0
        sy = box.h / nh if nh else 1.0
        placed = [(box.x + x * sx, box.y + y * sy) for x, y in points]
        made.start, made.end = placed[0], placed[-1]
        if len(placed) == 3 and line.int(2, 0) == 0:
            made.route, made.points = "curved", [placed[1]]
            along = math.dist(placed[0], placed[1]) + math.dist(placed[1], placed[2])
            if along <= math.dist(placed[0], placed[2]) + 0.5:
                made.route, made.points = "straight", []
        elif len(placed) > 2:
            made.route, made.points = "elbow", placed[1:-1]
        return made

    def _sized(self, box: Box, frame: Frame, source: Message | None) -> Box:
        """A text box that sizes itself to its words (stored 0 by 0): as large as Keynote last
        laid them out (its path's natural size), placed by the point its words grow from."""

        natural = None
        for number in (5, 8, 3, 4):
            found = source.message(number) if source is not None else None
            if found is not None:
                size = found.message(2) if number in (5, 8) else found.message(3)
                if size is not None:
                    natural = point(size)
                    break
        width, height = box.w, box.h
        if width <= 1:
            width = natural[0] if natural and natural[0] > 1 else max(len(max(frame.words.split("\n"), key=len)) * (
                _first_size(frame) or 24) * 0.5, 40.0)
            align = next((paragraph.align for paragraph in frame.paragraphs if paragraph.words.strip()), "start")
            x = box.x - (width / 2 if align == "middle" else width if align == "end" else 0.0)
        else:
            x = box.x
        if height <= 1:
            height = natural[1] if natural and natural[1] > 1 else (frame.words.count("\n") + 1) * (
                _first_size(frame) or 24) * 1.25
            y = box.y - (height / 2 if frame.anchor == "middle" else height if frame.anchor == "bottom" else 0.0)
        else:
            y = box.y
        return Box(x, y, width, height, box.rotate, box.flip_h, box.flip_v)

    # -- words --

    def paragraphs(self, storage: Archive) -> list[Paragraph]:
        """A storage's words as paragraphs of runs, with their lists, levels and looks."""

        message = storage.message
        text = "".join(message.texts(3))
        if not text:
            return []

        def table(number: int, carry: bool) -> list[tuple[int, int | None]]:
            found = message.message(number)
            out: list[tuple[int, int | None]] = []
            previous = None
            for entry in sorted(found.messages(1) if found is not None else [], key=lambda e: e.int(1, 0) or 0):
                ident = entry.reference(2)
                if ident is None and carry:
                    ident = previous
                previous = ident
                out.append((entry.int(1, 0) or 0, ident))
            return out

        para_styles = table(5, True)
        char_styles = table(8, False)
        list_styles = table(7, True)
        attachments = dict(table(9, False))
        links = table(11, False)
        data = message.message(6)
        levels = sorted(((entry.int(1, 0) or 0, entry.int(2, 0) or 0) for entry in data.messages(1)) if data else [])
        paragraphs: list[Paragraph] = []
        at = 0
        for line in re.split("[\n\u2029]", text):
            start, end = at, at + len(line)
            at = end + 1
            style = _at(para_styles, start)
            look = self._look(style)
            level = _at(levels, start) or 0
            label = self._label(_at(list_styles, start), level)
            paragraph = Paragraph(level=level, bullet=label if line.strip() else None, align=look.get("align"),
                                  space_before=float(look.get("before") or 0.0),
                                  space_after=float(look.get("after") or 0.0))
            if look.get("relative"):
                paragraph.line_spacing = float(look["relative"])
            if look.get("exact"):
                paragraph.line_points = float(look["exact"])
            bounds = sorted({start, end} | {index for index, _ in char_styles if start < index < end}
                            | {index for index, _ in links if start < index < end}
                            | {index for index in attachments if start <= index < end}
                            | {index + 1 for index in attachments if start <= index < end - 1})
            for run_start, run_end in itertools.pairwise(bounds):
                piece = text[run_start:run_end]
                if not piece:
                    continue
                if piece == "￼" and run_start in attachments:
                    run = self._attachment(attachments[run_start], look)
                    if run is not None:
                        paragraph.runs.append(run)
                    continue
                own = self._character(_at(char_styles, run_start))
                merged = {**look, **{key: value for key, value in own.items() if value is not None}}
                family, bold, italic = family_of(merged.get("font"))  # type: ignore[arg-type]
                link_ident = _at(links, run_start)
                link = None
                linked = self.get(link_ident)
                if linked is not None and linked.type == HYPERLINK:
                    link = linked.message.text(2)
                baseline = {1: 0.33, 2: -0.33}.get(int(merged.get("script") or 0), 0.0)
                for index, part in enumerate(re.split("[\u2028\u000b]", piece)):
                    if index:
                        paragraph.runs.append(Run("\n"))
                    if part:
                        paragraph.runs.append(Run(
                            part.replace("￼", ""), bold=bool(merged.get("bold")) or bold,
                            italic=bool(merged.get("italic")) or italic, underline=bool(merged.get("underline")),
                            baseline=baseline, size=merged.get("size"), colour=merged.get("colour"),  # type: ignore[arg-type]
                            font=family, link=link, caps=bool(merged.get("caps"))))
            if len(paragraph.runs) == 1 and paragraph.runs[0].tex is not None and not line.replace("￼", "").strip():
                paragraph.display = paragraph.runs[0].tex
                paragraph.size = paragraph.runs[0].size
                paragraph.runs = []
            if not paragraph.runs and paragraph.size is None:
                paragraph.size = look.get("size")  # type: ignore[assignment]
            paragraphs.append(paragraph)
        return paragraphs

    def _properties(self, characters: Message, out: dict[str, object]) -> None:
        """``TSWP.CharacterStylePropertiesArchive``'s look, where not said nearer."""

        for key, number, read in (("bold", 1, "bool"), ("italic", 2, "bool"), ("size", 3, "float"),
                                  ("font", 5, "text"), ("script", 10, "int"), ("underline", 11, "int"),
                                  ("caps", 13, "int")):
            if key not in out and characters.has(number):
                out[key] = getattr(characters, read)(number)
        if "colour" not in out and characters.has(7) and not characters.bool(6):
            out["colour"] = colour(characters.message(7))
        if "colour" not in out and characters.has(46):
            fill = self.fill(characters.message(46))
            if isinstance(fill, Colour):
                out["colour"] = fill
            elif isinstance(fill, Gradient) and fill.stops:
                out["colour"] = fill.stops[len(fill.stops) // 2][1]
        if "caps" in out:
            out["caps"] = out["caps"] == 1

    def _look(self, style: int | None) -> dict[str, object]:
        """A paragraph style's look, through its parents: its words' and its paragraph's."""

        out: dict[str, object] = {}
        for found in self._chain(style):
            characters = found.message.message(11)
            if characters is not None:
                self._properties(characters, out)
            paragraph = found.message.message(12)
            if paragraph is None:
                continue
            if "align" not in out and paragraph.has(1):
                out["align"] = ALIGNS.get(paragraph.int(1, 0) or 0, "start")
            if "before" not in out and paragraph.has(21):
                out["before"] = paragraph.float(21, 0.0)
            if "after" not in out and paragraph.has(20):
                out["after"] = paragraph.float(20, 0.0)
            spacing = paragraph.message(13)
            if "spacing" not in out and spacing is not None and spacing.has(2):
                out["spacing"] = True
                mode, amount = spacing.int(1, 0) or 0, spacing.float(2, 1.0) or 1.0
                if mode == 0:
                    out["relative"] = amount
                elif mode == 2:
                    out["exact"] = amount
        return out

    def _character(self, style: int | None) -> dict[str, object]:
        out: dict[str, object] = {}
        found = self.get(style)
        if found is not None and found.type == CHARACTER_STYLE:
            characters = found.message.message(11)
            if characters is not None:
                self._properties(characters, out)
        return out

    def _label(self, style: int | None, level: int) -> str | None:
        """A list style's label at a level (types 11: none 0, image 1, string 2, number 3)."""

        for found in self._chain(style):
            kinds = found.message.ints(11)
            if len(kinds) > level:
                return {1: "bullet", 2: "bullet", 3: "number"}.get(kinds[level])
        return None

    def _attachment(self, ident: int | None, look: dict[str, object]) -> Run | None:
        """What a U+FFFC holds: an equation (its TeX), a slide's number, or nothing shown."""

        found = self.get(ident)
        if found is None:
            return None
        if found.type == SLIDE_NUMBER or (found.type == NUMBER_ATTACHMENT and (
                found.message.message(1) is None or (found.message.message(1).int(2, 0) or 0) == 0)) or (
                found.type in TEXTUAL_ATTACHMENTS and (found.message.int(2, 0) or 0) == 0):
            return Run(str(self.number), field="slide-number", size=look.get("size"))  # type: ignore[arg-type]
        if found.type == DRAWABLE_ATTACHMENT:
            drawable = self.get(found.message.reference(1))
            if drawable is not None and drawable.type == IMAGE:
                source = drawable.message.text(103) or drawable.message.text(100)
                tex = equation_tex(source) if source else None
                if tex:
                    properties = drawable.message.message(101)
                    size = properties.float(3) if properties is not None else None
                    return Run("", tex=tex, size=size or look.get("size"))  # type: ignore[arg-type]
            self.report.note("A picture placed among a text box's words is left out of them.")
        return None


def _at(entries: list[tuple[int, int | None]], index: int) -> int | None:
    found = None
    for start, value in entries:
        if start > index:
            break
        found = value
    return found


def _connections_first(elements: list[Element]) -> list[Element]:
    """Lines joining shapes drawn under them, as Keynote draws a connection line."""

    joined = [element for element in elements if isinstance(element, Connector) and (
        element.start_glue or element.end_glue)]
    return joined + [element for element in elements if element not in joined] if joined else elements


def _first_size(frame: Frame) -> float | None:
    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            if run.size:
                return run.size
    return None


def _turn(members: list[Element], box: Box) -> None:
    """A turned group's members turned with it, about its middle."""

    cx, cy = box.centre
    theta = math.radians(box.rotate)

    def turned(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - cx, y - cy
        return cx + dx * math.cos(theta) - dy * math.sin(theta), cy + dx * math.sin(theta) + dy * math.cos(theta)

    for member in members:
        mx, my = turned(*member.box.centre)
        member.box = Box(mx - member.box.w / 2, my - member.box.h / 2, member.box.w, member.box.h,
                         (member.box.rotate + box.rotate) % 360, member.box.flip_h, member.box.flip_v)
        if isinstance(member, Connector):
            member.start, member.end = turned(*member.start), turned(*member.end)
            member.points = [turned(*point) for point in member.points]
        if isinstance(member, Group):
            _turn(member.children, Box(box.x, box.y, box.w, box.h, 0.0))


def _rectangle(path: Message | None) -> bool:
    """Whether a path is a plain box: four corners, straight sides, closed."""

    if path is None:
        return False
    elements = path.messages(1)
    kinds = [element.int(1, 0) for element in elements]
    while kinds and kinds[-1] == 1:
        kinds.pop()
    if kinds not in ([1, 2, 2, 2, 5], [1, 2, 2, 2, 2, 5]):
        return False
    points = [point(element.messages(2)[0]) for element in elements if element.messages(2)]
    xs = sorted({round(x, 2) for x, _ in points})
    ys = sorted({round(y, 2) for _, y in points})
    return len(xs) == 2 and len(ys) == 2


def _circle(path: Message | None) -> bool:
    if path is None:
        return False
    kinds = [element.int(1, 0) for element in path.messages(1)]
    while kinds and kinds[-1] == 1 and len(kinds) > 6:
        kinds.pop()
    return kinds == [1, 4, 4, 4, 4, 5]


def _is_circle(source: Message) -> bool:
    bezier = source.message(5)
    return bezier is not None and _circle(bezier.message(3))


def read(path: Path, report: Report, progress: Progress = quiet) -> Presentation:
    """The Keynote deck at ``path`` as a ``Presentation``."""

    try:
        package = Package(path)
    except zipfile.BadZipFile:
        raise ValueError(f"{path.name} is not a Keynote file.") from None
    try:
        reader = Reader(package, report, progress)
        reader.load()
        return reader.presentation(path.stem)
    finally:
        package.close()
