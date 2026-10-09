"""Decks in flexo studio: ``flexo-talk studio talk.yaml`` edits a deck document.

The page edits the document (see ``flexo_talk.document``) as JSON; each change
is drawn here slide by slide, and a slide whose document, place in the deck,
and files are as they were is not drawn again.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import fields
from pathlib import Path
from typing import Any, get_args

from flexo.studio import Drawing, Message, Page
from flexo.studio.plain import explain

from flexo_talk.deck import LAYOUTS, LOOKS, DeckStyle
from flexo_talk.document import (
    BLOCKS,
    COMMON_KEYS,
    SCHEMA_VERSION,
    SLIDE_KEYS,
    DeckDocumentError,
    InvalidFigure,
    InvalidObject,
    MissingFile,
    UnknownLayout,
    UntrustedCode,
    deck_from_document,
    dump_document,
    is_deck_document,
    load_document,
    parse_document,
    save_document,
)

LOOK_LABELS = {"keynote": "Centred"}
"""A look's name as the studio shows it, where its id is not that name."""

LOOK_NOTES = {
    "classic": "Short accent rule under titles, centred title slide",
    "band": "Titles on an accent band, filled section slides",
    "editorial": "Hairline under titles, large section numbers",
    "keynote": "Centred titles and content, no rules",
    "margin": "Accent-coloured titles, accent bar along the left edge",
}

LAYOUT_LABELS = {
    "content": "Content",
    "two-columns": "Two Columns",
    "columns": "Columns",
    "figure": "Figure",
    "title": "Title",
    "section": "Section",
    "statement": "Statement",
    "agenda": "Agenda",
    "blank": "Blank",
}
"""What the studio calls each layout."""

LAYOUT_NOTES = {
    "content": "Title with text, lists, pictures or figures",
    "two-columns": "Title with two columns side by side",
    "columns": "Title with any number of columns",
    "figure": "Title with one figure, as large as the slide allows",
    "title": "Title, subtitle, author and date",
    "section": "Divider between sections of the talk",
    "statement": "One large sentence in the centre",
    "agenda": "Numbered list of the talk's sections",
    "blank": "No title; the content fills the slide",
}

STYLE_LABELS = {
    "margin": "Margin",
    "title_size": "Title Size",
    "subtitle_size": "Subtitle Size",
    "body_size": "Body Size",
    "small_size": "Small Text Size",
    "figure_size": "Figure Text Size",
    "line_height": "Line Height",
    "paragraph_gap": "Paragraph Spacing",
    "indent": "Indent",
    "column_gap": "Column Spacing",
    "block_gap": "Object Spacing",
    "title_gap": "Title Spacing",
    "header": "Title Decoration",
    "opening": "Title Slide",
    "sections": "Section Slides",
    "edge": "Edge Bar",
    "align": "Content Position",
    "numbers": "Slide Numbers",
    "title_weight": "Title Weight",
    "title_align": "Title Alignment",
    "title_role": "Title Colour",
}
"""What the studio calls each of the deck's style settings."""

STYLE_NOTES = {
    "title_size": "Slide titles, in points",
    "subtitle_size": "Subtitles, in points",
    "body_size": "Body text and lists, in points",
    "small_size": "Footnotes, captions and the minimum text size, in points",
    "figure_size": "Text in figures, in points",
    "margin": "Space around the slide edges, in points",
    "line_height": "As a multiple of the font size",
    "paragraph_gap": "Space between bullets, as a fraction of the font size",
    "indent": "Indent for each list level, in points",
    "column_gap": "Space between columns, in points",
    "block_gap": "Space between objects, in points",
    "title_gap": "Space between the title and the body, in points",
    "header": "How slide titles are marked",
    "opening": "How the title slide is laid out",
    "sections": "How section slides are laid out",
    "edge": "An accent bar along the left edge",
    "align": "Where content sits on the slide",
    "numbers": "Show slide numbers",
    "title_weight": "Font weight of titles, 100 to 900",
    "title_align": "Titles aligned left or centred",
    "title_role": "The colour of titles",
}

CHOICE_LABELS = {
    "auto": "Automatic",
    "centred": "Centred",
    "middle": "Middle",
    "start": "Left",
    "ink": "Ink",
    "tone-1-stroke": "Accent",
    "tone-2-stroke": "Accent 2",
    "muted-ink": "Muted",
}
"""What the studio shows for a style setting's choices, where it is not the value
capitalised (``title_align: middle`` is Centre)."""

BLOCK_LABELS = {
    "bullets": "List", "text": "Text", "figure": "Figure", "image": "Picture", "plot": "Plot", "table": "Table",
    "gallery": "Gallery", "code": "Code", "quote": "Quote", "stats": "Numbers", "callout": "Callout",
    "math": "Equation", "mechanism": "Mechanism",
}
"""What the studio calls each kind of block."""

FIELD_LABELS = {
    "title": "Title", "subtitle": "Subtitle", "author": "Author", "date": "Date", "words": "Statement",
    "by": "Attribution", "notes": "Notes", "footnotes": "Footnotes", "background": "Background",
    "shade": "Background", "layout": "Layout", "columns": "Columns", "widths": "Columns", "split": "Columns",
    "dark": "Background", "align": "Content Position", "skip": "Skip Slide",
}
"""What the studio calls a slide's settings, where a message names one."""

