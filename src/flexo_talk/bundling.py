"""What a deck document names, for a bundle of it (``flexo.bundle``): every file it reads,
found as ``flexo_talk.document`` finds it, from the deck's folder.

The deck's theme and palette files, the picture behind every slide and each slide's own,
its logos; each slide's pictures, galleries, figures (a figure file, whose own files are
followed in turn; one written in the deck, whose parts' pictures, structures, maps and plots
are found from the deck's folder; or ``file.py:function``), plots (``file.py:function``) and
the pictures among its shapes (a drawing pasted in, its parts kept as drawn).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flexo.bundle import Reference, figure_references, shape_references

from flexo_talk.deck import named_colour

_THEMED = (".yaml", ".yml", ".json")


def references(data: Any, base: Path) -> list[Reference]:
    """The files a deck document (as it reads) names, each from ``base``, its folder."""

    found: list[Reference] = []
    if not isinstance(data, Mapping):
        return found
    deck = data.get("deck")
    if isinstance(deck, Mapping):
        for key, role in (("theme", "document"), ("palette", "file")):
            value = deck.get(key)
            if isinstance(value, str) and value.strip().lower().endswith(_THEMED):
                found.append(Reference(value, f"deck.{key}", base, role))
        background = deck.get("background")
        if isinstance(background, str) and background and not background.startswith("#"):
            found.append(Reference(background, "deck.background", base))
        logos = deck.get("logos")
        for index, name in enumerate([logos] if isinstance(logos, str) else logos or []):
            if isinstance(name, str) and name:
                found.append(Reference(name, f"deck.logos[{index}]", base))
    slides = data.get("slides")
    for index, slide in enumerate(slides if isinstance(slides, list) else []):
        if isinstance(slide, Mapping):
            found += _slide(slide, base, f"slides[{index}]")
    return found


def _slide(slide: Mapping[str, Any], base: Path, where: str) -> list[Reference]:
    found: list[Reference] = []
    background = slide.get("background")
    if isinstance(background, str) and background and not background.startswith("#") \
            and not named_colour(background):
        found.append(Reference(background, f"{where}.background", base))
    found += shape_references(slide.get("shapes"), base, f"{where}.shapes")
    for key in ("body", "left", "right"):
        blocks = slide.get(key)
        for index, block in enumerate(blocks if isinstance(blocks, list) else []):
            found += _block(block, base, f"{where}.{key}[{index}]")
    columns = slide.get("columns")
    for column, blocks in enumerate(columns if isinstance(columns, list) else []):
        for index, block in enumerate(blocks if isinstance(blocks, list) else []):
            found += _block(block, base, f"{where}.columns[{column}][{index}]")
    return found


def _block(block: object, base: Path, where: str) -> list[Reference]:
    if not isinstance(block, Mapping):
        return []
    found: list[Reference] = []
    image = block.get("image")
    if isinstance(image, str) and image:
        found.append(Reference(image, f"{where} (image)", base))
    gallery = block.get("gallery")
    for index, item in enumerate(gallery if isinstance(gallery, list) else []):
        picture = item.get("picture") if isinstance(item, Mapping) else item
        if isinstance(picture, str) and picture:
            found.append(Reference(picture, f"{where} (gallery)[{index}]", base))
    figure = block.get("figure")
    if isinstance(figure, Mapping):
        # Written in the deck: its parts' files are found from the deck's folder.
        found += figure_references(figure, base, f"{where} (figure)")
    elif isinstance(figure, str) and figure:
        found.append(_named(figure, f"{where} (figure)", base, "document"))
    plot = block.get("plot")
    if isinstance(plot, str) and ".py:" in plot:
        found.append(_named(plot, f"{where} (plot)", base, "document"))
    return found


def _named(value: str, where: str, base: Path, role: str) -> Reference:
    """A figure or plot block's file: a document of its own, or ``file.py:function``."""

    if ".py:" in value:
        file, _, function = value.rpartition(":")
        return Reference(file, where, base, "python", function)
    return Reference(value, where, base, role)
