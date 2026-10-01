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
    UntrustedCode,
    deck_from_document,
    dump_document,
    is_deck_document,
    load_document,
    parse_document,
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
                notes.append({"text": f"removed slide {a1 + 1}" if a2 - a1 == 1 else f"removed {a2 - a1} slides",
                              "where": {"page": at, "label": f"Slide {at}"}})
            else:
                # Slides replaced by others: pair each new one with the old one it most resembles.
                unused = list(range(a1, a2))
                for index in range(b1, b2):
                    text = json.dumps(new[index], sort_keys=True, default=str)
                    scored = [(_likeness(old[i], text), i) for i in unused]
                    best = max(scored, default=(0.0, -1))
                    if best[0] > 0.5:
                        unused.remove(best[1])
                        notes.append(_slide_note("edited", new, index, _what_changed(old[best[1]], new[index])))
                    else:
                        notes.append(_slide_note("added", new, index))
                if unused:
                    at = min(b1 + 1, max(len(new), 1))
                    count = len(unused)
                    notes.append({"text": f"removed slide {unused[0] + 1}" if count == 1 else f"removed {count} slides",
                                  "where": {"page": at, "label": f"Slide {at}"}})
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
            # What the figure editor offers, for figures edited on their slides.
            "figure_editor": _figure_editor(),
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
            return Drawing([], [Message(_plain_message(error), "error", error.where)])
        except Exception as error:
            return Drawing([], [Message(explain(error), "error", "deck")])
        slides = document.get("slides") or []
        failed = {_slide_of(error.where): error for error in errors}
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
                                             "diagnostics": rendered.diagnostics, "notes": rendered.notes,
                                             "held": rendered.held}
            except UntrustedCode as error:
                self._slides[keys[index]] = {"error": error.message, "code": "code.untrusted"}
            except DeckDocumentError as error:
                # Said on its slide, where it is: the message need not name the place again.
                self._slides[keys[index]] = {"error": _plain_message(error), "where": error.where}
            except Exception as error:
                self._slides[keys[index]] = {"error": explain(error)}
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
        return Drawing(pages, messages, sorted(watched), {"palette": _palette(deck), "tones": _tones(deck)})

    def act(self, document: dict[str, Any], action: dict[str, Any], base: Path) -> dict[str, Any]:
        """An edit to a figure on a slide, made where the figure is written: in the deck
        (a figure written inline) or in its own file. ``action`` is ``{"do": "figure",
        "at": {"slide", "region", "index"}, "edit": <a flexo figure edit>}`` -- or
        ``{"do": "mechanism", ...}``, drawing on a mechanism (``_mechanism``)."""

        import copy

        from flexo.studio.figure_edit import EditError, apply, apply_to_data, model

        if action.get("do") == "mechanism":
            return _mechanism(document, action, base)
        if action.get("do") != "figure":
            raise EditError(f'unknown deck edit "{action.get("do")}"')
        at = action.get("at") or {}
        edit = action.get("edit") or {}
        changed = copy.deepcopy(document)
        block = _block_at(changed, at)
        value = block.get("figure") if isinstance(block, dict) else None
        if isinstance(value, dict):
            made = apply_to_data(value, edit, base=base)
            block["figure"] = made["data"]
            return {"document": changed, "select": made["select"], "model": made["model"]}
        if isinstance(value, str) and value and ".py:" not in value:
            path = (base / value).resolve()
            if not path.is_file() or not path.is_relative_to(base.resolve()):
                raise EditError(f"no figure file {value} beside the deck")
            result = apply(path.read_text(encoding="utf-8"), edit, suffix=path.suffix, base=path.parent)
            if edit.get("do") != "read":
                path.write_text(result["text"], encoding="utf-8")
            return {"document": document, "select": result["select"],
                    "model": model(result["text"], suffix=path.suffix), "file": value}
        raise EditError("a figure made in Python is changed in its Python file")

    def export(self, document: dict[str, Any], base: Path, stem: str, formats: list[str]) -> list[Path]:
        deck = deck_from_document(document, base)
        result = deck.build(base / "build", formats=tuple(formats))
        written = [result.pptx, result.pdf, *result.svgs, *result.pngs]
        return [path for path in written if path]

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
        raise EditError("that part is not a mechanism any more: someone changed it meanwhile")
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
        raise EditError("that part of the slide is gone: someone changed it meanwhile") from error


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
    named = f" ({title[:40]})" if title and verb == "added" else ""
    return {"text": f"{verb} slide {index + 1}{named}{f': {what}' if what else ''}",
            "where": {"page": index + 1, "label": f"Slide {index + 1}"}}


def _what_changed(old: Any, new: Any) -> str:
    if not isinstance(old, dict) or not isinstance(new, dict):
        return ""
    keys = [key for key in dict.fromkeys([*old, *new]) if old.get(key) != new.get(key)]
    names = {"title": "the title", "words": "the words", "subtitle": "the subtitle", "notes": "the notes",
             "layout": "the layout", "body": "its content", "left": "the left column", "right": "the right column",
             "columns": "its columns", "background": "the background", "footnotes": "the footnotes"}
    said = list(dict.fromkeys(names.get(key, key) for key in keys))
    return " and ".join(said[:2])


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
        {"layout": "title", "title": "Folding proteins with diffusion", "subtitle": "What the model learns",
         "author": "Ada Lovelace", "date": "2026"},
        {"layout": "two-columns", "title": "From sequence to structure",
         "left": [{"bullets": ["A language model reads the sequence", "A denoiser makes the coordinates",
                               ["trained on solved structures"]]}],
         "right": [{"figure": {"figure": {"id": "sample-model"}, "nodes": [
             {"id": "s", "kind": "text", "label": "Sequence $s$"},
             {"id": "lm", "label": "Language model", "properties": {"tone": "encoder"}},
             {"id": "den", "label": "Denoiser", "properties": {"tone": "head"}},
             {"id": "x", "kind": "text", "label": "Structure $x_0$"}],
             "edges": [{"from": "s", "to": "lm"}, {"from": "lm", "to": "den"}, {"from": "den", "to": "x"}]}}]},
        {"title": "The gap", "body": [
            {"stats": [{"value": "200M", "label": "predicted"}, {"value": "0.1%", "label": "solved"}]},
            {"callout": "A model that knows *how sure it is* tells us what to solve first.", "title": "The idea"}]},
        {"title": "Results", "body": [{"table": [["Model", "Params", "Top-1 (%)"], ["Baseline", "25.6M", "76.1"],
                                                 ["Ours", "24.0M", "**81.2**"]]}]},
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