CACHE_SIZE = 600
CACHE_BYTES = 200_000_000
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

    def mended(self, document: object, notes: list | None = None, base: object = None) -> object:
        """A deck two edits were merged into: each figure written in it with no line left
        naming a shape the other side deleted; and an object one side made another kind (a
        paragraph a list) while the other typed in it one object, of the new kind, with the
        words typed -- not the two the merge kept (its note is settled, and left out)."""

        from flexo.studio.figure_edit import mend

        _aligned(document, notes if notes is not None else [])
        _converted(document, notes if notes is not None else [], base)
        _one_kind(document, base)
        _laid_out(document)
        # The shapes the deck's figures had before: a line kept to one of those is a line to
        # a shape deleted; one to a shape there never was is the person's, said where it is.
        before: set[str] | None = set() if base is not None else None

        def walk(value: object, found: set[str] | None = None) -> None:
            if isinstance(value, dict):
                figure = value.get("figure")
                if isinstance(figure, dict) and isinstance(figure.get("nodes"), list):
                    if found is not None:
                        found.update(str(node.get("id")) for node in figure["nodes"] if isinstance(node, dict))
                    else:
                        mend(figure, before)
                for item in value.values():
                    walk(item, found)
            elif isinstance(value, list):
                for item in value:
                    walk(item, found)

        if before is not None:
            walk(base, before)
        walk(document)
        return document

    def identity(self, document: object) -> str | None:
        """What names a deck inside it, wherever it is kept: its id (made its file's name)."""

        deck = document.get("deck") if isinstance(document, dict) else None
        return str(deck["id"]) if isinstance(deck, dict) and deck.get("id") else None

    def abandoned(self, document: object, where: dict[str, Any]) -> bool:
        """An object left empty where someone was typing (``where``, as the editor says where
        it is: its slide's ``page`` and its ``block``, "body[4]"), their window gone: taken
        away, as their window takes away an object added and left empty when its typing ends.
        Answers whether it was."""

        found = re.fullmatch(r"([\w.]+)\[(\d+)\]", str(where.get("block") or ""))
        slides = document.get("slides") if isinstance(document, dict) else None
        page = where.get("page")
        if not found or not isinstance(slides, list) or not isinstance(page, int) or not 1 <= page <= len(slides):
            return False
        slide, (region, index) = slides[page - 1], (found[1], int(found[2]))
        if region.startswith("columns."):
            columns = slide.get("columns") if isinstance(slide, dict) else None
            column = int(region.split(".")[1])
            blocks = columns[column] if isinstance(columns, list) and column < len(columns) else None
        else:
            blocks = slide.get(region) if isinstance(slide, dict) else None
        if not isinstance(blocks, list) or not 0 <= index < len(blocks):
            return False
        block = blocks[index]
        if not _placeholder(block) or (isinstance(block, dict) and block.get("placeholder")):
            return False
        del blocks[index]
        return True

    def new(self, path: Path) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "deck": {"id": path.stem, "theme": "paper", "look": "classic"},
            "slides": [
                # Placeholders: each holds its place and shows only while editing.
                {"layout": "title", "title": "", "subtitle": ""},
                {"title": "", "body": [{"bullets": [""]}]},
            ],
        }

    def load(self, path: Path) -> dict[str, Any]:
        return load_document(path)

    def save(self, path: Path, document: dict[str, Any], previous: str | None = None) -> None:
        # Over the file's words as they were (``previous``): its comments and quoting kept.
        save_document(document, path, previous=previous)

    def dump(self, document: dict[str, Any]) -> str:
        return dump_document(document)

    def theme_of(self, document: dict[str, Any]) -> str | None:
        theme = (document.get("deck") or {}).get("theme")
        return str(theme) if theme else None

    def with_theme(self, document: dict[str, Any], theme: str, base: Path) -> dict[str, Any]:
        changed = copy.deepcopy(document)
        changed.setdefault("deck", {})["theme"] = theme
        return changed

    def parse(self, text: str) -> Any:
        return parse_document(text)

    def guide(self) -> str:
        import flexo_talk.document as module

        blocks = "\n".join(f"  {kind}: options {', '.join(options) or '(none)'}" for kind, options in BLOCKS.items())
        layouts = "\n".join(f"  {name}: {', '.join(keys)} -- {LAYOUT_NOTES[name]}" for name, keys in SLIDE_KEYS.items())
        return (
            "A flexo-talk deck document.\n" + (module.__doc__ or "")
            + f"\nEvery slide may also take: {', '.join(COMMON_KEYS)}.\nLayouts and their keys:\n{layouts}"
            + f"\nBlocks:\n{blocks}\n"
            + f"Looks: {', '.join(LOOKS)}. Colours for words and panels: accent, accent2, ..., muted, #rrggbb.\n"
            "Slide words are markup: **strong**, *emphasis*, $maths$, `code`, [link](url), [words]{accent}.\n"
            "Good slides say one thing: a title that is a claim, few words, a figure where a picture helps. "
            "Look at each slide after changing it."
        )

    def malformed(self, document: Any) -> str | None:
        """What makes a document no deck the editor can show, if anything: slides that
        are no list, deck settings that are no mapping. A wrong slide or block is said on
        its slide instead."""

        from flexo.diagnostics import described

        if not isinstance(document, dict):
            return "it is not a deck (a mapping with deck and slides)"
        slides, deck = document.get("slides"), document.get("deck")
        if slides is not None and not isinstance(slides, list):
            return f"slides must be a list of slides, not {described(slides)}"
        if deck is not None and not isinstance(deck, dict):
            return f"deck must be a mapping of deck settings, not {described(deck)}"
        for number, slide in enumerate(slides or [], start=1):
            if not isinstance(slide, dict):
                continue  # said on its slide
            for key in ("body", "left", "right", "columns"):
                value = slide.get(key)
                if value is not None and not isinstance(value, list):
                    return f"slide {number}'s {key} must be a list, not {described(value)}"
            regions = [("body", slide.get("body")), ("left", slide.get("left")), ("right", slide.get("right"))]
            for column in slide.get("columns") or []:
                if column is not None and not isinstance(column, list):
                    return f"slide {number}'s columns must each be a list, not {described(column)}"
                regions.append(("columns", column))
            for key, blocks in regions:
                if any(block is None for block in blocks or []):
                    return f"slide {number}'s {key} has an empty item (a “-” with nothing after it)"
        return None

    def check(self, document: Any, base: Path) -> list[str]:
        errors: list[DeckDocumentError] = []
        try:
            deck_from_document(document, base, errors=errors)
        except DeckDocumentError as error:
            return [str(error)]
        return [str(error) for error in errors]

    def describe(self, before: Any, after: Any) -> list[dict[str, Any]]:
        """What a change did, slide by slide, for the activity list and for following."""

        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        notes: list[dict[str, Any]] = []
        old_deck, new_deck = before.get("deck") or {}, after.get("deck") or {}
        if old_deck != new_deck:
            changed = sorted(key for key in {*old_deck, *new_deck} if old_deck.get(key) != new_deck.get(key))
            words = {
                "look": "the look", "theme": "the theme", "palette": "the palette", "footer": "the footer",
                "font": "the type", "title_font": "the type", "figure_font": "the type", "style": "the proportions",
            }
            said = list(dict.fromkeys(words.get(key, "the deck's settings") for key in changed))
            notes.append({"text": "changed " + " and ".join(said[:2]), "where": {"label": "Design"}})
        old, new = before.get("slides") or [], after.get("slides") or []
        steps = _slide_pairs(old, new)
        now = {a: b for step, a, b in steps if step in ("equal", "moved", "changed")}
        was = {b: a for a, b in now.items()}
        carried: list[tuple[dict[str, Any], str, str, int, int]] = []
        for step, a, b in steps:
            if step == "added":
                notes.append(_slide_note("added", new, b))
            elif step == "moved":
                notes.append(_moved_note(a, b, new, was))
            elif step == "deleted":
                # Clicked, it goes where the slide was; it names no place, being gone.
                notes.append({"text": f"deleted slide {a[0] + 1}" if len(a) == 1 else f"deleted {len(a)} slides",
                              "where": {"page": min(b + 1, max(len(new), 1))}})
            elif step == "changed":
                # A placeholder put there and taken away again (a Code left empty) is nothing
                # done: said neither as added nor as deleted.
                if _without_placeholders(old[a]) == _without_placeholders(new[b]):
                    continue
                verb, what = _what_changed(old[a], new[b])
                note = _slide_note(verb, new, b, what)
                # About one object, it is that object's: followed where it goes (`follow`).
                if verb not in ("deleted", "emptied") and (thing := _object_changed(old[a], new[b])):
                    note["where"]["object"] = thing
                notes.append(note)
                if verb in ("added", "deleted") and (one := _one_block(old[a], new[b])):
                    carried.append((note, verb, one, a, b))
        # An object taken from one slide and put on another (dragged to its thumbnail) is
        # moved, said once: "moved the text from slide 3 to slide 6".
        for note, _, one, a, _ in [item for item in carried if item[1] == "deleted"]:
            there = next((item for item in carried if item[1] == "added" and item[2] == one), None)
            if there is None or note not in notes or there[0] not in notes:
                continue
            name = _object_name(json.loads(one)).lower()
            there[0]["text"] = f"moved the {name} from slide {a + 1} to slide {there[4] + 1}"
            notes.remove(note)
        return notes

    def follow(self, before: Any, after: Any) -> Any:
        """Where the slides and objects of a deck before a change are after it: a function
        from a place (a ``where`` of ``describe``'s) to where that is now -- the same slide
        moved, an object dragged to another slide -- or to one saying it is gone. None if no
        slide changed."""

        old = (before if isinstance(before, dict) else {}).get("slides") or []
        new = (after if isinstance(after, dict) else {}).get("slides") or []
        if old == new:
            return None
        steps = _slide_pairs(old, new)
        now = {a: b for step, a, b in steps if step in ("equal", "moved", "changed")}
        # The objects that arrived on a slide with this change -- in no place of the slide it was.
        arrived: dict[str, tuple[int, str, int]] = {}
        for step, a, b in steps:
            if step not in ("changed", "added"):
                continue
            there = {_stable(block) for key in _REGIONS for block in _blocks(old[a] if a is not None else {}, key)}
            for key in _REGIONS:
                for index, block in enumerate(_blocks(new[b], key)):
                    if (text := _stable(block)) not in there:
                        arrived.setdefault(text, (b, key, index))

        def place(page: int, thing: dict[str, Any] | None = None) -> dict[str, Any]:
            where = {"page": page + 1, "label": f"Slide {page + 1}"}
            return {**where, "object": thing} if thing else where

        def moved(where: Any) -> Any:
            # (A place where slides were deleted names none, and is not followed.)
            page = where.get("page") if isinstance(where, dict) and "label" in where else None
            if not isinstance(page, int) or where.get("gone") or not 0 < page <= len(old):
                return where
            found = followed(where, page - 1)
            if found.get("page") == page and found.get("object") == where.get("object"):
                return where
            # Somewhere else than its note says, it says so beside it: "Now on slide 3".
            first = where.get("first", page)
            if found.get("page") not in (None, first):
                found = {**found, "label": f"Now on slide {found['page']}", "first": first}
            return found

        def followed(where: dict[str, Any], a: int) -> dict[str, Any]:
            b = now.get(a)
            thing = where.get("object")
            blocks = _blocks(old[a], thing.get("region")) if isinstance(thing, dict) else []
            index = thing.get("index") if isinstance(thing, dict) else None
            block = blocks[index] if isinstance(index, int) and 0 <= index < len(blocks) else None
            if block is None:
                return place(b) if b is not None else _gone("slide")
            key, region = _stable(block), thing["region"]
            here = _blocks(new[b], region) if b is not None else []
            # Where it is unchanged: in its slide (moved up or down in it), or on another.
            same = [i for i, other in enumerate(here) if _stable(other) == key]
            if same:
                return place(b, {"region": region, "index": min(same, key=lambda i: abs(i - index))})
            if key in arrived and arrived[key][0] != b:
                to, into, at = arrived[key]
                return place(to, {"region": into, "index": at})
            if b is None:
                return _gone("slide")
            # Changed where it was (typed in, made another kind), or gone from its slide.
            others = {_stable(other) for i, other in enumerate(blocks) if i != index}
            if len(here) < len(blocks) and others <= {_stable(other) for other in here}:
                return _gone(_object_name(block).lower())
            return place(b, {"region": region, "index": min(index, max(len(here) - 1, 0))})

        return moved

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
            labels = {**CHOICE_LABELS, **({"middle": "Centre"} if item.name == "title_align" else {})}
            style.append({"name": item.name, "label": STYLE_LABELS.get(item.name, item.name.replace("_", " ").title()),
                          "kind": kind, "default": value, "choices": choices,
                          "labels": {choice: labels.get(choice, choice.capitalize()) for choice in choices},
                          "note": STYLE_NOTES.get(item.name, "")})
        return {
            "themes": list(theme_names()),
            "looks": [
                {"name": name, "label": LOOK_LABELS.get(name, name.title()), "note": LOOK_NOTES.get(name, ""),
                 "style": {**LOOKS[name]}}
                for name in LOOKS
            ],
            "palettes": {name: list(colours) for name, colours in design_palettes().items()},
            "fonts": sorted(available_families()),
            "style": style,
            "layouts": [{"name": name, "label": LAYOUT_LABELS.get(name, name.title()), "note": LAYOUT_NOTES[name]}
                        for name in LAYOUTS],
            "slide_keys": {layout: [*COMMON_KEYS, *keys] for layout, keys in SLIDE_KEYS.items()},
            "blocks": {kind: list(options) for kind, options in BLOCKS.items()},
            # What the figure editor offers, for figures edited on their slides.
            "figure_editor": _figure_editor(),
        }

    # -- drawing --

    def draw(self, document: dict[str, Any], base: Path, hints: dict[str, Any] | None = None) -> Drawing:
        """Draw what has changed, the slide in focus first and its neighbours next;
        slides not reached within ``BUDGET`` seconds are left pending for the next call."""

        from flexo.draft import give_up_if_newer

        from flexo_talk.compose import CANT_DRAW, EDITING, PLACEHOLDERS, STANDING_ASIDE, render_slide

        errors: list[DeckDocumentError] = []
        try:
            deck = deck_from_document(document, base, errors=errors)
        except DeckDocumentError as error:
            return Drawing([], _placed([Message(_plain_message(error), "error", error.where)], document))
        except Exception as error:
            return Drawing([], _placed([Message(explain(error), "error", "deck")], document))
        slides = document.get("slides") or []
        # A picture or figure whose file is missing is said, and a box stands in for it:
        # the rest of its slide is drawn. So is a figure, or any object, that cannot be
        # drawn as written.
        stood_in = MissingFile | InvalidFigure | InvalidObject | UnknownLayout
        absent = [error for error in errors if isinstance(error, stood_in)]
        failed = {_slide_of(error.where): error for error in errors if not isinstance(error, stood_in)}
        deck_data = document.get("deck") or {}
        from flexo.studio import code_allowed

        head = _stable({
            "deck": deck_data, "base": str(base), "count": len(slides), "trusted": code_allowed.get(),
            # A theme file edited in the studio changes every slide without changing the deck.
            "themes": [(str(path), _stamp(path)) for path in _theme_files(deck_data, base)],
        })
        # (A section skipped is not among them: compose._skipped.)
        sections = [
            (slide.get("title"), slide.get("subtitle")) for slide in slides
            if isinstance(slide, dict) and slide.get("layout") == "section" and not _skipped(slide)
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
                    1 for item in slides[:index]
                    if isinstance(item, dict) and item.get("layout") == "section" and not _skipped(item)
                ),
                "slide": data,
                "files": [(str(file), _stamp(file)) for file in files],
            }))
        focus = int((hints or {}).get("focus") or 0)
        # While the deck is changed its figures keep their layouts (compose.EDITING); once
        # the changes stop the page asks to settle, and the slides that kept one are
        # drawn again with the best.
        settle = bool((hints or {}).get("settle"))
        started = time.perf_counter()
        drawn_one = False
        for index in _order(len(slides), focus):
            known = self._slides.get(keys[index])
            if index in failed or (known is not None and (known.get("settled", True) or not settle)):
                continue
            if drawn_one and time.perf_counter() - started > BUDGET:
                break
            slide = deck.slides[index]
            give_up_if_newer()  # (a settling given up for a change: flexo.draft)
            editing, placeholders, aside = EDITING.set(not settle), PLACEHOLDERS.set(True), STANDING_ASIDE.set(True)
            try:
                rendered = render_slide(deck, slide)
                self._slides[keys[index]] = {"svg": _presentable(rendered.svg, deck, slide), "steps": rendered.steps,
                                             "diagnostics": rendered.diagnostics, "notes": rendered.notes,
                                             "held": rendered.held, "settled": rendered.settled}
            except UntrustedCode as error:
                self._slides[keys[index]] = {"error": error.message, "code": "code.untrusted"}
            except DeckDocumentError as error:
                # Said on its slide, where it is: the message need not name the place again.
                self._slides[keys[index]] = {"error": _plain_message(error), "where": error.where}
            except Exception as error:
                self._slides[keys[index]] = {"error": explain(error)}
            finally:
                EDITING.reset(editing)
                PLACEHOLDERS.reset(placeholders)
                STANDING_ASIDE.reset(aside)
            drawn_one = True
        # Slides with photos carry them inside: the cache is held to a size in bytes too.
        while len(self._slides) > CACHE_SIZE or (
            len(self._slides) > 1 and sum(len(item.get("svg", "")) for item in self._slides.values()) > CACHE_BYTES
        ):
            self._slides.popitem(last=False)
        pages: list[Page] = []
        messages: list[Message] = []
        for index, (slide, data) in enumerate(zip(deck.slides, slides, strict=True)):
            identifier = slide.id
            done = self._slides.get(keys[index])
            for error in absent:
                if _slide_of(error.where) == index:
                    code = ("deck.missing" if isinstance(error, MissingFile) else "deck.object"
                            if isinstance(error, InvalidObject) else "deck.figure")
                    if isinstance(error, UnknownLayout):
                        # Drawn all the same, as Content: a note to choose one, not a fault.
                        messages.append(Message(error.message, "warning", error.where, identifier, "deck.layout"))
                        continue
                    messages.append(Message(_plain_message(error), "error", error.where, identifier, code))
            if index in failed:
                error = failed[index]
                messages.append(Message(_plain_message(error), "error", error.where, identifier, "deck.document"))
                pages.append(Page(identifier, _blank(deck, slide), _label(data), extra=_extra(data, error=True)))
            elif done is None:
                pages.append(Page(identifier, "", _label(data), extra=_extra(data), pending=True))
            elif "error" in done:
                # Python held back until the folder is trusted is not a mistake in the deck.
                held = done.get("code") == "code.untrusted"
                messages.append(Message(done["error"], "warning" if held else "error",
                                        done.get("where") or f"slides[{index}]", identifier,
                                        done.get("code", "deck.draw")))
                pages.append(Page(identifier, _blank(deck, slide), _label(data), extra=_extra(data, error=not held)))
            else:
                self._slides.move_to_end(keys[index])
                for text in done["diagnostics"]:
                    # An object that can't be drawn says so in its box; why, under the slide.
                    cant = re.match(rf"(\S+ \S+: )This \w+ {CANT_DRAW}: (.*)", text, re.S)
                    if cant:
                        messages.append(_diagnostic(cant[1] + cant[2], identifier, index, "error"))
                        continue
                    messages.append(_sized(_diagnostic(text, identifier, index, "warning")))
                for text in done["notes"]:
                    messages.append(_sized(_diagnostic(text, identifier, index, "note")))
                for text in done.get("held", []):
                    messages.append(Message(text, "warning", f"slides[{index}]", identifier, "code.untrusted"))
                pages.append(Page(identifier, done["svg"], _label(data), done["steps"], _extra(data)))
        unsettled = any(not self._slides.get(key, {}).get("settled", True) for key in keys)
        return Drawing(pages, _placed(messages, document), sorted(watched),
                       {"palette": _palette(deck), "tones": _tones(deck), "order": _palette_order(deck),
                        "own": _palette_order(deck, own=True), "fonts": _fonts(deck),
                        "unsettled": unsettled})

    def act(self, document: dict[str, Any], action: dict[str, Any], base: Path) -> dict[str, Any]:
        """An edit to a figure on a slide, made where the figure is written: in the deck
        (a figure written inline) or in its own file. ``action`` is ``{"do": "figure",
        "at": {"slide", "region", "index"}, "edit": <a flexo figure edit>}`` -- or
        ``{"do": "mechanism", ...}``, drawing on a mechanism (``_mechanism``), or
        ``{"do": "inline", "at"}``, a figure file's figure written into the deck
        (``_inline``), or ``{"do": "figure-file", "file", "text", "expect"}``, a figure
        file put back as an edit made on its slide found it or left it (``_restore``).

        An edit to a figure file answers with the file's text before and after it
        (``was``, ``now``) and both read as data (``change``): the studio keeps them in
        the deck's history, to undo the edit and say what it did."""

        import copy

        from flexo.studio.figure_edit import EditError, apply, apply_to_data, model

        if action.get("do") == "structure-fetch":
            # A PDB entry downloaded before a structure is made of it: its ID, or why not.
            from flexo.studio.figure_kind import fetched

            # One that can't be had is an answer, said on the page -- not a failed request
            # (which the browser would also log as one).
            try:
                return {"document": document, "id": fetched(str(action.get("id") or ""))}
            except EditError as error:
                return {"document": document, "failed": explain(error)}
        if action.get("do") == "structure-name":
            # What structure files say they hold, to name the parts made of them.
            from flexo.structures import structure_caption

            names = [structure_caption(base / str(source)) for source in action.get("sources") or []]
            return {"document": document, "names": names}
        if action.get("do") == "mechanism":
            return _mechanism(document, action, base)
        if action.get("do") == "inline":
            return _inline(document, action, base)
        if action.get("do") == "figure-file":
            return _restore(document, action, base)
        if action.get("do") != "figure":
            raise EditError(f"Unknown deck edit “{action.get('do')}”.")
        at = action.get("at") or {}
        edit = action.get("edit") or {}
        if edit.get("do") == "structure-view":
            return {"document": document, "view": _structure_view(document, at, str(edit.get("id")), base)}
        if edit.get("do") == "structure-settings":
            from flexo.studio.figure_kind import settings_of

            spec = _slide_figure(document, at, base)
            return {"document": document, "settings": settings_of(spec, str(edit.get("id")))}
        changed = copy.deepcopy(document)
        block = _block_at(changed, at)
        value = block.get("figure") if isinstance(block, dict) else None
        if isinstance(value, dict):
            made = apply_to_data(value, edit, base=base)
            block["figure"] = made["data"]
            if made["data"] != value:
                # A sample figure changed is the person's own: presented and exported.
                block.pop("placeholder", None)
            return {"document": changed, "select": made["select"], "model": made["model"]}
        if isinstance(value, str) and value and ".py:" not in value:
            path = _figure_file(base, value)
            was = path.read_text(encoding="utf-8")
            result = apply(was, edit, suffix=path.suffix, base=path.parent)
            answer = {"document": document, "select": result["select"],
                      "model": model(result["text"], suffix=path.suffix), "file": value}
            if edit.get("do") != "read" and result["text"] != was:
                path.write_text(result["text"], encoding="utf-8")
                answer |= {"was": was, "now": result["text"],
                           "change": [_figure_data(was, path.suffix), _figure_data(result["text"], path.suffix)]}
            return answer
        raise EditError("This figure is made in Python. Edit it in its Python file.")

    def export(
        self,
        document: dict[str, Any],
        base: Path,
        stem: str,
        formats: list[str],
        *,
        into: Path | None = None,
        steps: bool = False,
    ) -> list[Path]:
        """The deck's files, in ``build/`` beside it, named after the deck (talk.pdf,
        talk-01.png), or ``into`` a folder of the page's, where each slide's pictures go in
        a folder named after the deck, as slide-01.png. The PDF has a page per slide,
        showing it whole, as Keynote's does; with ``steps``, a page per stage of each list
        a slide reveals."""

        from flexo_talk.compose import CANT_DRAW, STANDING_ASIDE
        from flexo_talk.export import build_deck, file_stem

        errors: list[DeckDocumentError] = []
        try:
            deck = deck_from_document(document, base, errors=errors)
            # An object that can't be drawn, or whose file is not there, is left out, and said
            # (``export_notes``): one object does not stop the export. A slide that can't be
            # made at all does, said where it is.
            stood_in = MissingFile | InvalidFigure | InvalidObject | UnknownLayout
            wrong = next((error for error in errors if not isinstance(error, stood_in)), None)
            if wrong is not None:
                raise wrong
        except DeckDocumentError as error:
            # Said where it is as a person says it (“Slide 4 · Picture”), not as the document does.
            place = _place(error.where, document)
            raise ValueError(f"{place}: {error.message}" if place else error.message) from error
        self.export_notes = [
            # A slide of a layout there is none of is exported as it is drawn: as Content.
            f"{_place(found[0], document)}: {error.message.removesuffix(' Choose one from Layout.')}"
            if isinstance(error, UnknownLayout) and (found := re.match(r"slides\[\d+\]", error.where))
            else f"{_place(error.where, document) or 'A picture'} is left out: it isn\u2019t in the deck\u2019s "
            f"folder ({error.name})."
            if isinstance(error, MissingFile)
            else f"{_place(error.where, document) or 'A figure'}: {_drawn_plainly(error.message)}"
            if getattr(error, "drawn", None) is not None
            else f"{_place(error.where, document) or 'An object'} is left empty: it can\u2019t be drawn as it is."
            for error in errors
        ]
        # A slide skipped (Keynote's Skip Slide) is not exported, as it is not presented; the
        # others keep their numbers, as they are shown when presented.
        skipped = {index for index, data in enumerate(document.get("slides") or []) if _skipped(data)}
        deck.slides = [slide for index, slide in enumerate(deck.slides) if index not in skipped]
        if not deck.slides:
            raise ValueError("Every slide is skipped: there is nothing to export.")
        self.export_notes = [note for note in self.export_notes
                             if not (found := re.match(r"Slide (\d+)\b", note)) or int(found[1]) - 1 not in skipped]
        folder = into or base / "build"
        images = folder / file_stem(deck.id) if into is not None else None
        aside = STANDING_ASIDE.set(True)
        try:
            result = build_deck(deck, folder, tuple(formats), handout=not steps, images=images)
        finally:
            STANDING_ASIDE.reset(aside)
        # (One that failed only as it was drawn for its slide is left empty too, and said.)
        self.export_notes += [
            f"{_place(f'slides[{int(found[1]) - 1}] {found[2]}', document)} is left empty: "
            "it can\u2019t be drawn as it is."
            for text in dict.fromkeys(result.diagnostics)
            if (found := re.match(r"slide(\d+) (\S+): This \w+ " + re.escape(CANT_DRAW), text))
        ]
        # A shape it can't draw as written is a plain box of its words, and said so.
        plain: dict[int, list[str]] = {}
        for text in dict.fromkeys(result.diagnostics):
            found = re.match(r"slide(\d+)\S* \S+#\S+: ((?:\u201c[^\u201d]*\u201d|A shape) can\u2019t be drawn yet.*)",
                             text)
            if found:
                plain.setdefault(int(found[1]) - 1, []).append(found[2])
        self.export_notes += [
            f"{_place(f'slides[{index}].body[0] (figure)', document)}: {_drawn_plainly(' '.join(said))}"
            for index, said in plain.items()
        ]
        # A line to a shape a figure has none of is left out of it, and said with its slide.
        self.export_notes += [
            f"{_place(f'slides[{int(found[1]) - 1}]', document)}: {found[2]} It is left out."
            for text in dict.fromkeys(result.diagnostics)
            if (found := re.match(r"slide(\d+)\S* \S+: (A line (?:to|from) .* has no shape to (?:go to|start from)\.)",
                                  text))
        ]
        written = [result.pptx, result.pdf, *result.svgs, *result.pngs]
        return [path for path in written if path]

    def export_part(
        self,
        document: dict[str, Any],
        base: Path,
        stem: str,
        part: dict[str, Any],
        formats: list[str],
        *,
        into: Path | None = None,
    ) -> list[Path]:
        """A figure on a slide written out as a figure of its own, in the deck's look: its
        document (``yaml``, a flexo figure file) and what flexo builds of it (``editable``
        and ``portable`` SVG, ``pdf``, ``png``). It is laid out as written, not as fitted
        to the slide. Files go in ``build/`` beside the deck, the files the figure names
        (a theme, structures, pictures) named from there; or ``into`` a folder of the
        page's, naming those files by where they are."""

        import os
        from dataclasses import replace

        import yaml
        from flexo.export import build
        from flexo.serialization import figure_to_document, parse_figure
        from flexo.studio.figure_edit import EditError

        from flexo_talk.deck import made
        from flexo_talk.document import _figure, make_deck

        block = _block_at(document, part)
        if not isinstance(block, dict) or "figure" not in block:
            raise EditError("The selected object isn't a figure.")
        deck = make_deck(document.get("deck") or {}, base)
        where = f"slides[{part.get('slide')}].{part.get('region')}[{part.get('index')}]"
        figure = made(_figure(base, block["figure"], where, None))
        spec = getattr(figure, "spec", figure)
        spec = replace(
            spec, style=deck.theme, palette=deck.palette_name,
            font=deck.figure_font or deck.font or spec.font,
        )
        # The files its parts draw, wherever it names them from (a figure file names them
        # from its own folder), found once and for all.
        value = block["figure"]
        origin = (base / value).parent if isinstance(value, str) and ".py:" not in value else base
        data = figure_to_document(spec)
        for node in data.get("nodes") or []:
            properties = node.get("properties") or {}
            source = properties.get("source")
            if isinstance(source, str) and source and not Path(source).is_absolute() and (origin / source).is_file():
                properties["source"] = str((origin / source).resolve())
        spec = parse_figure(data)
        folder = into or base / "build"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{stem}-{spec.id}"
        if into is not None:
            # Handed to a person, it is named as they would name it: the deck and the slide.
            slides = document.get("slides") or []
            number = int(part.get("slide") or 0)
            slide = slides[number] if 0 <= number < len(slides) and isinstance(slides[number], dict) else {}
            words = str(slide.get("title") or slide.get("words") or "")
            title = re.sub(r"[*`$\[\]{}]|\(https?://[^)]*\)", "", words).strip() or f"Slide {number + 1}"
            name = re.sub(r'[/\\*?"<>|]', "-", f"{stem} \u2013 {title}".replace(":", ""))[:120]
        written: list[Path] = []
        if "yaml" in formats:

            def beside(value: object) -> object:
                # A file inside the folder is named from where the figure file is.
                if into is not None or not (isinstance(value, str) and Path(value).is_absolute()):
                    return value
                return os.path.relpath(value, folder) if Path(value).is_relative_to(base.resolve()) else value

            for key in ("style", "theme", "palette"):
                if key in data["figure"]:
                    data["figure"][key] = beside(data["figure"][key])
            for node in data.get("nodes") or []:
                properties = node.get("properties") or {}
                if "source" in properties:
                    properties["source"] = beside(properties["source"])
            target = folder / f"{name}.yaml"
            target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
            written.append(target)
        built = [item for item in formats if item != "yaml"]
        if built:
            result = build(spec, folder, stem=name, formats=tuple(built))
            made = list(result.outputs.existing())
            if into is not None and "editable" not in built and len(made) > 1:
                # The editable SVG is written whatever is asked for: made aside, to be
                # handed over, only what was asked for is.
                result.outputs.editable_svg.unlink()
                made.remove(result.outputs.editable_svg)
            if into is not None and len(made) == 1:
                # One file, handed over: plainly named, not "….preview.png".
                plain = made[0].with_name(f"{name}{made[0].suffix}")
                made = [made[0].rename(plain)]
            written += made
        return written

    def text(self, document: dict[str, Any]) -> str:
        return dump_document(document)


