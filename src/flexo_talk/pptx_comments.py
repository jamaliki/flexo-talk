"""A deck's open comments, carried into its PowerPoint as PowerPoint's own comments.

The threads people left on a deck (``flexo_talk.studio.comments``) are never drawn on a slide.
A PowerPoint is what gets sent round for review, so an exported one carries each open thread
as a comment of the slide it is on -- by its author, at its time, its replies as replies (as
PowerPoint 2013 and later thread them) -- placed at the top right of the object it is about
(the slide's own, at the slide's top right). One on a part of a figure names the part. A
thread resolved is done with, and left out, as PowerPoint's comments have no word for it.

They are PowerPoint's comments as the Open XML standard writes them -- ``ppt/commentAuthors.xml``
and a ``ppt/comments/commentN.xml`` for each slide with any -- added to the package once it is
written (``write_pptx``), so the slides' own writing is untouched by them. PowerPoint for the
Mac opens such a file with no word of repair, its comments pane showing each thread, replies
under it, and a mark on the slide where each is.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from lxml import etree

_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_P15 = "http://schemas.microsoft.com/office/powerpoint/2012/main"
_AUTHORS_REL = f"{_R}/commentAuthors"
_COMMENTS_REL = f"{_R}/comments"
_AUTHORS_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.commentAuthors+xml"
_COMMENTS_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.comments+xml"
_THREADED = "{C676402C-5697-4E1C-873F-D02D1690AC5C}"
"""The extension by which PowerPoint 2013 and later make a comment a reply to another."""
UNITS = 8
"""A comment's place is written in eighths of a point (576 to the inch)."""
_TAG = re.compile(r"<(?:g|text)\b([^>]*)>")
_ATTRIBUTE = re.compile(r'([\w:-]+)="([^"]*)"')


def comments_of(slides: list[Any]) -> list[list[dict[str, Any]]]:
    """The open threads of each slide (``Slide``, as read from its document), each ``{"thread",
    "region", "index", "block"}`` -- region None for the slide's own; else its region's name
    as the slide's drawing names it (``body``, ``left``, ``column2``) and the object's place."""

    found: list[list[dict[str, Any]]] = []
    for slide in slides:
        here: list[dict[str, Any]] = []

        def take(held: Any, region: str | None, at: int | None, block: Any = None, here: list = here) -> None:
            for thread in held if isinstance(held, list) else []:
                written = isinstance(thread, dict) and isinstance(thread.get("text"), str)
                if written and thread.get("resolved") is not True:
                    here.append({"thread": thread, "region": region, "index": at, "block": block})

        take((getattr(slide, "source", None) or {}).get("comments"), None, None)
        for name, region in (getattr(slide, "regions", None) or {}).items():
            for at, source in enumerate(getattr(region, "sources", None) or []):
                if isinstance(source, dict):
                    take(source.get("comments"), name, at, source)
        found.append(here)
    return found


def add_comments(target: Path, slides: list[Any], rendered: list[Any], width: float = 960.0) -> int:
    """Add the open threads of the ``slides`` written to the PowerPoint at ``target`` (each drawn
    as ``rendered`` has it) as its comments; how many comments (replies too) it got."""

    threads = comments_of(slides)
    if not any(threads):
        return 0
    authors: dict[str, dict[str, Any]] = {}

    def author(name: Any) -> dict[str, Any]:
        named = " ".join(str(name or "Someone").split()) or "Someone"
        if named not in authors:
            authors[named] = {"id": len(authors), "name": named, "last": 0}
        return authors[named]

    with zipfile.ZipFile(target) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    slides = _slide_parts(parts)
    written: dict[str, bytes] = {}
    count = 0
    for number, (here, path) in enumerate(zip(threads, slides, strict=False), start=1):
        if not here:
            continue
        boxes = _boxes(rendered[number - 1].svg if number - 1 < len(rendered) else "")
        items = []
        for spot, one in enumerate(here):
            thread = one["thread"]
            x, y = _place(one, boxes, width)
            # (Two at one place a little apart, as PowerPoint lays its own out.)
            x, y = x - 12 * sum(1 for other in here[:spot] if _place(other, boxes, width) == (x, y)), y
            first = author(thread.get("author"))
            first["last"] += 1
            text = str(thread["text"])
            if thread.get("part"):
                text = f"On {_part_name(one['block'], thread['part'])}: {text}"
            items.append(_comment(first, first["last"], thread.get("time"), x, y, text))
            parent = (first, first["last"])
            count += 1
            for reply in thread.get("replies") if isinstance(thread.get("replies"), list) else []:
                if not isinstance(reply, dict) or not isinstance(reply.get("text"), str):
                    continue
                by = author(reply.get("author"))
                by["last"] += 1
                items.append(_comment(by, by["last"], reply.get("time"), x, y, reply["text"], parent=parent))
                count += 1
        name = f"ppt/comments/comment{number}.xml"
        written[name] = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:cmLst xmlns:p="{_P}" '
            f'xmlns:p15="{_P15}">{"".join(items)}</p:cmLst>'
        ).encode()
        rels = f"ppt/slides/_rels/{path.rsplit('/', 1)[1]}.rels"
        parts[rels] = _related(parts.get(rels), _COMMENTS_REL, f"../comments/comment{number}.xml")
        parts["[Content_Types].xml"] = _typed(parts["[Content_Types].xml"], f"/{name}", _COMMENTS_TYPE)
    listed = "".join(
        f'<p:cmAuthor id="{one["id"]}" name={quoteattr(one["name"])} initials={quoteattr(_initials(one["name"]))} '
        f'lastIdx="{one["last"]}" clrIdx="{one["id"] % 8}"/>'
        for one in authors.values()
    )
    written["ppt/commentAuthors.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<p:cmAuthorLst xmlns:p="{_P}">{listed}</p:cmAuthorLst>'
    ).encode()
    parts["ppt/_rels/presentation.xml.rels"] = _related(parts["ppt/_rels/presentation.xml.rels"], _AUTHORS_REL,
                                                        "commentAuthors.xml")
    parts["[Content_Types].xml"] = _typed(parts["[Content_Types].xml"], "/ppt/commentAuthors.xml", _AUTHORS_TYPE)
    parts.update(written)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        # ([Content_Types].xml first, as Office writes it.)
        for name in sorted(parts, key=lambda name: name != "[Content_Types].xml"):
            package.writestr(name, parts[name])
    target.write_bytes(buffer.getvalue())
    return count


