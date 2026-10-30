"""A group of very many shapes (a figure a slide program drew in thousands of outlines) as one
SVG picture of itself, drawn by Flexo as the shapes would be on the slide: a slide of it stays
quick to edit, and a double-click on it in the studio makes it shapes again, as any drawing
placed as a picture is (``flexo.svgimport``)."""

from __future__ import annotations

import contextlib
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from flexo_talk.importing.model import Group

if TYPE_CHECKING:
    from flexo_talk.importing.writing import Writer

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def drawn(group: Group, writer: Writer) -> str | None:
    """``group`` drawn alone, as an SVG as large as its box (in points); ``None`` where it
    draws nothing."""

    from flexo_talk.compose import render_slide
    from flexo_talk.document import deck_from_document

    known: list = []
    counted = writer.report.made.copy()
    shapes = [spec for spec in (writer.member(child, known) for child in group.children) if spec is not None]
    writer.report.made = counted  # (what it holds is a picture now, not shapes)
    if not shapes:
        return None
    for spec in _every(shapes):
        spec.pop("_members", None)
        spec.pop("_glue", None)
    # (Nothing of the deck's own on it: no number, no footer.)
    settings = {key: value for key, value in writer.settings.items() if key not in ("footer", "logos")}
    settings["style"] = {**settings.get("style", {}), "numbers": False}
    document = {"schema_version": 1, "deck": settings, "slides": [{"layout": "blank", "shapes": shapes}]}
    deck = deck_from_document(document, writer.folder)
    svg = render_slide(deck, deck.slides[0]).svg
    root = ET.fromstring(svg)
    for node in list(root.iter()):
        for item in list(node):
            if item.get("id") == "canvas.background" or (item.get("id") or "").endswith(".placeholders"):
                node.remove(item)
    for node in root.iter():
        for name in [name for name in node.attrib if name.startswith("data-flexo") or name == "id"]:
            del node.attrib[name]
    _plain(root)
    scale = writer.k
    box = group.box
    x, y, w, h = box.x * scale, box.y * scale, max(box.w * scale, 1.0), max(box.h * scale, 1.0)
    root.set("viewBox", f"{_n(x)} {_n(y)} {_n(w)} {_n(h)}")
    root.set("width", f"{_n(w)}pt")
    root.set("height", f"{_n(h)}pt")
    text = ET.tostring(root, encoding="unicode")
    return text if re.search(r"<(path|text|image|rect|ellipse|circle|line|polyline|polygon)\b", text) else None


def _plain(root: ET.Element) -> None:
    """The drawing as the drawing reader takes it as shapes and words (``flexo.drawing``):
    without the faces' stylesheet (the deck's own faces draw it), each line of words a text
    of its own rather than a line moved down from the one before (``dy``)."""

    for parent in list(root.iter()):
        for item in list(parent):
            if item.tag == f"{{{SVG}}}style":
                parent.remove(item)
    for parent in list(root.iter()):
        for index, text in reversed(list(enumerate(list(parent)))):
            if text.tag != f"{{{SVG}}}text" or not any(span.get("dy") for span in text):
                continue
            lines: list[ET.Element] = []
            y = float(text.get("y") or 0)
            for span in list(text):
                if span.get("x") is not None or not lines:
                    if lines and span.get("dy"):
                        with contextlib.suppress(ValueError):
                            y += float(span.get("dy") or 0)
                    line = ET.Element(text.tag, {key: value for key, value in text.attrib.items()})
                    line.set("y", _n(y))
                    if span.get("x") is not None:
                        line.set("x", span.get("x") or "0")
                    if not lines and text.text:
                        line.text = text.text
                    lines.append(line)
                copied = ET.SubElement(lines[-1], span.tag, {key: value for key, value in span.attrib.items()
                                                             if key not in ("x", "y", "dy")})
                copied.text, copied.tail = span.text, span.tail
                for inner in span:
                    copied.append(inner)
            parent.remove(text)
            for offset, line in enumerate(lines):
                parent.insert(index + offset, line)


def _every(specs: list) -> list:
    out = []
    for spec in specs:
        out.append(spec)
        if spec.get("kind") == "group":
            out.extend(_every(spec.get("shapes") or []))
    return out


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"