def _mechanism(document: dict[str, Any], action: dict[str, Any], base: Path) -> dict[str, Any]:
    """Drawing on a mechanism's ``step`` (from 0), as mechazyme's editor does: ``add``
    an arrow (``{"tail", "head", "half"}``, each end ``{"atom": i}`` or ``{"bond": [i, j]}``),
    ``remove`` one (its place in the step), ``place`` a molecule (``{"atom", "move",
    "turn", "flip", "reset"}``), or none of these, to see the step. Returns
    the ``document`` and the step's ``sheet`` -- laid out for the arrows ``holding`` gives,
    so it holds still while it is drawn on -- or, when a bond's electrons go to an atom
    outside it, the ``ends`` it could bond from, to ask which."""

    from flexo.studio.figure_edit import EditError
    from flexo.studio.mechanism_edit import OPTIONS, add_arrow, place_molecule, remove_arrow, sheet

    from flexo_talk.document import make_deck

    changed = copy.deepcopy(document)
    block = _block_at(changed, action.get("at") or {})
    if not isinstance(block, dict) or "mechanism" not in block:
        raise EditError("This object is no longer a mechanism. Someone else may have changed it.")
    options = {key: block.get(key) for key in OPTIONS}
    step = int(action.get("step") or 0)
    holding = action.get("holding")
    holding = [str(item) for item in holding] if isinstance(holding, list) else None
    said: dict[str, Any] = {}
    if isinstance(action.get("add"), dict):
        add = action["add"]
        made = add_arrow(block["mechanism"], step=step, tail=add.get("tail") or {}, head=add.get("head") or {},
                         half=bool(add.get("half")), options=options)
        if "ends" in made:
            return {"document": document, "ends": made["ends"]}
        block["mechanism"] = _written(made["steps"])
        said["arrow"] = made["arrow"]
    elif isinstance(action.get("place"), dict):
        how = action["place"]
        move = how.get("move")
        block["mechanism"] = _written(place_molecule(
            block["mechanism"], step=step, atom=int(how.get("atom") or 0),
            move=[float(move[0]), float(move[1])] if isinstance(move, list) and len(move) == 2 else None,
            turn=float(how.get("turn") or 0), flip=bool(how.get("flip")), reset=bool(how.get("reset")),
            options=options)["steps"])
    elif action.get("remove") is not None:
        block["mechanism"] = _written(remove_arrow(block["mechanism"], step=step, index=int(action["remove"]))["steps"])
    else:
        changed = document
        block = _block_at(changed, action.get("at") or {})
    try:
        # Drawn in the deck's look, as the slide draws it.
        look = make_deck(document.get("deck") or {}, base).figure_options()
    except (DeckDocumentError, ValueError, TypeError, OSError):
        look = {}
    drawn = sheet(block["mechanism"], step=step, holding=holding, options=options, look=look)
    return {"document": changed, "sheet": drawn, **said}


