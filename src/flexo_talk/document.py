"""A deck as a document: YAML or JSON that says what the Python API says.

```yaml
schema_version: 1
deck:
  id: results
  theme: paper
  look: classic
  footer: Group meeting
slides:
- layout: title
  title: Figures that draw themselves
  author: Kiarash Jamali
- title: Why another figure tool?
  body:
  - bullets:
    - Figures take hours to draw
    - - boxes drift out of line          # a nested list is the level below
  notes: Everyone here has redrawn a figure at 2 a.m.
- title: The model
  layout: two-columns
  left:
  - text: Write what the model *is*
  right:
  - figure: model.yaml                   # a flexo figure file, or model.py:figure
- title: Training
  body:
  - plot: plots.py:loss                  # a function returning a matplotlib figure
```

Each slide is a mapping: ``layout`` (``content`` when left out), the settings the
matching ``Deck`` call takes, and its regions -- ``body``, ``left`` and
``right``, or ``columns`` (a list of block lists) -- each a list of blocks. A
block is a mapping named by its kind (``bullets``, ``text``, ``figure``,
``image``, ``plot``, ``table``, ``gallery``, ``code``, ``quote``, ``stats``,
``callout``) with that call's options beside it. Files are found next to the
document. A figure is a flexo figure file, a flexo figure document written
inline, or ``file.py:function`` (a function returning a flexo figure); a plot is
``file.py:function`` returning a matplotlib figure, called inside
``deck.plotting()`` (and given the deck, if it takes an argument). A picture
(``image``) may be cropped: ``crop: [x, y, width, height]``, the part kept as
fractions of the whole picture (``[0.1, 0, 0.8, 1]`` keeps the middle 80% across),
and drawn round with ``mask: circle``.

``read_deck`` makes a ``Deck`` from a file, ``deck_from_document`` from a parsed
document, and ``deck_document`` writes any deck -- one made in Python too --
back as a document.
"""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import inspect
import json
import os
import re
import signal
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import fields, replace
from pathlib import Path, PurePath
from typing import Any

import yaml
from flexo.diagnostics import described
from flexo.roundtrip import rewrite

from flexo_talk.deck import (
    ACROSS,
    DOWN,
    LAYOUTS,
    LOGO_HEIGHT,
    Deck,
    DeckStyle,
    Reference,
    Region,
    SettingError,
    Slide,
    _Figure,
    _Plot,
    displayed,
    named_colour,
    share_of,
)

SCHEMA_VERSION = 1

BLOCKS: dict[str, tuple[str, ...]] = {
    "bullets": ("size", "numbered", "reveal", "colour", "plain"),
    "text": ("size", "align", "muted", "colour"),
    "figure": ("turn", "width", "description", "caption"),
    "image": ("width", "crop", "mask", "description", "caption"),
    "plot": ("aspect",),
    "table": ("header", "align", "size", "caption", "outline"),
    "gallery": ("columns", "height", "crop", "size", "align"),
    "code": ("size",),
    "quote": ("by", "size"),
    "stats": ("colour", "size"),
    "callout": ("title", "colour", "size"),
    "math": ("size", "align", "colour"),
    "mechanism": ("lone_pairs", "charges", "per_row", "arrow_colour"),
}
"""Each block kind and the options it takes beside its value."""

DECK_KEYS = (
    "id", "theme", "look", "palette", "font", "title_font", "figure_font", "footer", "background",
    "conventions", "sketch", "style", "logos", "logos_on", "logo_height",
)
COMMON_KEYS = ("layout", "notes", "footnotes", "background", "shade", "skip")
"""The keys every slide takes. ``skip: true`` is Keynote's Skip Slide: the slide is kept,
and edited, but the studio neither presents nor exports it."""
SLIDE_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("title", "subtitle", "author", "date"),
    "section": ("title", "subtitle"),
    "statement": ("words", "by"),
    "agenda": ("title",),
    "content": ("title", "subtitle", "dark", "align", "body"),
    "figure": ("title", "subtitle", "dark", "align", "body"),
    "blank": ("title", "subtitle", "dark", "align", "body"),
    "two-columns": ("title", "subtitle", "dark", "align", "split", "left", "right"),
    "columns": ("title", "subtitle", "dark", "align", "widths", "columns"),
}
"""The keys a slide of each layout takes, beside ``COMMON_KEYS``."""

STYLE_FIELDS = tuple(item.name for item in fields(DeckStyle))


class DeckDocumentError(ValueError):
    """A deck document that says something the deck cannot be made from; ``where``
    names the place (``slides[3].left[1]``)."""

    def __init__(self, where: str, message: str) -> None:
        super().__init__(f"{where}: {message}" if where else message)
        self.where = where
        self.message = message


class MissingFile(DeckDocumentError):
    """A file the document names (a picture, a figure file) that is not there: ``name``
    as the document writes it."""

    def __init__(self, where: str, message: str, name: str) -> None:
        super().__init__(where, message)
        self.name = name


class InvalidFigure(DeckDocumentError):
    """A figure written in the deck that cannot be drawn as it is written (a span that ends
    before it starts): said in plain words, in a box where it would be, the rest of its
    slide drawn. Where only some of its shapes can't be (a protein with no length), the
    rest of it is drawn all the same (``drawn``), each of those a plain box of its words;
    ``where`` then ends in ``#shape:what`` (its id, and what of it is wrong: ``length``)."""

    def __init__(self, where: str, message: str, drawn: object = None) -> None:
        super().__init__(where, message)
        self.drawn = drawn


class UnknownLayout(DeckDocumentError):
    """A slide of a layout there is none of (a typo, ``layout: quote``): drawn as Content
    all the same, every object it has in its body, and said in plain words."""


class InvalidObject(DeckDocumentError):
    """An object written in the deck that can't be made as written (a kind there is none
    of, a table that is not rows): a box where it would be, the rest of its slide drawn,
    and left empty when the deck is presented or exported."""


class UntrustedCode(DeckDocumentError):
    """Python a deck names, in a folder the studio has not been told to trust: not run."""


# -- reading ------------------------------------------------------------------------------


