"""Decks to import, made by script: a PowerPoint deck (``powerpoint``) and a Keynote deck
(``keynote``), each with one slide per case, named for it -- what an importer must bring across,
and what it must keep as its place without failing."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from flexo_talk.importing.iwa import Builder, write_archives

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def png(colour: tuple[int, int, int] = (200, 40, 40), size: tuple[int, int] = (40, 20)) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, "PNG")
    return out.getvalue()


PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 50]/Contents 4 0 R>>endobj\n"
       b"4 0 obj<</Length 35>>stream\n1 0 0 rg 10 10 80 30 re f\nendstream\nendobj\n"
       b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
       b"0000000176 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n259\n%%EOF\n")


# -- PowerPoint ---------------------------------------------------------------------------------


def powerpoint(path: Path, *, width: float = 960, height: float = 540) -> Path:
    """A PowerPoint deck with a slide for each case, made with python-pptx and its XML."""

    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Pt

    deck = Presentation()
    deck.slide_width, deck.slide_height = Pt(width), Pt(height)
    title_layout, content_layout, blank_layout = deck.slide_layouts[0], deck.slide_layouts[1], deck.slide_layouts[6]

    def named(slide, name: str):
        slide._element.cSld.set("name", name)
        return slide

    # 1. title-slide: a title and a subtitle, centred.
    slide = named(deck.slides.add_slide(title_layout), "title-slide")
    slide.shapes.title.text = "Imported talk"
    slide.placeholders[1].text = "A subtitle"

    # 2. bullets: a title, and a list of two levels with bold, italic, scripts, a colour and a link.
    slide = named(deck.slides.add_slide(content_layout), "bullets")
    slide.shapes.title.text = "Results"
    # (Across the slide, as its layout would set it on a slide of this size.)
    title = slide.shapes.title
    title.left, title.top, title.width, title.height = Pt(36), Pt(21.6), Pt(width - 72), Pt(90)
    body = slide.placeholders[1].text_frame
    body.text = "First point"
    paragraph = body.add_paragraph()
    paragraph.level = 1
    run = paragraph.add_run()
    run.text = "Bold"
    run.font.bold = True
    run = paragraph.add_run()
    run.text = " and "
    run = paragraph.add_run()
    run.text = "italic"
    run.font.italic = True
    paragraph = body.add_paragraph()
    for words, baseline in (("H", None), ("2", "-25000"), ("O and x", None), ("2", "30000")):
        run = paragraph.add_run()
        run.text = words
        if baseline:
            run.font._rPr.set("baseline", baseline)
    paragraph = body.add_paragraph()
    run = paragraph.add_run()
    run.text = "Red words"
    run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
    run = paragraph.add_run()
    run.text = " and a link"
    run.hyperlink.address = "https://example.org/paper"
    slide.notes_slide.notes_text_frame.text = "Say the results slowly."

    # 3. picture: a cropped picture, and one drawn round.
    slide = named(deck.slides.add_slide(blank_layout), "picture")
    picture = slide.shapes.add_picture(io.BytesIO(png(size=(80, 20))), Pt(100), Pt(100), Pt(200), Pt(100))
    picture.crop_left, picture.crop_right = 0.25, 0.25
    round_picture = slide.shapes.add_picture(io.BytesIO(png((40, 40, 200), (30, 30))), Pt(500), Pt(100), Pt(120),
                                             Pt(120))
    geometry = round_picture._element.spPr.find(f"{{{A}}}prstGeom")
    geometry.set("prst", "ellipse")

    # 4. shapes: Flexo's own kinds, a drawn outline, and a turned box with words.
    slide = named(deck.slides.add_slide(blank_layout), "shapes")
    rectangle = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(60), Pt(60), Pt(120), Pt(80))
    rectangle.fill.solid()
    rectangle.fill.fore_color.rgb = RGBColor(0x1A, 0x5D, 0x9B)
    rectangle.text_frame.text = "Box"
    slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Pt(220), Pt(60), Pt(120), Pt(80))
    slide.shapes.add_shape(MSO_SHAPE.OVAL, Pt(380), Pt(60), Pt(80), Pt(80))
    slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Pt(500), Pt(60), Pt(120), Pt(60))
    slide.shapes.add_shape(MSO_SHAPE.STAR_5_POINT, Pt(660), Pt(60), Pt(80), Pt(80))
    slide.shapes.add_shape(MSO_SHAPE.HEXAGON, Pt(60), Pt(200), Pt(100), Pt(80))
    turned = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(220), Pt(220), Pt(120), Pt(40))
    turned.rotation = 30
    builder = slide.shapes.build_freeform(Pt(400), Pt(200))
    builder.add_line_segments([(Pt(500), Pt(260)), (Pt(420), Pt(300))])
    builder.convert_to_shape()

    # 5. connector: two boxes, a line glued to both, an arrowhead at its end; and an elbow.
    slide = named(deck.slides.add_slide(blank_layout), "connector")
    left = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(100), Pt(200), Pt(120), Pt(80))
    right = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(600), Pt(200), Pt(120), Pt(80))
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Pt(0), Pt(0), Pt(10), Pt(10))
    line.begin_connect(left, 3)
    line.end_connect(right, 1)
    end = etree.SubElement(line.line._get_or_add_ln(), f"{{{A}}}tailEnd")
    end.set("type", "triangle")
    elbow = slide.shapes.add_connector(MSO_CONNECTOR.ELBOW, Pt(160), Pt(280), Pt(660), Pt(400))
    elbow.line.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 6. table: a header and two rows of numbers.
    slide = named(deck.slides.add_slide(blank_layout), "table")
    table = slide.shapes.add_table(3, 3, Pt(100), Pt(100), Pt(500), Pt(120)).table
    for row, cells in enumerate((("Model", "Loss", "Top-1"), ("A", "0.31", "76.1"), ("B", "0.27", "81.2"))):
        for column, words in enumerate(cells):
            table.cell(row, column).text = words

    # 7. equation: Office Math, displayed, and a formula among words.
    slide = named(deck.slides.add_slide(blank_layout), "equation")
    box = slide.shapes.add_textbox(Pt(100), Pt(100), Pt(400), Pt(60))
    box.text_frame.text = ""
    paragraph = box.text_frame.paragraphs[0]._p
    paragraph.append(etree.fromstring(
        f'<a14:m xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main" xmlns:m="{M}">'
        f'<m:oMathPara><m:oMath><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num><m:den><m:r><m:t>b</m:t></m:r></m:den>'
        f'</m:f><m:r><m:t>=</m:t></m:r><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r>'
        f'</m:sup></m:sSup></m:oMath></m:oMathPara></a14:m>'))
    words = slide.shapes.add_textbox(Pt(100), Pt(250), Pt(400), Pt(40)).text_frame.paragraphs[0]
    words.add_run().text = "The rate "
    words._p.append(etree.fromstring(
        f'<a14:m xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main" xmlns:m="{M}"><m:oMath>'
        f'<m:r><m:t>k</m:t></m:r><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>=</m:t></m:r><m:r><m:t>&#945;</m:t>'
        f'</m:r></m:oMath></a14:m>'))
    words.add_run().text = " rises."

    # 8. skipped: a slide kept, not shown.
    slide = named(deck.slides.add_slide(blank_layout), "skipped")
    slide.shapes.add_textbox(Pt(100), Pt(100), Pt(300), Pt(40)).text_frame.text = "Not shown"
    slide._element.set("show", "0")

    # 9. unknown: a chart, a picture of a kind no slide shows, a picture whose file is gone.
    slide = named(deck.slides.add_slide(blank_layout), "unknown")
    _frame(slide, 9001, "Chart 1", (100, 100, 300, 200), "http://schemas.openxmlformats.org/drawingml/2006/chart")
    gone = slide.shapes.add_picture(io.BytesIO(png()), Pt(500), Pt(100), Pt(100), Pt(50))
    gone._element.blipFill.blip.set(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", "rIdGone")

    # 10. group: two shapes and their words, scaled by their group.
    slide = named(deck.slides.add_slide(blank_layout), "group")
    group = slide.shapes.add_group_shape()
    first = group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(100), Pt(100), Pt(100), Pt(60))
    first.text_frame.text = "One"
    group.shapes.add_shape(MSO_SHAPE.OVAL, Pt(300), Pt(100), Pt(60), Pt(60))

    deck.save(path)
    _with_embedded_pdf(path)
    return path


def _frame(slide, ident: int, name: str, box: tuple[float, float, float, float], uri: str):
    """A graphic frame of another program's on a slide, its graphic data (to fill) answered."""

    from lxml import etree

    x, y, w, h = (round(value * 12700) for value in box)
    frame = etree.fromstring(
        f'<p:graphicFrame xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="{A}">'
        f'<p:nvGraphicFramePr><p:cNvPr id="{ident}" name="{name}"/><p:cNvGraphicFramePr/><p:nvPr/>'
        f'</p:nvGraphicFramePr><p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{uri}"/></a:graphic></p:graphicFrame>')
    slide.shapes._spTree.append(frame)
    return frame.find(f".//{{{A}}}graphicData")