def _figure_file(base: Path, value: str) -> Path:
    """The figure file ``value`` names, in the deck's folder."""

    from flexo.studio.figure_edit import EditError

    path = (base / value).resolve()
    figure = path.suffix.lower() in {".yaml", ".yml", ".json"}
    if not figure or not path.is_file() or not path.is_relative_to(base.resolve()):
        raise EditError(f"Can't find the figure file “{value}” in the deck's folder.")
    return path


def _restore(document: dict[str, Any], action: dict[str, Any], base: Path) -> dict[str, Any]:
    """A figure file put back as an edit made on its slide found it (undone) or left it
    (done again): from ``expect``, the file as the edit left (found) it, to ``text``. A
    change made to the file since, by hand or by someone else, is kept: the edit is
    taken back around it, unless it changed the same lines."""

    from flexo.studio.figure_edit import EditError

    value = str(action.get("file") or "")
    path = _figure_file(base, value)
    now, expect, text = path.read_text(encoding="utf-8"), str(action.get("expect") or ""), str(action.get("text") or "")
    if now != expect:
        text = _merged_lines(expect, now, text)
        if text is None or _figure_data(text, path.suffix) is None:
            raise EditError(f"“{value}” has changed in the same place since this edit, so it was left as it is.")
    path.write_text(text, encoding="utf-8")
    return {"document": document, "file": value}