def load_document(source: str | Path) -> dict[str, Any]:
    """A deck document from a ``.yaml``, ``.yml``, or ``.json`` file. Whatever is wrong
    with the file -- not text, a mistake in its YAML or JSON (said with its line), a
    key written twice -- is said in words."""

    path = Path(source)
    try:
        data = path.read_bytes()
    except IsADirectoryError:
        raise DeckDocumentError("", f"{path.name} is a folder, not a deck document.") from None
    except OSError as error:
        raise DeckDocumentError("", f"Cannot read {path.name}: {error.strerror or error}.") from None
    text = _text(data, path.name)
    try:
        json_file = path.suffix.lower() == ".json"
        document = json.loads(text) if json_file else parse_document(text)
    except json.JSONDecodeError as error:
        raise DeckDocumentError("", f"{path.name}, line {error.lineno}, column {error.colno}: {error.msg}") from None
    except yaml.YAMLError as error:
        raise DeckDocumentError("", f"{path.name}: {_yaml_said(error, text)}") from None
    except RecursionError:
        raise DeckDocumentError("", f"{path.name} is nested too deeply to read.") from None
    if not isinstance(document, dict):
        raise DeckDocumentError(
            "", f"{path.name} is not a deck document. A deck document is a mapping with deck and slides."
        )
    _bounded(document, path.name)
    return document


def parse_document(text: str) -> object:
    """Deck document text read as ``load_document`` reads a file: as YAML 1.2, with a key
    written twice said rather than lost (JSON is YAML too)."""

    return yaml.load(text, Loader=_DocumentLoader)


def _text(data: bytes, name: str) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DeckDocumentError("", f"{name} is not a UTF-8 text file.") from None
    if "\x00" in text:
        raise DeckDocumentError("", f"{name} is not a text file (it contains a NUL character).")
    return text


