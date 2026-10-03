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


def file_stem(identifier: object) -> str:
    """A deck's id as the name of its files: its own words, with nothing that would take
    them out of the folder they are written to (a slash, a leading dot) -- or "deck"."""

    import re

    words = re.sub(r"[\\/:\x00-\x1f]+", "-", str(identifier or "")).strip(" .-")
    return words or "deck"


def build_deck(
    deck: Deck,
    directory: Path,
    formats: tuple[str, ...],
    *,
    handout: bool = False,
    editable_maths: bool = True,
    images: Path | None = None,
) -> DeckBuild:
    """Write the deck into ``directory``: its PowerPoint and PDF, named after the deck,
    and an SVG and a PNG of each slide, beside them as talk-01.png, or in a folder of
    their own (``images``) as slide-01.png. The PDF has a page per step of each list a
    slide reveals, or, as a ``handout``, one page per slide, showing it whole."""

    unknown = set(formats) - set(FORMATS)
    if unknown:
        raise ValueError(f"Unknown {'format' if len(unknown) == 1 else 'formats'} {', '.join(sorted(unknown))}. "
                         f"Available formats: {', '.join(FORMATS)}.")
    directory.mkdir(parents=True, exist_ok=True)
    rendered = deck.render()
    name = file_stem(deck.id)
    diagnostics = [message for item in rendered for message in item.diagnostics]
    svgs: list[Path] = []
    pngs: list[Path] = []
    # Numbered as wide as the count needs, so the files sort in order: talk-100 after talk-099.
    digits = max(2, len(str(len(rendered))))
    folder, prefix = (directory, name) if images is None else (images, "slide")
    if images is not None and {"svg", "png"} & set(formats):
        folder.mkdir(parents=True, exist_ok=True)
    for item in rendered:
        stem = f"{prefix}-{item.slide.index:0{digits}d}"
        if "svg" in formats:
            path = folder / f"{stem}.svg"
            path.write_text(item.svg, encoding="utf-8")
            svgs.append(path)
        if "png" in formats:
            # Drawn from outlines, so the preview shows exactly the glyphs measured.
            path = folder / f"{stem}.png"
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
        pdf = write_pdf(pages, directory / f"{name}.pdf", title=str(deck.id or name))
    pptx = None
    if "pptx" in formats:
        pptx = directory / f"{name}.pptx"
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
    _properties(presentation, deck)
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
                outer = [index for index, (level, _, _) in enumerate(layout.items) if level == 0]
                if layout.reveal and outer:
                    # Each outer item appears with the items under it; any before the first
                    # are there from the start, as in the PDF.
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


def _properties(presentation: Presentation, deck: Deck) -> None:
    """The file's own properties, as PowerPoint shows them in its Properties: the talk's
    title and author, made now -- never python-pptx's template's (its author, its 2013
    dates, "generated using python-pptx")."""

    import datetime

    opening = next((slide for slide in deck.slides if slide.layout == "title"), None)
    titled = opening or next((slide for slide in deck.slides if slide.title_runs), None)
    properties = presentation.core_properties
    properties.title = "".join(run.text for run in titled.title_runs) if titled else str(deck.id)
    properties.author = str((opening.source.get("author") if opening else "") or "")
    properties.last_modified_by = properties.author
    properties.comments = ""
    properties.subject = ""
    properties.keywords = ""
    properties.revision = 1
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    properties.created = properties.modified = now


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
