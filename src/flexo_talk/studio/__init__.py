"""Decks in flexo studio: ``flexo-talk studio talk.yaml`` edits a deck document.

The page edits the document (see ``flexo_talk.document``) as JSON; each change
is drawn here slide by slide, and a slide whose document, place in the deck,
and files are as they were is not drawn again.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import fields
from pathlib import Path
from typing import Any, get_args

from flexo.studio import Drawing, Message, Page

from flexo_talk.deck import LAYOUTS, LOOKS, DeckStyle
from flexo_talk.document import (
    BLOCKS,
    COMMON_KEYS,
    SCHEMA_VERSION,
    SLIDE_KEYS,
    DeckDocumentError,
    deck_from_document,
    dump_document,
    is_deck_document,
    load_document,
    save_document,
)

LOOK_NOTES = {
    "classic": "A short accent rule under each title; centred opening",
    "band": "Titles on a band of the accent; sections filled with it",
    "editorial": "A hairline under each title; sections numbered large",
    "keynote": "Centred titles and content, no rules",
    "margin": "Titles in the accent; a bar down each slide's edge",
}

LAYOUT_NOTES = {
    "content": "A title over words, lists, pictures, figures",
    "two-columns": "A title over two columns side by side",
    "columns": "A title over any number of columns",
    "figure": "A title over one figure, as large as the slide allows",
    "title": "The opening: title, subtitle, who and when",
    "section": "A divider between parts of the talk",
    "statement": "One sentence, large, in the middle",
    "agenda": "The talk's sections, numbered",
    "blank": "The whole slide as one body",
}

STYLE_NOTES = {
    "title_size": "Slide titles (pt)",
    "subtitle_size": "Subtitles (pt)",
    "body_size": "Words and lists (pt)",
    "small_size": "Footnotes, captions, the smallest words may shrink to (pt)",
    "figure_size": "Words in figures (pt)",
    "margin": "Space around the slide's edge (pt)",
    "line_height": "Line height, as a multiple of the size",
    "paragraph_gap": "Space between bullets, as a fraction of the size",
    "indent": "How far each list level steps in (pt)",
    "column_gap": "Space between columns (pt)",
    "block_gap": "Space between blocks (pt)",
    "title_gap": "Space between the title and the body (pt)",
    "header": "What marks a slide's title",
    "opening": "How the title slide is set",
    "sections": "How section slides are set",
    "edge": "An accent bar down the left edge",
    "align": "Where content sits in the body",
    "numbers": "Slide numbers",
    "title_weight": "The weight of titles (100 to 900)",
    "title_align": "Titles flush left or centred",
    "title_role": "The colour titles are painted in",
}

CACHE_SIZE = 600
BUDGET = 0.4
"""Seconds a drawing spends on slides beyond the first before it returns what it has."""


class DeckKind:
    name = "deck"
    title = "Deck"
    static = Path(__file__).parent / "static"

    def __init__(self) -> None:
        self._slides: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def claims(self, document: object) -> bool:
        return is_deck_document(document)

    def new(self, path: Path) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "deck": {"id": path.stem, "theme": "paper", "look": "classic"},
            "slides": [
                {"layout": "title", "title": "A talk worth giving", "subtitle": "What we found, and why it matters",
                 "author": "Your name", "date": ""},
                {"title": "The question", "body": [{"bullets": ["What we asked", "Why it was hard",
                                                                 ["and why it still is"]]}]},
            ],
        }

    def load(self, path: Path) -> dict[str, Any]:
        return load_document(path)

    def save(self, path: Path, document: dict[str, Any]) -> None:
        save_document(document, path)

    def catalog(self) -> dict[str, Any]:
        from flexo.colour import design_palettes
        from flexo.fonts import available_families
        from flexo.themes import theme_names

        style = []
        defaults = DeckStyle()
        for item in fields(DeckStyle):
            if item.name in {"width", "height"}:
                continue
            value = getattr(defaults, item.name)
            choices = [str(choice) for choice in get_args(_literal(item.type))]
            kind = "choice" if choices else "bool" if isinstance(value, bool) else "number"
            if item.name == "title_role":
                kind, choices = "choice", ["ink", "tone-1-stroke", "tone-2-stroke", "muted-ink"]
            style.append({"name": item.name, "kind": kind, "default": value, "choices": choices,
                          "note": STYLE_NOTES.get(item.name, "")})
        return {
            "themes": list(theme_names()),
            "looks": [{"name": name, "note": LOOK_NOTES.get(name, ""), "style": {**LOOKS[name]}} for name in LOOKS],
            "palettes": {name: list(colours) for name, colours in design_palettes().items()},
            "fonts": sorted(available_families()),
            "style": style,
            "layouts": [{"name": name, "note": LAYOUT_NOTES[name]} for name in LAYOUTS],
            "slide_keys": {layout: [*COMMON_KEYS, *keys] for layout, keys in SLIDE_KEYS.items()},
            "blocks": {kind: list(options) for kind, options in BLOCKS.items()},
        }

    # -- drawing --

    def draw(self, document: dict[str, Any], base: Path, hints: dict[str, Any] | None = None) -> Drawing:
        """Draw what has changed, the slide in focus first and its neighbours next;
        slides not reached within ``BUDGET`` seconds are left pending for the next call."""

        from flexo_talk.compose import render_slide

        errors: list[DeckDocumentError] = []
        try:
            deck = deck_from_document(document, base, errors=errors)
        except DeckDocumentError as error:
            return Drawing([], [Message(error.message, "error", error.where)])
        except Exception as error:
            return Drawing([], [Message(f"{type(error).__name__}: {error}", "error", "deck")])
        slides = document.get("slides") or []
        failed = {_slide_of(error.where): error for error in errors}
        head = _stable({"deck": document.get("deck"), "base": str(base), "count": len(slides)})
        sections = [
            (slide.get("title"), slide.get("subtitle")) for slide in slides
            if isinstance(slide, dict) and slide.get("layout") == "section"
        ]
        watched: set[Path] = set(_theme_files(document.get("deck") or {}, base))
        keys: list[str] = []
        for index, data in enumerate(slides):
            files = sorted(_files(data, base))
            watched.update(files)
            layout = data.get("layout", "content") if isinstance(data, dict) else "content"
            keys.append(_stable({
                "head": head,
                "index": index,
                "sections": sections if layout == "agenda" else None,
                "before": sum(
                    1 for item in slides[:index] if isinstance(item, dict) and item.get("layout") == "section"
                ),
                "slide": data,
                "files": [(str(file), _stamp(file)) for file in files],
            }))
        focus = int((hints or {}).get("focus") or 0)
        started = time.perf_counter()
        drawn_one = False
        for index in _order(len(slides), focus):
            if index in failed or keys[index] in self._slides:
                continue
            if drawn_one and time.perf_counter() - started > BUDGET:
                break
            slide = deck.slides[index]
            try:
                rendered = render_slide(deck, slide)
                self._slides[keys[index]] = {"svg": rendered.svg, "steps": rendered.steps,
                                             "diagnostics": rendered.diagnostics, "notes": rendered.notes}
            except Exception as error:
                self._slides[keys[index]] = {"error": f"{type(error).__name__}: {error}"}
            drawn_one = True
        while len(self._slides) > CACHE_SIZE:
            self._slides.popitem(last=False)
        pages: list[Page] = []
        messages: list[Message] = []
        for index, (slide, data) in enumerate(zip(deck.slides, slides, strict=True)):
            identifier = slide.id
            done = self._slides.get(keys[index])
            if index in failed:
                error = failed[index]
                messages.append(Message(error.message, "error", error.where, identifier, "deck.document"))
                pages.append(Page(identifier, _blank(deck, slide), _label(data), extra=_extra(data, error=True)))
            elif done is None:
                pages.append(Page(identifier, "", _label(data), extra=_extra(data), pending=True))
            elif "error" in done:
                messages.append(Message(done["error"], "error", f"slides[{index}]", identifier, "deck.draw"))
                pages.append(Page(identifier, _blank(deck, slide), _label(data), extra=_extra(data, error=True)))
            else:
                self._slides.move_to_end(keys[index])
                for text in done["diagnostics"]:
                    messages.append(_diagnostic(text, identifier, index, "warning"))
                for text in done["notes"]:
                    messages.append(_diagnostic(text, identifier, index, "note"))
                pages.append(Page(identifier, done["svg"], _label(data), done["steps"], _extra(data)))
        return Drawing(pages, messages, sorted(watched), {"palette": _palette(deck)})

    def export(self, document: dict[str, Any], base: Path, stem: str, formats: list[str]) -> list[Path]:
        deck = deck_from_document(document, base)
        result = deck.build(base / "build", formats=tuple(formats))
        written = [result.pptx, result.pdf, *result.svgs, *result.pngs]
        return [path for path in written if path]

    def text(self, document: dict[str, Any]) -> str:
        return dump_document(document)


def _order(count: int, focus: int) -> list[int]:
    """The slide in focus, then outward from it, then the rest from the start."""

    focus = min(max(focus, 0), max(count - 1, 0))
    near = [focus, focus + 1, focus - 1, focus + 2, focus - 2]
    seen = [index for index in dict.fromkeys(near) if 0 <= index < count]
    return seen + [index for index in range(count) if index not in seen]


def _literal(annotation: object) -> object:
    # DeckStyle's annotations are strings (``from __future__ import annotations``).
    if isinstance(annotation, str) and annotation.startswith("Literal["):
        values = re.findall(r"""["']([^"']*)["']""", annotation)
        from typing import Literal

        return Literal[tuple(values)]  # type: ignore[valid-type]
    return annotation


def _stable(value: object) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stamp(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _slide_of(where: str) -> int:
    match = re.match(r"slides\[(\d+)\]", where)
    return int(match.group(1)) if match else -1


def _files(data: object, base: Path) -> set[Path]:
    """The files a slide's document names: pictures, figure files, Python modules."""

    found: set[Path] = set()
    if isinstance(data, list):
        for item in data:
            found |= _files(item, base)
    elif isinstance(data, dict):
        for key, value in data.items():
            if key in {"image", "background", "picture", "figure", "plot"} and isinstance(value, str):
                name = value.rpartition(":")[0] if ".py:" in value else value
                if name and not name.startswith("#"):
                    path = (base / name).resolve()
                    if path.is_file():
                        found.add(path)
            elif isinstance(value, dict | list) and not (key == "figure" and isinstance(value, dict)):
                found |= _files(value, base)
            elif key == "gallery" and isinstance(value, list):
                found |= _files([{"picture": item} if isinstance(item, str) else item for item in value], base)
    return found