def _with_embedded_pdf(path: Path) -> None:
    """The deck with one more slide holding a PDF embedded as an object (as Acrobat embeds one)."""

    from pptx import Presentation

    deck = Presentation(str(path))
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide._element.cSld.set("name", "embedded-pdf")
    part = slide.part
    from pptx.opc.package import Part
    from pptx.opc.packuri import PackURI

    kind = "application/vnd.openxmlformats-officedocument.oleObject"
    embedded = Part(PackURI("/ppt/embeddings/oleObject1.bin"), kind, part.package, PDF)
    ident = part.relate_to(embedded, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject")
    from lxml import etree

    data = _frame(slide, 9002, "Object 1", (100, 100, 200, 100), "http://schemas.openxmlformats.org/presentationml/2006/ole")
    data.append(etree.fromstring(
        f'<p:oleObj xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{ident}" '
        f'progId="AcroExch.Document.DC"/>'))
    _smartart(deck)
    deck.save(path)


def _smartart(deck) -> None:
    """A slide of SmartArt: its data, and the shapes PowerPoint drew it in (its drawing part)."""

    from pptx.opc.package import Part
    from pptx.opc.packuri import PackURI

    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide._element.cSld.set("name", "smartart")
    part = slide.part
    relation = "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing"
    drawing = Part(PackURI("/ppt/diagrams/drawing1.xml"), "application/vnd.ms-office.drawingml.diagramDrawing+xml",
                   part.package, (
                       f'<dsp:drawing xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram" '
                       f'xmlns:a="{A}"><dsp:spTree><dsp:nvGrpSpPr><dsp:cNvPr id="0" name=""/><dsp:cNvGrpSpPr/>'
                       f'</dsp:nvGrpSpPr><dsp:grpSpPr/>'
                       + "".join(
                           f'<dsp:sp modelId="{{{index}}}"><dsp:nvSpPr><dsp:cNvPr id="0" name=""/><dsp:cNvSpPr/>'
                           f'</dsp:nvSpPr><dsp:spPr><a:xfrm><a:off x="{index * 2540000}" y="0"/>'
                           f'<a:ext cx="2032000" cy="1270000"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/>'
                           f'</a:prstGeom><a:solidFill><a:srgbClr val="4472C4"/></a:solidFill></dsp:spPr>'
                           f'<dsp:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Step {index + 1}</a:t></a:r></a:p>'
                           f'</dsp:txBody></dsp:sp>' for index in range(2))
                       + "</dsp:spTree></dsp:drawing>").encode())
    drawn = part.relate_to(drawing, relation)
    kind = "application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml"
    data = Part(PackURI("/ppt/diagrams/data1.xml"), kind, part.package, (
        f'<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:a="{A}">'
        f'<dgm:ptLst/><dgm:extLst><a:ext uri="http://schemas.microsoft.com/office/drawing/2008/diagram">'
        f'<dsp:dataModelExt xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram" '
        f'relId="{drawn}" minVer="http://schemas.openxmlformats.org/drawingml/2006/diagram"/></a:ext>'
        f'</dgm:extLst></dgm:dataModel>').encode())
    model = part.relate_to(data, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData")
    from lxml import etree

    graphic = _frame(slide, 9003, "Diagram 1", (100, 100, 400, 100),
                     "http://schemas.openxmlformats.org/drawingml/2006/diagram")
    graphic.append(etree.fromstring(
        f'<dgm:relIds xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
        f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:dm="{model}" r:lo="" '
        f'r:qs="" r:cs=""/>'))


# -- Keynote ------------------------------------------------------------------------------------


class _Keynote:
    """Objects of a Keynote document, numbered as they are made."""

    def __init__(self) -> None:
        self.objects: list[tuple[int, int, bytes]] = []
        self.datas: list[tuple[int, str, bytes]] = []
        self.next = 100

    def add(self, kind: int, message: Builder) -> int:
        self.next += 1
        self.objects.append((self.next, kind, bytes(message)))
        return self.next

    def data(self, name: str, content: bytes) -> int:
        self.next += 1
        self.datas.append((self.next, name, content))
        return self.next


def _size(w: float, h: float) -> Builder:
    return Builder().float(1, w).float(2, h)


def _geometry(x: float, y: float, w: float, h: float, angle: float = 0.0, flags: int = 3) -> Builder:
    return (Builder().message(1, _size(x, y)).message(2, _size(w, h)).int(3, flags).float(4, angle))


def _drawable(x: float, y: float, w: float, h: float, angle: float = 0.0) -> Builder:
    return Builder().message(1, _geometry(x, y, w, h, angle))


def _colour(hex_colour: str, alpha: float = 1.0) -> Builder:
    value = hex_colour.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return Builder().int(1, 1).float(3, r).float(4, g).float(5, b).float(6, alpha)


def _rect_path(w: float, h: float) -> Builder:
    path = Builder()
    for kind, x, y in ((1, 0, 0), (2, w, 0), (2, w, h), (2, 0, h)):
        path.message(1, Builder().int(1, kind).message(2, _size(x, y)))
    path.message(1, Builder().int(1, 5))
    return path


def _shape_style(document: _Keynote, fill: str | None = None, stroke: str | None = None, *,
                 head: str | None = None) -> int:
    properties = Builder()
    if fill:
        properties.message(1, Builder().message(1, _colour(fill)))
    if stroke:
        properties.message(2, Builder().message(1, _colour(stroke)).float(2, 2.0).message(6, Builder().int(1, 1)))
    if head:
        properties.message(6, Builder().text(5, head))
    return document.add(3015, Builder().message(1, Builder().text(1, "style")).message(11, properties))


def _storage(document: _Keynote, paragraphs: list[tuple[str, int | None, int, int | None]],
             runs: list[tuple[int, int | None]] = ()) -> int:
    """A storage of paragraphs, each (words, paragraph style, level, list style); ``runs`` are
    (where, character style) by the text's index."""

    text = "\n".join(words for words, *_ in paragraphs)
    storage = Builder().int(1, 3).text(3, text)
    styles, levels, lists = Builder(), Builder(), Builder()
    at = 0
    for words, style, level, listed in paragraphs:
        entry = Builder().int(1, at)
        if style:
            entry.reference(2, style)
        styles.message(1, entry)
        levels.message(1, Builder().int(1, at).int(2, level).int(3, 0))
        entry = Builder().int(1, at)
        if listed:
            entry.reference(2, listed)
        lists.message(1, entry)
        at += len(words) + 1
    storage.message(5, styles).message(6, levels).message(7, lists)
    if runs:
        characters = Builder()
        for where, style in runs:
            entry = Builder().int(1, where)
            if style:
                entry.reference(2, style)
            characters.message(1, entry)
        storage.message(8, characters)
    return document.add(2001, storage)


def _paragraph_style(document: _Keynote, size: float, *, bold: bool = False, colour: str = "#222222",
                     align: int = 0, font: str = "HelveticaNeue") -> int:
    characters = Builder().bool(1, bold).float(3, size).text(5, font).message(7, _colour(colour))
    return document.add(2022, Builder().message(1, Builder().text(1, "para")).message(11, characters)
                        .message(12, Builder().int(1, align)))


def _text_box(document: _Keynote, x: float, y: float, w: float, h: float, storage: int, *,
              style: int | None = None, kind: int = 2011) -> Builder:
    shape = Builder().message(1, _drawable(x, y, w, h))
    if style:
        shape.reference(2, style)
    shape.message(3, Builder().message(5, Builder().message(2, _size(w, h)).message(3, _rect_path(w, h))))
    return Builder().message(1, shape).reference(4, storage).bool(6, True)


def keynote(path: Path) -> Path:
    """A Keynote deck (one zip, as Keynote saves one) with a slide for each case, its messages
    written as Keynote writes them, field by field (``flexo_talk.importing.iwa``)."""

    document = _Keynote()
    body = _paragraph_style(document, 40)
    title_style = _paragraph_style(document, 72, bold=True)
    bullets = document.add(2023, Builder().message(1, Builder().text(1, "list")).packed(11, [2, 2, 2]))
    numbers = document.add(2023, Builder().message(1, Builder().text(1, "numbers")).packed(11, [3, 3, 3]))
    italic = document.add(2021, Builder().message(1, Builder().text(1, "italic"))
                          .message(11, Builder().bool(2, True)))
    superscript = document.add(2021, Builder().message(1, Builder().text(1, "sup"))
                               .message(11, Builder().int(10, 1)))
    slides: list[int] = []

    def slide(name: str, drawables: list[int], *, title: int | None = None, background: str | None = None,
              note: str = "", skip: bool = False) -> None:
        properties = Builder()
        if background:
            properties.message(1, Builder().message(1, _colour(background)))
        style = document.add(9, Builder().message(1, Builder().text(1, "slide")).message(11, properties))
        made = Builder().reference(1, style).text(10, name).bool(19, True)
        for drawable in drawables:
            made.reference(7, drawable)
        if title:
            made.reference(5, title)
        if note:
            storage = _storage(document, [(note, body, 0, None)])
            made.reference(27, document.add(15, Builder().reference(1, storage)))
        ident = document.add(5, made)
        slides.append(document.add(4, Builder().reference(2, ident).bool(4, skip).bool(6, False).bool(7, False)))

    # 1. title-and-words: a title placeholder and words with a slanted word and a script.
    title = document.add(7, Builder().message(1, _text_box(document, 100, 80, 1600, 160, _storage(
        document, [("A Keynote talk", title_style, 0, None)]))).int(2, 2))
    words = document.add(2011, _text_box(document, 100, 400, 1600, 300, _storage(
        document, [("Plain slanted and x2", body, 0, None)], [(0, None), (6, italic), (13, None), (19, superscript)])))
    slide("title-and-words", [title, words], title=title, note="Speak to the title.")

    # 2. lists: bullets at two levels, and numbers.
    listed = document.add(2011, _text_box(document, 100, 100, 1600, 400, _storage(document, [
        ("First", body, 0, bullets), ("Under it", body, 1, bullets), ("Second", body, 0, bullets)])))
    numbered = document.add(2011, _text_box(document, 100, 600, 1600, 300, _storage(document, [
        ("One", body, 0, numbers), ("Two", body, 0, numbers)])))
    slide("lists", [listed, numbered])

    # 3. shapes: a filled rectangle, a rounded one, an ellipse, an arrow; a turned box.
    shapes = []
    for x, source in (
        (100, Builder().message(5, Builder().message(2, _size(200, 100)).message(3, _rect_path(200, 100)))),
        (400, Builder().message(4, Builder().int(1, 0).float(2, 20.0).message(3, _size(200, 100)))),
        (700, Builder().message(3, Builder().int(1, 1).message(2, _size(60, 0.5)).message(3, _size(200, 100)))),
    ):
        shapes.append(document.add(3004, Builder().message(1, _drawable(x, 100, 200, 100))
                                   .reference(2, _shape_style(document, fill="#1a5d9b")).message(3, source)))
    shapes.append(document.add(3004, Builder().message(1, _drawable(1000, 100, 200, 100, angle=30))
                               .reference(2, _shape_style(document, fill="#c0392b"))
                               .message(3, Builder().message(5, Builder().message(2, _size(200, 100))
                                                             .message(3, _rect_path(200, 100))))))
    slide("shapes", shapes, background="#fdf6e3")

    # 4. picture: cropped by its mask; and a group of two boxes, placed from the group's corner.
    picture_data = document.data("photo.png", png((30, 160, 90), (80, 40)))
    mask = document.add(3006, Builder().message(1, _drawable(20, 0, 160, 200)))
    picture = document.add(3005, Builder().message(1, _drawable(100, 100, 400, 200))
                           .message(11, Builder().int(1, picture_data)).reference(5, mask))
    members = [document.add(3004, Builder().message(1, _drawable(x, 0, 100, 100))
                            .reference(2, _shape_style(document, fill="#2e7d32"))
                            .message(3, Builder().message(5, Builder().message(2, _size(100, 100))
                                                          .message(3, _rect_path(100, 100)))))
               for x in (0, 200)]
    group = document.add(3008, Builder().message(1, _drawable(800, 500, 300, 100))
                         .message(2, Builder().int(1, members[0])).message(2, Builder().int(1, members[1])))
    slide("picture-and-group", [picture, group])

    # 5. connection: two boxes joined by a connection line with an arrowhead.
    ends = [document.add(3004, Builder().message(1, _drawable(x, 400, 200, 100))
                         .reference(2, _shape_style(document, fill="#eeeeee", stroke="#333333"))
                         .message(3, Builder().message(5, Builder().message(2, _size(200, 100))
                                                       .message(3, _rect_path(200, 100)))))
            for x in (200, 1200)]
    route = Builder()
    for kind, x, y in ((1, 0, 50), (3, 400, 50), (3, 800, 50)):
        route.message(1, Builder().int(1, kind).message(2, _size(x, y)))
    line_source = Builder().message(7, Builder().message(1, Builder().message(2, _size(800, 100)).message(3, route))
                                    .int(2, 0))
    line = document.add(3009, Builder().message(1, Builder().message(1, _drawable(400, 400, 800, 100))
                                                .reference(2, _shape_style(document, stroke="#333333",
                                                                           head="filled arrow"))
                                                .message(3, line_source)).reference(2, ends[0]).reference(3, ends[1]))
    slide("connection", [ends[0], ends[1], line])

    # 6. equation: TeX, and MathML, as Keynote keeps an equation (a picture with its source).
    pdf = document.data("equation.pdf", PDF)
    tex = document.add(3005, Builder().message(1, _drawable(100, 100, 400, 100)).message(11, Builder().int(1, pdf))
                       .text(103, r"\frac{a}{b} = x^2"))
    mathml = document.add(3005, Builder().message(1, _drawable(100, 400, 400, 100)).message(11, Builder().int(1, pdf))
                          .text(103, '<math xmlns="http://www.w3.org/1998/Math/MathML"><msqrt><mi>x</mi></msqrt>'
                                     '</math>'))
    slide("equation", [tex, mathml])

    # 7. skipped, and 8. unknown: a table Keynote draws in its own way.
    slide("skipped", [document.add(2011, _text_box(document, 100, 100, 800, 100, _storage(
        document, [("Not shown", body, 0, None)])))], skip=True)
    table = document.add(6000, Builder().message(1, _drawable(100, 100, 800, 400)))
    slide("unknown", [table])

    tree = Builder()
    for node in slides:
        tree.reference(2, node)
    show = document.add(2, Builder().message(3, tree).message(4, _size(1920, 1080)).bool(6, False))
    document.add(1, Builder().reference(2, show))
    metadata = Builder().int(1, document.next + 1)
    for ident, name, _ in document.datas:
        stem, ending = name.rsplit(".", 1)
        metadata.message(4, Builder().int(1, ident).raw(2, b"\0" * 20).text(3, name)
                         .text(4, f"{stem}-{ident}.{ending}"))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Index/Document.iwa", write_archives(document.objects))
        archive.writestr("Index/Metadata.iwa", write_archives([(2, 11006, bytes(metadata))]))
        for ident, name, content in document.datas:
            stem, ending = name.rsplit(".", 1)
            archive.writestr(f"Data/{stem}-{ident}.{ending}", content)
    return path
