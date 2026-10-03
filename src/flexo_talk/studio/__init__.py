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
    MissingFile,
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
    "dark": "Background", "align": "Content Position",
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

    def save(self, path: Path, document: dict[str, Any]) -> None:
        save_document(document, path)

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

        import difflib

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
        keys = [_stable(slide) for slide in old], [_stable(slide) for slide in new]
        for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, *keys, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            if tag == "insert":
                for index in range(b1, b2):
                    notes.append(_slide_note("added", new, index))
            elif tag == "delete":
                at = min(a1 + 1, max(len(new), 1))
                # Clicked, it goes where the slide was; it names no place, being gone.
                notes.append({"text": f"deleted slide {a1 + 1}" if a2 - a1 == 1 else f"deleted {a2 - a1} slides",
                              "where": {"page": at}})
            else:
                # Slides replaced by others: pair each new one with the old one it most resembles,
                # or, as many in as out, with the one in its place if it is of a kind with it (its
                # title or its layout): a list pasted into is that slide edited, not another.
                unused = list(range(a1, a2))
                for index in range(b1, b2):
                    text = json.dumps(new[index], sort_keys=True, default=str)
                    scored = [(_likeness(old[i], text), i) for i in unused]
                    best = max(scored, default=(0.0, -1))
                    placed = a1 + index - b1
                    if best[0] <= 0.5 and a2 - a1 == b2 - b1 and placed in unused and _kin(old[placed], new[index]):
                        best = (1.0, placed)
                    if best[0] > 0.5:
                        unused.remove(best[1])
                        verb, what = _what_changed(old[best[1]], new[index])
                        notes.append(_slide_note(verb, new, index, what))
                    else:
                        notes.append(_slide_note("added", new, index))
                if unused:
                    at = min(b1 + 1, max(len(new), 1))
                    count = len(unused)
                    notes.append({"text": f"deleted slide {unused[0] + 1}" if count == 1 else f"deleted {count} slides",
                                  "where": {"page": at}})
        return notes

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

        from flexo_talk.compose import EDITING, PLACEHOLDERS, render_slide

        errors: list[DeckDocumentError] = []
        try:
            deck = deck_from_document(document, base, errors=errors)
        except DeckDocumentError as error:
            return Drawing([], _placed([Message(_plain_message(error), "error", error.where)], document))
        except Exception as error:
            return Drawing([], _placed([Message(explain(error), "error", "deck")], document))
        slides = document.get("slides") or []
        # A picture or figure whose file is missing is said, and a box stands in for it:
        # the rest of its slide is drawn.
        absent = [error for error in errors if isinstance(error, MissingFile)]
        failed = {_slide_of(error.where): error for error in errors if not isinstance(error, MissingFile)}
        deck_data = document.get("deck") or {}
        from flexo.studio import code_allowed

        head = _stable({
            "deck": deck_data, "base": str(base), "count": len(slides), "trusted": code_allowed.get(),
            # A theme file edited in the studio changes every slide without changing the deck.
            "themes": [(str(path), _stamp(path)) for path in _theme_files(deck_data, base)],
        })
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
            editing, placeholders = EDITING.set(not settle), PLACEHOLDERS.set(True)
            try:
                rendered = render_slide(deck, slide)
                self._slides[keys[index]] = {"svg": rendered.svg, "steps": rendered.steps,
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
                    messages.append(Message(_plain_message(error), "error", error.where, identifier, "deck.missing"))
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
                    messages.append(_diagnostic(text, identifier, index, "warning"))
                for text in done["notes"]:
                    messages.append(_diagnostic(text, identifier, index, "note"))
                for text in done.get("held", []):
                    messages.append(Message(text, "warning", f"slides[{index}]", identifier, "code.untrusted"))
                pages.append(Page(identifier, done["svg"], _label(data), done["steps"], _extra(data)))
        unsettled = any(not self._slides.get(key, {}).get("settled", True) for key in keys)
        return Drawing(pages, _placed(messages, document), sorted(watched),
                       {"palette": _palette(deck), "tones": _tones(deck), "order": _palette_order(deck),
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

            return {"document": document, "id": fetched(str(action.get("id") or ""))}
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

        from flexo_talk.export import build_deck, file_stem

        try:
            deck = deck_from_document(document, base)
        except DeckDocumentError as error:
            # Said where it is as a person says it (“Slide 4 · Picture”), not as the document does.
            place = _place(error.where, document)
            raise ValueError(f"{place}: {error.message}" if place else error.message) from error
        folder = into or base / "build"
        images = folder / file_stem(deck.id) if into is not None else None
        result = build_deck(deck, folder, tuple(formats), handout=not steps, images=images)
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
    from flexo_talk.document import _figure, make_deck

    block = _block_at(document, at)
    if not isinstance(block, dict) or "figure" not in block:
        raise EditError("This object is no longer a figure. Someone else may have changed it.")
    deck = make_deck(document.get("deck") or {}, base)
    figure = made(_figure(base, block["figure"], "figure", None))
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


def _slide_note(verb: str, slides: list, index: int, what: str = "") -> dict[str, Any]:
    slide = slides[index] if index < len(slides) and isinstance(slides[index], dict) else {}
    title = str(slide.get("words") or slide.get("title") or "").strip()
    named = f", “{title[:40]}”" if title and verb == "added" else ""
    # "edited the title on slide 4", "added a table to slide 2", "added slide 5, “Methods”":
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


_OBJECTS = {"bullets": "list", "text": "text", "figure": "figure", "image": "picture", "table": "table",
            "math": "equation", "code": "code", "quote": "quote", "callout": "callout", "stats": "numbers",
            "gallery": "gallery", "plot": "plot", "mechanism": "mechanism"}
"""Each object a slide holds, by name."""


def _objects(old: Any, new: Any) -> tuple[str, str]:
    """What changed among a slide's objects, as said aloud: ("edited", "the list"), ("added",
    "a table"), ("edited", "the list and the figure")."""

    def name(block: Any) -> str:
        kind = next((key for key in block if key in _OBJECTS), "") if isinstance(block, dict) else ""
        return _OBJECTS.get(kind, "object")

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
    changed = list(dict.fromkeys(f"the {name(b)}" for a, b in zip(was, now, strict=True) if a != b))
    return "edited", " and ".join(changed[:2]) or "its content"


def _a(noun: str) -> str:
    return f"{'an' if noun[:1] in 'aeiou' else 'a'} {noun}"


def _what_changed(old: Any, new: Any) -> tuple[str, str]:
    """What a change did to a slide: its verb and what it did it to."""

    if not isinstance(old, dict) or not isinstance(new, dict):
        return "edited", ""
    keys = [key for key in dict.fromkeys([*old, *new]) if old.get(key) != new.get(key)]
    # An object added or deleted is what the change did.
    if "body" in keys and (done := _objects(old.get("body"), new.get("body")))[0] != "edited":
        return done
    names = {"title": "the title", "words": "the words", "subtitle": "the subtitle", "notes": "the notes",
             "layout": "the layout", "left": "the left column", "right": "the right column",
             "columns": "its columns", "background": "the background", "footnotes": "the footnotes",
             "author": "the author", "date": "the date", "shade": "the background", "dark": "the background"}
    said = list(dict.fromkeys(_objects(old.get(key), new.get(key))[1] if key == "body" else names.get(key, f"the {key}")
                              for key in keys))
    return "edited", " and ".join(said[:2])


class SlideSamples:
    """Slides for the theme editor: a few of every kind, or a deck's own."""

    title = "Slides"

    def pages(self, theme: str, base: Path, hints: dict[str, Any]) -> list[tuple[str, str, Any]]:
        from flexo_talk.compose import render_slide

        deck_file = hints.get("deck")
        if deck_file:
            path = (base / deck_file).resolve()
            document = load_document(path)
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
            named = next((BLOCK_LABELS[key] for key in region[int(block.group(4))] if key in BLOCK_LABELS), None)
        except (KeyError, IndexError, TypeError, ValueError):
            named = None
    elif field:
        named = FIELD_LABELS.get(field.group(1))
    return f"Slide {index + 1} · {named}" if named else f"Slide {index + 1}"


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
    return {"colours": colours, "used": {}}


def _palette_order(deck) -> list[str]:
    """The colours the deck's tones come from, in the order they take them: what Customise…
    writes into a theme of its own, so the copy looks as the deck did."""

    from flexo.themes import palette_order

    try:
        return palette_order(deck.theme, deck.palette_name)
    except Exception:
        return []


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


def _plain_message(error: DeckDocumentError) -> str:
    """A deck document's error in words: its own message, rid of any of Python's."""

    return explain(ValueError(error.message))