def _theme_files(deck: dict[str, Any], base: Path) -> list[Path]:
    found = []
    for key in ("theme", "palette"):
        value = deck.get(key)
        if isinstance(value, str) and value.lower().endswith((".yaml", ".yml", ".json")):
            path = (base / value).resolve()
            if path.is_file():
                found.append(path)
    return found


def _label(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    value = data.get("words") if data.get("layout") == "statement" else data.get("title")
    return str(value or "")


def _extra(data: object, *, error: bool = False) -> dict[str, Any]:
    layout = data.get("layout", "content") if isinstance(data, dict) else "content"
    return {"layout": layout, "error": error}


def _diagnostic(text: str, identifier: str, index: int, severity: str) -> Message:
    # A diagnostic names its slide first (``slide3 figure: ...``); the rest is the message.
    rest = text[len(identifier):].lstrip(" :") if text.startswith(identifier) else text
    region = re.match(r"(\S+):\s*(.*)", rest, re.S)
    where = f"slides[{index}]"
    if region and not region.group(1).startswith(("its", "the")):
        return Message(region.group(2), severity, f"{where} {region.group(1)}", identifier)
    return Message(rest, severity, where, identifier)


def _blank(deck, slide) -> str:
    """What stands for a slide that cannot be drawn: a warning sign on a pale page."""

    width, height = deck.style.width, deck.style.height
    x, y = width / 2, height / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" width="{width:g}pt" '
        f'height="{height:g}pt" id="{slide.id}"><rect width="{width:g}" height="{height:g}" fill="#fbf6f4"/>'
        f'<path d="M{x:g} {y - 30:g}L{x + 30:g} {y + 22:g}H{x - 30:g}Z" fill="none" stroke="#c53030" '
        f'stroke-width="3.5" stroke-linejoin="round"/><path d="M{x:g} {y - 10:g}V{y + 4:g}M{x:g} {y + 12:g}v0.5" '
        f'stroke="#c53030" stroke-width="4" stroke-linecap="round"/></svg>'
    )


def _palette(deck) -> dict[str, str]:
    palette = deck.palette
    colours = {"ink": palette.get("ink"), "muted": palette.get("muted-ink"), "canvas": palette.get("canvas")}
    for index in range(1, 9):
        try:
            colours["accent" if index == 1 else f"accent{index}"] = palette.get(f"tone-{index}-stroke")
        except (KeyError, ValueError):
            break
    return colours


kind = DeckKind