def _merged_lines(base: str, ours: str, theirs: str) -> str | None:
    """Two changes to a file's text, merged line by line; None where they touch the same
    words, so neither is lost (merged both ways round, the two must agree)."""

    from flexo.studio.merge import merge_lists

    lines = [text.splitlines(keepends=True) for text in (base, ours, theirs)]
    one, other = merge_lists(*lines), merge_lists(lines[0], lines[2], lines[1])
    return "".join(one) if one == other else None


def _figure_data(text: str, suffix: str) -> Any:
    """A figure file's text as data (None if it does not read)."""

    import json

    import yaml

    try:
        return json.loads(text) if suffix.lower() == ".json" else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError):
        return None


def _structure_view(document: dict[str, Any], at: dict[str, Any], identifier: str, base: Path) -> Any:
    """A structure's trace and turn on a slide, in the deck's look, as the slide draws it."""

    from flexo.studio.figure_kind import view_of

    return view_of(_slide_figure(document, at, base), identifier)


def _slide_figure(document: dict[str, Any], at: dict[str, Any], base: Path) -> Any:
    """The figure at ``at`` on a slide, in the deck's look, as the slide draws it."""

    from dataclasses import replace

    from flexo.studio.figure_edit import EditError

    from flexo_talk.deck import made
    from flexo_talk.document import InvalidFigure, _figure, _strays, make_deck

    block = _block_at(document, at)
    if not isinstance(block, dict) or "figure" not in block:
        raise EditError("This object is no longer a figure. Someone else may have changed it.")
    deck = make_deck(document.get("deck") or {}, base)
    # (As the slide draws it: a line to a shape it has none of left out, a shape that can't be
    # drawn as written a plain box -- what is asked of a structure in it the same.)
    value = block["figure"]
    strays = _strays(value)
    try:
        figure = made(_figure(base, {**value, "edges": strays[1]} if strays else value, "figure", None))
    except InvalidFigure as error:
        if error.drawn is None:
            raise
        figure = made(error.drawn)
    spec = getattr(figure, "spec", figure)
    return replace(spec, style=deck.theme, palette=deck.palette_name, font=deck.figure_font or deck.font or spec.font)


def _inline(document: dict[str, Any], action: dict[str, Any], base: Path) -> dict[str, Any]:
    """The figure a slide takes from a figure file, written into the deck as it is, so it
    is kept with the slide: the files it names (structures, pictures, a theme) named from
    the deck's folder. The file is left as it was."""

    import os

    import yaml
    from flexo.studio.figure_edit import EditError

    changed = copy.deepcopy(document)
    block = _block_at(changed, action.get("at") or {})
    value = block.get("figure") if isinstance(block, dict) else None
    if isinstance(value, dict):
        return {"document": document}
    if not isinstance(value, str) or not value or ".py:" in value:
        raise EditError("Only a figure stored in a file can be moved into the deck.")
    path = (base / value).resolve()
    if not path.is_file() or not path.is_relative_to(base.resolve()):
        raise EditError(f"Can't find the figure file “{value}” in the deck's folder.")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))  # JSON reads as YAML too
    if not isinstance(data, dict):
        raise EditError(f"“{value}” isn't a figure.")

    def rebased(name: object) -> object:
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            return name
        found = (path.parent / name).resolve()
        return os.path.relpath(found, base.resolve()) if found.is_file() else name

    for key in ("theme", "style", "palette"):
        if isinstance(data.get("figure"), dict) and key in data["figure"]:
            data["figure"][key] = rebased(data["figure"][key])
    for node in data.get("nodes") or []:
        properties = node.get("properties") if isinstance(node, dict) else None
        if isinstance(properties, dict) and "source" in properties:
            properties["source"] = rebased(properties["source"])
    block["figure"] = data
    return {"document": changed}