_BASE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class _DocumentLoader(_BASE_LOADER):  # type: ignore[misc, valid-type]
    """YAML read as YAML 1.2 reads it -- ``yes`` and ``no`` are words, ``012`` is twelve,
    a date is the words written -- with a key written twice said rather than lost."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, list | dict):
                continue
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


_DocumentLoader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers if tag not in {
        "tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float",
        "tag:yaml.org,2002:timestamp"}]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_DocumentLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
_DocumentLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"), list("-+0123456789")
)


_DocumentLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"),
    list("-+.0123456789"),
)


def _construct_int(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> int:
    value = loader.construct_scalar(node)
    return int(value, 0) if value[:2] in {"0o", "0x"} else int(value, 10)


_DocumentLoader.add_constructor("tag:yaml.org,2002:int", _construct_int)


def _yaml_said(error: yaml.YAMLError, text: str) -> str:
    mark = getattr(error, "problem_mark", None) or getattr(error, "context_mark", None)
    problem = getattr(error, "problem", None) or str(error).splitlines()[0]
    lines = text.splitlines()
    if mark is not None and mark.line < len(lines) and "\t" in lines[mark.line][: mark.column + 1]:
        problem = "found a tab; YAML must be indented with spaces"
    where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark is not None else ""
    return f"{where}{problem}"


_MOST_PARTS = 2_000_000
"""More parts than any deck holds: a document past it (aliases repeating a list into
billions) is refused rather than read for minutes."""

_DEEPEST = 100
"""More levels than any deck nests (a figure's groups, a list's levels): a document
deeper is refused in words, before Python runs out of room to read it."""


def _bounded(document: object, name: str) -> None:
    count = 0
    stack = [(document, 0)]
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > _MOST_PARTS:
            raise DeckDocumentError("", f"{name} has more than {_MOST_PARTS:,} items, more than a deck can hold.")
        if depth > _DEEPEST:
            raise DeckDocumentError("", f"{name} nests lists or mappings more than {_DEEPEST} levels deep.")
        if isinstance(item, dict):
            stack.extend((value, depth + 1) for value in item.values())
            stack.extend((key, depth + 1) for key in item if isinstance(key, str))
        elif isinstance(item, list):
            stack.extend((value, depth + 1) for value in item)
        elif isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                # A JSON escape of half a UTF-16 pair ("\\ud800"): not a character at all.
                raise DeckDocumentError(
                    "", f"{name} contains an invalid character (half of a surrogate pair) in {item!r:.40}."
                ) from None


def read_deck(source: str | Path) -> Deck:
    """The deck a document file describes; its files are found next to it."""

    path = Path(source).resolve()
    return deck_from_document(load_document(path), path.parent)


def is_deck_document(document: object) -> bool:
    return isinstance(document, dict) and "slides" in document and "nodes" not in document


def deck_from_document(
    document: dict[str, Any],
    base: str | Path = ".",
    *,
    errors: list[DeckDocumentError] | None = None,
) -> Deck:
    """A deck from its document. Files it names are found from ``base``.

    With ``errors`` given, a slide that cannot be made is reported there and
    stands in the deck as a blank slide, so the others keep their places, and a
    picture or figure whose file is missing is reported there and stands in its
    slide as a box saying so; without it, the first such slide raises
    ``DeckDocumentError``.
    """

    base = Path(base).resolve()
    if not isinstance(document, dict):
        raise DeckDocumentError("", "A deck document must be a mapping with deck and slides.")
    _bounded(document, "The document")  # one not read from a file too (the studio's, an agent's)
    _only(document, ("schema_version", "deck", "slides"), "")
    version = document.get("schema_version", SCHEMA_VERSION)
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise DeckDocumentError(
            "schema_version", f"Unsupported schema_version {version!r}. This version of flexo-talk reads "
            f"version {SCHEMA_VERSION}."
        )
    deck = make_deck(document.get("deck") or {}, base, missing=errors)
    slides = document.get("slides") or []
    if not isinstance(slides, list):
        raise DeckDocumentError("slides", "slides must be a list.")
    for index, data in enumerate(slides):
        where = f"slides[{index}]"
        try:
            add_slide(deck, data, base, where, missing=errors)
        except DeckDocumentError as error:
            if errors is None:
                raise
            errors.append(error)
            _stand_in(deck, index)
        except (ValueError, TypeError, OSError, AttributeError) as error:
            if errors is None:
                raise DeckDocumentError(where, str(error)) from error
            errors.append(DeckDocumentError(where, str(error)))
            _stand_in(deck, index)
    return deck


def _stand_in(deck: Deck, index: int) -> None:
    # A slide that failed part way is replaced, so the next keeps its number.
    del deck.slides[index:]
    deck.slide(layout="blank")


def make_deck(data: dict[str, Any], base: Path, *, missing: list[DeckDocumentError] | None = None) -> Deck:
    """The ``Deck`` the ``deck`` mapping of a document describes. With ``missing`` given, a
    logo whose file is not there is said there, and keeps its place in the row (the slide
    shows where it was, while editing); without it, it is an error."""

    if not isinstance(data, dict):
        raise DeckDocumentError("deck", "deck must be a mapping of deck settings.")
    _only(data, DECK_KEYS, "deck")
    changes = data.get("style") or {}
    if not isinstance(changes, dict):
        raise DeckDocumentError("deck.style", "style must be a mapping of DeckStyle fields.")
    _only(changes, STYLE_FIELDS, "deck.style")
    try:
        theme = data.get("theme", "paper")
        if isinstance(theme, str) and theme.lower().endswith((".yaml", ".yml", ".json")):
            theme = str(_file(base, theme, "deck.theme"))
        palette = data.get("palette", "default")
        if isinstance(palette, str) and palette.lower().endswith((".yaml", ".yml", ".json")):
            palette = str(_file(base, palette, "deck.palette"))
        background = data.get("background", True)
        if isinstance(background, str) and background and not background.startswith("#"):
            # A picture behind every slide is found beside the document, as a slide's is.
            background = str(_file(base, background, "deck.background"))
        logos = _logos(base, data.get("logos"), missing)
        deck = Deck(
            data.get("id") if data.get("id") is not None else "talk",
            theme=theme,
            palette=palette,
            font=data.get("font"),
            title_font=data.get("title_font"),
            figure_font=data.get("figure_font"),
            conventions=data.get("conventions"),
            sketch=data.get("sketch"),
            background=background,
            footer=data.get("footer"),
            look=data.get("look"),
            logos=logos,
            logos_on=data.get("logos_on") or "title",
            logo_height=LOGO_HEIGHT if data.get("logo_height") is None else data["logo_height"],
        )
        # The document's proportions are changes to what the look and theme set.
        try:
            deck.style = replace(deck.style, **changes)
        except (TypeError, ValueError) as error:
            raise DeckDocumentError(_at("deck.style", changes, error), str(error)) from None
    except DeckDocumentError:
        raise
    except SettingError as error:
        raise DeckDocumentError(_at("deck", data, error), str(error)) from None
    except Exception as error:
        raise DeckDocumentError("deck", str(error)) from error
    deck.source = {**deck.source, **{key: value for key, value in data.items() if key != "style"}}
    return deck


def _logos(base: Path, value: object, missing: list[DeckDocumentError] | None) -> object:
    """The logos a deck names, each found beside the document; anything but a list of names
    is left for the deck to say what it should be."""

    if value is None:
        return []
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
        return value
    found = []
    for index, name in enumerate(names):
        try:
            found.append(str(_file(base, name, f"deck.logos[{index}]")))
        except MissingFile as error:
            if missing is None:
                raise
            # Kept where it stands in the row, its file not there: the slide shows where.
            missing.append(error)
            found.append(str(base / name))
    return found


def add_slide(
    deck: Deck, data: object, base: Path, where: str, *, missing: list[DeckDocumentError] | None = None
) -> Slide:
    """Add the slide ``data`` describes to ``deck``. With ``missing`` given, a file it names
    that is not there is said there, and the slide is made without it (see ``add_block``)."""

    if not isinstance(data, dict):
        raise DeckDocumentError(where, "A slide must be a mapping (title, layout, body, \u2026).")
    layout = data.get("layout") or "content"  # none written (an empty ``layout:``) is Content
    if layout not in LAYOUTS:
        if missing is None:
            raise DeckDocumentError(
                f"{where}.layout", f"Unknown layout \u201c{layout}\u201d. Available layouts: {', '.join(LAYOUTS)}."
            )
        # Drawn as Content rather than not at all, and said as the Layout menu names layouts.
        missing.append(UnknownLayout(
            f"{where}.layout", f"\u201c{layout}\u201d isn\u2019t a layout: drawn as Content. Choose one from Layout."
        ))
        data, layout = _as_content(data), "content"
    _only(data, COMMON_KEYS + SLIDE_KEYS[layout], where)
    if not isinstance(data.get("skip", False), bool):
        raise DeckDocumentError(f"{where}.skip", "skip must be true or false.")
    background = data.get("background")
    # A picture file, unless it names a colour (#1b2a41, or one of the theme's: accent).
    if isinstance(background, str) and not background.startswith("#") and not named_colour(background):
        try:
            background = str(_file(base, background, f"{where}.background"))
        except MissingFile as error:
            if missing is None:
                raise
            missing.append(error)
            background = None
    shade = data.get("shade", 0.0)
    text = _text_of(data, where)
    try:
        slide = _slide_of(deck, data, layout, background, shade, text, base, where, missing)
    except DeckDocumentError:
        raise
    except (ValueError, TypeError) as error:
        raise DeckDocumentError(_at(where, data, error), str(error)) from None
    if data.get("notes"):
        slide.notes(text("notes"))
    footnotes = data.get("footnotes") or []
    if isinstance(footnotes, str | int | float):
        footnotes = [footnotes]
    if not isinstance(footnotes, list) or not all(_is_words(note) for note in footnotes):
        raise DeckDocumentError(f"{where}.footnotes", "footnotes must be text or a list of text.")
    for note in footnotes:
        slide.footnote(str(note))
    slide.placeholders = frozenset(
        key for key in ("title", "subtitle", "words") if key in data and not str(data[key] or "").strip()
    )
    slide.source = {key: value for key, value in data.items() if key not in {"body", "left", "right"}}
    if layout == "columns":
        slide.source.pop("columns", None)
    return slide


def _as_content(data: dict[str, Any]) -> dict[str, Any]:
    """A slide of a layout there is none of, as a Content slide: its title (or its words),
    subtitle and the rest it shares with one kept, and every object it has -- in its body,
    its columns -- in its body, in order."""

    blocks: list[object] = []
    for key in ("body", "left", "right"):
        if isinstance(data.get(key), list):
            blocks += data[key]
    for column in data.get("columns") if isinstance(data.get("columns"), list) else []:
        if isinstance(column, list):
            blocks += column
    kept = {key: value for key, value in data.items() if key in COMMON_KEYS + SLIDE_KEYS["content"]}
    kept.pop("layout", None)
    if "title" not in kept and _is_words(data.get("words")):
        kept["title"] = data["words"]
    return {**kept, "body": blocks}


def _at(where: str, data: dict[str, Any], error: Exception) -> str:
    """Where a setting's error is: at its key, when the error names one this mapping has."""

    key = getattr(error, "key", None)
    return f"{where}.{key}" if isinstance(error, SettingError) and key in data else where


def _is_words(value: object) -> bool:
    """Words, or a number written as words; never yes/no, which YAML reads as true/false."""

    return isinstance(value, str | int | float) and not isinstance(value, bool)


