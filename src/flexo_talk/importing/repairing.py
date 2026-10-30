"""A written deck made one that reads: whatever of it the deck cannot make -- written wrong by
an import, or of a kind its slide does not take -- put back as its place, and said."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from flexo_talk.importing.report import Report

MOST_REPAIRS = 200
"""How many of a written deck's objects may be put right before it is given up as written."""


def repaired(document: dict[str, Any], base: Path, report: Report) -> dict[str, Any]:
    """A written deck that reads as a deck: an object or shape it cannot make (written wrong
    by an import, or of a kind its slide does not take) put back as its place, and said."""

    from flexo_talk.document import DeckDocumentError, deck_from_document

    for _ in range(MOST_REPAIRS):
        errors: list[DeckDocumentError] = []
        try:
            deck_from_document(document, base, errors=errors)
        except DeckDocumentError as error:
            errors = [error]
        except Exception as error:  # the deck as a whole: its settings
            report.note(f"The deck's settings were put back to Flexo's own ({error}).")
            document["deck"] = {"id": document.get("deck", {}).get("id", "deck"), "theme": "paper"}
            continue
        fixable = [error for error in errors if _repair(document, error.where, error.message, report)]
        if not fixable:
            break
    return document


_WHERE = re.compile(r"slides\[(\d+)\](?:\.(body|shapes)\[(\d+)\])?")


def _repair(document: dict[str, Any], where: str, message: str, report: Report) -> bool:
    found = _WHERE.match(where or "")
    if not found:
        return False
    slides = document.get("slides") or []
    index = int(found[1])
    if index >= len(slides):
        return False
    slide = slides[index]
    region, at = found[2], found[3]
    if region is None:
        notes = slide.get("notes")
        emptied = {"layout": "blank", **({"notes": notes} if notes else {})}
        if slide == emptied:
            return False
        report.placeholder(index + 1, "Slide", f"could not be made as written ({message})")
        slides[index] = emptied
        return True
    items = slide.get(region) or []
    at = int(at)
    if at >= len(items):
        return False
    item = items[at]
    if isinstance(item, dict) and item.get("hide") and str(item.get("text", "")).startswith("TODO"):
        return False
    box = _box_of(item)
    report.placeholder(index + 1, "Object" if region == "body" else "Shape", f"could not be made ({message})")
    stand_in = {"kind": "rectangle", "at": box[:2], "size": box[2:], "fill": "none", "line": "muted",
                "line_width": 1, "dash": "dashed", "text": f"TODO An object from the original: {_plain(message)}",
                "font_size": 12, "colour": "muted", "hide": True}
    if region == "body":
        del items[at]
        if not items:
            slide.pop("body", None)
        slide.setdefault("shapes", []).append(stand_in)
        for line in slide.get("shapes") or []:
            _unglue(line, at)
    else:
        items[at] = stand_in
    return True


def _plain(words: str) -> str:
    return re.sub(r"[*`$\[\]]", "", words)[:120]


def _box_of(item: object) -> list[float]:
    if isinstance(item, dict):
        at = item.get("at")
        if isinstance(at, list) and len(at) == 2 and all(isinstance(value, int | float) for value in at):
            size = item.get("size")
            width = item.get("width") if isinstance(item.get("width"), int | float) else 200
            if isinstance(size, list) and len(size) == 2:
                return [float(at[0]), float(at[1]), float(size[0]), float(size[1])]
            return [float(at[0]), float(at[1]), float(width), 60.0]
    return [40.0, 40.0, 200.0, 60.0]


def _unglue(line: dict[str, Any], removed: int) -> None:
    """A line glued to an object taken out of the body: glued no longer (where it was kept),
    and one glued to an object after it pointed at it where it now is."""

    for key in ("from", "to"):
        end = line.get(key)
        if not isinstance(end, dict) or "object" not in end:
            continue
        found = re.fullmatch(r"body\[(\d+)\]", str(end["object"]))
        if not found:
            continue
        number = int(found[1])
        if number == removed:
            line[key] = end.get("at") or [0, 0]
        elif number > removed:
            end["object"] = f"body[{number - 1}]"