def _written(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Steps as the document keeps them: a step's arrows left out when it has none."""

    return [{key: value for key, value in step.items() if not (key == "arrows" and not value)} for step in steps]


def _figure_editor() -> dict[str, Any]:
    from flexo.studio.figure_parts import catalogue

    return catalogue()


def _block_at(document: dict[str, Any], at: dict[str, Any]) -> Any:
    """The block at ``{"slide", "region", "index"}``: a region is ``body``, ``left``,
    ``right``, or ``columns.N``."""

    from flexo.studio.figure_edit import EditError

    try:
        slide = (document.get("slides") or [])[int(at["slide"])]
        region = str(at["region"])
        column = region.startswith("columns.")
        blocks = slide["columns"][int(region.split(".", 1)[1])] if column else slide[region]
        return blocks[int(at["index"])]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise EditError("This object no longer exists. Someone else may have changed the slide.") from error


def _order(count: int, focus: int) -> list[int]:
    """The slide in focus, then outward from it, then the rest from the start."""

    focus = min(max(focus, 0), max(count - 1, 0))
    near = [focus, focus + 1, focus - 1, focus + 2, focus - 2]
    seen = [index for index in dict.fromkeys(near) if 0 <= index < count]
    return seen + [index for index in range(count) if index not in seen]


def _likeness(old: Any, text: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, json.dumps(old, sort_keys=True, default=str), text).ratio()


_REGIONS = ("body", "left", "right")
"""A slide's places for objects that an object is followed in (a column's are not)."""


def _blocks(slide: Any, region: Any) -> list:
    blocks = slide.get(region) if isinstance(slide, dict) and region in _REGIONS else None
    return blocks if isinstance(blocks, list) else []


def _slide_pairs(old: list, new: list) -> list[tuple[str, Any, Any]]:
    """How a deck's slides before a change are those after it, in their order after:
    ("equal", a, b), ("moved", a, b) -- the same slide taken out and put back elsewhere --
    ("changed", a, b), ("added", None, b), and ("deleted", [a, ...], b), b where they were."""

    import difflib

    keys = [_stable(slide) for slide in old], [_stable(slide) for slide in new]
    codes = difflib.SequenceMatcher(None, *keys, autojunk=False).get_opcodes()
    out = [a for tag, a1, a2, _, _ in codes if tag in ("delete", "replace") for a in range(a1, a2)]
    into = [b for tag, _, _, b1, b2 in codes if tag in ("insert", "replace") for b in range(b1, b2)]
    moves: dict[int, int] = {}
    for b in into:
        a = next((a for a in out if keys[0][a] == keys[1][b] and a not in moves.values()), None)
        if a is not None:
            moves[b] = a
    taken = set(moves.values())
    steps: list[tuple[str, Any, Any]] = []
    for tag, a1, a2, b1, b2 in codes:
        if tag == "equal":
            steps += [("equal", a1 + k, b1 + k) for k in range(a2 - a1)]
            continue
        # Slides replaced by others: pair each new one with the old one it most resembles,
        # or, as many in as out, with the one in its place if it is of a kind with it (its
        # title or its layout): a list pasted into is that slide edited, not another.
        olds = [a for a in range(a1, a2) if a not in taken]
        fresh = [b for b in range(b1, b2) if b not in moves]
        unused = list(olds)
        for b in range(b1, b2):
            if b in moves:
                steps.append(("moved", moves[b], b))
                continue
            text = json.dumps(new[b], sort_keys=True, default=str)
            best = max(((_likeness(old[i], text), i) for i in unused), default=(0.0, -1))
            placed = olds[fresh.index(b)] if len(olds) == len(fresh) else -1
            # (The one in its place with its title is itself, however much else changed: an
            # object dragged from it to the slide beside it leaves each slide itself.)
            itself = placed in unused and _titled(old[placed]) == _titled(new[b]) != ""
            if itself or (best[0] <= 0.5 and placed in unused and _kin(old[placed], new[b])):
                best = (1.0, placed)
            if best[0] > 0.5:
                unused.remove(best[1])
                steps.append(("changed", best[1], b))
            else:
                steps.append(("added", None, b))
        if unused:
            steps.append(("deleted", unused, b1))
    return steps


def _titled(slide: Any) -> str:
    return str(slide.get("title") or slide.get("words") or "").strip() if isinstance(slide, dict) else ""


def _moved_note(a: int, b: int, new: list, was: dict[int, int]) -> dict[str, Any]:
    """A slide moved, by the slides it is now between: "moved slide 3 after slide 4" -- as
    numbered before (two slides swapped, the first said moved down past the second)."""

    after, before = was.get(b - 1), was.get(b + 1)
    if after is not None and after > a:
        text = f"moved slide {a + 1} after slide {after + 1}"
    elif before is not None and before == a - 1 and (after is None or after < before):
        text, b = f"moved slide {before + 1} after slide {a + 1}", b + 1
    elif before is not None and before < a:
        text = f"moved slide {a + 1} before slide {before + 1}"
    else:
        text = f"moved slide {a + 1} to slide {b + 1}"
    return {"text": text, "where": {"page": b + 1, "label": f"Slide {b + 1}"}}


def _object_changed(old: Any, new: Any) -> dict[str, Any] | None:
    """The one object a change to a slide added or changed, as {region, index}; None if it
    changed more, or less."""

    regions = [key for key in _REGIONS if _blocks(old, key) != _blocks(new, key)]
    if len(regions) != 1:
        return None
    was, now = _blocks(old, regions[0]), _blocks(new, regions[0])
    kept = {_stable(block) for block in was}
    if len(now) == len(was):
        changed = [index for index, (a, b) in enumerate(zip(was, now, strict=True)) if a != b]
    else:
        changed = [index for index, block in enumerate(now) if _stable(block) not in kept]
    return {"region": regions[0], "index": changed[0]} if len(changed) == 1 else None


def _one_block(old: Any, new: Any) -> str | None:
    """The one object a change to a slide took away or put there, by what it says (as JSON);
    None if it did more."""

    before = [json.dumps(block, sort_keys=True, default=str) for key in _REGIONS for block in _blocks(old, key)]
    after = [json.dumps(block, sort_keys=True, default=str) for key in _REGIONS for block in _blocks(new, key)]
    gone = [block for block in before if block not in after]
    came = [block for block in after if block not in before]
    return (gone or came)[0] if len(gone) + len(came) == 1 else None


def _gone(what: str) -> dict[str, Any]:
    """A place in the activity list that is no more: said so when it is clicked."""

    return {"label": "Since deleted", "gone": f"That {what} has since been deleted."}


def _clipped(text: str, limit: int = 40) -> str:
    """A title as long as a note has room for: cut at a word, and said to be ("…")."""

    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    cut = cut.rsplit(" ", 1)[0] if " " in cut.strip() else text[:limit]
    return cut.rstrip(" ,;:.-\u2013\u2014\u00b7") + "\u2026"


def _slide_note(verb: str, slides: list, index: int, what: str = "") -> dict[str, Any]:
    slide = slides[index] if index < len(slides) and isinstance(slides[index], dict) else {}
    title = str(slide.get("words") or slide.get("title") or "").strip()
    named = f", “{_clipped(title)}”" if title and verb == "added" else ""
    # "edited the title on slide 4", "added Table to slide 2", "added slide 5, “Methods”":
    # what changed first, as said aloud.
    where = {"added": "to", "deleted": "from"}.get(verb, "on")
    text = f"{verb} {what} {where} slide {index + 1}" if what else f"{verb} slide {index + 1}{named}"
    return {"text": text,
            "where": {"page": index + 1, "label": f"Slide {index + 1}"}}


def _kin(old: Any, new: Any) -> bool:
    """Whether two slides are one slide before and after a change: the same title, or the
    same layout."""

    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    title = str(old.get("title") or old.get("words") or "").strip()
    same_title = bool(title) and title == str(new.get("title") or new.get("words") or "").strip()
    return same_title or old.get("layout") == new.get("layout")


_OBJECTS = {"bullets": "List", "text": "Text", "figure": "Figure", "image": "Picture", "table": "Table",
            "math": "Equation", "code": "Code", "quote": "Quote", "callout": "Callout", "stats": "Numbers",
            "gallery": "Gallery", "plot": "Plot", "mechanism": "Mechanism"}
"""Each object a slide holds, by its name in the studio (its Insert menu, its inspector)."""


def _object_name(block: Any) -> str:
    """An object's name in the studio: a figure of steps and decisions is a Flow Chart, one of
    structures alone a Structure."""

    kind = next((key for key in block if key in _OBJECTS), "") if isinstance(block, dict) else ""
    figure = block.get("figure") if kind == "figure" else None
    nodes = [node for node in figure.get("nodes") or [] if isinstance(node, dict)] if isinstance(figure, dict) else []
    if nodes and all(node.get("kind") == "structure" for node in nodes):
        return "Structure"
    if any(node.get("kind") in ("terminal", "decision") for node in nodes):
        return "Flow Chart"
    return _OBJECTS.get(kind, "Object")


def _a(name: str) -> str:
    """An object as said aloud after "added" or "deleted", as "the list" is after "edited":
    "a table", "an equation", "a flow chart" -- text, numbers and code with no article
    ("added text", never "a numbers")."""

    word = name.lower()
    if name in ("Text", "Numbers", "Code"):
        return word
    return f"{'an' if word[0] in 'aeiou' else 'a'} {word}"


def _objects(old: Any, new: Any) -> tuple[str, str]:
    """What changed among a slide's objects, as said aloud: ("edited", "the list"), ("added",
    "a table") -- an object added or deleted by its name, as the studio names it -- ("edited",
    "the list and the figure")."""

    name = _object_name

    was = old if isinstance(old, list) else []
    now = new if isinstance(new, list) else []
    if len(now) > len(was):
        kept = [json.dumps(block, sort_keys=True, default=str) for block in was]
        added = [block for block in now if json.dumps(block, sort_keys=True, default=str) not in kept]
        return ("added", _a(name(added[0]))) if added else ("edited", "its content")
    if len(now) < len(was):
        kept = [json.dumps(block, sort_keys=True, default=str) for block in now]
        gone = [block for block in was if json.dumps(block, sort_keys=True, default=str) not in kept]
        return ("deleted", _a(name(gone[0]))) if gone else ("edited", "its content")
    changed = list(dict.fromkeys(_part_edited(a, b) for a, b in zip(was, now, strict=True) if a != b))
    return "edited", " and ".join(changed[:2]) or "its content"


def _part_edited(old: Any, new: Any) -> str:
    """An object edited, as said aloud: "the quote" -- or the part of it edited, by the name
    the inspector gives it ("the attribution")."""

    if isinstance(old, dict) and isinstance(new, dict):
        keys = {key for key in {*old, *new} if old.get(key) != new.get(key)}
        if keys == {"by"}:
            return "the attribution"
    return f"the {_object_name(new).lower()}"


_WORDY = ("text", "bullets")


def _lines(block: dict[str, Any]) -> list[str] | None:
    """An object's words a line each, as a paragraph and a list are made one of the other
    (each line an item, each item a line), if it is one of those."""

    # (A space at a line's end, typed and waiting for the next word, stays: as the editor's.)
    if isinstance(block.get("text"), str):
        return [line.lstrip() for line in block["text"].split("\n") if line.strip()]
    if "bullets" not in block:
        return None
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif str(value or "").strip():
            found.append(str(value).lstrip())

    walk(block["bullets"])
    return found


def _alike_lines(first: list[str], second: list[str]) -> float:
    """How alike two objects' words are, from 0 to 1, by the letters they share at their ends
    (as the editor's alikeLines)."""

    a, b = "\n".join(first), "\n".join(second)
    if not a and not b:
        return 1.0
    start = 0
    while start < len(a) and start < len(b) and a[start] == b[start]:
        start += 1
    end = 0
    while end < len(a) - start and end < len(b) - start and a[-1 - end] == b[-1 - end]:
        end += 1
    return 2 * (start + end) / (len(a) + len(b))


def _aligned(document: object, notes: list) -> None:
    """A table's cell kept for someone typing in it (merge3's ``{"kept": …}`` note) while the
    other side took its column away: the cell goes with its column -- the rows stay aligned,
    the taking away wins -- and its note is settled (taken out of ``notes``)."""

    kept = [note for note in notes if "kept" in note and isinstance(note.get("item"), str)]
    if not kept:
        return

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        table = value.get("table")
        if isinstance(table, list) and len(table) > 1 and all(isinstance(row, list) for row in table):
            holds = [any(note["item"] in row for note in kept) for row in table]
            others = [row for row, held in zip(table, holds, strict=True) if not held]
            width = len(others[0]) if others else None
            if others and all(len(row) == width for row in others):
                for row in table:
                    note = next((one for one in kept if one["item"] in row), None) if len(row) == width + 1 else None
                    if note is None:
                        continue
                    row.pop(row.index(note["item"]))
                    kept.remove(note)
                    notes.remove(note)
        for item in value.values():
            walk(item)

    walk(document)


def _converted(document: object, notes: list, base: object) -> None:
    """An object kept for someone typing in it (merge3's ``{"kept": …}`` note) while the other
    side made it another kind, beside it: the two made one, of the new kind, with both sides'
    words. Settled notes are taken out of ``notes``."""

    if not isinstance(document, dict) or not any("kept" in note for note in notes):
        return
    from flexo.studio.merge import merge3

    def lists(slide: Any) -> list[list]:
        if not isinstance(slide, dict):
            return []
        found = [slide[key] for key in ("body", "left", "right") if isinstance(slide.get(key), list)]
        return found + [column for column in slide.get("columns") or [] if isinstance(column, list)]

    slides = base.get("slides") or [] if isinstance(base, dict) else []
    olds = [block for slide in slides for blocks in lists(slide) for block in blocks if isinstance(block, dict)]
    for note in list(notes):
        item = note.get("item")
        if "kept" not in note or not isinstance(item, dict) or _lines(item) is None:
            continue
        kind = next(key for key in _WORDY if key in item)
        for blocks in (blocks for slide in document.get("slides") or [] for blocks in lists(slide)):
            index = next((n for n, block in enumerate(blocks) if block == item), None)
            if index is None:
                continue
            for near in (index + 1, index - 1):
                other = blocks[near] if 0 <= near < len(blocks) and isinstance(blocks[near], dict) else None
                if other is None or _lines(other) is None or kind in other:
                    continue
                if _alike_lines(_lines(other), _lines(item)) < 0.5:
                    continue
                # Both sides' words: from what it was, as the kind it became.
                was = next(
                    (old for old in olds if kind in old and _alike_lines(_lines(old), _lines(item)) >= 0.5),
                    None,
                )
                lines = merge3(_lines(was) if was else _lines(other), _lines(other), _lines(item))
                made = dict(other)
                if "bullets" in made:
                    made["bullets"] = lines or [""]
                else:
                    made["text"] = "\n".join(lines)
                blocks[near] = made
                del blocks[index]
                notes.remove(note)
                break
            break


def _one_kind(document: object, base: object) -> None:
    """Every object of one kind, as a slide draws it: one written with two kinds' words (a
    paragraph's typed into it while it was made a list) is the kind it was made, the other's
    words merged into it -- never written as a block the slide cannot draw."""

    from flexo_talk.document import BLOCKS

    olds = [block for blocks in _regions(base) for block in blocks if isinstance(block, dict)]
    for blocks in _regions(document):
        for block in blocks:
            kinds = [key for key in block if key in BLOCKS] if isinstance(block, dict) else []
            if len(kinds) > 1:
                _made_one(block, kinds, olds)


def _laid_out(document: object) -> None:
    """Every slide's objects in the places its layout has: one a merge left where the layout
    has none (a body beside the two columns the slide was just set out in) is put in the
    first place it has -- each object not there already, after those there -- never left for
    the slide not to draw. (A layout with no place for objects is left as it is.)"""

    from flexo_talk.document import SLIDE_KEYS

    for slide in (document.get("slides") or []) if isinstance(document, dict) else []:
        if not isinstance(slide, dict):
            continue
        keys = SLIDE_KEYS.get(str(slide.get("layout", "content")), ())
        places = [key for key in _PLACES if key in keys]
        stray = [key for key in _PLACES if key in slide and key not in keys]
        if not places or not stray:
            continue
        there = [block for key in places for block in _blocks_in(slide.get(key), key)]
        lost = [
            block
            for key in stray
            for block in _blocks_in(slide.pop(key), key)
            if not any(_alike_blocks(block, other) for other in there)
        ]
        if not lost:
            continue
        if places[0] == "columns":
            columns = slide.get("columns") if isinstance(slide.get("columns"), list) else []
            slide["columns"] = [*(columns or [[]])]
            slide["columns"][0] = [*slide["columns"][0], *lost]
        else:
            slide[places[0]] = [*(slide.get(places[0]) or []), *lost]


_PLACES = ("body", "left", "right", "columns")


def _blocks_in(value: Any, key: str) -> list:
    """The objects in one of a slide's places (a list of them, or, columns, of lists)."""

    if not isinstance(value, list):
        return []
    if key == "columns":
        return [block for column in value if isinstance(column, list) for block in column]
    return list(value)


def _alike_blocks(first: Any, second: Any) -> bool:
    """Whether two objects are one, as kept twice: the same, or with words alike."""

    if first == second:
        return True
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    ours, theirs = _lines(first), _lines(second)
    return ours is not None and theirs is not None and _alike_lines(ours, theirs) >= 0.5


def _regions(deck: object) -> list[list]:
    """The lists of objects of a deck's slides: their bodies, sides and columns."""

    found: list[list] = []
    for slide in (deck.get("slides") or []) if isinstance(deck, dict) else []:
        if isinstance(slide, dict):
            found += [slide[key] for key in ("body", "left", "right") if isinstance(slide.get(key), list)]
            found += [column for column in slide.get("columns") or [] if isinstance(column, list)]
    return found


def _made_one(block: dict[str, Any], kinds: list[str], olds: list[dict[str, Any]]) -> None:
    """``block``, written with several ``kinds``, made the one it was made since: the kind it
    was is its old self's among ``olds`` (else, a list made of a paragraph, the paragraph's),
    and its words are merged into the other's."""

    from flexo.studio.merge import merge3

    def alike(old: dict[str, Any], kind: str) -> float:
        ours, theirs = _lines({kind: old[kind]}), _lines({kind: block[kind]})
        if ours is None or theirs is None:
            return 1.0 if old[kind] == block[kind] else 0.0
        return _alike_lines(ours, theirs)

    scored = [
        (alike(old, kind), kind, old)
        for old in olds
        if sum(key in old for key in kinds) == 1
        for kind in kinds
        if kind in old
    ]
    best = max(scored, key=lambda found: found[0], default=None)
    found = best is not None and best[0] >= 0.5
    stale = best[1] if found else ("text" if "text" in kinds else kinds[-1])
    kind = next(key for key in kinds if key != stale)
    if stale in _WORDY and kind in _WORDY:
        made, typed = _lines({kind: block[kind]}) or [], _lines({stale: block[stale]}) or []
        lines = merge3(_lines({stale: best[2][stale]}) if found else made, made, typed)
        if lines != made:
            block[kind] = (lines or [""]) if kind == "bullets" else "\n".join(lines)
    for other in kinds:
        if other != kind:
            del block[other]


def _placeholder(block: Any) -> bool:
    """An object with nothing of its person's in it yet, as the studio's editor reads one: an
    empty text, list, quote, callout, code, numbers, table or equation, a new figure's lone
    empty shape, or a sample (``placeholder: true``)."""

    from flexo_talk.document import _lone_shape

    if not isinstance(block, dict):
        return False
    if block.get("placeholder") or ("figure" in block and _lone_shape(block["figure"])):
        return True
    kinds = ("text", "bullets", "code", "quote", "callout", "stats", "table", "math")
    kind = next((key for key in kinds if key in block), None)

    def words(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [word for item in value.values() for word in words(item)]
        if isinstance(value, list):
            return [word for item in value for word in words(item)]
        return [] if value is None else [str(value)]

    said = words([block[kind], block.get("title"), block.get("by")]) if kind is not None else []
    return kind is not None and not any(word.strip() for word in said)


def _without_placeholders(slide: Any) -> Any:
    """A slide as it would be without its placeholders."""

    if not isinstance(slide, dict):
        return slide
    kept = dict(slide)
    for key in ("body", "left", "right"):
        if isinstance(kept.get(key), list):
            kept[key] = [block for block in kept[key] if not _placeholder(block)]
    if isinstance(kept.get("columns"), list):
        kept["columns"] = [
            [block for block in column if not _placeholder(block)] if isinstance(column, list) else column
            for column in kept["columns"]
        ]
    return kept


def _what_changed(old: Any, new: Any) -> tuple[str, str]:
    """What a change did to a slide: its verb and what it did it to."""

    if not isinstance(old, dict) or not isinstance(new, dict):
        return "edited", ""
    keys = [key for key in dict.fromkeys([*old, *new]) if old.get(key) != new.get(key)]
    # A slide's layout changed is what it is, whatever its objects did with it.
    if "layout" in keys:
        return "changed", "the layout"
    # An object made another kind in its place ("- " typed in a text): "made the text a list".
    bodies = [slide.get("body") if isinstance(slide.get("body"), list) else [] for slide in (old, new)]
    if "body" in keys and len(bodies[0]) == len(bodies[1]):
        for was, now in zip(*bodies, strict=True):
            if isinstance(was, dict) and isinstance(now, dict) and _object_name(was) != _object_name(now):
                # (One put in an empty placeholder's place is added: there was nothing to make.)
                if _placeholder(was):
                    return "added", _a(_object_name(now))
                return "made", f"the {_object_name(was).lower()} {_a(_object_name(now))}"
    # A figure's shapes changed, said as the figure says it: "added “Log it” to the flow chart".
    if "body" in keys and len(bodies[0]) == len(bodies[1]):
        changed = [(was, now) for was, now in zip(*bodies, strict=True) if was != now]
        if len(changed) == 1 and (said := _figure_said(*changed[0])):
            return said
    # An object added or deleted is what the change did. One that was there empty and is
    # typed in is filled in, and one made empty again (its typing undone) is emptied: still
    # there, neither added nor deleted.
    held = [len(body) for body in bodies]
    old, new = _without_placeholders(old), _without_placeholders(new)
    if "body" in keys and (done := _objects(old.get("body"), new.get("body")))[0] != "edited":
        if held[0] == held[1]:
            name = re.sub(r"^an? ", "", done[1])
            return ("emptied" if done[0] == "deleted" else "filled in"), f"the {name}"
        return done
    # A setting by the name the inspector gives it ("the statement", "the attribution"), never its key.
    names = {"left": "the left column", "right": "the right column", "columns": "its columns"}
    said = list(dict.fromkeys(_objects(old.get(key), new.get(key))[1] if key == "body"
                              else names.get(key) or f"the {FIELD_LABELS.get(key, key).lower()}" for key in keys))
    return "edited", " and ".join(said[:2])


def _figure_said(old: Any, new: Any) -> tuple[str, str] | None:
    """A figure written in a slide, changed, as its activity says it: its first change and
    the figure by its name ("added “Log it” to", "the flow chart"); None if it is not one."""

    from flexo.studio.figure_kind import figure_changes

    figures = [block.get("figure") if isinstance(block, dict) else None for block in (old, new)]
    if not all(isinstance(figure, dict) for figure in figures):
        return None
    said = figure_changes(*figures)
    if not said:
        return None
    what = f"the {_object_name(new).lower()}"
    note = said[0]
    if note.startswith("added "):
        return f"{note} to", what
    if note.startswith("deleted "):
        return f"{note} from", what
    if note == "rearranged the figure":
        return "rearranged", what
    if note == "changed the figure's settings":
        return "changed the settings of", what
    return f"{note} in", what


class Unreadable(ValueError):
    """A deck to show a theme on that does not read: said as it is (``plain``), whole."""

    plain = True


class SlideSamples:
    """Slides for the theme editor: a few of every kind, or a deck's own."""

    title = "Slides"

    def pages(self, theme: str, base: Path, hints: dict[str, Any]) -> list[tuple[str, str, Any]]:
        from flexo_talk.compose import render_slide

        deck_file = hints.get("deck")
        if deck_file:
            path = (base / deck_file).resolve()
            try:
                document = load_document(path)
            except Exception:
                # Why, and on which line, its own page says (as it does): here, only that.
                said = f"“{Path(deck_file).stem}” can\u2019t be read. Open it to see why and put it right."
                raise Unreadable(said) from None
            folder = path.parent
        else:
            document, folder = SAMPLE_DECK, base
        document = {**document, "deck": {**(document.get("deck") or {}), "theme": theme}}
        document["deck"].pop("palette", None)
        errors: list[DeckDocumentError] = []
        deck = deck_from_document(document, folder, errors=errors)
        return [
            (f"slide{slide.index}", _label(data) or f"Slide {slide.index}",
             (lambda slide=slide: render_slide(deck, slide).svg))
            for slide, data in list(zip(deck.slides, document.get("slides") or [], strict=True))[:8]
        ]


SAMPLE_DECK: dict[str, Any] = {
    "deck": {"id": "sample", "footer": "A sample · 2026"},
    "slides": [
        {"layout": "title", "title": "Making the service fast", "subtitle": "What we changed, and what it bought us",
         "author": "Ada Lovelace", "date": "2026"},
        {"layout": "two-columns", "title": "From request to reply",
         "left": [{"bullets": ["A cache answers most reads", "A queue takes the slow writes",
                               ["drained by four workers"]]}],
         "right": [{"figure": {"figure": {"id": "sample-path"}, "nodes": [
             {"id": "r", "kind": "text", "label": "Request $r$"},
             {"id": "api", "label": "API", "properties": {"tone": "1"}},
             {"id": "cache", "kind": "database", "label": "Cache", "properties": {"tone": "2"}},
             {"id": "reply", "kind": "text", "label": "Reply"}],
             "edges": [{"from": "r", "to": "api"}, {"from": "api", "to": "cache"},
                       {"from": "cache", "to": "reply"}]}}]},
        {"title": "The gap", "body": [
            {"stats": [{"value": "120 ms", "label": "before"}, {"value": "18 ms", "label": "after"}]},
            {"callout": "A request that *waits on nothing* is one nobody notices.", "title": "The idea"}]},
        {"title": "Results", "body": [{"table": [["Service", "p50 (ms)", "p99 (ms)"], ["Before", "120", "940"],
                                                 ["After", "18", "**210**"]]}]},
        {"layout": "section", "title": "What next", "subtitle": "Three open questions"},
    ],
}


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
                        if path.suffix == ".py":
                            # Python beside it may be what it imports: a change there counts.
                            found.update(sorted(path.parent.glob("*.py"))[:50])
                    elif not path.exists():
                        found.add(path)  # missing: watched, so the slide is drawn again once it is there
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
    """A slide's name, as its title reads on it: its words, not their marks (``*E. coli*``)."""

    from flexo_talk.deck import inline

    if not isinstance(data, dict):
        return ""
    value = str((data.get("words") if data.get("layout") == "statement" else data.get("title")) or "")
    try:
        return "".join(run.text for run in inline(value)).strip()
    except Exception:
        return value


def _extra(data: object, *, error: bool = False) -> dict[str, Any]:
    layout = data.get("layout", "content") if isinstance(data, dict) else "content"
    return {"layout": layout, "error": error}


def _sized(message: Message) -> Message:
    """A figure drawn small, its message coded for the studio to offer what makes it larger:
    turning it to fit (``figure.small.turn``), else a slide of its own (``figure.small.own``),
    else nothing it can do (``figure.small``)."""

    from flexo_talk.compose import OWN_SLIDE, TURNED_LARGER

    if "small for a talk" in message.text or "too small to read" in message.text:
        message.code = (
            "figure.small.turn" if TURNED_LARGER in message.text
            else "figure.small.own" if OWN_SLIDE in message.text
            else "figure.small"
        )
    return message


def _diagnostic(text: str, identifier: str, index: int, severity: str) -> Message:
    # A diagnostic names its slide first (``slide3 figure: ...``); the rest is the message.
    rest = text[len(identifier):].lstrip(" :") if text.startswith(identifier) else text
    region = re.match(r"(\S+):\s*(.*)", rest, re.S)
    where = f"slides[{index}]"
    # An object of the slide's (``left.0``, ``column2.1``: one that can't be drawn) is said
    # where the document has it, to be chosen by.
    own = re.fullmatch(r"(body|left|right|column(\d+))\.(\d+)", region.group(1)) if region else None
    if own:
        name = f"columns[{int(own[2]) - 1}]" if own[2] else own[1]
        return Message(region.group(2), severity, f"{where}.{name}[{own[3]}]", identifier)
    if region and not region.group(1).startswith(("its", "the")):
        return Message(region.group(2), severity, f"{where} {region.group(1)}", identifier)
    return Message(rest, severity, where, identifier)


def _placed(messages: list[Message], document: Any) -> list[Message]:
    for message in messages:
        message.place = _place(message.where, document)
    return messages


def _place(where: str, document: Any) -> str:
    """A message's ``where`` as a person says it: ``slides[3].body[1] (image)`` is
    “Slide 4 · Picture”, ``deck.style.title_size`` “Design · Title Size”."""

    found = re.match(r"slides\[(\d+)\](.*)", where or "")
    if not found:
        if not (where or "").startswith("deck"):
            return ""
        key = where.split(".")[-1]
        named = STYLE_LABELS.get(key) or FIELD_LABELS.get(key)
        return f"Design · {named}" if named and key != "deck" else "Design"
    index, rest = int(found.group(1)), found.group(2)
    kind = re.search(r"\((\w+)\)", rest)
    block = re.match(r"\s*\.?(?:(body|left|right)|columns\[(\d+)\]|column(\d+))[\[.](\d+)", rest)
    field = re.match(r"\.(\w+)", rest)
    named = None
    if kind:
        named = BLOCK_LABELS.get(kind.group(1))
    elif block:
        try:
            slide = document["slides"][index]
            column = int(block.group(2)) if block.group(2) else int(block.group(3) or 1) - 1  # drawn ids count from 1
            region = slide[block.group(1)] if block.group(1) else slide["columns"][column]
            # (One of no kind there is, an object all the same.)
            named = next((BLOCK_LABELS[key] for key in region[int(block.group(4))] if key in BLOCK_LABELS), "Object")
        except (KeyError, IndexError, TypeError, ValueError):
            named = None
    elif field:
        named = FIELD_LABELS.get(field.group(1))
    elif re.match(r"\s+[^\s.#]+#\S", rest):
        named = BLOCK_LABELS.get("figure")  # a part of a figure, named by its id ("f#p:length")
    return f"Slide {index + 1} · {named}" if named else f"Slide {index + 1}"


def _skipped(data: object) -> bool:
    """Whether a slide as the document writes it is skipped (Keynote's Skip Slide)."""

    return isinstance(data, dict) and data.get("skip") is True


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


def _tones(deck) -> dict[str, Any]:
    """The deck's tone colours, for the colour chips of a figure on a slide."""

    colours = []
    for index in range(1, 9):
        try:
            colours.append({"fill": deck.palette.get(f"tone-{index}-fill"),
                            "stroke": deck.palette.get(f"tone-{index}-stroke")})
        except (KeyError, ValueError):
            break
    # The theme's grey, as a shape toned ``neutral`` is painted.
    try:
        neutral = {"fill": deck.palette.get("block-fill"), "stroke": deck.palette.get("block-stroke")}
    except (KeyError, ValueError):
        neutral = None
    return {"colours": colours, "used": {}, **({"neutral": neutral} if neutral else {})}


def _palette_order(deck, *, own: bool = False) -> list[str]:
    """The colours the deck's tones come from, in the order they take them: what Customise…
    writes into a theme of its own, so the copy looks as the deck did. ``own``: its theme's
    own colours, a palette of the deck's aside (the Palette pop-up's first choice)."""

    from flexo.themes import palette_order

    try:
        return palette_order(deck.theme, None if own else deck.palette_name)
    except Exception:
        return []


def _fonts(deck) -> dict[str, str]:
    """The families the deck's words are set in, and the theme's own (for the Design tab's
    font choices to show as they are)."""

    body = deck.typography(20).family
    try:
        from flexo.themes import resolve_style

        theme = resolve_style(deck.theme, None, None, None).typography.family
    except Exception:
        theme = body
    return {"body": body, "title": deck.typography(20, title=True).family,
            "figure": deck.figure_font or body, "theme": theme}


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


def _drawn_plainly(message: str) -> str:
    """An export's note for a figure drawn with a shape it can't draw as a plain box: which,
    and why, from what is said of each (“Spike” can't be drawn yet: ...)."""

    found = re.findall(r"(\u201c[^\u201d]*\u201d|A shape) can\u2019t be drawn yet: (.*?)"
                       r"(?: Choose it to set this in its panel\.|$)", message)
    said = [f"{name} is drawn as a plain box: {why}" for name, why in dict.fromkeys(found)]
    return " ".join(said) or "A shape is drawn as a plain box: it can\u2019t be drawn as it is."


def _plain_message(error: DeckDocumentError) -> str:
    """A deck document's error in words: its own message, rid of any of Python's."""

    return explain(ValueError(error.message))


PRESENTED = "presented-"
"""What the ids of a slide's drawing as presented start with, beside its drawing for editing."""


def _presentable(svg: str, deck: Any, slide: Any) -> str:
    """A slide's drawing for editing, with the slide as it is presented (and exported) inside
    it, hidden, where empty words hold their place while edited (an empty Text above a figure):
    Present shows that instead (present.js), so what is there sits where the PDF has it, the
    placeholders taking no room. The slide is drawn again for it only then."""

    import xml.etree.ElementTree as ET

    from flexo.svg import xml_document

    from flexo_talk.compose import PLACEHOLDERS, render_slide

    held = re.findall(r'id="([^"]+)"[^>]*data-flexo-placeholder="([^"]+)"', svg)
    block = re.compile(rf"{re.escape(slide.id)}\.[^.]+\.\d+")
    # (An object that can't be drawn, or whose file is not there, says so on the stage, and
    # is a quiet box presented.)
    invalid = 'data-flexo-talk="invalid"' in svg or 'data-flexo-talk="missing"' in svg
    if not invalid and not any(words != "Placeholder" and block.fullmatch(ident) for ident, words in held):
        return svg
    token = PLACEHOLDERS.set(False)
    try:
        shown = render_slide(deck, slide).svg
    finally:
        PLACEHOLDERS.reset(token)
    root, other = ET.fromstring(svg), ET.fromstring(shown)
    content = f"{slide.id}.content"
    parents = {child: parent for parent in root.iter() for child in parent}
    editing = next((item for item in root.iter() if item.get("id") == content), None)
    presented = next((item for item in other.iter() if item.get("id") == content), None)
    if editing is None or presented is None:
        return svg
    # Its own ids, so the editor never finds it for the drawing it edits, and what in it
    # points at them (a marker, a clip) pointed at them still.
    named = {item.get("id") for item in presented.iter() if item.get("id")}
    pointer = re.compile(r"(url\(#|^#)([^)]+)")

    def renamed(value: str) -> str:
        return pointer.sub(lambda found: found.group(1) + (PRESENTED + found.group(2) if found.group(2) in named
                                                          else found.group(2)), value)

    for item in presented.iter():
        for key, value in list(item.attrib.items()):
            if key == "id":
                item.set(key, PRESENTED + value)
            elif "#" in value:
                item.set(key, renamed(value))
    presented.set("display", "none")
    presented.set("data-flexo-presented", "")
    editing.set("data-flexo-editing", "")
    parent = parents[editing]
    parent.insert(list(parent).index(editing) + 1, presented)
    return xml_document(root)