def _slide_of(deck: Deck, data: dict[str, Any], layout: str, background: object, shade: object,
              text: Callable[[str], str], base: Path, where: str,
              missing: list[DeckDocumentError] | None = None) -> Slide:
    if layout == "title":
        slide = deck.title(
            text("title"), subtitle=text("subtitle"), author=text("author"), date=text("date"),
            background=background, shade=shade,
        )
    elif layout == "section":
        slide = deck.section(text("title"), subtitle=text("subtitle"), background=background, shade=shade)
    elif layout == "statement":
        slide = deck.statement(text("words"), by=text("by"), background=background, shade=shade)
    elif layout == "agenda":
        slide = deck.agenda(text("title") or "Outline")
        slide.background, slide.shade = background, shade
    else:
        widths = data.get("widths")
        columns = data.get("columns") if layout == "columns" else None
        if layout == "columns":
            if not isinstance(columns, list) or not columns:
                raise DeckDocumentError(f"{where}.columns", "A columns slide needs columns, a list of block lists.")
            if widths is not None and (not isinstance(widths, list) or len(widths) != len(columns)):
                raise DeckDocumentError(f"{where}.widths", "widths must give one share for each column.")
        slide = deck.slide(
            text("title"),
            layout=layout,
            subtitle=text("subtitle"),
            split=data.get("split", 0.5),
            columns=len(columns) if columns else 3,
            widths=widths,
            background=background,
            shade=shade,
            dark=data.get("dark"),
            align=data.get("align"),
        )
        if layout == "columns":
            places = {region.name: blocks for region, blocks in zip(slide.columns, columns, strict=True)}
            names = {region.name: f"{where}.columns[{index}]" for index, region in enumerate(slide.columns)}
        else:
            places = {name: data.get(name) for name in slide.regions}
            names = {name: f"{where}.{name}" for name in slide.regions}
        for name, blocks in places.items():
            if blocks is None:
                continue
            if not isinstance(blocks, list):
                raise DeckDocumentError(names[name], "A region must be a list of blocks.")
            for index, block in enumerate(blocks):
                region, count = slide.regions[name], len(slide.regions[name].blocks)
                try:
                    add_block(region, block, base, f"{names[name]}[{index}]", missing=missing)
                except DeckDocumentError as error:
                    if missing is None:
                        raise
                    # One object that can't be made is a box where it would be, the rest of its
                    # slide drawn -- not a slide that is not drawn.
                    del region.blocks[count:], region.sources[count:]
                    missing.append(InvalidObject(error.where, error.message))
                    kind = next((key for key in block if key in BLOCKS), None) if isinstance(block, dict) else None
                    noun = {"bullets": "list", "image": "picture", "stats": "object", "math": "equation"}.get(
                        kind, kind or "object")
                    region.stand_in("object", "", said=f"This {noun} can\u2019t be drawn as it is")
    return slide


def _text_of(data: dict[str, Any], where: str) -> Callable[[str], str]:
    def text(key: str) -> str:
        value = data.get(key)
        if value is None:
            return ""
        if isinstance(value, datetime.date):  # read by a YAML 1.1 reader (yaml.safe_load)
            return value.isoformat()
        if not _is_words(value):
            raise DeckDocumentError(f"{where}.{key}", f"{key} must be text, not {described(value)}.")
        return str(value)

    return text


_STAND_INS = {"image": "picture", "gallery": "picture", "figure": "figure", "plot": "plot"}
"""What a block stands for, said in the box standing in for it while its file is missing."""


def add_block(
    region: Region, block: object, base: Path, where: str, *, missing: list[DeckDocumentError] | None = None
) -> None:
    """Add the block ``block`` describes to ``region``. With ``missing`` given, a picture
    or figure whose file is not there is said there, and a box saying so stands in for it."""

    if not isinstance(block, dict):
        raise DeckDocumentError(where, f"A block must be a mapping named by its kind ({', '.join(BLOCKS)}).")
    kinds = [key for key in block if key in BLOCKS]
    if not kinds:
        named = next(iter(block), None)
        said = f"Unknown kind of block \u201c{named}\u201d" if named is not None else "This block is empty"
        raise DeckDocumentError(where, f"{said}. Name one of {', '.join(BLOCKS)}.")
    if len(kinds) > 1:
        raise DeckDocumentError(
            where, f"This block names more than one kind ({', '.join(kinds)}). Name only one of {', '.join(BLOCKS)}."
        )
    kind = kinds[0]
    # Any block may be a placeholder (``placeholder: true``): see ``Region.placeholders``;
    # and any may build in, appearing on a click (``build: true``): see ``Region.builds``.
    # And any may stand across and down its place where it is asked to (``horizontal:
    # middle``, ``vertical: 0.25``): see ``Region.place``.
    _only(block, (kind, *BLOCKS[kind], "placeholder", "build", "horizontal", "vertical"), f"{where} ({kind})")
    value = block[kind]
    options = {key: block[key] for key in BLOCKS[kind] if key in block}
    here = f"{where} ({kind})"
    if not isinstance(block.get("placeholder", False), bool):
        raise DeckDocumentError(here, "placeholder must be true or false.")
    if not isinstance(block.get("build", False), bool):
        raise DeckDocumentError(here, "build must be true or false.")
    shares = {}
    for key, names, said in (("horizontal", ACROSS, "start (left), middle (centre) or end (right)"),
                             ("vertical", DOWN, "top, middle or bottom")):
        if block.get(key) is None:
            continue
        shares[key] = share_of(block[key], names)
        if shares[key] is None:
            raise DeckDocumentError(
                here, f"{key} must be {said}, or a number from 0 to 1 between them, not {block[key]!r}."
            )
    try:
        if kind == "bullets":
            items = value if isinstance(value, list) else [value]
            _check_items(items, here)
            region.bullets(*items, **options)
        elif kind == "text" and isinstance(value, str) and displayed(value):
            # A paragraph that is one equation ($$...$$) is displayed, as LaTeX displays it.
            muted = options.pop("muted", False)
            if muted and not options.get("colour"):
                options["colour"] = "muted"
            region.math(value, **{"align": "middle", **options})
        elif kind == "math":
            # Empty, it is a placeholder (as an empty text is): drawn faintly while editing.
            if not _is_words(value):
                raise DeckDocumentError(here, "math must be a LaTeX equation (for example, math: E = mc^2).")
            region.math(str(value), **options)
        elif kind in {"text", "code", "quote", "callout"}:
            if not _is_words(value):
                raise DeckDocumentError(here, f"A {kind} block must contain text, not {described(value)}.")
            getattr(region, kind)(str(value), **options)
        elif kind == "image":
            region.image(_file(base, str(value), here), **options)
        elif kind == "table":
            if not isinstance(value, list) or not all(isinstance(row, list) for row in value):
                raise DeckDocumentError(here, "A table must be a list of rows, each a list of cells.")
            region.table(value, **options)
        elif kind == "gallery":
            if not isinstance(value, list):
                raise DeckDocumentError(
                    here, "A gallery must be a list of pictures (each a file, or a picture and caption)."
                )
            region.gallery([_picture(base, item, here) for item in value], **options)
        elif kind == "stats":
            if not isinstance(value, list) or not value:
                raise DeckDocumentError(here, "stats must be a list of {value, label} pairs.")
            region.stats(*(_stat(item, here) for item in value), **options)
        elif kind == "figure":
            # A lone shape with no words shows its hint, faintly (see _lone_shape).
            hint = _lone_shape(value)
            shown = {**value, "nodes": [{**value["nodes"][0], "label": hint}]} if hint else value
            # A line to a shape it has none of (``to: nowhere``) is left out, and said.
            strays = _strays(shown)
            if strays:
                shown = {**shown, "edges": strays[1]}
            region.add(_figure(base, shown, here, region), **options)
            if strays and isinstance(region.blocks[-1], _Figure):
                region.blocks[-1].said = (*region.blocks[-1].said, *strays[0])
        elif kind == "plot":
            region.plot(_plot(base, value, here, region), **options)
        elif kind == "mechanism":
            region.mechanism(_steps(value, here), **options)
    except MissingFile as error:
        if missing is None or kind not in _STAND_INS:
            raise
        missing.append(error)
        region.stand_in(_STAND_INS[kind], error.name)
    except InvalidFigure as error:
        # One figure that cannot be drawn is a box saying why, not a slide that is not drawn
        # -- or, where only some of its shapes can't be, drawn with plain boxes for those.
        if missing is None:
            raise
        missing.append(error)
        if error.drawn is not None:
            region.add(error.drawn, **options)
        else:
            region.stand_in("figure", "", said=error.message)
    except DeckDocumentError:
        raise
    except (ValueError, TypeError, OSError) as error:
        raise DeckDocumentError(here, str(error)) from error
    region.sources[-1] = dict(block)
    if block.get("placeholder") or (kind == "figure" and _lone_shape(value)):
        region.placeholders.add(len(region.blocks) - 1)
    if block.get("build"):
        region.builds.add(len(region.blocks) - 1)
    if "horizontal" in shares:
        region.across[len(region.blocks) - 1] = shares["horizontal"]
    if "vertical" in shares:
        region.down[len(region.blocks) - 1] = shares["vertical"]


