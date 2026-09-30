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
from flexo_talk.pptx import (
    Placement,
    add_drawing,
    add_list,
    add_reveals,
    add_table,
    linking,
    slide_pictures,
)
from flexo_talk.pptx import editable_maths as editable_maths_of

FORMATS = ("pptx", "pdf", "svg", "png")


def build_deck(
    deck: Deck, directory: Path, formats: tuple[str, ...], *, handout: bool = False, editable_maths: bool = True
) -> DeckBuild:
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
        write_pptx(deck, rendered, pptx, editable_maths=editable_maths)
    notes = tuple(note for item in rendered for note in item.notes)
    return DeckBuild(pptx, pdf, tuple(svgs), tuple(pngs), tuple(diagnostics), notes)


def write_pptx(
    deck: Deck, rendered: list[RenderedSlide], target: Path, *, groups: bool = True, editable_maths: bool = True
) -> Path:
    """The deck as PowerPoint: every shape native, lists as lists, notes as notes.

    With ``editable_maths``, its maths is PowerPoint's own equations -- editable in its
    equation editor, set in its maths font -- over flexo's drawing of each, which
    other slide programs show instead (see ``pptx.alternate``).
    """

    presentation = Presentation()
    presentation.slide_width = Pt(deck.style.width)
    presentation.slide_height = Pt(deck.style.height)
    blank = presentation.slide_layouts[6]
    for item in rendered:
        slide = presentation.slides.add_slide(blank)
        with linking(slide):
            page = deck.background
            own = item.slide.backdrop
            if own and own.startswith("#"):
                page = own
            if page:
                # A picture page (paper) comes as the slide's first picture; under it, the theme's page.
                colour = str(page) if str(page).startswith("#") else deck.palette.get("canvas")
                slide.background.fill.solid()
                slide.background.fill.fore_color.rgb = RGBColor.from_string(colour.lstrip("#").upper())
            drawing = read_drawing(item.svg)
            formulas = _drop_lists(drawing.root)
            _dissolve_regions(drawing.root)
            add_drawing(
                slide.shapes._spTree, drawing, Placement(), name=item.slide.id, background=False,
                groups=groups, pictures=slide_pictures(slide),
                backdrop=deck.palette.get("canvas"),
            )
            if editable_maths:
                editable_maths_of(slide.shapes._spTree, drawing, item.worded, deck, deck.palette)
            reveals = []
            for layout in item.lists:
                shape_id = add_list(
                    slide.shapes._spTree, deck, layout, formulas=formulas.get(layout.id), editable=editable_maths
                )
                if layout.reveal:
                    outer = [index for index, (level, _, _) in enumerate(layout.items) if level == 0]
                    ends = [*outer[1:], len(layout.items)]
                    ranges = [(first, end - 1) for first, end in zip(outer, ends, strict=True)]
                    reveals.append((shape_id, ranges))
            for layout in item.tables:
                add_table(
                    slide.shapes._spTree, deck, layout, formulas=formulas.get(layout.id), editable=editable_maths
                )
            if item.slide.notes_text:
                slide.notes_slide.notes_text_frame.text = item.slide.notes_text
            add_reveals(slide._element, reveals)
    buffer = BytesIO()
    presentation.save(buffer)
    target.write_bytes(buffer.getvalue())
    return target


def _drop_lists(group: Group, found: dict[str, list] | None = None) -> dict[str, list]:
    """Bulleted lists and tables are set natively (``add_list``, ``add_table``), so
    their drawn copies go -- all but their formulas, which native words leave room for
    and cannot draw: each list's and table's, by its id, for its writer."""

    found = {} if found is None else found
    kept: list = []
    for item in group.items:
        if isinstance(item, Group) and item.data.get("data-flexo-talk") in {"bullets", "table"}:
            if item.id:
                found[item.id] = _formulas(item)
        else:
            kept.append(item)
    group.items = kept
    for item in group.items:
        if isinstance(item, Group):
            _drop_lists(item, found)
    return found


def _formulas(group: Group) -> list[Group]:
    found: list[Group] = []
    for item in group.items:
        if isinstance(item, Group):
            if "data-flexo-math" in item.data:
                found.append(item)
            else:
                found.extend(_formulas(item))
    return found


def _dissolve_regions(group: Group) -> None:
    """A slide's regions are groups only so the layout can move each whole; in the
    PowerPoint their shapes stand on the slide, as if placed there by hand."""

    items: list = []
    for item in group.items:
        if isinstance(item, Group):
            _dissolve_regions(item)
            if item.data.get("data-flexo-talk") == "region":
                items.extend(item.items)
                continue
        items.append(item)
    group.items = items


_ = etree
