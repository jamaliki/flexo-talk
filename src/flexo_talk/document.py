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
``deck.plotting()`` (and given the deck, if it takes an argument).

``read_deck`` makes a ``Deck`` from a file, ``deck_from_document`` from a parsed
document, and ``deck_document`` writes any deck -- one made in Python too --
back as a document.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any

import yaml

from flexo_talk.deck import LAYOUTS, LOOKS, Deck, DeckStyle, Reference, Region, Slide, _Figure, _Plot

SCHEMA_VERSION = 1

BLOCKS: dict[str, tuple[str, ...]] = {
    "bullets": ("size", "numbered", "reveal"),
    "text": ("size", "align", "muted", "colour"),
    "figure": ("turn",),
    "image": ("width",),
    "plot": ("aspect",),
    "table": ("header", "align", "size"),
    "gallery": ("columns", "height", "crop", "size", "align"),
    "code": ("size",),
    "quote": ("by", "size"),
    "stats": ("colour", "size"),
    "callout": ("title", "colour", "size"),
}
"""Each block kind and the options it takes beside its value."""

DECK_KEYS = (
    "id", "theme", "look", "palette", "font", "title_font", "figure_font", "footer", "background",
    "conventions", "sketch", "style",
)
COMMON_KEYS = ("layout", "notes", "footnotes", "background", "shade")
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


# -- reading ------------------------------------------------------------------------------