def _figure_problem(value: dict, error: Exception) -> str:
    """What is wrong with a figure written in the deck, in plain words: flexo's own, naming
    the shape by its words rather than its id ("In “λ infection”, span 1 ends where it
    starts (1)")."""

    from flexo.diagnostics import FlexoError

    if not isinstance(error, FlexoError):
        return str(error)
    names = {
        str(node.get("id")): str(node.get("label") or "").strip()
        for node in value.get("nodes") or []
        if isinstance(node, dict)
    }
    said = []
    for diagnostic in error.diagnostics:
        message = diagnostic.message.strip()
        name = names.get(str(diagnostic.entity_id or ""))
        # (Its first word in lower case after the shape's name, unless it is a name itself:
        # "In “Spike”, a protein needs…", "In “1A8O”, PDB…")
        first = message.split(" ", 1)[0]
        lower = message if len(first) > 1 and first.isupper() else message[:1].lower() + message[1:]
        said.append(f"In “{name}”, {lower}" if name else message[:1].upper() + message[1:])
    return " ".join(said)


def _strays(value: object) -> tuple[list[str], list] | None:
    """A figure's lines to (or from) shapes it has none of: what to say of them, and the
    lines it has without them -- None with none."""

    from flexo.studio.figure_edit import astray

    if not isinstance(value, dict) or not isinstance(value.get("edges"), list):
        return None
    copy = {"nodes": value.get("nodes"), "edges": list(value["edges"])}
    ids: list[str] = []
    said = astray(copy, ids)
    # (Each names the line it is about, to be chosen by: "#edge.2.b-to-nowhere: A line ...".)
    return ([f"#{edge}: {text}" for text, edge in zip(said, ids, strict=True)], copy["edges"]) if said else None


def _stood_in(base: Path, value: dict, error: Exception) -> tuple[object, str, str] | None:
    """A figure only some of whose shapes can't be drawn as written (a protein with no
    length), drawn with each of those a plain box of its words -- the rest as written --
    what to say of them, and the first of them (``id:what``, what of it is wrong); None
    should it not draw even so."""

    from flexo.diagnostics import FlexoError
    from flexo.serialization import parse_figure

    if not isinstance(error, FlexoError):
        return None
    nodes = [node for node in value.get("nodes") or [] if isinstance(node, dict)]
    ids = {str(node.get("id")) for node in nodes}
    wrong = [item for item in error.diagnostics if str(item.entity_id or "") in ids]
    if not wrong or len(wrong) != len(error.diagnostics):
        return None
    bad = {str(item.entity_id) for item in wrong}
    plain = [
        {key: node[key] for key in ("id", "label") if key in node} if str(node.get("id")) in bad else node
        for node in nodes
    ]
    try:
        drawn = parse_figure(_beside(base, {**value, "nodes": plain}))
    except Exception:
        return None
    names = {str(node.get("id")): re.sub(r"[*`$]", "", str(node.get("label") or "")).strip() for node in nodes}
    said = []
    for item in wrong:
        message = item.message.strip()
        first = message.split(" ", 1)[0]
        lower = message if len(first) > 1 and first.isupper() else message[:1].lower() + message[1:]
        name = names.get(str(item.entity_id))
        called = f"\u201c{name}\u201d" if name else "A shape"
        said.append(f"{called} can\u2019t be drawn yet: {lower} Choose it to set this in its panel.")
    first = wrong[0]
    return drawn, " ".join(said), f"{first.entity_id}:{str(first.code or '').rsplit('.', 1)[-1]}"


def _lone_shape(value: object) -> str | None:
    """A figure written in the deck that is one shape with no words and nothing more (as the
    studio starts one) is a placeholder, as an empty text is: the word it shows faintly while
    it waits for its own ("Shape", or "Start" for a flow chart's first step); else None."""

    if not isinstance(value, dict) or value.get("edges") or len(value.get("nodes") or []) != 1:
        return None
    node = value["nodes"][0]
    if not isinstance(node, dict) or set(node) - {"id", "kind", "label"} or str(node.get("label") or "").strip():
        return None
    return {"terminal": "Start", None: "Shape", "block": "Shape", "decision": "Decision"}.get(node.get("kind"))


