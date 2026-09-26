"""Writing a deck: one PowerPoint file, one PDF, and an SVG and a PNG per slide."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from flexo.drawing import Group, read_drawing
from flexo.export import rasterise
from flexo.pdf import write_pdf
from flexo.portable import portable_svg
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt

from flexo_talk.deck import Deck, DeckBuild, RenderedSlide
from flexo_talk.pptx import Placement, add_drawing, add_list, add_reveals, add_table, slide_pictures

FORMATS = ("pptx", "pdf", "svg", "png")


def build_deck(deck: Deck, directory: Path, formats: tuple[str, ...], *, handout: bool = False) -> DeckBuild:
    unknown = set(formats) - set(FORMATS)
    if unknown:
        raise ValueError(f"unknown format(s) {', '.join(sorted(unknown))}; use {', '.join(FORMATS)}")
    directory.mkdir(parents=True, exist_ok=True)
    rendered = deck.render()
    diagnostics = [message for item in rendered for message in item.diagnostics]
    svgs: list[Path] = []
    pngs: list[Path] = []
    for item in rendered:
        stem = f"{deck.id}-{item.slide.index:02d}"
        if "svg" in formats:
            path = directory / f"{stem}.svg"
            path.write_text(item.svg, encoding="utf-8")
            svgs.append(path)
        if "png" in formats:
            # Drawn from outlines, so the preview shows exactly the glyphs measured.
            path = directory / f"{stem}.png"
            path.write_bytes(rasterise(portable_svg(item.svg), dpi=144))
            pngs.append(path)
    pdf = None
    if "pdf" in formats:
        # A slide that reveals its list takes a page per step, unless this is a handout.
        pages = [
            page
            for item in rendered
            for page in ([item.svg] if handout else [item.at_step(step) for step in range(1, item.steps + 1)])
        ]
        pdf = write_pdf(pages, directory / f"{deck.id}.pdf", title=deck.id)
    pptx = None
    if "pptx" in formats:
        pptx = directory / f"{deck.id}.pptx"
        write_pptx(deck, rendered, pptx)
    notes = tuple(note for item in rendered for note in item.notes)
    return DeckBuild(pptx, pdf, tuple(svgs), tuple(pngs), tuple(diagnostics), notes)


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
        add_drawing(
            slide.shapes._spTree, drawing, Placement(), name=item.slide.id, background=False,
            groups=groups, pictures=slide_pictures(slide),
            backdrop=deck.palette.get("canvas"),
        )
        reveals = []
        for layout in item.lists:
            shape_id = add_list(slide.shapes._spTree, deck, layout)
            if layout.reveal:
                outer = [index for index, (level, _, _) in enumerate(layout.items) if level == 0]
                ends = [*outer[1:], len(layout.items)]
                ranges = [(first, end - 1) for first, end in zip(outer, ends, strict=True)]
                reveals.append((shape_id, ranges))
        for layout in item.tables:
            add_table(slide.shapes._spTree, deck, layout)
        if item.slide.notes_text:
            slide.notes_slide.notes_text_frame.text = item.slide.notes_text
        add_reveals(slide._element, reveals)
    buffer = BytesIO()
    presentation.save(buffer)
    target.write_bytes(buffer.getvalue())
    return target


def _drop_lists(group: Group) -> None:
    """Bulleted lists and tables are set natively (``add_list``, ``add_table``), so
    their drawn copies go."""

    group.items = [
        item
        for item in group.items
        if not (isinstance(item, Group) and item.data.get("data-flexo-talk") in {"bullets", "table"})
    ]
    for item in group.items:
        if isinstance(item, Group):
            _drop_lists(item)


_ = etree
