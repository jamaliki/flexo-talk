"""A deck's slide drawn in a design before it is chosen, for the studio's Design bar: its
theme gallery (the deck's title slide, or its first, in each theme) and its live preview (the
slide shown, in the theme, palette, fonts, look or background the pointer is over).

The page asks with ``{"do": "previews", "slide": 0, "variants": [{"theme": "dark"}, ...],
"placeholders": false}``: each variant is a change to the deck's own settings -- a key set
to ``None`` taken away, the deck's default -- and the answer has one drawing for each, in
order, ``{"svg", "key"}``, or ``{"error"}`` where that design can't be drawn. Nothing is
changed: the deck is drawn as it would be, and kept a while by what it was drawn from, so a
gallery shown again, or a theme pointed at twice, is drawn once.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

DESIGN = frozenset({"theme", "palette", "font", "title_font", "figure_font", "look", "background", "style"})
"""What a variant may change: the deck's settings that are its design."""

MOST = 24
"""Variants drawn for one question: a gallery asks for those in sight, a few at a time."""

KEPT = 120
"""Drawings kept, the oldest let go first."""

_kept: OrderedDict[str, dict[str, Any]] = OrderedDict()
_lock = threading.Lock()


def previews(document: dict[str, Any], action: dict[str, Any], base: Path) -> dict[str, Any]:
    """The slide ``action["slide"]`` of ``document`` drawn in each of ``action["variants"]``."""

    slides = document.get("slides") if isinstance(document, dict) else None
    slides = slides if isinstance(slides, list) else []
    index = action.get("slide")
    variants = action.get("variants") or []
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(slides):
        return {"previews": [{"error": "There is no such slide."} for _ in variants[:MOST]]}
    placeholders = bool(action.get("placeholders"))
    deck = document.get("deck") if isinstance(document.get("deck"), dict) else {}
    return {
        "previews": [
            _drawn(document, base, index, designed(deck, variant), placeholders) for variant in variants[:MOST]
        ]
    }


def designed(deck: dict[str, Any], variant: object) -> dict[str, Any]:
    """The deck's settings with a variant's put over them (``None`` takes one away)."""

    made = dict(deck)
    if not isinstance(variant, dict):
        return made
    for key, value in variant.items():
        if key not in DESIGN:
            continue
        if value is None:
            made.pop(key, None)
        else:
            made[key] = value
    return made


def _drawn(
    document: dict[str, Any], base: Path, index: int, deck: dict[str, Any], placeholders: bool
) -> dict[str, Any]:
    from flexo.studio import code_allowed

    from flexo_talk.studio import (
        _files,
        _logo_files,
        _shared_names,
        _skipped,
        _stable,
        _stamp,
        _theme_files,
    )

    slides = document["slides"]
    slide = slides[index]
    shared = document.get("figures") if isinstance(document.get("figures"), dict) else {}
    named = {name: shared.get(name) for name in sorted(_shared_names(slide))}
    files = sorted(_files(slide, base) | _files([{"figure": figure} for figure in named.values()], base))
    layout = slide.get("layout", "content") if isinstance(slide, dict) else "content"
    # (Drawn again where anything it is drawn from has changed: as the deck's own drawings are.)
    key = _stable(
        {
            "deck": deck,
            "base": str(base),
            "slide": slide,
            "index": index,
            "figures": named,
            "placeholders": placeholders,
            "trusted": code_allowed.get(),
            "shown": sum(1 for item in slides[:index] if not _skipped(item)),
            "sections": [
                (item.get("title"), item.get("subtitle"))
                for item in slides
                if isinstance(item, dict) and item.get("layout") == "section" and not _skipped(item)
            ]
            if layout == "agenda"
            else None,
            "files": [
                (str(file), _stamp(file)) for file in [*files, *_theme_files(deck, base), *_logo_files(deck, base)]
            ],
        }
    )
    with _lock:
        found = _kept.get(key)
        if found is not None:
            _kept.move_to_end(key)
            return found
    found = _draw({**document, "deck": deck}, base, index, placeholders)
    found = {**found, "key": key[:16]} if "svg" in found else found
    with _lock:
        _kept[key] = found
        while len(_kept) > KEPT:
            _kept.popitem(last=False)
    return found


def _draw(document: dict[str, Any], base: Path, index: int, placeholders: bool) -> dict[str, Any]:
    from flexo.studio.plain import explain

    from flexo_talk.compose import EDITING, PLACEHOLDERS, STANDING_ASIDE, render_slide
    from flexo_talk.document import DeckDocumentError, deck_from_document

    errors: list[DeckDocumentError] = []
    # (As the slide shown is drawn while it is edited: its figures as they are laid out, its
    # empty words holding their places only where they are asked to.)
    editing, held, aside = EDITING.set(True), PLACEHOLDERS.set(placeholders), STANDING_ASIDE.set(True)
    try:
        deck = deck_from_document(document, base, errors=errors)
        return {"svg": render_slide(deck, deck.slides[index]).svg}
    except DeckDocumentError as error:
        return {"error": explain(ValueError(error.message))}
    except Exception as error:
        return {"error": explain(error)}
    finally:
        EDITING.reset(editing)
        PLACEHOLDERS.reset(held)
        STANDING_ASIDE.reset(aside)