def _steps(value: object, where: str) -> str | list[str | dict[str, object]]:
    """A mechanism's steps as a document writes them: a SMILES, or a list of SMILES and
    of steps ({smiles, arrows, label, reagents, conditions, arrow, place})."""

    if isinstance(value, str) and value.strip():
        return value
    if not isinstance(value, list) or not value:
        raise DeckDocumentError(
            where, "A mechanism must be a SMILES string or a list of steps, each {smiles, arrows}."
        )
    steps: list[str | dict[str, object]] = []
    for number, step in enumerate(value, start=1):
        here = f"{where}[{number - 1}]"
        if isinstance(step, str):
            steps.append(step)
            continue
        if not isinstance(step, dict):
            raise DeckDocumentError(here, "A step must be a SMILES string or a mapping with smiles and arrows.")
        _only(step, ("smiles", "arrows", "label", "reagents", "conditions", "arrow", "place"), here)
        arrows = step.get("arrows")
        if arrows is not None and not isinstance(arrows, str | list):
            raise DeckDocumentError(here, 'arrows must be a list, such as ["5 -> 2", "2=3 -> 3"].')
        if step.get("place") is not None:
            from flexo.mechanism import place_record

            try:
                place_record(step["place"])
            except (ValueError, IndexError, TypeError, AttributeError):
                raise DeckDocumentError(f"{here}.place", "place must map an atom to its molecule's placement, "
                                        "such as {5: {move: [-1, 0.5], turn: 30, flip: true}}.") from None
        for key in ("smiles", "label", "reagents", "conditions", "arrow"):
            if key in step and step[key] is not None and not _is_words(step[key]):
                raise DeckDocumentError(f"{here}.{key}", f"{key} must be text.")
        steps.append({key: item for key, item in step.items() if item is not None})
    return steps


def _check_items(items: list, where: str) -> None:
    for item in items:
        if isinstance(item, list):
            _check_items(item, where)
        elif not _is_words(item):
            raise DeckDocumentError(where, "bullets must be text, with nested lists for the levels below.")


def _picture(base: Path, item: object, where: str) -> str | tuple[str, str]:
    if isinstance(item, str):
        return str(_file(base, item, where))
    if isinstance(item, dict) and "picture" in item:
        _only(item, ("picture", "caption"), where)
        caption = item.get("caption")
        return str(_file(base, str(item["picture"]), where)), "" if caption is None else caption
    raise DeckDocumentError(where, "A gallery picture must be a file, or a mapping with picture and caption.")


def _stat(item: object, where: str) -> tuple[object, str]:
    # The value and label are checked as words where they are set, not written as Python writes them.
    if isinstance(item, dict) and "value" in item:
        _only(item, ("value", "label"), where)
        label = item.get("label")
        return item["value"], "" if label is None else label
    if isinstance(item, list) and len(item) == 2:
        return item[0], "" if item[1] is None else item[1]
    raise DeckDocumentError(where, "Each stat must be a mapping with value and label.")


_FIGURES: OrderedDict[str, object] = OrderedDict()
_FIGURES_LOCK = threading.Lock()


def _figure(base: Path, value: object, where: str, region: Region) -> object:
    from flexo.serialization import parse_figure
    from flexo.studio.figure_kind import parse

    if isinstance(value, dict):
        # A figure is read once for each version of it: the studio reads the deck on every edit.
        key = json.dumps([str(base), value], sort_keys=True, default=str)
        with _FIGURES_LOCK:
            if key in _FIGURES:
                _FIGURES.move_to_end(key)
                return _FIGURES[key]
        try:
            figure = parse_figure(_beside(base, value))
        except Exception as error:
            stood = _stood_in(base, value, error)
            if stood is not None:
                drawn, said, shape = stood
                raise InvalidFigure(f"{where} #{shape}", said, drawn) from error
            raise InvalidFigure(where, f"This figure can\u2019t be drawn: {_figure_problem(value, error)}") from error
        with _FIGURES_LOCK:
            _FIGURES[key] = figure
            while len(_FIGURES) > 64:
                _FIGURES.popitem(last=False)
        return figure
    if not isinstance(value, str) or not value:
        raise DeckDocumentError(
            where, "A figure must be a figure file, file.py:function, or a flexo figure document."
        )
    if _is_code(value):
        return Reference(value, _maker(base, value, where, lambda made: _as_figure(made, value, where), kind="figure"))
    try:
        path = _file(base, value, where)
        # Its theme, and the pictures and structures its parts draw, found beside the file
        # (as they are found beside the deck for a figure written in it).
        return parse(path.read_text(encoding="utf-8"), path.parent, suffix=path.suffix.lower())
    except DeckDocumentError:
        raise
    except Exception as error:
        raise DeckDocumentError(where, f"{value}: {error}") from error


def _beside(base: Path, figure: dict) -> dict:
    """A figure written in the deck, the pictures and structures its parts draw found
    beside the deck."""

    nodes = figure.get("nodes")
    if not isinstance(nodes, list):
        return figure
    found = []
    for node in nodes:
        properties = node.get("properties") if isinstance(node, dict) else None
        for key in ("source", "density"):
            value = properties.get(key) if isinstance(properties, dict) else None
            if isinstance(value, str) and value and (base / value).is_file():
                properties = {**properties, key: str((base / value).resolve())}
                node = {**node, "properties": properties}
        found.append(node)
    return {**figure, "nodes": found}


def _as_figure(made: object, target: str, where: str) -> object:
    import flexo
    from flexo.ir.semantic import FigureSpec

    if not isinstance(made, flexo.Figure | FigureSpec):
        raise DeckDocumentError(where, f"{target} did not return a flexo figure")
    return made


def _plot(base: Path, value: object, where: str, region: Region) -> Reference:
    if not isinstance(value, str) or not _is_code(value):
        raise DeckDocumentError(
            where, "A plot must be file.py:function, naming a function that returns a matplotlib figure."
        )
    deck = region._slide.deck

    def call(function: Callable[..., object]) -> object:
        return function(deck) if _takes_argument(function) else function()

    # The file is read inside the deck's plotting look too: a style it sets as it is
    # imported is then the deck's for that plot, not the whole app's from then on.
    return Reference(value, _maker(
        base, value, where, lambda made: _as_plot(made, value, where), call=call, around=deck.plotting, deck=deck
    ))


def _as_plot(made: object, target: str, where: str) -> object:
    if not hasattr(made, "savefig"):  # as the studio's worker says it
        raise DeckDocumentError(where, f"{target} did not return a matplotlib figure")
    return made


def _is_code(value: str) -> bool:
    return ".py:" in value


def _maker(
    base: Path,
    target: str,
    where: str,
    check: Callable[[object], object],
    *,
    call: Callable[[Callable[..., object]], object] | None = None,
    around: Callable[[], contextlib.AbstractContextManager] | None = None,
    deck: Deck | None = None,
    kind: str = "plot",
) -> Callable[[], object]:
    file, _, name = target.rpartition(":")
    path = _file(base, file, where)

    def make() -> object:
        from flexo.studio import code_allowed

        from flexo_talk import worker

        if not code_allowed.get():
            raise UntrustedCode(
                where, f"{file} hasn\u2019t been run: Python in this folder runs once you trust the folder."
            )
        root = worker.root()
        if root is not None:
            return _made_apart(root, path.resolve(), name, target, where, kind, deck, check)
        with around() if around else contextlib.nullcontext(), _own_code(target, where):
            module = import_file(path)
            function = getattr(module, name, None)
            if not callable(function):
                raise DeckDocumentError(where, f"{file} has no function {name}")
            made = call(function) if call else function()
        return check(made)

    return make