def load_document(source: str | Path) -> dict[str, Any]:
    """A deck document from a ``.yaml``, ``.yml``, or ``.json`` file."""

    path = Path(source)
    text = path.read_text(encoding="utf-8")
    document = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(document, dict):
        raise DeckDocumentError("", f"{path.name} is not a deck document (a mapping with deck and slides)")
    return document


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
    stands in the deck as a blank slide, so the others keep their places;
    without it, the first such slide raises ``DeckDocumentError``.
    """

    base = Path(base).resolve()
    if not isinstance(document, dict):
        raise DeckDocumentError("", "a deck document is a mapping with deck and slides")
    _only(document, ("schema_version", "deck", "slides"), "")
    version = document.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise DeckDocumentError("schema_version", f"this flexo-talk reads version {SCHEMA_VERSION}, not {version}")
    deck = make_deck(document.get("deck") or {}, base)
    slides = document.get("slides") or []
    if not isinstance(slides, list):
        raise DeckDocumentError("slides", "slides is a list")
    for index, data in enumerate(slides):
        where = f"slides[{index}]"
        try:
            add_slide(deck, data, base, where)
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


def make_deck(data: dict[str, Any], base: Path) -> Deck:
    """The ``Deck`` the ``deck`` mapping of a document describes."""

    if not isinstance(data, dict):
        raise DeckDocumentError("deck", "deck is a mapping of the deck's settings")
    _only(data, DECK_KEYS, "deck")
    look = data.get("look")
    if look is not None and look not in LOOKS:
        raise DeckDocumentError("deck.look", f'unknown look "{look}"; looks are {", ".join(LOOKS)}')
    changes = data.get("style") or {}
    if not isinstance(changes, dict):
        raise DeckDocumentError("deck.style", "style is a mapping of DeckStyle fields")
    _only(changes, STYLE_FIELDS, "deck.style")
    try:
        style = DeckStyle.look(look, **changes) if look else DeckStyle(**changes)
        theme = data.get("theme", "paper")
        if isinstance(theme, str) and theme.lower().endswith((".yaml", ".yml", ".json")):
            theme = str(_file(base, theme))
        palette = data.get("palette", "default")
        if isinstance(palette, str) and palette.lower().endswith((".yaml", ".yml", ".json")):
            palette = str(_file(base, palette))
        deck = Deck(
            str(data.get("id", "talk")),
            theme=theme,
            palette=palette,
            font=data.get("font"),
            title_font=data.get("title_font"),
            figure_font=data.get("figure_font"),
            conventions=data.get("conventions"),
            sketch=data.get("sketch"),
            background=data.get("background", True),
            footer=str(data.get("footer", "")),
            style=style,
        )
    except DeckDocumentError:
        raise
    except Exception as error:
        raise DeckDocumentError("deck", str(error)) from error
    deck.look = look
    deck.source = {**deck.source, **{key: value for key, value in data.items() if key != "style"}}
    return deck


def add_slide(deck: Deck, data: object, base: Path, where: str) -> Slide:
    """Add the slide ``data`` describes to ``deck``."""

    if not isinstance(data, dict):
        raise DeckDocumentError(where, "a slide is a mapping (title, layout, body, ...)")
    layout = data.get("layout", "content")
    if layout not in LAYOUTS:
        raise DeckDocumentError(f"{where}.layout", f'unknown layout "{layout}"; layouts are {", ".join(LAYOUTS)}')
    _only(data, COMMON_KEYS + SLIDE_KEYS[layout], where)
    background = data.get("background")
    if isinstance(background, str) and not background.startswith("#"):
        background = str(_file(base, background, f"{where}.background"))
    shade = float(data.get("shade", 0.0))
    text = _text_of(data, where)
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
                raise DeckDocumentError(f"{where}.columns", "a columns slide has columns: a list of block lists")
            if widths is not None and (not isinstance(widths, list) or len(widths) != len(columns)):
                raise DeckDocumentError(f"{where}.widths", "widths gives one share for each column")
        slide = deck.slide(
            text("title"),
            layout=layout,
            subtitle=text("subtitle"),
            split=float(data.get("split", 0.5)),
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
                raise DeckDocumentError(names[name], "a region is a list of blocks")
            for index, block in enumerate(blocks):
                add_block(slide.regions[name], block, base, f"{names[name]}[{index}]")
    if data.get("notes"):
        slide.notes(text("notes"))
    footnotes = data.get("footnotes") or []
    if isinstance(footnotes, str):
        footnotes = [footnotes]
    for note in footnotes:
        slide.footnote(str(note))
    slide.source = {key: value for key, value in data.items() if key not in {"body", "left", "right"}}
    if layout == "columns":
        slide.source.pop("columns", None)
    return slide


def _text_of(data: dict[str, Any], where: str) -> Callable[[str], str]:
    def text(key: str) -> str:
        value = data.get(key)
        if value is None:
            return ""
        if isinstance(value, dict | list):
            raise DeckDocumentError(f"{where}.{key}", f"{key} is words, not a {type(value).__name__}")
        return str(value)

    return text


def add_block(region: Region, block: object, base: Path, where: str) -> None:
    """Add the block ``block`` describes to ``region``."""

    if not isinstance(block, dict):
        raise DeckDocumentError(where, f"a block is a mapping named by its kind ({', '.join(BLOCKS)})")
    kinds = [key for key in block if key in BLOCKS]
    if len(kinds) != 1:
        found = "none" if not kinds else ", ".join(kinds)
        raise DeckDocumentError(where, f"a block names one kind of {', '.join(BLOCKS)}; this names {found}")
    kind = kinds[0]
    _only(block, (kind, *BLOCKS[kind]), f"{where} ({kind})")
    value = block[kind]
    options = {key: block[key] for key in BLOCKS[kind] if key in block}
    here = f"{where} ({kind})"
    try:
        if kind == "bullets":
            items = value if isinstance(value, list) else [value]
            _check_items(items, here)
            region.bullets(*items, **options)
        elif kind in {"text", "code", "quote", "callout"}:
            if not isinstance(value, str | int | float):
                raise DeckDocumentError(here, f"{kind} is words")
            getattr(region, kind)(str(value), **options)
        elif kind == "image":
            region.image(_file(base, str(value), here), **options)
        elif kind == "table":
            if not isinstance(value, list) or not all(isinstance(row, list) for row in value):
                raise DeckDocumentError(here, "a table is a list of rows, each a list of cells")
            region.table(value, **options)
        elif kind == "gallery":
            if not isinstance(value, list):
                raise DeckDocumentError(here, "a gallery is a list of pictures (a file, or picture and caption)")
            region.gallery([_picture(base, item, here) for item in value], **options)
        elif kind == "stats":
            if not isinstance(value, list) or not value:
                raise DeckDocumentError(here, "stats is a list of {value, label}")
            region.stats(*(_stat(item, here) for item in value), **options)
        elif kind == "figure":
            region.add(_figure(base, value, here, region), **options)
        elif kind == "plot":
            region.plot(_plot(base, value, here, region), **options)
    except DeckDocumentError:
        raise
    except (ValueError, TypeError, OSError) as error:
        raise DeckDocumentError(here, str(error)) from error
    region.sources[-1] = dict(block)


def _check_items(items: list, where: str) -> None:
    for item in items:
        if isinstance(item, list):
            _check_items(item, where)
        elif not isinstance(item, str | int | float):
            raise DeckDocumentError(where, "bullets are words, and nested lists of words for the level below")


def _picture(base: Path, item: object, where: str) -> str | tuple[str, str]:
    if isinstance(item, str):
        return str(_file(base, item, where))
    if isinstance(item, dict) and "picture" in item:
        _only(item, ("picture", "caption"), where)
        return str(_file(base, str(item["picture"]), where)), str(item.get("caption") or "")
    raise DeckDocumentError(where, "a gallery picture is a file, or a mapping with picture and caption")


def _stat(item: object, where: str) -> tuple[object, str]:
    if isinstance(item, dict) and "value" in item:
        _only(item, ("value", "label"), where)
        return item["value"], str(item.get("label") or "")
    if isinstance(item, list) and len(item) == 2:
        return item[0], str(item[1])
    raise DeckDocumentError(where, "each of stats is {value, label}")


_FIGURES: OrderedDict[str, object] = OrderedDict()
_FIGURES_LOCK = threading.Lock()


def _figure(base: Path, value: object, where: str, region: Region) -> object:
    from flexo.serialization import load_figure, parse_figure

    if isinstance(value, dict):
        # A figure is read once for each version of it: the studio reads the deck on every edit.
        key = json.dumps(value, sort_keys=True, default=str)
        with _FIGURES_LOCK:
            if key in _FIGURES:
                _FIGURES.move_to_end(key)
                return _FIGURES[key]
        try:
            figure = parse_figure(value)
        except Exception as error:
            raise DeckDocumentError(where, f"the figure is not a flexo figure document: {error}") from error
        with _FIGURES_LOCK:
            _FIGURES[key] = figure
            while len(_FIGURES) > 64:
                _FIGURES.popitem(last=False)
        return figure
    if not isinstance(value, str) or not value:
        raise DeckDocumentError(where, "a figure is a figure file, file.py:function, or a flexo figure document")
    if _is_code(value):
        return Reference(value, _maker(base, value, where, lambda made: _as_figure(made, value, where)))
    try:
        return load_figure(_file(base, value, where))
    except DeckDocumentError:
        raise
    except Exception as error:
        raise DeckDocumentError(where, f"{value}: {error}") from error


def _as_figure(made: object, target: str, where: str) -> object:
    import flexo
    from flexo.ir.semantic import FigureSpec

    if not isinstance(made, flexo.Figure | FigureSpec):
        raise DeckDocumentError(where, f"{target} returned {type(made).__name__}, not a flexo figure")
    return made


def _plot(base: Path, value: object, where: str, region: Region) -> Reference:
    if not isinstance(value, str) or not _is_code(value):
        raise DeckDocumentError(where, "a plot is file.py:function, a function returning a matplotlib figure")
    deck = region._slide.deck

    def call(function: Callable[..., object]) -> object:
        with deck.plotting():
            return function(deck) if _takes_argument(function) else function()

    return Reference(value, _maker(base, value, where, lambda made: made, call=call))


def _is_code(value: str) -> bool:
    return ".py:" in value


def _maker(
    base: Path,
    target: str,
    where: str,
    check: Callable[[object], object],
    *,
    call: Callable[[Callable[..., object]], object] | None = None,
) -> Callable[[], object]:
    file, _, name = target.rpartition(":")
    path = _file(base, file, where)

    def make() -> object:
        module = import_file(path)
        function = getattr(module, name, None)
        if not callable(function):
            raise DeckDocumentError(where, f"{file} has no function {name}")
        return check(call(function) if call else function())

    return make


_MODULES: dict[Path, tuple[float, object]] = {}


def import_file(path: Path) -> object:
    """The module a Python file makes, imported again when the file has changed."""

    stamp = path.stat().st_mtime
    known = _MODULES.get(path)
    if known and known[0] == stamp:
        return known[1]
    spec = importlib.util.spec_from_file_location(f"_flexo_talk_{path.stem}_{abs(hash(path))}", path)
    if spec is None or spec.loader is None:
        raise DeckDocumentError("", f"cannot read {path}")
    module = importlib.util.module_from_spec(spec)
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    _MODULES[path] = (stamp, module)
    return module


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
    path = Path(name).expanduser()
    path = path if path.is_absolute() else base / path
    if not path.exists():
        raise DeckDocumentError(where, f"no file {name} (looked in {path.parent})")
    return path


def _only(data: dict[str, Any], allowed: tuple[str, ...], where: str) -> None:
    unknown = [key for key in data if key not in allowed]
    if unknown:
        raise DeckDocumentError(
            where, f"unknown {'key' if len(unknown) == 1 else 'keys'} {', '.join(map(str, unknown))}; "
            f"known here: {', '.join(allowed)}"
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
    defaults = {"theme": "paper", "palette": "default", "background": True, "footer": "", "look": None}
    for key in ("theme", "look", "palette", "font", "title_font", "figure_font", "footer", "background",
                "conventions", "sketch"):
        value = given.get(key)
        if value is None or value == defaults.get(key):
            continue
        data[key] = value
    start = DeckStyle.look(deck.look) if deck.look else DeckStyle()
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
                raise DeckDocumentError(here, "a plot made in Python has no document; name it as file.py:function")
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


def dump_document(document: dict[str, Any], *, format: str = "yaml") -> str:
    """A deck document as YAML (or JSON) text."""

    if format == "json":
        return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    return yaml.dump(document, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def save_document(document: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_document(document, format="json" if path.suffix.lower() == ".json" else "yaml"),
                    encoding="utf-8")
    return path
