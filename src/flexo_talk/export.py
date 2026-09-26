"""Writing a deck: one PowerPoint file, and an SVG and a PNG per slide."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from flexo.drawing import Group, read_drawing
from flexo.fonts import font_directories
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt

from flexo_talk.deck import Deck, DeckBuild, RenderedSlide
from flexo_talk.pptx import Placement, add_drawing, add_list


def build_deck(deck: Deck, directory: Path, formats: tuple[str, ...]) -> DeckBuild:
    unknown = set(formats) - {"pptx", "svg", "png"}
    if unknown:
        raise ValueError(f"unknown format(s) {', '.join(sorted(unknown))}; use pptx, svg, png")
    directory.mkdir(parents=True, exist_ok=True)
    rendered = deck.render()
    diagnostics: list[str] = []
    svgs: list[Path] = []
    pngs: list[Path] = []
    for item in rendered:
        stem = f"{deck.id}-{item.slide.index:02d}"
        if "svg" in formats:
            path = directory / f"{stem}.svg"
            path.write_text(item.svg, encoding="utf-8")
            svgs.append(path)
        if "png" in formats:
            import resvg_py

            data = resvg_py.svg_to_bytes(
                svg_string=item.svg,
                font_dirs=[str(folder) for folder in font_directories()],
                dpi=144,
            )
            path = directory / f"{stem}.png"
            path.write_bytes(bytes(data))
            pngs.append(path)
    pptx = None
    if "pptx" in formats:
        pptx = directory / f"{deck.id}.pptx"
        write_pptx(deck, rendered, pptx)
    return DeckBuild(pptx, tuple(svgs), tuple(pngs), tuple(diagnostics))


def write_pptx(deck: Deck, rendered: list[RenderedSlide], target: Path, *, groups: bool = True) -> Path:
    """The deck as PowerPoint: every shape native, lists as lists, notes as notes."""

    presentation = Presentation()
    presentation.slide_width = Pt(deck.style.width)
    presentation.slide_height = Pt(deck.style.height)
    blank = presentation.slide_layouts[6]
    for item in rendered:
        slide = presentation.slides.add_slide(blank)
        page = deck.background
        if page:
            colour = deck.palette.get("canvas") if page is True else str(page)
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = RGBColor.from_string(colour.lstrip("#").upper())
        drawing = read_drawing(item.svg)
        _drop_lists(drawing.root)
        add_drawing(slide.shapes._spTree, drawing, Placement(), name=item.slide.id, background=False, groups=groups)
        for layout in item.lists:
            add_list(slide.shapes._spTree, deck, layout)
        if item.slide.notes_text:
            slide.notes_slide.notes_text_frame.text = item.slide.notes_text
    buffer = BytesIO()
    presentation.save(buffer)
    target.write_bytes(buffer.getvalue())
    return target


def _drop_lists(group: Group) -> None:
    """Bulleted lists are set natively (``add_list``), so their drawn copy goes."""

    group.items = [
        item
        for item in group.items
        if not (isinstance(item, Group) and item.data.get("data-flexo-talk") == "bullets")
    ]
    for item in group.items:
        if isinstance(item, Group):
            _drop_lists(item)


_ = etree