def _made_apart(
    root: Path, path: Path, name: str, target: str, where: str, kind: str, deck: Deck | None,
    check: Callable[[object], object],
) -> object:
    """A figure or plot made by the studio's worker for ``root`` (``flexo_talk.worker``):
    a plot that hangs or crashes is said on its slide, and the app goes on."""

    from flexo_talk import worker

    request: dict[str, Any] = {"do": kind, "file": str(path), "function": name}

    def asked(extra: dict[str, Any]) -> dict[str, Any]:
        try:
            answer = worker.ask(root, {**request, **extra})
        except worker.Stopped as stopped:
            raise DeckDocumentError(where, f"{target} {stopped}") from None
        if "error" in answer:
            raise DeckDocumentError(where, f"{target}: {answer['error']}")
        return answer

    if kind == "plot":
        view = worker.deck_view(deck) if deck is not None else {}

        def draw(
            width: float, height: float, family: str, identifier: str, maths: str, options: dict[str, Any]
        ) -> tuple[str, list]:
            answer = asked({"deck": view, "width": width, "height": height, "family": family,
                            "identifier": identifier, "maths": maths, "options": options})
            return answer["svg"], [tuple(item) for item in answer.get("said") or []]

        return worker.RemotePlot(draw)
    from flexo.serialization import parse_figure

    document = asked({})["document"]
    try:
        return check(parse_figure(_beside(path.parent, document)))
    except DeckDocumentError:
        raise
    except Exception as error:
        raise DeckDocumentError(where, f"{target} returned a figure that flexo cannot read: {error}") from error


CODE_TIMEOUT = 300.0
"""Seconds a plot or figure a document names may take where it is made here (on the
command line): one that never returns is stopped and said, not waited on for ever. The
studio's worker stops one sooner (``worker.TIMEOUT``)."""


class _TooLong(BaseException):
    """A deck's own Python, stopped for taking longer than ``CODE_TIMEOUT``."""


@contextlib.contextmanager
def _own_code(target: str, where: str):
    """Around a deck's own Python: whatever it does to stop (``sys.exit()``) is said on
    its slide, so is running past ``CODE_TIMEOUT``, and the folder it may have moved
    into is left again."""

    folder = os.getcwd()
    cancel = _alarm(CODE_TIMEOUT)
    try:
        yield
    except _TooLong:
        from flexo_talk.worker import duration

        raise DeckDocumentError(where, f"{target} took longer than {duration(CODE_TIMEOUT)} and was stopped.") from None
    except (DeckDocumentError, KeyboardInterrupt):
        raise
    except BaseException as error:
        if isinstance(error, Exception) and not isinstance(error, SystemExit):
            raise
        raise DeckDocumentError(where, f"{target} stopped: {type(error).__name__} {error}".strip()) from None
    finally:
        cancel()
        if os.getcwd() != folder:
            os.chdir(folder)


def _alarm(seconds: float) -> Callable[[], None]:
    """Raise ``_TooLong`` in this thread after ``seconds``; the function returned calls
    it off. Only the main thread can be interrupted so (by a signal, where there are
    signals), and an alarm someone else has set is left to ring as they meant."""

    if (
        not hasattr(signal, "setitimer")
        or threading.current_thread() is not threading.main_thread()
        or signal.getitimer(signal.ITIMER_REAL)[0]
    ):
        return lambda: None

    def ring(number: int, frame: object) -> None:
        raise _TooLong

    before = signal.signal(signal.SIGALRM, ring)
    signal.setitimer(signal.ITIMER_REAL, seconds)

    def cancel() -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, before)

    return cancel


_MODULES: dict[Path, tuple[float, object]] = {}
_IMPORTING = threading.Lock()


def import_file(path: Path) -> object:
    """The module a Python file makes, imported again when it, or any Python file beside
    it (a helper it imports), has changed.

    Its folder is on the import path only while it is imported, and the modules it
    imports from there are forgotten after: so an edited helper is read again, and a
    helper of the same name in another deck's folder is never taken for this one's.
    """

    stamp = _stamp(path)
    known = _MODULES.get(path)
    if known and known[0] == stamp:
        return known[1]
    name = f"_flexo_talk_{path.stem}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DeckDocumentError("", f"Cannot read {path}.")
    module = importlib.util.module_from_spec(spec)
    folder = path.parent.resolve()
    with _IMPORTING:
        before = set(sys.modules)
        sys.path.insert(0, str(folder))
        sys.modules[name] = module  # a dataclass in the file looks its module up
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        finally:
            with contextlib.suppress(ValueError):
                sys.path.remove(str(folder))
            for key in set(sys.modules) - before - {name}:
                source = getattr(sys.modules.get(key), "__file__", None)
                if source and folder in Path(source).resolve().parents:
                    del sys.modules[key]
    _MODULES[path] = (stamp, module)
    return module


def _stamp(path: Path) -> float:
    """When the file, or the latest Python file beside it, last changed."""

    stamps = [path.stat().st_mtime]
    with contextlib.suppress(OSError):
        stamps += [item.stat().st_mtime for item in list(path.parent.glob("*.py"))[:200]]
    return max(stamps)


def _takes_argument(function: Callable[..., object]) -> bool:
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        item.kind in {item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD} and item.default is item.empty
        for item in parameters
    )


def _file(base: Path, name: str, where: str = "") -> Path:
    from flexo.studio import folder_root

    path = Path(name).expanduser()
    path = path if path.is_absolute() else base / path
    root = folder_root.get()
    if root is not None and root != path.resolve() and root not in path.resolve().parents:
        # In the studio a deck reads only its own folder: a deck someone sends cannot
        # carry a file of yours into its slides.
        raise DeckDocumentError(where, f"{name} is outside the folder.")
    if not path.exists():
        if root is not None:
            # In the studio a file is named as the deck names it: from the deck's folder.
            raise MissingFile(where, f"Can't find {name} in the deck's folder.", name)
        raise MissingFile(where, f"Cannot find {name} (looked in {path.parent}).", name)
    return path


def _only(data: dict[str, Any], allowed: tuple[str, ...], where: str) -> None:
    unknown = [key for key in data if key not in allowed]
    if unknown:
        raise DeckDocumentError(
            where, f"Unknown {'key' if len(unknown) == 1 else 'keys'} {', '.join(map(str, unknown))}. "
            f"Valid keys here: {', '.join(allowed)}."
        )