def _comment(author: dict[str, Any], index: int, time: Any, x: float, y: float, text: str,
             parent: tuple[dict[str, Any], int] | None = None) -> str:
    threaded = ""
    if parent is not None:
        threaded = (
            f'<p:extLst><p:ext uri="{_THREADED}"><p15:threadingInfo timeZoneBias="0">'
            f'<p15:parentCm authorId="{parent[0]["id"]}" idx="{parent[1]}"/></p15:threadingInfo></p:ext></p:extLst>'
        )
    return (
        f'<p:cm authorId="{author["id"]}" dt="{_time(time)}" idx="{index}">'
        f'<p:pos x="{round(x * UNITS)}" y="{round(y * UNITS)}"/><p:text>{escape(text)}</p:text>{threaded}</p:cm>'
    )


def _time(value: Any) -> str:
    """A comment's time as PowerPoint writes one: its moment in UTC, to the millisecond."""

    try:
        moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        moment = datetime.now(UTC)
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}"


def _boxes(svg: str) -> dict[str, tuple[float, float, float, float]]:
    """Each region's and object's box on the slide drawn as ``svg`` (``slide3.body``,
    ``slide3.body.0``: x, y, width, height in points), as the drawing says it -- a figure's
    and a region's in so many words; a text's from where its first line is set, and how wide
    it is wrapped."""

    found: dict[str, tuple[float, float, float, float]] = {}
    for tag in _TAG.finditer(svg):
        attributes = dict(_ATTRIBUTE.findall(tag[1]))
        ident = attributes.get("id", "")
        if not ident.startswith("slide"):
            continue
        try:
            if "data-flexo-box" in attributes:
                x, y, width, height = (float(value) for value in attributes["data-flexo-box"].split()[:4])
                found[ident] = (x, y, width, height)
            elif "data-flexo-wrap" in attributes and "x" in attributes and "y" in attributes:
                size = float(attributes.get("font-size", "20"))
                width = float(attributes["data-flexo-wrap"].split()[0])
                found[ident] = (float(attributes["x"]), float(attributes["y"]) - size, width, size)
        except ValueError:
            continue
    return found


Box = tuple[float, float, float, float]


def _place(one: dict[str, Any], boxes: dict[str, Box], width: float) -> tuple[float, float]:
    """Where a thread's comment goes: at the top right of what it is about, else of the slide."""

    if one["region"] is not None:
        # (Its object's box; else, one drawn with none said, its region's.)
        for ending in (f".{one['region']}.{one['index']}", f".{one['region']}"):
            mine = [box for key, box in boxes.items() if key.endswith(ending) and key.count(".") == ending.count(".")]
            box = mine[0] if mine else None
            if box is not None:
                return max(0.0, min(width - 20, box[0] + box[2] - 10)), max(0.0, box[1] - 6)
    return width - 40, 10.0


def _part_name(block: Any, part: Any) -> str:
    """A part of the figure ``block`` shows, by its label (in quotation marks), else its id."""

    figure = block.get("figure") if isinstance(block, dict) else None
    nodes = [*(figure.get("nodes") or []), *(figure.get("groups") or [])] if isinstance(figure, dict) else []
    node = next((node for node in nodes if isinstance(node, dict) and str(node.get("id")) == str(part)), None)
    label = (node or {}).get("label") or (node or {}).get("title")
    if isinstance(label, str) and label.strip():
        return f"\u201c{label.strip().splitlines()[0]}\u201d"
    return str(part)


def _initials(name: str) -> str:
    return "".join(word[0] for word in name.split()[:3]).upper() or "?"


def _slide_parts(parts: dict[str, bytes]) -> list[str]:
    """The slides' parts, in the presentation's order."""

    presentation = etree.fromstring(parts["ppt/presentation.xml"])
    rels = etree.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    targets = {rel.get("Id"): rel.get("Target") for rel in rels}
    ids = presentation.find(f"{{{_P}}}sldIdLst")
    order = [targets[slide.get(f"{{{_R}}}id")] for slide in (ids if ids is not None else [])]
    return [f"ppt/{target.lstrip('/')}" if not target.startswith("/ppt/") else target.lstrip("/") for target in order]


def _related(rels: bytes | None, kind: str, target: str) -> bytes:
    """A part's relationships with one more, of ``kind`` to ``target`` (if it has none such)."""

    root = etree.fromstring(rels) if rels else etree.Element(f"{{{_RELS}}}Relationships", nsmap={None: _RELS})
    if any(rel.get("Type") == kind and rel.get("Target") == target for rel in root):
        return rels or b""
    taken = {rel.get("Id") for rel in root}
    number = 1
    while f"rId{number}" in taken:
        number += 1
    etree.SubElement(root, f"{{{_RELS}}}Relationship", Id=f"rId{number}", Type=kind, Target=target)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _typed(types: bytes, part: str, kind: str) -> bytes:
    root = etree.fromstring(types)
    if any(item.get("PartName") == part for item in root):
        return types
    etree.SubElement(root, f"{{{_TYPES}}}Override", PartName=part, ContentType=kind)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