# -- writing ------------------------------------------------------------------------------


def deck_document(deck: Deck, *, plots: Callable[[_Plot, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """A deck -- one read from a document or made in Python -- as its document.

    A figure made in Python is written inline as a flexo figure document. A
    matplotlib plot has no document: ``plots(block, where)`` gives the block to
    write in its place (``flexo-talk convert`` saves it as an SVG and writes an
    image); without it, a plot made in Python raises ``DeckDocumentError``.
    """

    return {"schema_version": SCHEMA_VERSION, "deck": _deck_data(deck), "slides": [
        _slide_data(slide, f"slides[{index}]", plots) for index, slide in enumerate(deck.slides)
    ]}


def _deck_data(deck: Deck) -> dict[str, Any]:
    given = deck.source
    data: dict[str, Any] = {"id": deck.id}
    defaults = {"theme": "paper", "palette": "default", "background": True, "footer": "", "look": None,
                "logos": [], "logos_on": "title", "logo_height": LOGO_HEIGHT}
    for key in ("theme", "look", "palette", "font", "title_font", "figure_font", "footer", "background",
                "conventions", "sketch", "logos", "logos_on", "logo_height"):
        value = given.get(key)
        if key == "logos" and isinstance(value, str | PurePath):
            value = [value]
        if key == "logos" and isinstance(value, list | tuple):
            value = [str(logo) for logo in value]
        if value is None or value == defaults.get(key):
            continue
        data[key] = value
    start = deck.baseline
    changes = {name: getattr(deck.style, name) for name in STYLE_FIELDS
               if getattr(deck.style, name) != getattr(start, name)}
    if changes:
        data["style"] = changes
    return data


def _slide_data(
    slide: Slide, where: str, plots: Callable[[_Plot, str], dict[str, Any]] | None
) -> dict[str, Any]:
    given = slide.source
    layout = slide.layout
    data: dict[str, Any] = {}
    if layout != "content":
        data["layout"] = layout
    defaults: dict[str, object] = {"split": 0.5, "shade": 0.0, "columns": 3}
    for key in SLIDE_KEYS[layout] + ("background", "shade"):
        if key in {"body", "left", "right", "columns"}:
            continue
        # A statement made in Python keeps its words as its title.
        value = given.get("words", given.get("title")) if key == "words" else given.get(key)
        if key == "title" and layout == "agenda" and value == "Outline":
            continue
        if value is None or value == "" or value == defaults.get(key):
            continue
        data[key] = value
    if slide.footnote_sources:
        data["footnotes"] = list(slide.footnote_sources)
    if slide.notes_text:
        data["notes"] = slide.notes_text
    if layout == "columns":
        data["columns"] = [
            _blocks(region, f"{where}.columns[{index}]", plots) for index, region in enumerate(slide.columns)
        ]
    elif layout not in {"title", "section", "statement", "agenda"}:
        for name, region in slide.regions.items():
            if region.blocks:
                data[name] = _blocks(region, f"{where}.{name}", plots)
    return data


def _blocks(
    region: Region, where: str, plots: Callable[[_Plot, str], dict[str, Any]] | None
) -> list[dict[str, Any]]:
    import flexo
    from flexo.serialization import figure_to_document

    written = []
    for index, (block, source) in enumerate(zip(region.blocks, region.sources, strict=True)):
        here = f"{where}[{index}]"
        if isinstance(block, _Figure) and source.get("figure") is None:
            figure = block.figure
            spec = figure.spec if isinstance(figure, flexo.Figure) else figure
            source = {**source, "figure": figure_to_document(spec)}
        elif isinstance(block, _Plot) and source.get("plot") is None:
            if plots is None:
                raise DeckDocumentError(
                    here, "A plot made in Python cannot be saved in a document. Name it as file.py:function instead."
                )
            source = plots(block, here)
        written.append(source)
    return written


class _Dumper(yaml.SafeDumper):
    """Block style throughout; words over several lines as literal blocks."""


def _string(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _string)
_Dumper.add_representer(tuple, lambda dumper, value: dumper.represent_list(list(value)))
_Dumper.add_multi_representer(PurePath, lambda dumper, value: _string(dumper, str(value)))


def _json_value(value: object) -> object:
    """What JSON has no word for, as a deck document writes it: a date as YAML writes
    one (2026-10-01), a file as its name."""

    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, PurePath):
        return str(value)
    raise TypeError(f"A deck document cannot contain a {type(value).__name__} value ({value!r:.40}).")


_SLIDE_ORDER = (
    "layout", "title", "subtitle", "author", "date", "words", "by", "dark", "align", "split", "widths",
    "background", "shade", "body", "left", "right", "columns", "notes", "footnotes",
)
"""A slide's keys in the order a person reads them: what it is, its words, its look, its
content, then its notes."""


def _tidy(value: Any, *, slide: bool = False) -> Any:
    """``value`` as it is written: a slide's keys in ``_SLIDE_ORDER`` (the rest after, as
    they were), and an id first wherever there is one. Only the order changes."""

    if isinstance(value, list):
        return [_tidy(item) for item in value]
    if not isinstance(value, dict):
        return value
    keys = list(value)
    if slide:
        keys = [key for key in _SLIDE_ORDER if key in value] + [key for key in keys if key not in _SLIDE_ORDER]
    elif "id" in value:
        keys = ["id", *(key for key in keys if key != "id")]
    return {key: _tidy(value[key]) for key in keys}


def dump_document(document: dict[str, Any], *, format: str = "yaml") -> str:
    """A deck document as YAML (or JSON) text."""

    document = _tidied(document)
    if format == "json":
        return json.dumps(document, indent=2, ensure_ascii=False, default=_json_value) + "\n"
    return yaml.dump(document, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def _tidied(document: Any) -> Any:
    if isinstance(document, dict) and isinstance(document.get("slides"), list):
        return {
            key: [_tidy(slide, slide=True) for slide in item] if key == "slides" else _tidy(item)
            for key, item in document.items()
        }
    return document


def save_document(document: dict[str, Any], destination: str | Path, *, previous: str | None = None) -> Path:
    """Write a deck document. YAML is written over the file's text as it was (``previous``,
    else the file there now): the comments, blank lines, quoting and order of keys its
    person or an agent wrote are kept wherever the document did not change them."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        text = dump_document(document, format="json")
    else:
        if previous is None and path.is_file():
            previous = path.read_text(encoding="utf-8")
        # (By its name: what was deleted from this file, and only this one, comes back as it was.)
        text = rewrite(previous, _tidied(document), dump_document, name=str(path.resolve()))
    path.write_text(text, encoding="utf-8")
    return path
